"""
tests/test_server.py
--------------------
Server-side tests covering:
  - Submission endpoint accepts valid payloads and rejects invalid ones
  - Anonymisation boundary: identity fields are never stored
  - Department endpoint returns expected structure
  - Admin authentication
  - Export formats

Run with: pytest tests/
"""

import json
import os
import sys
import tempfile
import unittest.mock as mock
import pytest


# Point config to test fixture before importing anything from the app
os.environ["LETTERBOX_CONFIG"] = os.path.join(
    os.path.dirname(__file__), "fixtures", "test_config.yaml"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app():
    """
    Flask test app backed by a temp-file SQLite database.

    A real file (not :memory:) is needed because SQLAlchemy's SessionLocal
    factory creates a new connection per call; :memory: gives each connection
    an isolated empty database, so rows written in one request are invisible
    to the next.  A named temp file persists across connections and is cleaned
    up at teardown.
    """
    import server.config as cfg_module
    import server.models.db as db_module
    from server.app import create_app

    cfg_module.load_config.cache_clear()

    # Temp db file
    fd, test_db_path = tempfile.mkstemp(suffix=".db", prefix="letterbox_test_")
    os.close(fd)

    # Load the test config and override the db path
    base_cfg = cfg_module.load_config()
    base_cfg = dict(base_cfg)  # shallow copy
    base_cfg["database"] = dict(base_cfg["database"])
    base_cfg["database"]["path"] = test_db_path

    # Reset db module globals so init_db() starts fresh
    db_module._engine = None
    db_module.SessionLocal = None
    db_module.init_db(test_db_path)

    with mock.patch.object(cfg_module, "load_config", return_value=base_cfg):
        flask_app = create_app()
        flask_app.config["TESTING"] = True
        flask_app.config["WTF_CSRF_ENABLED"] = False
        flask_app.config["SECRET_KEY"] = "test-secret-key"

        yield flask_app

    try:
        os.unlink(test_db_path)
    except OSError:
        pass


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_client(app):
    """A test client pre-authenticated as admin."""
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["admin_logged_in"] = True
    return c


# ---------------------------------------------------------------------------
# Submission endpoint
# ---------------------------------------------------------------------------

class TestSubmitEndpoint:

    def test_valid_single_entry(self, client):
        payload = {
            "department": "finance",
            "timestamp": "2024-06-15T10:30:00",
            "stress_level": 3,
            "reason_category": "workload",
        }
        resp = client.post(
            "/api/submit",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["saved"] == 1
        assert data["errors"] == 0

    def test_valid_batch(self, client):
        batch = [
            {"department": "it",  "timestamp": "2024-06-15T09:00:00", "stress_level": 2},
            {"department": "it",  "timestamp": "2024-06-15T14:00:00", "stress_level": 4,
             "reason_category": "noise"},
            {"department": "hr",  "timestamp": "2024-06-15T11:30:00", "stress_level": 1},
        ]
        resp = client.post(
            "/api/submit",
            data=json.dumps(batch),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["saved"] == 3

    def test_missing_department_rejected(self, client):
        payload = {"timestamp": "2024-06-15T10:00:00", "stress_level": 3}
        resp = client.post(
            "/api/submit",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["saved"] == 0
        assert data["errors"] == 1

    def test_invalid_stress_level_rejected(self, client):
        payload = {
            "department": "finance",
            "timestamp": "2024-06-15T10:00:00",
            "stress_level": 9,  # out of 1-5 range
        }
        resp = client.post(
            "/api/submit",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["errors"] == 1

    def test_location_from_older_client_ignored(self, client):
        """An older client may still send floor coordinates; they're dropped
        and the entry is still saved."""
        payload = {
            "department": "sales",
            "timestamp": "2024-06-15T10:00:00",
            "stress_level": 2,
            "floor_x": 0.4,
            "floor_y": 0.6,
        }
        resp = client.post(
            "/api/submit",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["saved"] == 1

    def test_empty_body_rejected(self, client):
        resp = client.post("/api/submit", data="", content_type="application/json")
        assert resp.status_code == 400

    def test_batch_too_large_rejected(self, client):
        big_batch = [
            {"department": "ops", "timestamp": "2024-01-01T00:00:00", "stress_level": 1}
        ] * 501
        resp = client.post(
            "/api/submit",
            data=json.dumps(big_batch),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_partial_batch_errors_counted(self, client):
        """A batch with some invalid entries should report partial save."""
        batch = [
            {"department": "finance", "timestamp": "2024-06-20T09:00:00",
             "stress_level": 2},                            # valid
            {"timestamp": "2024-06-20T09:01:00", "stress_level": 3},  # missing dept
            {"department": "hr", "timestamp": "2024-06-20T09:02:00",
             "stress_level": 6},                            # invalid level
        ]
        resp = client.post(
            "/api/submit",
            data=json.dumps(batch),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["saved"] == 1
        assert data["errors"] == 2

    def test_unknown_department_rejected(self, client):
        """Made-up department names must not reach the dashboard filters."""
        resp = client.post(
            "/api/submit",
            data=json.dumps({"department": "not_a_real_dept",
                             "timestamp": "2024-06-21T09:00:00", "stress_level": 2}),
            content_type="application/json",
        )
        assert resp.get_json() == {"saved": 0, "errors": 1}

    def test_unknown_reason_dropped_but_entry_kept(self, admin_client):
        """reason_category is optional, so an unknown one is cleared, not fatal."""
        admin_client.post(
            "/api/submit",
            data=json.dumps({"department": "hr", "timestamp": "2031-01-01T09:00:00",
                             "stress_level": 4, "reason_category": "made_up"}),
            content_type="application/json",
        )
        resp = admin_client.get("/api/admin/entries?date_from=2031-01-01&date_to=2031-01-02")
        entries = resp.get_json()["entries"]
        assert len(entries) == 1
        assert entries[0]["reason_category"] is None

    def test_solution_category_stored(self, admin_client):
        admin_client.post(
            "/api/submit",
            data=json.dumps({"department": "hr", "timestamp": "2031-02-01T09:00:00",
                             "stress_level": 4, "reason_category": "noise",
                             "solution_category": "focus_time"}),
            content_type="application/json",
        )
        resp = admin_client.get("/api/admin/entries?date_from=2031-02-01&date_to=2031-02-02")
        entries = resp.get_json()["entries"]
        assert len(entries) == 1
        assert entries[0]["solution_category"] == "focus_time"

    def test_unknown_solution_dropped_but_entry_kept(self, admin_client):
        """solution_category is optional, so an unknown one is cleared, not fatal."""
        admin_client.post(
            "/api/submit",
            data=json.dumps({"department": "hr", "timestamp": "2031-03-01T09:00:00",
                             "stress_level": 3,
                             "solution_category": "fire everyone"}),
            content_type="application/json",
        )
        resp = admin_client.get("/api/admin/entries?date_from=2031-03-01&date_to=2031-03-02")
        entries = resp.get_json()["entries"]
        assert len(entries) == 1
        assert entries[0]["solution_category"] is None

    def test_malformed_entries_rejected_not_500(self, client):
        """Non-object entries and non-string departments are errors, not crashes."""
        batch = [
            "just a string",
            {"department": 42, "timestamp": "2024-06-21T09:00:00", "stress_level": 2},
            {"department": ["it"], "timestamp": "2024-06-21T09:00:00", "stress_level": 2},
        ]
        resp = client.post("/api/submit", data=json.dumps(batch),
                           content_type="application/json")
        assert resp.status_code == 200
        assert resp.get_json() == {"saved": 0, "errors": 3}

    def test_inactive_departments_still_accepted(self, monkeypatch):
        """Retired departments stay valid so pending entries aren't lost."""
        import server.config as cfg
        monkeypatch.setattr(cfg, "load_config", lambda: {
            "departments": [{"id": "legacy", "name": "Legacy", "active": False},
                            {"id": "it", "name": "IT", "active": True}],
        })
        assert cfg.get_department_ids() == {"legacy", "it"}
        assert [d["id"] for d in cfg.get_departments()] == ["it"]


# ---------------------------------------------------------------------------
# Anonymisation boundary
# ---------------------------------------------------------------------------

class TestAnonymisationBoundary:
    """
    These tests verify the core privacy guarantee:
    identity fields are never stored, even if present in the payload.
    """

    def test_identity_fields_not_stored(self, client, app):
        """
        Submit a payload containing fabricated identity fields.
        Verify none appear in the stored entry.
        """
        payload = {
            "department": "finance",
            "timestamp": "2024-07-01T08:00:00",
            "stress_level": 4,
            # These MUST be silently ignored by the server:
            "user_id":       "u-12345",
            "username":      "jsmith",
            "email":         "j.smith@example.com",
            "machine_name":  "DESKTOP-ABC123",
            "ip_address":    "192.168.1.55",
            "session_token": "fake-token-xyz",
            "pin_hash":      "$2b$12$fakehash",
        }
        resp = client.post(
            "/api/submit",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["saved"] == 1

        from server.models.db import Entry, SessionLocal
        db = SessionLocal()
        try:
            entry = db.query(Entry).order_by(Entry.id.desc()).first()
            entry_dict = entry.to_dict()

            forbidden = [
                "user_id", "username", "email", "machine_name",
                "ip_address", "session_token", "pin_hash",
            ]
            for key in forbidden:
                assert key not in entry_dict, (
                    f"PRIVACY BREACH: identity field '{key}' found in stored entry!"
                )

            # Exact expected key set (elaboration deliberately excluded —
            # to_dict() never exposes it, see server/models/db.py)
            expected = {
                "id", "department", "timestamp", "stress_level",
                "reason_category", "solution_category",
            }
            assert set(entry_dict.keys()) == expected
        finally:
            db.close()

    def test_payload_builder_output_fields_only(self):
        """
        Unit test _build_payload() in isolation.
        Output must contain exactly the fields in SUBMISSION_FIELDS — no more.
        """
        from client.api.submit import _build_payload
        from shared.constants import SUBMISSION_FIELDS

        raw_entries = [{
            "id":           42,           # local DB id — must NOT appear
            "description":  "Loud office", # local plaintext — must NOT appear
            "department":   "it",
            "timestamp":    "2024-06-01T09:00:00",
            "stress_level": 3,
            "reason_category": "noise",
            "elaboration":  "Open plan",   # local plaintext — must NOT appear
            "floor_x":      0.5,           # from an older local db — must NOT appear
            "floor_y":      0.3,
            "submitted":    0,            # local flag — must NOT appear
            "submitted_at": None,
        }]

        result = _build_payload(raw_entries)
        assert len(result) == 1
        got  = set(result[0].keys())
        want = set(SUBMISSION_FIELDS)

        extra   = got - want
        missing = want - got

        assert not extra,   f"Extra fields in payload (privacy risk): {extra}"
        assert not missing, f"Missing expected fields: {missing}"

    def test_submission_fields_constant_unchanged(self):
        """
        Regression guard: SUBMISSION_FIELDS must not silently gain identity fields.
        If this test fails, the anonymisation guarantee has been broken.
        """
        from shared.constants import SUBMISSION_FIELDS

        forbidden_terms = [
            "user", "name", "email", "password", "hash", "token",
            "machine", "host", "ip", "address", "session", "id",
        ]
        # "id" is forbidden in field names; the server-assigned int primary key
        # is acceptable in DB responses but must not be in SUBMISSION_FIELDS.
        for field in SUBMISSION_FIELDS:
            for term in forbidden_terms:
                assert term not in field.lower(), (
                    f"SUBMISSION_FIELDS contains a potentially identifying field: "
                    f"'{field}' matches forbidden term '{term}'"
                )


# ---------------------------------------------------------------------------
# Departments / config endpoints
# ---------------------------------------------------------------------------

class TestPublicEndpoints:

    def test_departments_returns_list(self, client):
        resp = client.get("/api/departments")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_each_department_has_id_and_name(self, client):
        resp = client.get("/api/departments")
        for dept in resp.get_json():
            assert "id" in dept
            assert "name" in dept
            assert dept["id"]   # not empty
            assert dept["name"] # not empty

    def test_config_endpoint_excludes_admin_credentials(self, client):
        """
        /api/config is called by clients.
        It must never expose admin credentials or server internals.
        """
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.get_json()

        # Must NOT contain any of these
        forbidden = ["password_hash", "secret_key", "admin", "database"]
        for key in forbidden:
            assert key not in data, (
                f"Admin/server field '{key}' exposed on public /api/config endpoint!"
            )

        # Must contain expected client-facing fields
        assert "departments"        in data
        assert "reason_categories"  in data
        assert "solution_categories" in data
        assert "reminder_frequency" in data
        assert "entry_char_limit"   in data

    def test_solution_categories_present_in_config(self, client):
        sols = client.get("/api/config").get_json().get("solution_categories", [])
        assert len(sols) > 0
        for sol in sols:
            assert "id"    in sol
            assert "label" in sol

    def test_reason_categories_present_in_config(self, client):
        resp = client.get("/api/config")
        cats = resp.get_json().get("reason_categories", [])
        assert isinstance(cats, list)
        assert len(cats) > 0
        for cat in cats:
            assert "id"    in cat
            assert "label" in cat


# ---------------------------------------------------------------------------
# Admin authentication
# ---------------------------------------------------------------------------

def _login_csrf_token(client) -> str:
    """GET the login page and pull the hidden csrf_token out of the form."""
    import re
    html = client.get("/admin/login").get_data(as_text=True)
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "login form has no csrf_token field"
    return match.group(1)


class TestAdminAuth:

    @pytest.fixture(autouse=True)
    def _fresh_rate_limits(self):
        """Login POSTs are limited to 5/min; keep these tests from starving each other."""
        from server.extensions import limiter
        limiter.reset()
        yield
        limiter.reset()

    def test_dashboard_root_redirects_to_login_when_unauthenticated(self, client):
        resp = client.get("/admin/", follow_redirects=False)
        assert resp.status_code in (301, 302)
        location = resp.headers.get("Location", "")
        assert "login" in location.lower()

    def test_wrong_password_rejected(self, client):
        token = _login_csrf_token(client)
        resp = client.post(
            "/admin/login",
            data={"username": "testadmin", "password": "wrongpassword",
                  "csrf_token": token},
            follow_redirects=True,
        )
        assert b"Invalid" in resp.data

    def test_correct_login_with_csrf_token_succeeds(self, client):
        token = _login_csrf_token(client)
        resp = client.post(
            "/admin/login",
            data={"username": "testadmin", "password": "testpassword123",
                  "csrf_token": token},
        )
        assert resp.status_code == 302
        assert client.get("/admin/").status_code == 200

    def test_login_without_csrf_token_rejected(self, client):
        """A forged cross-site login POST has no token and must not log in."""
        client.get("/admin/login")  # session exists, but the token isn't sent
        resp = client.post(
            "/admin/login",
            data={"username": "testadmin", "password": "testpassword123"},
        )
        assert resp.status_code == 400
        assert client.get("/admin/").status_code == 302  # still logged out

    def test_login_with_wrong_csrf_token_rejected(self, client):
        client.get("/admin/login")
        resp = client.post(
            "/admin/login",
            data={"username": "testadmin", "password": "testpassword123",
                  "csrf_token": "forged"},
        )
        assert resp.status_code == 400

    def test_session_cookie_is_samesite_lax(self, client):
        resp = client.get("/admin/login")
        cookie = resp.headers.get("Set-Cookie", "")
        assert "SameSite=Lax" in cookie
        assert "HttpOnly" in cookie

    def test_malformed_password_hash_fails_closed(self):
        """A placeholder hash in config.yaml must mean 'wrong password', not a 500."""
        from server.dashboard.auth import _password_matches
        assert _password_matches(b"anything", "REPLACE-WITH-BCRYPT-HASH") is False

    def test_login_rate_limited_after_five_attempts(self, client):
        token = _login_csrf_token(client)
        codes = [
            client.post("/admin/login",
                        data={"username": "testadmin", "password": "wrong",
                              "csrf_token": token}).status_code
            for _ in range(6)
        ]
        assert codes[:5] == [200] * 5
        assert codes[5] == 429

    def test_login_page_itself_not_rate_limited(self, client):
        """Only POST attempts count; viewing the form stays available."""
        for _ in range(10):
            assert client.get("/admin/login").status_code == 200

    def test_export_endpoint_requires_auth(self, client):
        resp = client.get("/api/admin/export")
        assert resp.status_code == 401

    def test_authenticated_client_can_reach_entries(self, admin_client):
        resp = admin_client.get("/api/admin/entries")
        assert resp.status_code == 200
        assert "entries" in resp.get_json()


# ---------------------------------------------------------------------------
# Export endpoint
# ---------------------------------------------------------------------------

class TestExport:

    def _seed_entries(self, client):
        """Insert a couple of known entries for export testing."""
        batch = [
            {"department": "finance", "timestamp": "2024-08-01T09:00:00",
             "stress_level": 2, "reason_category": "workload"},
            {"department": "it", "timestamp": "2024-08-02T14:00:00",
             "stress_level": 4, "solution_category": "focus_time"},
        ]
        client.post(
            "/api/submit",
            data=json.dumps(batch),
            content_type="application/json",
        )

    def test_csv_export_returns_csv(self, admin_client):
        self._seed_entries(admin_client)
        resp = admin_client.get("/api/admin/export?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type
        # Should have a header row
        text = resp.data.decode("utf-8")
        assert "department" in text
        assert "stress_level" in text

    def test_json_export_returns_json(self, admin_client):
        self._seed_entries(admin_client)
        resp = admin_client.get("/api/admin/export?format=json")
        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        data = json.loads(resp.data)
        assert isinstance(data, list)

    def test_export_filters_by_department(self, admin_client):
        self._seed_entries(admin_client)
        resp = admin_client.get("/api/admin/export?format=json&department=finance")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        for entry in data:
            assert entry["department"] == "finance"

    def test_csv_export_has_no_identity_columns(self, admin_client):
        """Exported CSV must not contain any identity-adjacent column names."""
        self._seed_entries(admin_client)
        resp = admin_client.get("/api/admin/export?format=csv")
        header_line = resp.data.decode("utf-8").split("\n")[0].lower()

        forbidden_cols = ["user", "email", "name", "token", "hash", "machine", "ip"]
        for col in forbidden_cols:
            assert col not in header_line, (
                f"Identity-adjacent column '{col}' found in CSV export header!"
            )


# ---------------------------------------------------------------------------
# Floor plan location tagging has been removed
# ---------------------------------------------------------------------------

class TestNoLocation:
    """
    The floor plan feature is gone: its routes no longer exist, and
    coordinates sent by an older client are neither stored nor shown.
    """

    def _seed_with_coords(self, client):
        client.post(
            "/api/submit",
            data=json.dumps([
                {"department": "it", "timestamp": "2032-01-01T10:00:00",
                 "stress_level": 3, "floor_x": 0.2, "floor_y": 0.8},
            ]),
            content_type="application/json",
        )

    def test_heatmap_page_gone(self, admin_client):
        assert admin_client.get("/admin/heatmap").status_code == 404

    def test_heatmap_data_gone(self, admin_client):
        assert admin_client.get("/api/admin/heatmap-data").status_code == 404

    def test_floorplan_api_gone(self, admin_client):
        assert admin_client.get("/api/floorplan").status_code == 404
        assert admin_client.post("/api/floorplan/upload").status_code == 404

    def test_no_floor_plan_nav_link(self, admin_client):
        resp = admin_client.get("/admin/")
        assert b"Floor Plan" not in resp.data

    def test_entries_api_has_no_coordinates(self, admin_client):
        self._seed_with_coords(admin_client)
        resp = admin_client.get("/api/admin/entries?date_from=2032-01-01&date_to=2032-01-02")
        entries = resp.get_json()["entries"]
        assert len(entries) == 1
        assert "floor_x" not in entries[0]
        assert "floor_y" not in entries[0]

    def test_exports_have_no_coordinates(self, admin_client):
        self._seed_with_coords(admin_client)
        csv_text = admin_client.get("/api/admin/export?format=csv").data.decode("utf-8")
        csv_header = csv_text.splitlines()[0]
        assert "floor" not in csv_header
        data = json.loads(admin_client.get("/api/admin/export?format=json").data)
        assert all("floor_x" not in e for e in data)


# ---------------------------------------------------------------------------
# Overview filters apply to the figures on the page
# ---------------------------------------------------------------------------

class TestDatabaseUpgrade:

    def test_init_db_upgrades_older_database(self, tmp_path):
        """A server database from an older version keeps its rows, gains the
        solution column, and has any stored floor coordinates wiped."""
        import sqlite3
        import server.models.db as db_module

        path = tmp_path / "old_server.db"
        conn = sqlite3.connect(path)
        conn.execute("""CREATE TABLE entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT, department VARCHAR(64) NOT NULL,
            timestamp DATETIME NOT NULL, stress_level INTEGER NOT NULL,
            reason_category VARCHAR(64), elaboration TEXT, floor_x FLOAT,
            floor_y FLOAT, received_at DATETIME NOT NULL)""")
        conn.execute("""INSERT INTO entries (department, timestamp, stress_level,
                                             floor_x, floor_y, received_at)
                        VALUES ('hr', '2024-01-01 09:00:00', 3, 0.4, 0.6,
                                '2024-01-01 09:00:00')""")
        conn.commit()
        conn.close()

        old_engine, old_session = db_module._engine, db_module.SessionLocal
        try:
            db_module.init_db(str(path))
            db = db_module.SessionLocal()
            try:
                rows = db.query(db_module.Entry).all()
                assert len(rows) == 1
                assert rows[0].solution_category is None
            finally:
                db.close()
            db_module._engine.dispose()
        finally:
            db_module._engine, db_module.SessionLocal = old_engine, old_session

        conn = sqlite3.connect(path)
        try:
            coords = conn.execute("SELECT floor_x, floor_y FROM entries").fetchall()
        finally:
            conn.close()
        assert coords == [(None, None)]


class TestOverviewFilters:

    def test_filter_narrows_totals(self, admin_client):
        admin_client.post(
            "/api/submit",
            data=json.dumps([
                {"department": "sales", "timestamp": "2033-01-01T10:00:00",
                 "stress_level": 2, "solution_category": "clearer_priorities"},
            ]),
            content_type="application/json",
        )
        resp = admin_client.get(
            "/admin/?solution_category=clearer_priorities"
            "&date_from=2033-01-01&date_to=2033-01-02"
        )
        assert resp.status_code == 200
        assert b'<div class="stat-value">1</div>' in resp.data


# ---------------------------------------------------------------------------
# Client-side storage unit tests
# ---------------------------------------------------------------------------

class TestClientStorage:

    def test_pin_stored_as_bcrypt_hash(self, tmp_path, monkeypatch):
        """PIN must be bcrypt-hashed, never stored as plaintext."""
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "c1.db"))
        db_mod.init_db()

        from client.storage.session import create_pin, get_setting
        create_pin("correct-horse-battery")

        stored = get_setting("pin_hash")
        assert stored is not None
        assert stored != "correct-horse-battery"
        assert stored.startswith("$2b$"), "Expected bcrypt hash prefix $2b$"

    def test_pin_verify_correct(self, tmp_path, monkeypatch):
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "c2.db"))
        db_mod.init_db()

        from client.storage.session import create_pin, verify_pin
        create_pin("mypin1234")
        assert verify_pin("mypin1234") is True

    def test_pin_verify_wrong(self, tmp_path, monkeypatch):
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "c3.db"))
        db_mod.init_db()

        from client.storage.session import create_pin, verify_pin
        create_pin("mypin1234")
        assert verify_pin("wrongpin") is False

    def test_delete_entry_is_hard_delete(self, tmp_path, monkeypatch):
        """
        Deleted entries must be permanently gone — no soft-delete, no recovery.
        """
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "c4.db"))
        db_mod.init_db()

        from client.storage.entries import add_entry, get_entry, delete_entry
        eid = add_entry("stressful thing", 3, "finance")
        assert get_entry(eid) is not None, "Entry should exist before deletion"

        delete_entry(eid)
        assert get_entry(eid) is None, (
            "Entry must be permanently deleted — found it after delete_entry()"
        )

    def test_submitted_entry_not_in_pending(self, tmp_path, monkeypatch):
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "c5.db"))
        db_mod.init_db()

        from client.storage.entries import (
            add_entry, get_pending_entries, mark_submitted
        )
        eid = add_entry("note", 2, "it")
        assert any(e["id"] == eid for e in get_pending_entries())

        mark_submitted([eid])
        assert not any(e["id"] == eid for e in get_pending_entries()), (
            "Submitted entry should not appear in pending list"
        )

    def test_payload_builder_never_leaks_local_fields(self, tmp_path, monkeypatch):
        """
        _build_payload() must strip every local-only field before transmission.
        """
        import client.storage.db as db_mod
        monkeypatch.setattr(db_mod, "get_db_path", lambda: str(tmp_path / "c6.db"))
        db_mod.init_db()

        from client.storage.session import create_pin
        from client.storage.entries import add_entry, get_pending_entries
        from client.api.submit import _build_payload

        create_pin("sentinel-pin-value")
        add_entry("test stress note", 4, "operations")

        entries = get_pending_entries()
        payload = _build_payload(entries)

        payload_str = json.dumps(payload)

        # The PIN value must never appear in the payload
        assert "sentinel-pin-value" not in payload_str
        assert "$2b$" not in payload_str  # no hash fragments either

        # Local DB fields that must not be transmitted
        local_only = ["id", "submitted", "submitted_at", "description", "elaboration"]
        # Note: both free-text fields -- "description" (the quick-log note) and
        # "elaboration" (the letterbox "more detail" note) -- stay on the device.
        # Neither is in SUBMISSION_FIELDS.
        for key in local_only:
            for item in payload:
                assert key not in item, (
                    f"Local-only field '{key}' leaked into submission payload!"
                )
