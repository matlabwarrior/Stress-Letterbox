"""
client/storage/session.py
-------------------------
Local PIN setup and session management.

The PIN hash is stored ONLY in the local SQLite database.
It is NEVER read into memory for transmission.
Session tokens are random strings stored locally — not server-issued.
"""

import os
import secrets
import bcrypt
from client.storage.db import get_connection


# ── Settings helpers ───────────────────────────────────────

def get_setting(key: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_setting(key: str, value: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value)
        )


# ── First-launch detection ─────────────────────────────────

def is_first_launch() -> bool:
    return get_setting("pin_hash") is None


def is_setup_complete() -> bool:
    return (
        get_setting("pin_hash") is not None and
        get_setting("department") is not None
    )


# ── PIN management ─────────────────────────────────────────

def create_pin(pin: str):
    """Hash and store the user's PIN. The plaintext PIN is never stored."""
    hashed = bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    set_setting("pin_hash", hashed)


def verify_pin(pin: str) -> bool:
    stored = get_setting("pin_hash")
    if not stored:
        return False
    return bcrypt.checkpw(pin.encode("utf-8"), stored.encode("utf-8"))


def change_pin(old_pin: str, new_pin: str) -> bool:
    if not verify_pin(old_pin):
        return False
    create_pin(new_pin)
    return True


# ── Session management ─────────────────────────────────────

def create_session() -> str:
    """Generate and store a local session token. Returns the token."""
    token = secrets.token_hex(32)
    set_setting("session_token", token)
    return token


def get_session_token() -> str | None:
    return get_setting("session_token")


def is_logged_in() -> bool:
    return get_setting("session_token") is not None


def logout():
    """Clear the session token. The PIN hash remains, protecting the letterbox."""
    with get_connection() as conn:
        conn.execute("DELETE FROM settings WHERE key = 'session_token'")


# ── Department ─────────────────────────────────────────────

def get_department() -> str | None:
    return get_setting("department")


def set_department(dept_id: str):
    set_setting("department", dept_id)


# ── Reminder tracking ──────────────────────────────────────

def get_last_reminder_date() -> str | None:
    return get_setting("last_reminder_date")


def set_last_reminder_date(date_str: str):
    set_setting("last_reminder_date", date_str)
