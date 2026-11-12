"""One-off helper: replace __HASH_<id>__ placeholders in seed.sql with real
werkzeug password hashes and write the result to seed_ready.sql.

Usage:
    pip install werkzeug
    python gen_hashes.py                      # demo password: ChangeMe123!
    SEED_PASSWORD='something-else' python gen_hashes.py

Each placeholder gets its own salt, so no two hashes are identical.
seed.sql keeps the placeholders (safe to commit); seed_ready.sql holds real
hashes (add it to .gitignore).
"""
import os
import re

from werkzeug.security import generate_password_hash

PASSWORD = os.environ.get("SEED_PASSWORD", "ChangeMe123!")

with open("seed.sql", encoding="utf-8") as f:
    sql = f.read()

sql, count = re.subn(
    r"__HASH_\d+__", lambda _m: generate_password_hash(PASSWORD), sql
)

with open("seed_ready.sql", "w", encoding="utf-8") as f:
    f.write(sql)

print(f"Replaced {count} placeholders -> seed_ready.sql (password: {PASSWORD})")
