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
            "floor_x": 0.45,
            "floor_y": 0.62,
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

    def test_floor_coords_out_of_range_ignored(self, client):
        """Out-of-range coordinates are silently dropped; entry is still saved."""
        payload = {
            "department": "sales",
            "timestamp": "2024-06-15T10:00:00",
            "stress_level": 2,
            "floor_x": 1.5,   # > 1.0 — invalid
            "floor_y": -0.1,  # < 0.0 — invalid
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
                "reason_category", "floor_x", "floor_y",
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
            "floor_x":      0.5,
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
        assert "reminder_frequency" in data
        assert "entry_char_limit"   in data

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

    def test_heatmap_data_endpoint_requires_auth(self, client):
        resp = client.get("/api/admin/heatmap-data")
        assert resp.status_code == 401

    def test_export_endpoint_requires_auth(self, client):
        resp = client.get("/api/admin/export")
        assert resp.status_code == 401

    def test_floorplan_upload_requires_auth(self, client):
        resp = client.post("/api/floorplan/upload")
        assert resp.status_code == 401

    def test_authenticated_client_can_reach_heatmap_data(self, admin_client):
        resp = admin_client.get("/api/admin/heatmap-data")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "points" in data
        assert "count"  in data


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
             "stress_level": 4, "floor_x": 0.3, "floor_y": 0.7},
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
# Heatmap data
# ---------------------------------------------------------------------------

class TestHeatmapData:

    def _seed_with_coords(self, client):
        batch = [
            {"department": "it", "timestamp": "2024-09-01T10:00:00",
             "stress_level": 3, "floor_x": 0.2, "floor_y": 0.8},
            {"department": "it", "timestamp": "2024-09-01T11:00:00",
             "stress_level": 5, "floor_x": 0.6, "floor_y": 0.4},
            {"department": "finance", "timestamp": "2024-09-01T12:00:00",
             "stress_level": 1},  # no location — should NOT appear in heatmap
        ]
        client.post(
            "/api/submit",
            data=json.dumps(batch),
            content_type="application/json",
        )

    def test_heatmap_returns_only_located_entries(self, admin_client):
        self._seed_with_coords(admin_client)
        resp = admin_client.get("/api/admin/heatmap-data")
        assert resp.status_code == 200
        data = resp.get_json()
        for point in data["points"]:
            # Every returned point must have valid coordinates
            assert 0.0 <= point["x"] <= 1.0
            assert 0.0 <= point["y"] <= 1.0
            assert 0.0 <= point["intensity"] <= 1.0

    def test_heatmap_filters_by_department(self, admin_client):
        self._seed_with_coords(admin_client)
        resp = admin_client.get("/api/admin/heatmap-data?department=finance")
        data = resp.get_json()
        # The `app` fixture is session-scoped, so unrelated entries from other
        # tests may already exist for "finance" — assert only that the it-department
        # points just seeded above do not leak into a finance-filtered query.
        it_seeded_points = {(0.2, 0.8), (0.6, 0.4)}
        returned_points = {(p["x"], p["y"]) for p in data["points"]}
        assert not (it_seeded_points & returned_points)

    def test_heatmap_intensity_normalised(self, admin_client):
        self._seed_with_coords(admin_client)
        resp = admin_client.get("/api/admin/heatmap-data")
        for point in resp.get_json()["points"]:
            assert point["intensity"] <= 1.0, "Intensity must be normalised to 0–1"
            assert point["intensity"] >  0.0, "Intensity must be > 0 for real entries"


# ---------------------------------------------------------------------------
# floorplan.enabled must gate the feature end-to-end, not just hide the flag
# ---------------------------------------------------------------------------

class TestFloorplanToggle:
    """
    Each route that touches floor plans checks is_floorplan_enabled()
    independently, so there's no single place the check can be missed.
    The default in the shipped config.yaml/example is False -- these tests
    verify the disabled path directly by patching the flag off, since the
    test fixture config itself has it on (so the *other* floorplan/heatmap
    tests can exercise the feature normally).
    """

    def test_get_floorplan_404_when_disabled(self, client, monkeypatch):
        import server.api.floorplan as floorplan_mod
        monkeypatch.setattr(floorplan_mod, "is_floorplan_enabled", lambda: False)
        resp = client.get("/api/floorplan")
        assert resp.status_code == 404

    def test_floorplan_upload_404_when_disabled_even_for_admin(self, admin_client, monkeypatch):
        import server.api.floorplan as floorplan_mod
        monkeypatch.setattr(floorplan_mod, "is_floorplan_enabled", lambda: False)
        resp = admin_client.post("/api/floorplan/upload")
        assert resp.status_code == 404

    def test_heatmap_page_404_when_disabled(self, admin_client, monkeypatch):
        import server.dashboard.routes as routes_mod
        monkeypatch.setattr(routes_mod, "is_floorplan_enabled", lambda: False)
        resp = admin_client.get("/admin/heatmap")
        assert resp.status_code == 404

    def test_heatmap_data_404_when_disabled(self, admin_client, monkeypatch):
        import server.dashboard.routes as routes_mod
        monkeypatch.setattr(routes_mod, "is_floorplan_enabled", lambda: False)
        resp = admin_client.get("/api/admin/heatmap-data")
        assert resp.status_code == 404

    def test_nav_link_hidden_when_disabled(self, admin_client, monkeypatch):
        import server.config as config_mod
        monkeypatch.setattr(config_mod, "is_floorplan_enabled", lambda: False)
        resp = admin_client.get("/admin/")
        assert b"Floor Plan" not in resp.data

    def test_nav_link_present_when_enabled(self, admin_client):
        """Sanity check the flag's default (enabled, per the test fixture)."""
        resp = admin_client.get("/admin/")
        assert b"Floor Plan" in resp.data


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
