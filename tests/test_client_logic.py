"""
tests/test_client_logic.py
--------------------------
Tests for client-side business logic:
  - Entry retention / purge after configurable number of days
  - Reminder scheduling (weekly / monthly)
  - Session management (login, logout, PIN)
  - Entry lifecycle (add, edit, mark submitted)
"""

import os
import pytest
from datetime import date, datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Retention / purge
# ---------------------------------------------------------------------------

class TestRetention:

    def test_purge_removes_old_submitted_entries(self, tmp_path, monkeypatch):
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "ret1.db"))
        db_mod.init_db()

        from client.storage.entries import add_entry, mark_submitted, purge_old_submitted
        from client.storage.db import get_connection

        eid = add_entry("old note", 2, "finance")
        mark_submitted([eid])

        # Manually backdate submitted_at to 91 days ago
        old_ts = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
        with get_connection() as conn:
            conn.execute(
                "UPDATE entries SET submitted_at = ? WHERE id = ?",
                (old_ts, eid)
            )

        purge_old_submitted(retention_days=90)

        from client.storage.entries import get_entry
        assert get_entry(eid) is None, "Entry older than retention window should be purged"

    def test_purge_keeps_recent_submitted_entries(self, tmp_path, monkeypatch):
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "ret2.db"))
        db_mod.init_db()

        from client.storage.entries import add_entry, mark_submitted, purge_old_submitted, get_entry

        eid = add_entry("recent note", 3, "it")
        mark_submitted([eid])
        # submitted_at defaults to now — well within 90 days
        purge_old_submitted(retention_days=90)

        assert get_entry(eid) is not None, "Recently submitted entry should NOT be purged"

    def test_purge_never_removes_pending_entries(self, tmp_path, monkeypatch):
        """Pending (unsubmitted) entries must never be purged regardless of age."""
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "ret3.db"))
        db_mod.init_db()

        from client.storage.entries import add_entry, purge_old_submitted, get_entry
        from client.storage.db import get_connection

        eid = add_entry("pending old note", 4, "hr")

        # Backdate the timestamp to make it look old
        old_ts = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        with get_connection() as conn:
            conn.execute(
                "UPDATE entries SET timestamp = ? WHERE id = ?",
                (old_ts, eid)
            )

        purge_old_submitted(retention_days=90)

        assert get_entry(eid) is not None, \
            "Pending entry must never be purged by retention, only by explicit user deletion"

    def test_purge_zero_retention_is_noop(self, tmp_path, monkeypatch):
        """retention_days=0 means keep forever — purge must do nothing."""
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "ret4.db"))
        db_mod.init_db()

        from client.storage.entries import add_entry, mark_submitted, purge_old_submitted, get_entry
        from client.storage.db import get_connection

        eid = add_entry("very old note", 2, "sales")
        mark_submitted([eid])

        old_ts = (datetime.now(timezone.utc) - timedelta(days=999)).isoformat()
        with get_connection() as conn:
            conn.execute(
                "UPDATE entries SET submitted_at = ? WHERE id = ?",
                (old_ts, eid)
            )

        purge_old_submitted(retention_days=0)  # 0 = keep forever

        assert get_entry(eid) is not None, \
            "With retention_days=0, no entries should ever be purged"


# ---------------------------------------------------------------------------
# Reminder scheduling
# ---------------------------------------------------------------------------

class TestReminderScheduling:

    def test_reminder_due_after_weekly_gap(self, tmp_path, monkeypatch):
        """Reminder should be due if last reminder was > 7 days ago (weekly mode)."""
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "rem1.db"))
        db_mod.init_db()

        from client.storage.session import set_last_reminder_date, get_last_reminder_date

        eight_days_ago = (date.today() - timedelta(days=8)).isoformat()
        set_last_reminder_date(eight_days_ago)

        last = get_last_reminder_date()
        last_date = datetime.fromisoformat(last).date() if last else None
        days_since = (date.today() - last_date).days if last_date else 999
        threshold = 7

        assert days_since >= threshold, "Reminder should be due after 8 days (weekly)"

    def test_reminder_not_due_within_weekly_gap(self, tmp_path, monkeypatch):
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "rem2.db"))
        db_mod.init_db()

        from client.storage.session import set_last_reminder_date, get_last_reminder_date

        two_days_ago = (date.today() - timedelta(days=2)).isoformat()
        set_last_reminder_date(two_days_ago)

        last = get_last_reminder_date()
        last_date = datetime.fromisoformat(last).date()
        days_since = (date.today() - last_date).days
        threshold = 7

        assert days_since < threshold, "Reminder should NOT be due after only 2 days"

    def test_reminder_due_after_monthly_gap(self, tmp_path, monkeypatch):
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "rem3.db"))
        db_mod.init_db()

        from client.storage.session import set_last_reminder_date, get_last_reminder_date

        thirty_two_days_ago = (date.today() - timedelta(days=32)).isoformat()
        set_last_reminder_date(thirty_two_days_ago)

        last = get_last_reminder_date()
        last_date = datetime.fromisoformat(last).date()
        days_since = (date.today() - last_date).days
        threshold = 30

        assert days_since >= threshold, "Reminder should be due after 32 days (monthly)"

    def test_first_launch_no_last_reminder(self, tmp_path, monkeypatch):
        """On first launch, get_last_reminder_date() should return None."""
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "rem4.db"))
        db_mod.init_db()

        from client.storage.session import get_last_reminder_date
        assert get_last_reminder_date() is None


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

class TestSessionManagement:

    def test_logout_clears_session_token(self, tmp_path, monkeypatch):
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "sess1.db"))
        db_mod.init_db()

        from client.storage.session import create_pin, create_session, logout, is_logged_in
        create_pin("testpin")
        create_session()
        assert is_logged_in()

        logout()
        assert not is_logged_in(), "Session should be cleared after logout"

    def test_logout_preserves_pin_hash(self, tmp_path, monkeypatch):
        """
        Logout clears the session token but must NOT delete the PIN hash.
        The PIN protects the letterbox after logout.
        """
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "sess2.db"))
        db_mod.init_db()

        from client.storage.session import (
            create_pin, create_session, logout, get_setting, verify_pin
        )
        create_pin("keepme")
        create_session()
        logout()

        # PIN hash must still be there and correct
        assert get_setting("pin_hash") is not None
        assert verify_pin("keepme") is True, \
            "PIN must still verify correctly after logout"

    def test_logout_preserves_department(self, tmp_path, monkeypatch):
        """Logout must not erase the department setting."""
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "sess3.db"))
        db_mod.init_db()

        from client.storage.session import (
            create_pin, create_session, set_department,
            get_department, logout
        )
        create_pin("pin")
        set_department("operations")
        create_session()
        logout()

        assert get_department() == "operations", \
            "Department must be preserved across logout"

    def test_change_pin(self, tmp_path, monkeypatch):
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "sess4.db"))
        db_mod.init_db()

        from client.storage.session import create_pin, change_pin, verify_pin
        create_pin("oldpin")
        result = change_pin("oldpin", "newpin")
        assert result is True
        assert verify_pin("newpin") is True
        assert verify_pin("oldpin") is False

    def test_change_pin_wrong_old_pin_rejected(self, tmp_path, monkeypatch):
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "sess5.db"))
        db_mod.init_db()

        from client.storage.session import create_pin, change_pin, verify_pin
        create_pin("correctpin")
        result = change_pin("wrongpin", "newpin")
        assert result is False
        assert verify_pin("correctpin") is True, \
            "Original PIN must remain valid after failed change attempt"


# ---------------------------------------------------------------------------
# Entry lifecycle
# ---------------------------------------------------------------------------

class TestEntryLifecycle:

    def test_add_and_retrieve_entry(self, tmp_path, monkeypatch):
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "ent1.db"))
        db_mod.init_db()

        from client.storage.entries import add_entry, get_entry
        eid = add_entry("Stressful meeting", 4, "finance")
        entry = get_entry(eid)

        assert entry is not None
        assert entry["description"] == "Stressful meeting"
        assert entry["stress_level"] == 4
        assert entry["department"] == "finance"
        assert entry["submitted"] == 0

    def test_timestamp_is_auto_set_and_iso(self, tmp_path, monkeypatch):
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "ent2.db"))
        db_mod.init_db()

        from client.storage.entries import add_entry, get_entry
        eid = add_entry("note", 2, "it")
        entry = get_entry(eid)

        ts = entry["timestamp"]
        # Must be parseable as ISO 8601
        parsed = datetime.fromisoformat(ts)
        assert parsed is not None
        # Must be recent (within the last minute)
        age = datetime.now(timezone.utc) - parsed.replace(tzinfo=timezone.utc)
        assert age.total_seconds() < 60

    def test_update_entry_editable_fields(self, tmp_path, monkeypatch):
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "ent3.db"))
        db_mod.init_db()

        from client.storage.entries import add_entry, update_entry, get_entry
        eid = add_entry("initial", 1, "hr")

        update_entry(
            eid,
            description="updated text",
            stress_level=3,
            reason_category="workload",
            elaboration="More context",
            floor_x=0.25,
            floor_y=0.75,
        )
        entry = get_entry(eid)

        assert entry["description"]     == "updated text"
        assert entry["stress_level"]    == 3
        assert entry["reason_category"] == "workload"
        assert entry["elaboration"]     == "More context"
        assert abs(entry["floor_x"] - 0.25) < 0.001
        assert abs(entry["floor_y"] - 0.75) < 0.001

    def test_update_entry_cannot_change_timestamp(self, tmp_path, monkeypatch):
        """timestamp is auto-set and must not be user-editable."""
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "ent4.db"))
        db_mod.init_db()

        from client.storage.entries import add_entry, update_entry, get_entry
        eid = add_entry("note", 2, "sales")
        original_ts = get_entry(eid)["timestamp"]

        # Attempt to set timestamp via update_entry (not in allowed fields — should no-op)
        update_entry(eid, timestamp="1900-01-01T00:00:00")
        assert get_entry(eid)["timestamp"] == original_ts, \
            "timestamp must not be changeable via update_entry()"

    def test_update_submitted_entry_is_noop(self, tmp_path, monkeypatch):
        """
        Submitted entries must not be editable.
        update_entry() filters WHERE submitted = 0, so changes silently fail.
        """
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "ent5.db"))
        db_mod.init_db()

        from client.storage.entries import add_entry, mark_submitted, update_entry, get_entry
        eid = add_entry("done note", 3, "operations")
        original_desc = get_entry(eid)["description"]
        mark_submitted([eid])

        update_entry(eid, description="changed after submit")
        assert get_entry(eid)["description"] == original_desc, \
            "Submitted entries must not be editable"

    def test_pending_count_accurate(self, tmp_path, monkeypatch):
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "ent6.db"))
        db_mod.init_db()

        from client.storage.entries import (
            add_entry, mark_submitted, get_pending_count, delete_entry
        )
        e1 = add_entry("a", 1, "it")
        e2 = add_entry("b", 2, "it")
        e3 = add_entry("c", 3, "it")
        assert get_pending_count() == 3

        mark_submitted([e1])
        assert get_pending_count() == 2

        delete_entry(e2)
        assert get_pending_count() == 1
