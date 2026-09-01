"""SQLite access layer. Thin wrapper -- deliberately not an ORM so the
SQL the LLM writes/reads maps 1:1 to what's on screen here."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "db", "engineering_intel.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(reset: bool = False):
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


def run_readonly_sql(sql: str, params: tuple = ()):
    """Executes a SELECT-only query. Rejects anything that could mutate
    the DB -- the SQL agent is only ever allowed to read."""
    forbidden = ("insert", "update", "delete", "drop", "alter", "create", "attach", "pragma")
    lowered = sql.strip().lower()
    if not lowered.startswith("select"):
        raise ValueError("Only SELECT statements are permitted for the analytics agent.")
    if any(f" {kw} " in f" {lowered} " for kw in forbidden):
        raise ValueError("Query contains a disallowed keyword.")
    conn = get_connection()
    cur = conn.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_schema_description() -> str:
    """Returns a compact schema description used as context for NL->SQL."""
    conn = get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    lines = []
    for t in tables:
        cols = conn.execute(f"PRAGMA table_info({t['name']})").fetchall()
        col_desc = ", ".join(f"{c['name']} {c['type']}" for c in cols)
        lines.append(f"{t['name']}({col_desc})")
    conn.close()
    return "\n".join(lines)
