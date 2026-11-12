# ZANE & SPECTER Law Firm Management Portal

Internal portal for a corporate law firm: staff directory, matters, billable
hours, invoice generation, partner revenue ranking, conflict-of-interest
checks and overdue invoices. Flask + MySQL 8, server-side rendered, raw parameterized SQL (no ORM).
The full specification is in `ZANE & SPECTER Law Firm Management Portal Engineering Proposal.pdf`.

## Setup

```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 1. Create the database (needs MySQL 8.0.16+; re-running drops and rebuilds all tables)
mysql -u root -p < schema.sql       # must be run with the mysql client (uses DELIMITER for triggers)

# 2. Generate seed data with real password hashes, then load it
python gen_hashes.py                # writes seed_ready.sql; demo password: ChangeMe123!
mysql -u root -p < seed_ready.sql

# 3. Configure and run
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export DB_USER=root DB_PASSWORD=your-password DB_NAME=zane_specter
# optional: DB_HOST (default localhost), DB_PORT (default 3306)
# set SESSION_COOKIE_SECURE=1 once served over HTTPS
flask --app app run
```

On Windows PowerShell use `$env:SECRET_KEY = "..."` instead of `export`.

## Demo accounts

Password for all: `ChangeMe123!` (or whatever you set in `SEED_PASSWORD`).

| Email | Role | Can see |
|---|---|---|
| victoria.lex@zanespecter.example | Managing Partner | everything; can manage every account |
| marcus.hale@zanespecter.example | Partner | everything; can manage Associates, Paralegals and Admin |
| tom.whitfield@zanespecter.example | Associate | read-only: no Leaderboard / Overdue / Invoices, no staff or client changes |
| oscar.reyes@zanespecter.example | Admin | manage Associates / Paralegals, clients and invoices; no Leaderboard / Overdue |

## Routes

| Route | Who | Feature |
|---|---|---|
| `/login`, `/logout` (POST) | anyone / signed in | Authentication |
| `/` | signed in | Dashboard with summary counts |
| `/staff` | signed in | 1. Self-join |
| `/staff/add` (POST), `/staff/<id>/edit`, `/staff/<id>/delete` | Partner, Managing Partner, Admin (only for roles below their own) | 1. INSERT, UPDATE, DELETE, recursive CTE |
| `/clients`, `/clients/add` (POST), `/clients/<id>/edit`, `/clients/<id>/delete` | list: signed in; changes: Partner, Managing Partner, Admin | Client management, LEFT JOIN + COUNT |
| `/matters` | signed in | 2. Three-way join; the Active filter reads the `ActiveMatters` view |
| `/time` | signed in | 3. INSERT + aggregation readback |
| `/invoices`, `/invoices/generate` (POST), `/invoices/<id>` | Partner, Managing Partner, Admin | Invoice generation: transaction + `FOR UPDATE` |
| `/leaderboard` | Partner, Managing Partner | 4. JOIN + GROUP BY + SUM + LIMIT |
| `/conflict` | signed in | 5. EXISTS / IN subqueries |
| `/overdue` | Partner, Managing Partner | 6. Date filtering + GROUP BY + HAVING |

## Design decisions worth knowing

- **Staff changes follow a hierarchy.** Only Partners, the Managing Partner and
  Admin can add, edit or delete staff, and only for roles below their own
  (`MANAGEABLE_ROLES` in `app.py`). An Admin therefore cannot reset a Partner's
  password and take over the account, and nobody can edit their own role or
  delete their own account.
- **Logout is a POST** (with CSRF token) rather than the GET in the proposal's
  route map, so a stray link cannot sign someone out.
- **Industry is optional** on the conflict checker. Leave it blank to check the
  name only.
- **Conflict matching is exact** (case-insensitive) on the opposing party name.
  "Acme Inc" will not match "Acme Inc.".
- **The hours-by-matter summary is firm-wide**, as specified, so billable
  amounts hint at colleagues' rates. Filter it by `staff_id` if that is a concern.
- **The overdue threshold** (clients above $10,000) is the `OVERDUE_MIN_TOTAL`
  constant, passed to the query as a parameter.
- **Reporting loops are blocked.** When editing a manager, a recursive CTE walks
  up the proposed manager's chain; if the person being edited appears in it, the
  change is rejected (A manages B manages A).
- **Deletes protect the record.** Staff who lead matters or have time entries,
  and clients with matters, cannot be deleted (the foreign keys are `RESTRICT`
  and the app explains why). Deleting a manager leaves their reports with no
  manager. Every delete goes through a confirmation page.
- **Invoices are generated from unbilled time.** `/invoices` lists matters
  with time where `invoice_id IS NULL`. Generating an invoice runs in one
  transaction: lock the entries (`FOR UPDATE`), sum hours x rate, insert the
  invoice, stamp each entry with the invoice id. Two people clicking at once
  cannot bill the same hours twice. Terms are `INVOICE_TERMS_DAYS` (30).
- **Billing rate is snapshotted.** The rate used is copied to
  `TimeEntries.billed_rate`, so editing someone's rate later never changes an
  issued invoice. Closed matters can still be billed (the final invoice).
- **Closed matters take no new time.** The form only offers active matters, and
  the `trg_time_no_closed_insert` trigger enforces it in the database too. The
  seed loads matters 12-14 as Active and closes them afterwards for that reason.

## Security checklist (proposal section 5.2)

- Every query uses `%s` placeholders; no string-formatted SQL (the invoice line updates use `executemany` with placeholders too).
- Passwords hashed with `generate_password_hash`; login timing evened out for unknown emails.
- `SECRET_KEY` and DB credentials come from environment variables.
- `@login_required` on every route except `/login`; role checks on Leaderboard, Overdue, Invoices and every staff / client change.
- Server-side validation on every POST; client-side `validate.js` is only a convenience.
- Jinja auto-escaping on; no `|safe`.
- Generic error pages (400, 403, 404, 405, 500, 503); SQL errors are logged, not shown.
- CSRF token on every POST (deletes are POST-only behind a confirmation page), security headers, `no-store` caching on pages.
- Staff changes are limited to roles below the editor's own (see above), so editing cannot be used to escalate privileges.

## Stretch goals

All four are built: invoice generation from time entries, the `ActiveMatters`
view, the closed-matter trigger, and edit/delete for staff and clients.

## Ideas for later

Mark invoices paid or void, printable / PDF invoices, edit and delete for
matters and time entries, and a self-service password change.
