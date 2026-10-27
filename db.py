"""Database helpers: create the schema, install the KRI views, and run queries."""
import sqlite3
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def connect(path=":memory:"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn):
    conn.executescript((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))


def install_views(conn):
    conn.executescript((SQL_DIR / "kri_views.sql").read_text(encoding="utf-8"))


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]
