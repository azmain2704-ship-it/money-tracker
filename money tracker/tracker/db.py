"""SQLite helpers. Every query uses ? placeholders, never string formatting, so input can't inject SQL."""
import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT    NOT NULL,                       -- YYYY-MM-DD
    description  TEXT    NOT NULL DEFAULT '',
    kind         TEXT    NOT NULL CHECK (kind IN ('income', 'expense')),
    category     TEXT    NOT NULL,
    amount_pence INTEGER NOT NULL CHECK (amount_pence > 0), -- money as whole pence, never floats
    source       TEXT    NOT NULL DEFAULT 'manual'          -- 'manual' or 'statement'
);
CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(date);

CREATE TABLE IF NOT EXISTS budgets (
    category    TEXT PRIMARY KEY,
    limit_pence INTEGER NOT NULL CHECK (limit_pence > 0)    -- monthly limit
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    get_db().executescript(SCHEMA)


def add_entry(date, description, kind, category, amount_pence, source="manual"):
    db = get_db()
    db.execute(
        "INSERT INTO entries (date, description, kind, category, amount_pence, source) VALUES (?, ?, ?, ?, ?, ?)",
        (date, description, kind, category, amount_pence, source),
    )
    db.commit()


def entry_exists(date, description, amount_pence, kind):
    row = get_db().execute(
        "SELECT 1 FROM entries WHERE date = ? AND description = ? AND amount_pence = ? AND kind = ? LIMIT 1",
        (date, description, amount_pence, kind),
    ).fetchone()
    return row is not None


def entries_for_month(month):
    """month is 'YYYY-MM'. Newest first."""
    rows = get_db().execute(
        "SELECT * FROM entries WHERE substr(date, 1, 7) = ? ORDER BY date DESC, id DESC", (month,)
    ).fetchall()
    return [dict(r) for r in rows]


def months_with_entries():
    rows = get_db().execute("SELECT DISTINCT substr(date, 1, 7) AS m FROM entries ORDER BY m DESC").fetchall()
    return [r["m"] for r in rows]


def delete_entry(entry_id):
    db = get_db()
    db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    db.commit()


def get_budgets():
    rows = get_db().execute("SELECT category, limit_pence FROM budgets ORDER BY category").fetchall()
    return {r["category"]: r["limit_pence"] for r in rows}


def set_budget(category, limit_pence):
    db = get_db()
    db.execute(
        "INSERT INTO budgets (category, limit_pence) VALUES (?, ?) "
        "ON CONFLICT(category) DO UPDATE SET limit_pence = excluded.limit_pence",
        (category, limit_pence),
    )
    db.commit()


def remove_budget(category):
    db = get_db()
    db.execute("DELETE FROM budgets WHERE category = ?", (category,))
    db.commit()
