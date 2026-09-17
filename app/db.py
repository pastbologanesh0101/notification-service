"""SQLite persistence helpers for the notification service.

The service intentionally uses a single, long-lived sqlite3 connection per
Flask app instance (rather than opening a new connection per request).
This keeps an in-memory database (``:memory:``) usable across requests in
tests, since SQLite's in-memory databases are private to the connection
that created them.
"""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient TEXT NOT NULL,
    channel TEXT NOT NULL,
    template_name TEXT NOT NULL,
    rendered_body TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def connect(database_path):
    """Open a new sqlite3 connection with row access by column name."""
    conn = sqlite3.connect(database_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn):
    """Create the notifications table if it does not already exist."""
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def row_to_dict(row):
    if row is None:
        return None
    return dict(row)
