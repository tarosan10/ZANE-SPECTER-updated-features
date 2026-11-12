import mysql.connector
from flask import current_app, g


def get_db():
    """Return this request's MySQL connection, opening it on first use."""
    if "db" not in g:
        cfg = current_app.config
        g.db = mysql.connector.connect(
            host=cfg["DB_HOST"],
            port=cfg["DB_PORT"],
            user=cfg["DB_USER"],
            password=cfg["DB_PASSWORD"],
            database=cfg["DB_NAME"],
            charset="utf8mb4",
            connection_timeout=5,
        )
    return g.db


def close_db(exc=None):
    conn = g.pop("db", None)
    if conn is not None and conn.is_connected():
        conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)


# --------------------------------------------------------------------------
# Query helpers. Every query goes through cursor.execute(sql, params) with %s
# placeholders; never build SQL with string formatting.
# --------------------------------------------------------------------------
def query_all(sql, params=()):
    """Run a SELECT and return every row as a dict."""
    cur = get_db().cursor(dictionary=True, buffered=True)
    try:
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        cur.close()


def query_one(sql, params=()):
    """Run a SELECT and return the first row as a dict, or None."""
    cur = get_db().cursor(dictionary=True, buffered=True)
    try:
        cur.execute(sql, params)
        return cur.fetchone()
    finally:
        cur.close()


def execute_write(sql, params=()):
    """Run an INSERT/UPDATE/DELETE: commit on success, roll back on failure.

    Returns the new AUTO_INCREMENT id (for INSERTs). Exceptions are re-raised
    after the rollback so callers can decide how to report them.
    """
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def execute_transaction(work):
    """Run work(cursor) as one all-or-nothing transaction.

    `work` receives a dict cursor and may run several statements. If it returns
    normally the transaction is committed; if it raises, everything is rolled
    back and the exception is re-raised. The cursor's return value is passed back.
    """
    conn = get_db()
    cur = conn.cursor(dictionary=True, buffered=True)
    try:
        result = work(cur)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
