"""
tests/test_anonymisation_audit.py
----------------------------------
STANDALONE PRIVACY AUDIT TEST SUITE

This file is designed to be readable and runnable by a non-developer
privacy officer or external auditor without needing to understand the
full application codebase.

Run this file alone to verify the anonymisation guarantee:
    pytest tests/test_anonymisation_audit.py -v

Every test in this file has a plain-English docstring explaining
exactly what it verifies and why it matters for privacy.

These tests cover the three layers of the anonymisation guarantee:

  LAYER 1 — Data construction (client side)
    The payload builder can only output the fields in SUBMISSION_FIELDS.
    No other data can reach this function from the local database.

  LAYER 2 — Data transmission (API layer)
    The server endpoint silently discards any field not in _ACCEPTED_FIELDS,
    even if a malformed client were to send identity data.

  LAYER 3 — Data storage (server side)
    The Entry model has no identity column. The database schema is
    verified directly to confirm no identity fields exist.

Each layer is independently sufficient to prevent identity leakage.
All three together make the guarantee structural rather than policy-based.
"""

import json
import os
import sys
import sqlite3
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ---------------------------------------------------------------------------
# LAYER 1 — Payload construction audit
# ---------------------------------------------------------------------------

class TestLayer1_PayloadConstruction:
    """
    Verifies that _build_payload() — the sole function that assembles
    outbound data — cannot transmit identity information.

    A privacy reviewer should inspect _build_payload() in
    client/api/submit.py alongside these tests.
    """

    SAFE_FIELDS = {
        "department",
        "timestamp",
        "stress_level",
        "reason_category",
        "floor_x",
        "floor_y",
    }

    # These fields must NEVER appear in a payload — either because they're
    # identity fields, or (elaboration, description) because they're free
    # text: exactly the kind of thing that can re-identify someone or be
    # read out of context by whoever has dashboard access. If any of these
    # surface in a submission, the privacy guarantee is broken.
    FORBIDDEN_FIELDS = {
        "id",
        "description",     # raw quick-log text — stays on device
        "elaboration",     # user-added context — stays on device
        "submitted",       # local DB flag
        "submitted_at",    # local DB flag
        "pin_hash",        # bcrypt hash of user PIN
        "session_token",   # local session identifier
        "machine_name",    # hostname
        "username",        # OS username
        "email",           # any email
        "ip_address",      # network address
        "user_id",         # any user identifier
    }

    def test_payload_fields_match_exactly(self):
        """
        The output of _build_payload() must contain EXACTLY the fields
        in SAFE_FIELDS — no more, no fewer.

        Adding a field to the payload requires a deliberate code change
        to _build_payload(), which is the intended friction point.
        """
        from client.api.submit import _build_payload

        # Simulate a full local database row with every possible field present
        full_local_row = {
            # Fields that SHOULD appear in payload
            "department":      "finance",
            "timestamp":       "2024-06-01T09:00:00+00:00",
            "stress_level":    3,
            "reason_category": "workload",
            "floor_x":         0.45,
            "floor_y":         0.62,
            # Fields that must NEVER appear in payload
            "id":              42,
            "description":     "Private quick-log note",
            "elaboration":     "Private context note",
            "submitted":       0,
            "submitted_at":    None,
            "pin_hash":        "$2b$12$fakehashvalue",
            "session_token":   "abc123token",
            "machine_name":    "DESKTOP-SECRET",
            "username":        "jsmith",
            "email":           "j.smith@example.com",
            "ip_address":      "192.168.1.42",
            "user_id":         "uid-9999",
        }

        result = _build_payload([full_local_row])
        assert len(result) == 1
        output_fields = set(result[0].keys())

        extra = output_fields - self.SAFE_FIELDS
        missing = self.SAFE_FIELDS - output_fields

        assert not extra, (
            f"PRIVACY BREACH — _build_payload() is transmitting unexpected fields: "
            f"{extra}. These must be removed immediately."
        )
        assert not missing, (
            f"Expected fields missing from payload: {missing}. "
            f"Check _build_payload() in client/api/submit.py."
        )

    def test_forbidden_fields_not_in_payload(self):
        """
        Each forbidden field is checked individually.
        This makes failures easier to diagnose in a CI report.
        """
        from client.api.submit import _build_payload

        row = {
            "department": "it", "timestamp": "2024-06-01T10:00:00",
            "stress_level": 2,
            **{k: f"SENTINEL_{k}" for k in self.FORBIDDEN_FIELDS},
        }
        payload = _build_payload([row])
        payload_json = json.dumps(payload)

        for field in self.FORBIDDEN_FIELDS:
            assert field not in payload[0], (
                f"PRIVACY BREACH — forbidden field '{field}' present in payload dict"
            )
            assert f"SENTINEL_{field}" not in payload_json, (
                f"PRIVACY BREACH — sentinel value for '{field}' found in payload JSON"
            )

    def test_payload_values_not_identity_shaped(self):
        """
        None of the safe fields are free text — department and reason_category
        are constrained to admin-defined lists, stress_level is 1-5, timestamp
        is auto-generated, and floor_x/floor_y are bounded floats. There is no
        field left in the payload where an email, name, or other identity-shaped
        string could hide, even if a user typed one somewhere on the client —
        because the only free-text fields (description, elaboration) never
        reach _build_payload()'s output at all.
        """
        from client.api.submit import _build_payload

        row = {
            "department":      "hr",
            "timestamp":       "2024-06-01T11:00:00",
            "stress_level":    4,
            "elaboration":     "j.smith@example.com was rude in the meeting",
            "reason_category": "time_pressure",
            "floor_x":         None,
            "floor_y":         None,
        }
        payload = _build_payload([row])
        assert "elaboration" not in payload[0]
        payload_json = json.dumps(payload)
        assert "j.smith@example.com" not in payload_json, (
            "PRIVACY BREACH — free text reached the payload despite not being "
            "in SUBMISSION_FIELDS."
        )
        # department is a coarse label, not a personal identifier
        assert payload[0]["department"] == "hr"

    def test_submission_fields_constant_is_exhaustive(self):
        """
        SUBMISSION_FIELDS in shared/constants.py must list exactly the
        safe fields and nothing else.

        If this constant drifts from _build_payload()'s output,
        the documentation no longer reflects the actual boundary.
        """
        from shared.constants import SUBMISSION_FIELDS
        from client.api.submit import _build_payload

        row = {
            "department": "ops", "timestamp": "2024-01-01T00:00:00",
            "stress_level": 1,
            "reason_category": None,
            "floor_x": None, "floor_y": None,
            # local-only fields that should be stripped:
            "id": 1, "description": "x", "elaboration": "x", "submitted": 0,
        }
        payload = _build_payload([row])
        assert set(payload[0].keys()) == set(SUBMISSION_FIELDS), (
            "SUBMISSION_FIELDS constant is out of sync with _build_payload() output. "
            "Update shared/constants.py to match the actual transmitted fields."
        )

    def test_empty_optional_fields_are_null_not_omitted(self):
        """
        Optional fields (reason_category, floor_x, floor_y) must be present
        in the payload as null, not omitted entirely. Omitting them would
        cause server-side schema mismatches.
        """
        from client.api.submit import _build_payload

        row = {
            "department": "sales", "timestamp": "2024-06-01T09:00:00",
            "stress_level": 2,
            # Optional fields absent from local row
        }
        payload = _build_payload([row])
        assert "reason_category" in payload[0]
        assert "floor_x"         in payload[0]
        assert "floor_y"         in payload[0]
        assert payload[0]["reason_category"] is None
        assert payload[0]["floor_x"]         is None
        assert payload[0]["floor_y"]         is None


# ---------------------------------------------------------------------------
# LAYER 2 — Server-side field filtering audit
# ---------------------------------------------------------------------------

class TestLayer2_ServerFiltering:
    """
    Verifies that the server's _extract_entry() function acts as a
    second independent anonymisation filter.

    Even if a modified or malicious client sends identity fields,
    the server silently drops them before any database write.

    A privacy reviewer should inspect _extract_entry() in
    server/api/submissions.py alongside these tests.
    """

    def _extract(self, raw: dict):
        """Call _extract_entry() directly, bypassing HTTP."""
        from server.api.submissions import _extract_entry
        return _extract_entry(raw)

    def test_identity_fields_dropped_by_server(self):
        """
        A payload containing identity fields sent by a hypothetical
        rogue client must produce an extracted entry with none of them.
        """
        rogue_payload = {
            "department":    "finance",
            "timestamp":     "2024-06-01T09:00:00",
            "stress_level":  3,
            # Identity fields that a rogue client might add:
            "user_id":       "uid-1234",
            "username":      "jsmith",
            "email":         "j.smith@example.com",
            "machine_name":  "LAPTOP-SECRET",
            "ip_address":    "10.0.0.55",
            "session_id":    "sess-abcdef",
            "pin_hash":      "$2b$fakehash",
            "full_name":     "John Smith",
            "employee_id":   "EMP-00042",
        }
        result = self._extract(rogue_payload)

        assert result is not None, "Valid entry should be extracted despite extra fields"

        forbidden = {
            "user_id", "username", "email", "machine_name",
            "ip_address", "session_id", "pin_hash", "full_name", "employee_id",
        }
        for field in forbidden:
            assert field not in result, (
                f"PRIVACY BREACH — server stored identity field '{field}' "
                f"from a rogue payload!"
            )

    def test_server_accepted_fields_match_submission_fields(self):
        """
        _ACCEPTED_FIELDS in submissions.py must equal SUBMISSION_FIELDS
        in constants.py. If they diverge, one of the two boundary
        definitions has become stale.
        """
        from server.api.submissions import _ACCEPTED_FIELDS
        from shared.constants import SUBMISSION_FIELDS

        assert _ACCEPTED_FIELDS == set(SUBMISSION_FIELDS), (
            "server/api/submissions.py _ACCEPTED_FIELDS is out of sync with "
            "shared/constants.py SUBMISSION_FIELDS. Both must be updated together."
        )

    def test_extract_returns_only_safe_field_names(self):
        """Every key in the extracted entry must be a safe, non-identity field."""
        safe = {
            "department", "timestamp", "stress_level",
            "reason_category", "floor_x", "floor_y",
        }
        result = self._extract({
            "department": "hr", "timestamp": "2024-06-01T10:00:00",
            "stress_level": 2, "reason_category": "noise",
            "floor_x": 0.3, "floor_y": 0.7,
        })
        assert result is not None
        assert set(result.keys()) == safe

    def test_elaboration_dropped_even_if_client_sends_it(self):
        """
        A malformed or outdated client might still send 'elaboration'.
        The server must silently drop it regardless — this is the Layer 2
        defense-in-depth check, independent of the client ever being fixed.
        """
        result = self._extract({
            "department": "hr", "timestamp": "2024-06-01T10:00:00",
            "stress_level": 2, "reason_category": "noise",
            "elaboration": "j.smith@example.com said this was too loud",
        })
        assert result is not None
        assert "elaboration" not in result, (
            "PRIVACY BREACH — _extract_entry() stored free text sent by a client."
        )

    def test_missing_required_fields_return_none(self):
        """
        Entries missing department or timestamp or a valid stress_level
        are rejected at extraction time — they never reach the database.
        """
        assert self._extract({}) is None
        assert self._extract({"timestamp": "2024-01-01T00:00:00", "stress_level": 3}) is None
        assert self._extract({"department": "it", "stress_level": 3}) is None
        assert self._extract({"department": "it", "timestamp": "2024-01-01T00:00:00"}) is None

    def test_stress_level_boundary_validation(self):
        """stress_level must be 1–5 inclusive. Out-of-range values are rejected."""
        base = {"department": "it", "timestamp": "2024-01-01T00:00:00"}

        for valid_level in [1, 2, 3, 4, 5]:
            result = self._extract({**base, "stress_level": valid_level})
            assert result is not None, f"Level {valid_level} should be accepted"

        for invalid_level in [0, 6, -1, 100, 1.5, "high"]:
            result = self._extract({**base, "stress_level": invalid_level})
            assert result is None, f"Level {invalid_level!r} should be rejected"

    def test_floor_coords_must_be_zero_to_one(self):
        """
        Floor coordinates outside [0.0, 1.0] are silently nulled out.
        The entry is still saved without coordinates.
        """
        base = {"department": "it", "timestamp": "2024-01-01T00:00:00",
                "stress_level": 2}

        # Valid coords
        result = self._extract({**base, "floor_x": 0.5, "floor_y": 0.5})
        assert result["floor_x"] == pytest.approx(0.5)
        assert result["floor_y"] == pytest.approx(0.5)

        # Boundary values
        result = self._extract({**base, "floor_x": 0.0, "floor_y": 1.0})
        assert result["floor_x"] == pytest.approx(0.0)
        assert result["floor_y"] == pytest.approx(1.0)

        # Out-of-range — entry saved, coords nulled
        result = self._extract({**base, "floor_x": 1.5, "floor_y": -0.1})
        assert result is not None
        assert result["floor_x"] is None
        assert result["floor_y"] is None


# ---------------------------------------------------------------------------
# LAYER 3 — Database schema audit
# ---------------------------------------------------------------------------

class TestLayer3_DatabaseSchema:
    """
    Verifies the server database schema directly.

    The Entry table is inspected at the SQLite PRAGMA level — this is
    independent of the ORM models and catches schema drift.

    A privacy reviewer can run this test and then independently open
    the .db file with any SQLite browser to confirm the same thing.
    """

    @pytest.fixture
    def temp_db(self):
        """Create an initialised server database in a temp file."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        from server.models.db import init_db, _engine, SessionLocal, Base
        import server.models.db as db_mod
        db_mod._engine = None
        db_mod.SessionLocal = None
        db_mod.init_db(path)
        yield path
        try:
            os.unlink(path)
        except OSError:
            pass

    def test_entries_table_has_no_identity_columns(self, temp_db):
        """
        Inspect the entries table schema via raw SQLite PRAGMA.
        No column name should suggest user identity.

        This test does NOT use SQLAlchemy — it reads the schema directly
        from the SQLite file, making it suitable for independent audit.
        """
        conn = sqlite3.connect(temp_db)
        try:
            cursor = conn.execute("PRAGMA table_info(entries)")
            columns = [row[1] for row in cursor.fetchall()]  # row[1] = column name
        finally:
            conn.close()

        assert columns, "entries table should exist and have columns"

        # Columns that are EXPECTED (privacy-safe)
        expected = {
            "id", "department", "timestamp", "stress_level",
            "reason_category", "elaboration", "floor_x", "floor_y",
            "received_at",  # server-set receipt timestamp, not user identity
        }

        # Terms that must NOT appear in any column name
        forbidden_terms = [
            "user", "name", "email", "password", "hash", "token",
            "machine", "host", "session", "address", "employee",
            "login", "auth", "personal", "identity",
        ]

        for col in columns:
            for term in forbidden_terms:
                assert term not in col.lower(), (
                    f"PRIVACY BREACH — entries table has column '{col}' which "
                    f"matches forbidden term '{term}'. Schema must be reviewed."
                )

        unexpected = set(columns) - expected
        assert not unexpected, (
            f"Unexpected columns in entries table: {unexpected}. "
            f"Review whether any of these could identify a user."
        )

    def test_no_user_table_exists(self, temp_db):
        """
        There must be no 'users', 'accounts', or 'sessions' table in the
        server database. The server never provisions user accounts.
        """
        conn = sqlite3.connect(temp_db)
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}
        finally:
            conn.close()

        identity_tables = [
            "users", "user", "accounts", "account",
            "sessions", "session", "logins", "credentials",
            "employees", "persons",
        ]
        for table in identity_tables:
            assert table not in tables, (
                f"PRIVACY BREACH — server database contains table '{table}'. "
                f"The server must never store user accounts or sessions."
            )

    def test_entries_table_columns_match_to_dict_output(self, temp_db):
        """
        Entry.to_dict() is used for all data exports. Its keys must match
        the actual database columns (minus server-internal columns like received_at).

        If to_dict() ever gains an identity field, this test fails.
        """
        from server.models.db import Entry, SessionLocal

        # Insert a test entry
        db = SessionLocal()
        from datetime import datetime
        entry = Entry(
            department="test",
            timestamp=datetime(2024, 1, 1, 9, 0, 0),
            stress_level=3,
        )
        db.add(entry)
        db.commit()

        entry_dict = entry.to_dict()
        db.close()

        # These are the only keys that should appear in exported data.
        # Note: elaboration is deliberately absent -- the column still exists
        # in the schema (see test_entries_table_has_no_identity_columns) but
        # to_dict() never surfaces it, so it can never reach an export.
        allowed_export_keys = {
            "id", "department", "timestamp", "stress_level",
            "reason_category", "floor_x", "floor_y",
        }
        forbidden_terms = [
            "user", "email", "name", "hash", "token", "machine",
            "session", "password", "pin", "address",
        ]

        for key in entry_dict.keys():
            for term in forbidden_terms:
                assert term not in key.lower(), (
                    f"to_dict() output contains suspicious key '{key}' "
                    f"matching forbidden term '{term}'"
                )

        unexpected = set(entry_dict.keys()) - allowed_export_keys
        assert not unexpected, (
            f"to_dict() is exposing unexpected fields: {unexpected}. "
            f"These will appear in CSV/JSON exports — review immediately."
        )

    def test_local_client_db_pin_column_not_transmitted(self, tmp_path, monkeypatch):
        """
        The local client database has a pin_hash column in the settings table.
        This test confirms that column is never readable by _build_payload().

        _build_payload() receives a list of dicts from the entries table,
        which has no pin_hash column. This test verifies that isolation.
        """
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "audit.db"))
        db_mod.init_db()

        from client.storage.session import create_pin
        from client.storage.entries import add_entry, get_pending_entries
        from client.api.submit import _build_payload

        create_pin("auditpin")
        add_entry("audit note", 3, "finance")

        entries = get_pending_entries()

        # Verify entries rows don't contain pin_hash at all
        for entry in entries:
            assert "pin_hash" not in entry, (
                "entries table row should not contain pin_hash — "
                "check the db schema in client/storage/db.py"
            )

        # Verify _build_payload output doesn't contain it either
        payload = _build_payload(entries)
        payload_str = json.dumps(payload)
        assert "pin_hash" not in payload_str
        assert "auditpin" not in payload_str
        assert "$2b$" not in payload_str


# ---------------------------------------------------------------------------
# Cross-layer integration audit
# ---------------------------------------------------------------------------

class TestCrossLayerAudit:
    """
    End-to-end anonymisation audit tests that verify all three layers
    working together.
    """

    def test_full_pipeline_no_identity_leakage(self, tmp_path, monkeypatch):
        """
        Simulate the full client-to-server pipeline:
          1. Client logs an entry with a real PIN set
          2. Payload is built
          3. Payload is passed through server _extract_entry()
          4. Result is verified to contain no identity data

        This is the closest thing to an end-to-end privacy audit
        without spinning up a real HTTP server.
        """
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "e2e.db"))
        db_mod.init_db()

        from client.storage.session import create_pin, set_department
        from client.storage.entries import add_entry, get_pending_entries
        from client.api.submit import _build_payload
        from server.api.submissions import _extract_entry

        # Set up a user
        create_pin("private-pin-must-not-leak")
        set_department("finance")

        # Log an entry
        add_entry("Stressful meeting with management", 4, "finance")

        # Build payload (client side)
        entries = get_pending_entries()
        payload = _build_payload(entries)

        # Pass through server extraction (server side)
        for item in payload:
            extracted = _extract_entry(item)
            assert extracted is not None

            # Verify the complete extracted entry
            payload_str = json.dumps(extracted, default=str)
            assert "private-pin-must-not-leak" not in payload_str
            assert "$2b$" not in payload_str
            assert "Stressful meeting with management" not in payload_str, (
                "Raw description must not appear in the transmitted payload. "
                "No free-text field is ever transmitted -- description and "
                "elaboration both stay on the device."
            )
            assert "finance" in payload_str  # department IS transmitted, that's correct

    def test_department_is_the_only_group_identifier(self):
        """
        Confirm by inspection that 'department' is the only field in
        SUBMISSION_FIELDS that could identify a group of people.

        All other fields are either categorical (stress_level, reason_category),
        temporal (timestamp), or spatial (floor_x, floor_y) — none are personal
        identifiers, and none are free text (elaboration and description both
        stay on the device -- see SUBMISSION_FIELDS' docstring).

        This test is deliberately simple: it reads the constant and
        checks each field against a classification.
        """
        from shared.constants import SUBMISSION_FIELDS

        GROUP_IDENTIFIERS = {"department"}  # intentionally coarse
        TEMPORAL_FIELDS   = {"timestamp"}
        ORDINAL_FIELDS    = {"stress_level"}
        CATEGORICAL_FIELDS = {"reason_category"}
        SPATIAL_FIELDS    = {"floor_x", "floor_y"}
        # No FREE_TEXT_FIELDS category: elaboration and description both stay
        # on the device and are never part of SUBMISSION_FIELDS at all.

        all_classified = (
            GROUP_IDENTIFIERS | TEMPORAL_FIELDS | ORDINAL_FIELDS |
            CATEGORICAL_FIELDS | SPATIAL_FIELDS
        )

        unclassified = set(SUBMISSION_FIELDS) - all_classified
        assert not unclassified, (
            f"Unclassified fields in SUBMISSION_FIELDS: {unclassified}. "
            f"Each field must be reviewed for privacy implications and added "
            f"to a classification group in this test."
        )
