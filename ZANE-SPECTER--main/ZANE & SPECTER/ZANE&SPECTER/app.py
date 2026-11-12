import hmac
import re
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import wraps

import mysql.connector
from flask import (
    Flask, abort, flash, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import db
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

PARTNER_ROLES = ("Managing Partner", "Partner")
# Who may create accounts. Matches the Staff.role ENUM values in schema.sql.
STAFF_ADMIN_ROLES = PARTNER_ROLES + ("Admin",)
ROLES = ("Managing Partner", "Partner", "Associate", "Paralegal", "Admin")
# Which roles each manager may create, edit or delete. Nobody can touch an
# account at or above their own level, so an Admin cannot reset a Partner's
# password and take over their account.
MANAGEABLE_ROLES = {
    "Managing Partner": frozenset(ROLES),
    "Partner": frozenset({"Associate", "Paralegal", "Admin"}),
    "Admin": frozenset({"Associate", "Paralegal"}),
}
CLIENT_ADMIN_ROLES = STAFF_ADMIN_ROLES  # may add, edit and delete clients
BILLING_ROLES = STAFF_ADMIN_ROLES       # may generate and view invoices
MATTER_STATUSES = ("Active", "On Hold", "Closed")
OVERDUE_MIN_TOTAL = 10000  # clients below this overdue total are hidden
INVOICE_TERMS_DAYS = 30    # generated invoices fall due this many days after issue

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MYSQL_DUPLICATE_KEY = 1062
MYSQL_ROW_IS_REFERENCED = 1451   # foreign key blocks a DELETE
MYSQL_SIGNAL_EXCEPTION = 1644    # raised by our SIGNAL in the closed-matter trigger

# Checked when an email is not found, so unknown and known emails take similar time.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


# --------------------------------------------------------------------------
# Auth helpers
# --------------------------------------------------------------------------
def login_required(view=None, roles=None):
    """Require a signed-in staff member, optionally restricted to certain roles.

    Usage:
        @login_required
        @login_required(["Managing Partner", "Partner"])
        @login_required(roles=PARTNER_ROLES)
    """
    # Allow the roles list to be passed positionally: @login_required([...])
    if view is not None and not callable(view):
        roles, view = view, None
    if isinstance(roles, str):
        roles = [roles]
    allowed = frozenset(roles) if roles else None

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "staff_id" not in session:
                flash("Sign in to continue.", "warning")
                target = request.full_path if request.query_string else request.path
                return redirect(url_for("login", next=target))
            if allowed is not None and session.get("role") not in allowed:
                abort(403)
            return f(*args, **kwargs)
        return wrapped

    return decorator(view) if view is not None else decorator


def _manageable():
    """Roles the signed-in person is allowed to create, edit and delete."""
    return MANAGEABLE_ROLES.get(session.get("role"), frozenset())


def _safe_next(target):
    """Only follow redirects to paths on this site."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return None


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(32)
    return session["_csrf"]


@app.before_request
def check_csrf():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        expected = session.get("_csrf")
        sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
        if not expected or not sent or not hmac.compare_digest(sent, expected):
            abort(400)


@app.after_request
def set_security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if request.endpoint != "static":
        # Pages hold firm data: don't let the back button show them after logout.
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


@app.context_processor
def inject_template_globals():
    return {
        "csrf_token": csrf_token,
        "partner_roles": PARTNER_ROLES,
        "staff_admin_roles": STAFF_ADMIN_ROLES,
        "client_admin_roles": CLIENT_ADMIN_ROLES,
        "billing_roles": BILLING_ROLES,
        "manageable_roles": _manageable(),
    }


@app.template_filter("money")
def money(value):
    """12345.5 -> $12,345.50"""
    return "${:,.2f}".format(value or 0)


@app.template_filter("hours")
def hours_filter(value):
    return "{:,.2f}".format(value or 0)


# --------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------
def _parse_decimal(raw, places=2):
    """Return a finite Decimal with at most `places` decimal places, or None.

    Decimal() happily parses "NaN" and "Infinity", so finiteness is checked.
    """
    raw = (raw or "").strip()
    if not raw or len(raw) > 20:
        return None
    try:
        value = Decimal(raw)
        if not value.is_finite():
            return None
        if value != value.quantize(Decimal(1).scaleb(-places)):
            return None
    except InvalidOperation:
        return None
    return value


def _parse_int(raw):
    try:
        return int((raw or "").strip())
    except ValueError:
        return None


def _parse_date(raw):
    try:
        return date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------
_ERROR_COPY = {
    400: ("Request expired", "Reload the page and try again."),
    403: ("Access restricted", "Your role does not have access to this page."),
    404: ("Page not found", "Check the address, or return to the home page."),
    405: ("Action not available", "That page does not accept this kind of request."),
    500: ("Something went wrong", "The problem has been logged. Try again in a moment."),
}


def _http_error(e):
    title, message = _ERROR_COPY[e.code]
    return render_template("placeholder.html", title=title, message=message), e.code


for _code in _ERROR_COPY:
    app.register_error_handler(_code, _http_error)


@app.errorhandler(mysql.connector.Error)
def _db_error(e):
    app.logger.exception("Database error")
    return render_template(
        "placeholder.html",
        title="Database unavailable",
        message="The firm database could not be reached. Try again in a moment.",
    ), 503


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if "staff_id" in session:
        return redirect(url_for("home"))

    next_url = _safe_next(request.args.get("next"))
    email = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        row = None
        if email:
            row = db.query_one(
                "SELECT staff_id, name, role, password_hash FROM Staff WHERE email = %s;",
                (email,),
            )

        password_ok = check_password_hash(row["password_hash"] if row else _DUMMY_HASH, password)

        if row and password_ok:
            session.clear()  # drop any pre-login session data
            session.permanent = True
            session["staff_id"] = row["staff_id"]
            session["name"] = row["name"]
            session["role"] = row["role"]
            return redirect(next_url or url_for("home"))

        flash("Email or password is incorrect.", "danger")

    return render_template("login.html", email=email, next_url=next_url)


@app.post("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("login"))


# --------------------------------------------------------------------------
# Home
# --------------------------------------------------------------------------
@app.route("/")
@login_required
def home():
    stats = db.query_one(
        """
        SELECT
            (SELECT COUNT(*) FROM Matters WHERE status = 'Active')  AS active_matters,
            (SELECT COUNT(*) FROM Staff)                            AS staff_count,
            (SELECT COALESCE(SUM(hours_logged), 0) FROM TimeEntries
              WHERE staff_id = %s
                AND entry_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)) AS my_hours,
            (SELECT COUNT(*) FROM Invoices
              WHERE status = 'Unpaid' AND due_date < CURDATE())     AS overdue_invoices;
        """,
        (session["staff_id"],),
    )
    return render_template("home.html", stats=stats)


# --------------------------------------------------------------------------
# Feature 1: Staff directory (self-join + insert, edit, delete)
# --------------------------------------------------------------------------
def _staff_page(form=None, errors=None, status=200):
    practice_area = request.args.get("practice_area", "").strip() or None

    rows = db.query_all(
        """
        SELECT e.staff_id, e.name, e.role, e.practice_area, e.hourly_rate,
               m.name AS manager
        FROM Staff e
        LEFT JOIN Staff m ON e.manager_id = m.staff_id
        WHERE (%s IS NULL OR e.practice_area = %s)
        ORDER BY e.name;
        """,
        (practice_area, practice_area),
    )
    practice_areas = db.query_all(
        "SELECT DISTINCT practice_area FROM Staff ORDER BY practice_area;"
    )
    managers = db.query_all("SELECT staff_id, name, role FROM Staff ORDER BY name;")

    return render_template(
        "staff.html",
        rows=rows,
        practice_areas=practice_areas,
        managers=managers,
        practice_area=practice_area,
        roles=[r for r in ROLES if r in _manageable()],
        can_add=session.get("role") in STAFF_ADMIN_ROLES,
        form=form or {},
        errors=errors or {},
        active_page="staff",
    ), status


@app.route("/staff")
@login_required
def staff():
    return _staff_page()


def _staff_form_from_request():
    form = {
        "name": request.form.get("name", "").strip(),
        "email": request.form.get("email", "").strip().lower(),
        "role": request.form.get("role", ""),
        "practice_area": request.form.get("practice_area", "").strip(),
        "hourly_rate": request.form.get("hourly_rate", "").strip(),
        "manager_id": request.form.get("manager_id", "").strip(),
        "hire_date": request.form.get("hire_date", "").strip(),
    }
    return form, request.form.get("password", "")


def _creates_reporting_loop(staff_id, manager_id):
    """True if making `manager_id` the manager of `staff_id` would create a loop.

    Walks up the proposed manager's chain of managers with a recursive CTE;
    if `staff_id` appears anywhere in that chain, the new link would close a circle.
    """
    row = db.query_one(
        """
        WITH RECURSIVE chain (staff_id, manager_id) AS (
            SELECT staff_id, manager_id FROM Staff WHERE staff_id = %s
            UNION
            SELECT s.staff_id, s.manager_id
            FROM Staff s JOIN chain c ON s.staff_id = c.manager_id
        )
        SELECT 1 AS found FROM chain WHERE staff_id = %s LIMIT 1;
        """,
        (manager_id, staff_id),
    )
    return row is not None


def _validate_staff(form, password, staff_id=None):
    """Validate the staff form. Returns (errors, rate, manager_id, hire_date).

    staff_id is None when adding. When editing, the password is optional
    (blank keeps the current one) and the manager is checked for loops.
    """
    errors = {}

    if not form["name"]:
        errors["name"] = "Enter the person's name."
    elif len(form["name"]) > 100:
        errors["name"] = "Use 100 characters or fewer."

    if not form["email"]:
        errors["email"] = "Enter an email address."
    elif len(form["email"]) > 120 or not EMAIL_RE.match(form["email"]):
        errors["email"] = "Enter a valid email address (120 characters or fewer)."

    if staff_id is None or password:
        if len(password) < 8:
            errors["password"] = "Use at least 8 characters."
        elif len(password) > 128:
            errors["password"] = "Use 128 characters or fewer."

    if form["role"] not in _manageable():
        errors["role"] = "Choose a role from the list."

    if not form["practice_area"]:
        errors["practice_area"] = "Enter a practice area."
    elif len(form["practice_area"]) > 60:
        errors["practice_area"] = "Use 60 characters or fewer."

    rate = _parse_decimal(form["hourly_rate"])
    if rate is None:
        errors["hourly_rate"] = "Enter a rate with at most two decimal places."
    elif rate < 0 or rate > Decimal("999999.99"):
        errors["hourly_rate"] = "Enter a rate between 0 and 999,999.99."

    manager_id = None
    if form["manager_id"]:
        manager_id = _parse_int(form["manager_id"])
        if manager_id is None or not db.query_one(
            "SELECT staff_id FROM Staff WHERE staff_id = %s;", (manager_id,)
        ):
            errors["manager_id"] = "Choose a manager from the list."
        elif staff_id is not None:
            if manager_id == staff_id:
                errors["manager_id"] = "A person cannot be their own manager."
            elif _creates_reporting_loop(staff_id, manager_id):
                errors["manager_id"] = "That would make two people manage each other."

    hire_date = _parse_date(form["hire_date"])
    if hire_date is None:
        errors["hire_date"] = "Enter a valid hire date."

    return errors, rate, manager_id, hire_date


@app.post("/staff/add")
@login_required(roles=STAFF_ADMIN_ROLES)
def staff_add():
    form, password = _staff_form_from_request()
    errors, rate, manager_id, hire_date = _validate_staff(form, password)

    if not errors:
        try:
            db.execute_write(
                """
                INSERT INTO Staff (name, email, password_hash, role, practice_area,
                                   hourly_rate, manager_id, hire_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    form["name"], form["email"], generate_password_hash(password),
                    form["role"], form["practice_area"], rate, manager_id, hire_date,
                ),
            )
        except mysql.connector.errors.IntegrityError as e:
            if e.errno != MYSQL_DUPLICATE_KEY:
                raise
            errors["email"] = "A staff member with this email already exists."
        else:
            flash(f"Added {form['name']} to the directory.", "success")
            return redirect(url_for("staff"))

    flash("The staff member was not added. Fix the highlighted fields.", "danger")
    return _staff_page(form=form, errors=errors, status=422)


def _get_staff_or_404(staff_id):
    row = db.query_one(
        """
        SELECT staff_id, name, email, role, practice_area, hourly_rate,
               manager_id, hire_date
        FROM Staff WHERE staff_id = %s;
        """,
        (staff_id,),
    )
    if row is None:
        abort(404)
    if row["role"] not in _manageable():
        abort(403)
    return row


def _staff_edit_page(target, form, errors, status=200):
    return render_template(
        "staff_edit.html",
        target=target,
        form=form,
        errors=errors,
        is_self=target["staff_id"] == session["staff_id"],
        roles=[r for r in ROLES if r in _manageable()],
        managers=db.query_all(
            "SELECT staff_id, name, role FROM Staff WHERE staff_id <> %s ORDER BY name;",
            (target["staff_id"],),
        ),
        practice_areas=db.query_all(
            "SELECT DISTINCT practice_area FROM Staff ORDER BY practice_area;"
        ),
        active_page="staff",
    ), status


@app.route("/staff/<int:staff_id>/edit", methods=["GET", "POST"])
@login_required(roles=STAFF_ADMIN_ROLES)
def staff_edit(staff_id):
    target = _get_staff_or_404(staff_id)
    is_self = staff_id == session["staff_id"]

    if request.method == "GET":
        form = {
            "name": target["name"],
            "email": target["email"],
            "role": target["role"],
            "practice_area": target["practice_area"],
            "hourly_rate": f"{target['hourly_rate']:.2f}",
            "manager_id": str(target["manager_id"] or ""),
            "hire_date": target["hire_date"].isoformat(),
        }
        return _staff_edit_page(target, form, {})

    form, password = _staff_form_from_request()
    if is_self:
        form["role"] = target["role"]  # you cannot change your own role
    errors, rate, manager_id, hire_date = _validate_staff(form, password, staff_id)

    if not errors:
        try:
            if password:
                db.execute_write(
                    """
                    UPDATE Staff
                    SET name = %s, email = %s, role = %s, practice_area = %s,
                        hourly_rate = %s, manager_id = %s, hire_date = %s,
                        password_hash = %s
                    WHERE staff_id = %s;
                    """,
                    (
                        form["name"], form["email"], form["role"], form["practice_area"],
                        rate, manager_id, hire_date, generate_password_hash(password),
                        staff_id,
                    ),
                )
            else:
                db.execute_write(
                    """
                    UPDATE Staff
                    SET name = %s, email = %s, role = %s, practice_area = %s,
                        hourly_rate = %s, manager_id = %s, hire_date = %s
                    WHERE staff_id = %s;
                    """,
                    (
                        form["name"], form["email"], form["role"], form["practice_area"],
                        rate, manager_id, hire_date, staff_id,
                    ),
                )
        except mysql.connector.errors.IntegrityError as e:
            if e.errno != MYSQL_DUPLICATE_KEY:
                raise
            errors["email"] = "A staff member with this email already exists."
        else:
            if is_self:
                session["name"] = form["name"]
            flash(f"Updated {form['name']}.", "success")
            return redirect(url_for("staff"))

    flash("The changes were not saved. Fix the highlighted fields.", "danger")
    return _staff_edit_page(target, form, errors, status=422)


def _staff_delete_blockers(target):
    """Reasons this person cannot be deleted, plus how many people report to them."""
    usage = db.query_one(
        """
        SELECT (SELECT COUNT(*) FROM Matters     WHERE lead_staff_id = %s) AS matters,
               (SELECT COUNT(*) FROM TimeEntries WHERE staff_id      = %s) AS entries,
               (SELECT COUNT(*) FROM Staff       WHERE manager_id    = %s) AS reports;
        """,
        (target["staff_id"],) * 3,
    )
    blockers = []
    if target["staff_id"] == session["staff_id"]:
        blockers.append("You cannot delete your own account.")
    if usage["matters"]:
        blockers.append(f"They lead {usage['matters']} matter(s). Reassign those first.")
    if usage["entries"]:
        blockers.append(
            f"They have {usage['entries']} time entr{'y' if usage['entries'] == 1 else 'ies'} "
            "on file, which are kept as a billing record."
        )
    return blockers, usage["reports"]


@app.route("/staff/<int:staff_id>/delete", methods=["GET", "POST"])
@login_required(roles=STAFF_ADMIN_ROLES)
def staff_delete(staff_id):
    target = _get_staff_or_404(staff_id)
    blockers, reports = _staff_delete_blockers(target)

    if request.method == "POST":
        if blockers:
            flash(f"{target['name']} was not deleted. {blockers[0]}", "danger")
            return redirect(url_for("staff"))
        try:
            db.execute_write("DELETE FROM Staff WHERE staff_id = %s;", (staff_id,))
        except mysql.connector.errors.IntegrityError as e:
            if e.errno != MYSQL_ROW_IS_REFERENCED:
                raise
            flash(f"{target['name']} is still referenced by firm records and was not deleted.", "danger")
        else:
            flash(f"Deleted {target['name']} from the directory.", "success")
        return redirect(url_for("staff"))

    notes = []
    if reports:
        notes.append(
            f"{reports} {'person reports' if reports == 1 else 'people report'} to them "
            "and will be left with no manager."
        )
    return render_template(
        "confirm_delete.html",
        title=f"Delete {target['name']}?",
        what=f"{target['name']} ({target['role']})",
        blockers=blockers,
        notes=notes,
        action=url_for("staff_delete", staff_id=staff_id),
        cancel_url=url_for("staff"),
        active_page="staff",
    )


# --------------------------------------------------------------------------
# Feature 2: Matters dashboard (3-way join)
# --------------------------------------------------------------------------
@app.route("/matters")
@login_required
def matters():
    status = request.args.get("status", "Active")
    if status not in MATTER_STATUSES:
        status = "Active"

    if status == "Active":
        # The ActiveMatters view already joins Matters, Clients and Staff.
        rows = db.query_all(
            """
            SELECT matter_id, matter_title, company_name, lead_partner,
                   opened_date, opposing_party
            FROM ActiveMatters
            ORDER BY opened_date DESC;
            """
        )
    else:
        rows = db.query_all(
            """
            SELECT m.matter_id, m.matter_title, c.company_name, s.name AS lead_partner,
                   m.opened_date, m.opposing_party
            FROM Matters m
            JOIN Clients c ON m.client_id = c.client_id
            JOIN Staff   s ON m.lead_staff_id = s.staff_id
            WHERE m.status = %s
            ORDER BY m.opened_date DESC;
            """,
            (status,),
        )
    return render_template("matters.html", rows=rows, status=status, statuses=MATTER_STATUSES)


# --------------------------------------------------------------------------
# Feature 3: Billable hours tracker (insert + aggregation readback)
# --------------------------------------------------------------------------
def _time_page(form=None, errors=None, status=200):
    open_matters = db.query_all(
        """
        SELECT matter_id, matter_title, company_name
        FROM ActiveMatters
        ORDER BY company_name, matter_title;
        """
    )
    recent = db.query_all(
        """
        SELECT t.entry_id, t.entry_date, m.matter_title, t.hours_logged, t.description
        FROM TimeEntries t
        JOIN Matters m ON t.matter_id = m.matter_id
        WHERE t.staff_id = %s
        ORDER BY t.entry_date DESC, t.entry_id DESC
        LIMIT 10;
        """,
        (session["staff_id"],),
    )
    summary = db.query_all(
        """
        SELECT m.matter_title,
               SUM(t.hours_logged)                 AS total_hours,
               SUM(t.hours_logged * s.hourly_rate) AS billable_amount
        FROM TimeEntries t
        JOIN Matters m ON t.matter_id = m.matter_id
        JOIN Staff   s ON t.staff_id = s.staff_id
        GROUP BY m.matter_id, m.matter_title
        ORDER BY billable_amount DESC;
        """
    )
    today = date.today().isoformat()
    return render_template(
        "time_entry.html",
        open_matters=open_matters,
        recent=recent,
        summary=summary,
        form=form or {"matter_id": "", "hours": "", "entry_date": today, "description": ""},
        errors=errors or {},
        today=today,
    ), status


@app.route("/time", methods=["GET", "POST"])
@login_required
def log_time():
    if request.method == "GET":
        return _time_page()

    form = {
        "matter_id": request.form.get("matter_id", "").strip(),
        "hours": request.form.get("hours", "").strip(),
        "entry_date": request.form.get("entry_date", "").strip(),
        "description": request.form.get("description", "").strip(),
    }
    errors = {}

    matter = None
    matter_id = _parse_int(form["matter_id"])
    if matter_id is not None:
        matter = db.query_one(
            "SELECT matter_id, matter_title FROM Matters WHERE matter_id = %s AND status = 'Active';",
            (matter_id,),
        )
    if matter is None:
        errors["matter_id"] = "Choose an active matter from the list."

    hours = _parse_decimal(form["hours"])
    if hours is None:
        errors["hours"] = "Enter hours as a number with at most two decimal places."
    elif hours <= 0 or hours > 24:
        errors["hours"] = "Hours must be more than 0 and at most 24."

    entry_date = _parse_date(form["entry_date"])
    if entry_date is None:
        errors["entry_date"] = "Enter a valid date."
    elif entry_date > date.today():
        errors["entry_date"] = "The date cannot be in the future."

    if not form["description"]:
        errors["description"] = "Describe the work you did."
    elif len(form["description"]) > 500:
        errors["description"] = "Use 500 characters or fewer."

    if errors:
        flash("The entry was not saved. Fix the highlighted fields.", "danger")
        return _time_page(form=form, errors=errors, status=422)

    # staff_id comes from the session, never from the form.
    try:
        db.execute_write(
            """
            INSERT INTO TimeEntries (staff_id, matter_id, hours_logged, entry_date, description)
            VALUES (%s, %s, %s, %s, %s);
            """,
            (session["staff_id"], matter["matter_id"], hours, entry_date, form["description"]),
        )
    except mysql.connector.Error as e:
        # The database trigger refuses time on a matter that was closed after
        # the check above ran.
        if getattr(e, "errno", None) != MYSQL_SIGNAL_EXCEPTION:
            raise
        errors["matter_id"] = "That matter has been closed, so time can no longer be logged on it."
        flash("The entry was not saved. Fix the highlighted fields.", "danger")
        return _time_page(form=form, errors=errors, status=422)
    flash(f"Logged {hours:.2f} hours on {matter['matter_title']}.", "success")
    return redirect(url_for("log_time"))


# --------------------------------------------------------------------------
# Feature 4: Rainmaker leaderboard (join + GROUP BY + SUM + ORDER BY + LIMIT)
# --------------------------------------------------------------------------
@app.route("/leaderboard")
@login_required(roles=PARTNER_ROLES)
def leaderboard():
    rows = db.query_all(
        """
        SELECT s.name, s.practice_area, SUM(i.amount) AS revenue
        FROM Staff s
        JOIN Matters  m ON s.staff_id = m.lead_staff_id
        JOIN Invoices i ON m.matter_id = i.matter_id
        WHERE i.status = 'Paid'
        GROUP BY s.staff_id, s.name, s.practice_area
        ORDER BY revenue DESC
        LIMIT 5;
        """
    )
    top = float(rows[0]["revenue"]) if rows else 0
    ranked = [
        {**r, "share": (float(r["revenue"]) / top * 100) if top else 0}
        for r in rows
    ]
    return render_template("leaderboard.html", rows=ranked)


# --------------------------------------------------------------------------
# Feature 5: Conflict of interest checker (subqueries)
# --------------------------------------------------------------------------
@app.route("/conflict", methods=["GET", "POST"])
@login_required
def conflict():
    industries = db.query_all("SELECT DISTINCT industry FROM Clients ORDER BY industry;")
    form = {"name": "", "industry": ""}
    errors = {}
    result = None

    if request.method == "POST":
        form = {
            "name": request.form.get("name", "").strip(),
            "industry": request.form.get("industry", "").strip(),
        }
        if not form["name"]:
            errors["name"] = "Enter the prospective client's name."
        elif len(form["name"]) > 150:
            errors["name"] = "Use 150 characters or fewer."
        if len(form["industry"]) > 80:
            errors["industry"] = "Use 80 characters or fewer."

        if not errors:
            # Level 1: EXISTS subquery. Is the prospect an opposing party in an active matter?
            flag = db.query_one(
                """
                SELECT EXISTS (
                    SELECT 1 FROM Matters
                    WHERE status = 'Active'
                      AND LOWER(opposing_party) = LOWER(%s)
                ) AS direct_conflict;
                """,
                (form["name"],),
            )
            direct = bool(flag["direct_conflict"])

            direct_matters = []
            if direct:
                direct_matters = db.query_all(
                    """
                    SELECT m.matter_title, m.opposing_party, c.company_name
                    FROM Matters m
                    JOIN Clients c ON m.client_id = c.client_id
                    WHERE m.status = 'Active'
                      AND LOWER(m.opposing_party) = LOWER(%s)
                    ORDER BY m.matter_title;
                    """,
                    (form["name"],),
                )

            # Level 2: IN subquery. Does the firm act for active clients in the same industry?
            overlap = []
            if form["industry"]:
                overlap = db.query_all(
                    """
                    SELECT company_name FROM Clients
                    WHERE industry = %s
                      AND client_id IN (SELECT client_id FROM Matters WHERE status = 'Active')
                    ORDER BY company_name;
                    """,
                    (form["industry"],),
                )

            result = {
                "name": form["name"],
                "industry": form["industry"],
                "direct": direct,
                "direct_matters": direct_matters,
                "overlap": overlap,
            }

    return render_template(
        "conflict.html", form=form, errors=errors, result=result, industries=industries
    ), (422 if errors else 200)


# --------------------------------------------------------------------------
# Feature 6: Overdue invoice alerts (date logic + GROUP BY + HAVING)
# --------------------------------------------------------------------------
@app.route("/overdue")
@login_required(roles=PARTNER_ROLES)
def overdue():
    rows = db.query_all(
        """
        SELECT c.company_name,
               COUNT(i.invoice_id)                  AS overdue_invoices,
               SUM(i.amount)                        AS total_overdue,
               MIN(i.due_date)                      AS oldest_due_date,
               DATEDIFF(CURDATE(), MIN(i.due_date)) AS days_overdue
        FROM Clients c
        JOIN Matters  m ON c.client_id = m.client_id
        JOIN Invoices i ON m.matter_id = i.matter_id
        WHERE i.status = 'Unpaid'
          AND i.due_date < CURDATE()
        GROUP BY c.client_id, c.company_name
        HAVING SUM(i.amount) > %s
        ORDER BY total_overdue DESC;
        """,
        (OVERDUE_MIN_TOTAL,),
    )
    grand_total = sum((r["total_overdue"] for r in rows), Decimal(0))
    return render_template(
        "overdue.html", rows=rows, grand_total=grand_total, threshold=OVERDUE_MIN_TOTAL
    )


# --------------------------------------------------------------------------
# Clients: list, add, edit, delete
# --------------------------------------------------------------------------
def _client_form_from_request():
    return {
        "company_name": request.form.get("company_name", "").strip(),
        "industry": request.form.get("industry", "").strip(),
        "contact_email": request.form.get("contact_email", "").strip().lower(),
    }


def _validate_client(form):
    errors = {}
    if not form["company_name"]:
        errors["company_name"] = "Enter the company name."
    elif len(form["company_name"]) > 150:
        errors["company_name"] = "Use 150 characters or fewer."

    if not form["industry"]:
        errors["industry"] = "Enter an industry."
    elif len(form["industry"]) > 80:
        errors["industry"] = "Use 80 characters or fewer."

    if form["contact_email"] and (
        len(form["contact_email"]) > 120 or not EMAIL_RE.match(form["contact_email"])
    ):
        errors["contact_email"] = "Enter a valid email address (120 characters or fewer), or leave it blank."
    return errors


def _clients_page(form=None, errors=None, status=200):
    rows = db.query_all(
        """
        SELECT c.client_id, c.company_name, c.industry, c.contact_email, c.created_at,
               COUNT(m.matter_id) AS matter_count
        FROM Clients c
        LEFT JOIN Matters m ON m.client_id = c.client_id
        GROUP BY c.client_id, c.company_name, c.industry, c.contact_email, c.created_at
        ORDER BY c.company_name;
        """
    )
    industries = db.query_all("SELECT DISTINCT industry FROM Clients ORDER BY industry;")
    return render_template(
        "clients.html",
        rows=rows,
        industries=industries,
        can_manage=session.get("role") in CLIENT_ADMIN_ROLES,
        form=form or {},
        errors=errors or {},
        active_page="clients",
    ), status


@app.route("/clients")
@login_required
def clients():
    return _clients_page()


@app.post("/clients/add")
@login_required(roles=CLIENT_ADMIN_ROLES)
def client_add():
    form = _client_form_from_request()
    errors = _validate_client(form)

    if not errors:
        try:
            db.execute_write(
                "INSERT INTO Clients (company_name, industry, contact_email) VALUES (%s, %s, %s);",
                (form["company_name"], form["industry"], form["contact_email"] or None),
            )
        except mysql.connector.errors.IntegrityError as e:
            if e.errno != MYSQL_DUPLICATE_KEY:
                raise
            errors["company_name"] = "A client with this name already exists."
        else:
            flash(f"Added {form['company_name']} as a client.", "success")
            return redirect(url_for("clients"))

    flash("The client was not added. Fix the highlighted fields.", "danger")
    return _clients_page(form=form, errors=errors, status=422)


def _get_client_or_404(client_id):
    row = db.query_one(
        "SELECT client_id, company_name, industry, contact_email FROM Clients WHERE client_id = %s;",
        (client_id,),
    )
    if row is None:
        abort(404)
    return row


def _client_edit_page(client, form, errors, status=200):
    return render_template(
        "client_edit.html",
        client=client,
        form=form,
        errors=errors,
        industries=db.query_all("SELECT DISTINCT industry FROM Clients ORDER BY industry;"),
        active_page="clients",
    ), status


@app.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
@login_required(roles=CLIENT_ADMIN_ROLES)
def client_edit(client_id):
    client = _get_client_or_404(client_id)

    if request.method == "GET":
        form = {
            "company_name": client["company_name"],
            "industry": client["industry"],
            "contact_email": client["contact_email"] or "",
        }
        return _client_edit_page(client, form, {})

    form = _client_form_from_request()
    errors = _validate_client(form)

    if not errors:
        try:
            db.execute_write(
                """
                UPDATE Clients SET company_name = %s, industry = %s, contact_email = %s
                WHERE client_id = %s;
                """,
                (form["company_name"], form["industry"], form["contact_email"] or None, client_id),
            )
        except mysql.connector.errors.IntegrityError as e:
            if e.errno != MYSQL_DUPLICATE_KEY:
                raise
            errors["company_name"] = "A client with this name already exists."
        else:
            flash(f"Updated {form['company_name']}.", "success")
            return redirect(url_for("clients"))

    flash("The changes were not saved. Fix the highlighted fields.", "danger")
    return _client_edit_page(client, form, errors, status=422)


@app.route("/clients/<int:client_id>/delete", methods=["GET", "POST"])
@login_required(roles=CLIENT_ADMIN_ROLES)
def client_delete(client_id):
    client = _get_client_or_404(client_id)
    count = db.query_one(
        "SELECT COUNT(*) AS n FROM Matters WHERE client_id = %s;", (client_id,)
    )["n"]
    blockers = []
    if count:
        blockers.append(
            f"They have {count} matter{'s' if count != 1 else ''} on file, "
            "which are kept as a legal record."
        )

    if request.method == "POST":
        if blockers:
            flash(f"{client['company_name']} was not deleted. {blockers[0]}", "danger")
            return redirect(url_for("clients"))
        try:
            db.execute_write("DELETE FROM Clients WHERE client_id = %s;", (client_id,))
        except mysql.connector.errors.IntegrityError as e:
            if e.errno != MYSQL_ROW_IS_REFERENCED:
                raise
            flash(f"{client['company_name']} is still referenced by firm records and was not deleted.", "danger")
        else:
            flash(f"Deleted {client['company_name']}.", "success")
        return redirect(url_for("clients"))

    return render_template(
        "confirm_delete.html",
        title=f"Delete {client['company_name']}?",
        what=client["company_name"],
        blockers=blockers,
        notes=[],
        action=url_for("client_delete", client_id=client_id),
        cancel_url=url_for("clients"),
        active_page="clients",
    )


# --------------------------------------------------------------------------
# Invoices: generate from unbilled time entries
# --------------------------------------------------------------------------
class NothingToBill(Exception):
    """Raised inside the invoice transaction when there is no billable time."""


@app.route("/invoices")
@login_required(roles=BILLING_ROLES)
def invoices():
    ready = db.query_all(
        """
        SELECT m.matter_id, m.matter_title, m.status, c.company_name,
               COUNT(t.entry_id)                   AS entries,
               SUM(t.hours_logged)                 AS hours,
               SUM(t.hours_logged * s.hourly_rate) AS amount
        FROM TimeEntries t
        JOIN Matters m ON t.matter_id = m.matter_id
        JOIN Clients c ON m.client_id = c.client_id
        JOIN Staff   s ON t.staff_id  = s.staff_id
        WHERE t.invoice_id IS NULL
        GROUP BY m.matter_id, m.matter_title, m.status, c.company_name
        ORDER BY amount DESC;
        """
    )
    recent = db.query_all(
        """
        SELECT i.invoice_id, i.amount, i.issue_date, i.due_date, i.status,
               m.matter_title, c.company_name
        FROM Invoices i
        JOIN Matters m ON i.matter_id = m.matter_id
        JOIN Clients c ON m.client_id = c.client_id
        ORDER BY i.issue_date DESC, i.invoice_id DESC
        LIMIT 25;
        """
    )
    return render_template("invoices.html", ready=ready, recent=recent, terms=INVOICE_TERMS_DAYS)


@app.post("/invoices/generate")
@login_required(roles=BILLING_ROLES)
def invoice_generate():
    matter_id = _parse_int(request.form.get("matter_id", ""))
    matter = None
    if matter_id is not None:
        matter = db.query_one(
            "SELECT matter_id, matter_title FROM Matters WHERE matter_id = %s;", (matter_id,)
        )
    if matter is None:
        flash("Choose a matter from the list.", "danger")
        return redirect(url_for("invoices"))

    def build_invoice(cur):
        # Lock this matter's unbilled entries so two people clicking at once
        # cannot bill the same hours twice.
        cur.execute(
            """
            SELECT t.entry_id, t.hours_logged, s.hourly_rate
            FROM TimeEntries t
            JOIN Staff s ON t.staff_id = s.staff_id
            WHERE t.matter_id = %s AND t.invoice_id IS NULL
            FOR UPDATE OF t;
            """,
            (matter["matter_id"],),
        )
        lines = cur.fetchall()
        total = sum((l["hours_logged"] * l["hourly_rate"] for l in lines), Decimal(0))
        total = total.quantize(Decimal("0.01"))
        if not lines or total <= 0:
            raise NothingToBill()

        cur.execute(
            """
            INSERT INTO Invoices (matter_id, amount, issue_date, due_date, status)
            VALUES (%s, %s, CURDATE(), DATE_ADD(CURDATE(), INTERVAL %s DAY), 'Unpaid');
            """,
            (matter["matter_id"], total, INVOICE_TERMS_DAYS),
        )
        invoice_id = cur.lastrowid
        cur.executemany(
            """
            UPDATE TimeEntries SET invoice_id = %s, billed_rate = %s
            WHERE entry_id = %s AND invoice_id IS NULL;
            """,
            [(invoice_id, l["hourly_rate"], l["entry_id"]) for l in lines],
        )
        return invoice_id, total, len(lines)

    try:
        invoice_id, total, count = db.execute_transaction(build_invoice)
    except NothingToBill:
        flash(f"There is no billable time on {matter['matter_title']}.", "warning")
        return redirect(url_for("invoices"))

    flash(
        f"Invoice #{invoice_id} created for {matter['matter_title']}: "
        f"{money(total)} from {count} time {'entry' if count == 1 else 'entries'}.",
        "success",
    )
    return redirect(url_for("invoice_detail", invoice_id=invoice_id))


@app.route("/invoices/<int:invoice_id>")
@login_required(roles=BILLING_ROLES)
def invoice_detail(invoice_id):
    invoice = db.query_one(
        """
        SELECT i.invoice_id, i.amount, i.issue_date, i.due_date, i.status,
               m.matter_title, c.company_name
        FROM Invoices i
        JOIN Matters m ON i.matter_id = m.matter_id
        JOIN Clients c ON m.client_id = c.client_id
        WHERE i.invoice_id = %s;
        """,
        (invoice_id,),
    )
    if invoice is None:
        abort(404)
    lines = db.query_all(
        """
        SELECT t.entry_date, s.name AS staff_name, t.description, t.hours_logged,
               t.billed_rate, t.hours_logged * t.billed_rate AS line_amount
        FROM TimeEntries t
        JOIN Staff s ON t.staff_id = s.staff_id
        WHERE t.invoice_id = %s
        ORDER BY t.entry_date, t.entry_id;
        """,
        (invoice_id,),
    )
    return render_template(
        "invoice_detail.html", invoice=invoice, lines=lines, active_page="invoices"
    )


if __name__ == "__main__":
    app.run()
