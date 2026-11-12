# ZANE & SPECTER

**ZANE & SPECTER Law Firm Management Portal**: an internal web app for a corporate law firm. It handles the staff directory, matters, billable hours, partner revenue ranking, invoice generation, conflict-of-interest checks and overdue invoice alerts.

Built with **Flask + MySQL 8**, server-side rendered, with raw parameterized SQL (no ORM).

---

## Screens and the SQL behind them

| # | Feature | Route | SQL concept |
|---|---|---|---|
| 1 | Staff directory + add staff | `/staff` | Self-join, INSERT |
| 2 | Matters dashboard | `/matters` | Three-way JOIN |
| 3 | Billable hours tracker | `/time` | INSERT + aggregation readback |
| 4 | Rainmaker leaderboard | `/leaderboard` | JOIN + GROUP BY + SUM + LIMIT |
| 5 | Conflict-of-interest checker | `/conflict` | EXISTS / IN subqueries |
| 6 | Overdue invoice alerts | `/overdue` | Date filtering + GROUP BY + HAVING |
| 7 | Invoice generation from time entries | `/invoices` | Transaction, `FOR UPDATE`, aggregation |
| 8 | Client management (add / edit / delete) | `/clients` | LEFT JOIN + COUNT, foreign-key safe deletes |
| 9 | Staff edit / delete | `/staff/<id>/edit` | UPDATE, recursive CTE (no reporting loops) |

Also in the database: an `ActiveMatters` view and a trigger that blocks new time on closed matters.

Role-based access: Partners and the Managing Partner see everything. Associates and Paralegals are read-only with no Leaderboard / Overdue / Invoices. Admin can manage Associates, Paralegals, clients and invoices. Nobody can edit or delete an account at or above their own level.

## Repository layout

```
ZANE & SPECTER/
├── ZANE&SPECTER/              # the application
│   ├── app.py                 # routes, auth, validation, invoicing
│   ├── db.py                  # MySQL connection + query helpers
│   ├── config.py              # settings from environment variables
│   ├── schema.sql             # tables, constraints, indexes, view, triggers
│   ├── seed.sql               # demo data (password hash placeholders)
│   ├── gen_hashes.py          # builds seed_ready.sql with real hashes
│   ├── templates/             # Jinja pages
│   ├── static/                # theme.css, validate.js
│   ├── requirements.txt
│   ├── README.md              # detailed app docs (setup, routes, design notes)
│   └── ZANE & SPECTER Law Firm Management Portal Engineering Proposal.pdf
├── ZANE&SPECTER_schema/       # relational schema diagram (PNG, SVG)
└── ZAND&SPECTER_EER FILE/     # EER diagram (PNG, SVG)
```

## Quick start

Requires Python 3.10+ and MySQL 8.0.16+.

```bash
cd "ZANE & SPECTER/ZANE&SPECTER"

python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 1. Create the database
mysql -u root -p < schema.sql       # re-running rebuilds all tables

# 2. Generate seed data with real password hashes, then load it
python gen_hashes.py                # demo password: ChangeMe123!
mysql -u root -p < seed_ready.sql

# 3. Configure and run
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export DB_USER=root DB_PASSWORD=your-password DB_NAME=zane_specter
flask --app app run
```

Then open <http://127.0.0.1:5000>. On Windows PowerShell, use `$env:SECRET_KEY = "..."` instead of `export`.

Optional variables: `DB_HOST` (default `localhost`), `DB_PORT` (default `3306`), `SESSION_COOKIE_SECURE=1` once served over HTTPS.

## Demo accounts

Password for all: `ChangeMe123!`

| Email | Role |
|---|---|
| victoria.lex@zanespecter.example | Managing Partner |
| marcus.hale@zanespecter.example | Partner |
| tom.whitfield@zanespecter.example | Associate |
| oscar.reyes@zanespecter.example | Admin |

## Database

Five tables: `Staff` (self-referencing manager hierarchy), `Clients`, `Matters`, `Invoices` and `TimeEntries`. Foreign keys use `ON DELETE RESTRICT` on legal and billing records so history can't vanish when a client or lawyer is removed. `TimeEntries.invoice_id` is `NULL` until the time is billed, and `billed_rate` freezes the hourly rate at that moment. Also: the `ActiveMatters` view and the `trg_time_no_closed_*` triggers. See the diagrams in `ZANE&SPECTER_schema/` and `ZAND&SPECTER_EER FILE/`.

![Schema](ZANE%20%26%20SPECTER/ZANE%26SPECTER_schema/LAW_FIRM_schema.png)

## Security highlights

- Every query uses `%s` placeholders; no string-built SQL
- Passwords hashed with Werkzeug; login timing evened out for unknown emails
- CSRF token on every POST, POST-only logout, security headers, `no-store` caching
- Server-side validation on all inputs; Jinja auto-escaping on
- Secrets and DB credentials come from environment variables
- Staff edits are limited to roles below the editor's own, so edits can't escalate privileges
- Invoice generation is one locked transaction, so hours can't be billed twice
- Generic error pages; SQL errors are logged, never shown

## Ideas for later

Mark invoices paid or void, printable / PDF invoices, edit and delete for matters and time entries, and a self-service password change.

## More docs

The full specification is in the Engineering Proposal PDF, and `ZANE&SPECTER/README.md` has the detailed design decisions (conflict matching rules, overdue threshold, role restrictions).
