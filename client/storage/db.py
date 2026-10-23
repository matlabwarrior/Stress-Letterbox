"""
client/storage/db.py
--------------------
Local SQLite database setup for the client.
One database file per user device, stored in the OS app-data directory.

PRIVACY NOTE: This database is local-only and contains full entry data
including the user's PIN hash. None of this data is ever transmitted.
The PIN hash column, in particular, must NEVER appear in any network payload.
"""

import os
import sqlite3
from appdirs import user_data_dir
from shared.constants import APP_NAME, APP_AUTHOR, DB_FILENAME


def get_db_path() -> str:
    data_dir = user_data_dir(APP_NAME, APP_AUTHOR)
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, DB_FILENAME)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all local tables if they don't exist."""
    with get_connection() as conn:
        conn.executescript("""
            -- Settings table: PIN hash, department, server URL, session
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            -- Local entry store (pre-submission)
            CREATE TABLE IF NOT EXISTS entries (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                description      TEXT NOT NULL,
                stress_level     INTEGER NOT NULL CHECK(stress_level BETWEEN 1 AND 5),
                timestamp        TEXT NOT NULL,       -- ISO 8601, auto-set, not user-editable
                department       TEXT NOT NULL,       -- from setup, not editable per entry
                reason_category  TEXT,
                elaboration      TEXT,
                floor_x          REAL,                -- 0.0–1.0 relative, nullable
                floor_y          REAL,                -- 0.0–1.0 relative, nullable
                submitted        INTEGER DEFAULT 0,   -- 0=pending, 1=sent
                submitted_at     TEXT                 -- ISO 8601 when sent
            );

            -- Submission log: tracks what was sent (for retention cleanup)
            CREATE TABLE IF NOT EXISTS submission_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                sent_at      TEXT NOT NULL,
                entry_count  INTEGER NOT NULL
            );
        """)
