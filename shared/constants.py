"""
shared/constants.py
-------------------
Field definitions shared between client and server.
These define the exact fields that cross the anonymisation boundary.

ANONYMISATION GUARANTEE:
The SUBMISSION_FIELDS tuple is the canonical definition of what is
transmitted from client to server. It contains NO user-identifying fields.
Any code review for privacy compliance should start here.

DESCRIPTION AND ELABORATION STAY LOCAL:
The local client database stores two free-text fields — `description` (the
user's raw quick-log note) and `elaboration` (optional added context from
the letterbox review step). Neither crosses the anonymisation boundary.
Free text is exactly the kind of thing that can re-identify someone or be
read out of context by whoever has dashboard access, so it never leaves
the device, full stop -- not behind a config flag, not for any deployment.
Only the structured, categorical fields below are ever transmitted.

To add a field to the submission payload, you must update ALL of:
  1. This tuple
  2. server/api/submissions.py  _ACCEPTED_FIELDS
  3. server/models/db.py        Entry model
  4. client/api/submit.py       _build_payload()
This four-point checklist is intentional friction against accidental
identity field leakage.
"""

# ── Fields transmitted at submission (anonymisation boundary) ──────────────
# This is the complete and exhaustive list. Nothing else is ever sent.
SUBMISSION_FIELDS = (
    "department",       # str   -- coarse org unit, admin-defined
    "timestamp",        # str   -- ISO 8601, auto-generated, not user-editable
    "stress_level",     # int   -- 1-5 scale
    "reason_category",  # str   -- from admin-defined list, nullable
    "floor_x",          # float -- 0.0-1.0 relative to floorplan width, nullable
    "floor_y",          # float -- 0.0-1.0 relative to floorplan height, nullable
)

# ── Stress level definitions ───────────────────────────────────────────────
STRESS_LEVELS = {
    1: "Low",
    2: "Mild",
    3: "Moderate",
    4: "High",
    5: "Intense",
}

# ── API endpoints ──────────────────────────────────────────────────────────
API_SUBMIT      = "/api/submit"
API_DEPARTMENTS = "/api/departments"
API_FLOORPLAN   = "/api/floorplan"
API_CONFIG      = "/api/config"

# ── Local storage ─────────────────────────────────────────────────────────
APP_NAME   = "StressLetterbox"
APP_AUTHOR = "YourOrg"
DB_FILENAME = "letterbox.db"
