"""
client/storage/entries.py
-------------------------
Local entry CRUD operations.

DELETION GUARANTEE:
- delete_entry() uses a hard DELETE SQL statement.
- There is no soft-delete, no audit log, no recovery mechanism.
- Once deleted, an entry is gone. This is intentional and documented.
"""

from datetime import datetime, timezone
from client.storage.db import get_connection


def add_entry(description: str, stress_level: int, department: str) -> int:
    """Create a new entry. Returns the new entry's ID."""
    ts = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO entries
               (description, stress_level, timestamp, department)
               VALUES (?, ?, ?, ?)""",
            (description.strip(), stress_level, ts, department)
        )
        return cur.lastrowid


def get_all_entries(include_submitted: bool = False) -> list[dict]:
    """Return all entries, optionally including already-submitted ones."""
    with get_connection() as conn:
        if include_submitted:
            rows = conn.execute(
                "SELECT * FROM entries ORDER BY timestamp DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM entries WHERE submitted = 0 ORDER BY timestamp DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def get_entry(entry_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM entries WHERE id = ?", (entry_id,)
        ).fetchone()
        return dict(row) if row else None


def update_entry(entry_id: int, **fields):
    """
    Update editable fields of an entry.
    Allowed: description, stress_level, reason_category, elaboration, floor_x, floor_y.
    NOT allowed: timestamp, department, submitted (use mark_submitted for that).
    """
    allowed = {"description", "stress_level", "reason_category",
               "elaboration", "floor_x", "floor_y"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [entry_id]
    with get_connection() as conn:
        conn.execute(
            f"UPDATE entries SET {set_clause} WHERE id = ? AND submitted = 0",
            values
        )


def delete_entry(entry_id: int):
    """
    Permanently delete an entry. No recovery. No logging of the deletion.
    This method does NOT check submitted status — users can delete anything.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))


def get_pending_entries() -> list[dict]:
    """Return entries pending submission (not yet sent)."""
    return get_all_entries(include_submitted=False)


def get_pending_count() -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM entries WHERE submitted = 0"
        ).fetchone()
        return row["c"]


def mark_submitted(entry_ids: list[int]):
    """Mark entries as submitted after a successful send."""
    if not entry_ids:
        return
    ts = datetime.now(timezone.utc).isoformat()
    placeholders = ",".join("?" * len(entry_ids))
    with get_connection() as conn:
        conn.execute(
            f"UPDATE entries SET submitted = 1, submitted_at = ? WHERE id IN ({placeholders})",
            [ts] + entry_ids
        )
        conn.execute(
            "INSERT INTO submission_log (sent_at, entry_count) VALUES (?, ?)",
            (ts, len(entry_ids))
        )


def purge_old_submitted(retention_days: int):
    """
    Remove submitted entries older than retention_days.
    Only called if retention_days > 0.
    """
    if retention_days <= 0:
        return
    with get_connection() as conn:
        conn.execute(
            """DELETE FROM entries
               WHERE submitted = 1
               AND submitted_at < datetime('now', ?)""",
            (f"-{retention_days} days",)
        )
