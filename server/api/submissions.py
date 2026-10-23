"""
server/api/submissions.py
-------------------------
POST /api/submit — receives anonymised batch submissions from clients.

ANONYMISATION VERIFICATION POINT:
This endpoint accepts only the fields in shared.constants.SUBMISSION_FIELDS.
Any field not in that list is silently ignored. This is enforced by _extract_entry().
"""

from datetime import datetime
from flask import Blueprint, request, jsonify
from server.config import get_department_ids, get_reason_ids
from server.models import db as db_module
from server.models.db import Entry

bp = Blueprint("submissions", __name__)

# The canonical set of accepted fields — matches shared/constants.py SUBMISSION_FIELDS
# elaboration is deliberately NOT here: free text never crosses this boundary,
# even if a client sends it. See shared/constants.py for why.
_ACCEPTED_FIELDS = {"department", "timestamp", "stress_level",
                    "reason_category", "floor_x", "floor_y"}


def _extract_entry(raw: dict,
                   valid_departments: set[str] | None = None,
                   valid_reasons: set[str] | None = None) -> dict | None:
    """
    Extract only anonymisation-safe fields from a raw submission dict.
    Any field not in _ACCEPTED_FIELDS is dropped here.
    Returns None if required fields are missing or invalid.

    valid_departments / valid_reasons come from config.yaml (passed in by the
    route, so this stays a pure function the privacy audit can call without a
    config file). An unknown department rejects the entry; an unknown reason
    is just dropped, since reason is optional.
    """
    if not isinstance(raw, dict):
        return None

    dept = raw.get("department")
    if not isinstance(dept, str) or not dept.strip():
        return None
    dept = dept.strip()
    if valid_departments is not None and dept not in valid_departments:
        return None

    reason = raw.get("reason_category")
    if not isinstance(reason, str) or not reason:
        reason = None
    elif valid_reasons is not None and reason not in valid_reasons:
        reason = None

    try:
        ts = datetime.fromisoformat(raw["timestamp"])
    except (KeyError, ValueError):
        return None

    raw_level = raw.get("stress_level", 0)
    if isinstance(raw_level, bool) or isinstance(raw_level, float):
        return None
    try:
        level = int(raw_level)
        if level not in range(1, 6):
            return None
    except (TypeError, ValueError):
        return None

    floor_x = floor_y = None
    try:
        if raw.get("floor_x") is not None and raw.get("floor_y") is not None:
            fx, fy = float(raw["floor_x"]), float(raw["floor_y"])
            if 0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0:
                floor_x, floor_y = fx, fy
    except (TypeError, ValueError):
        pass  # Invalid coords — treat as no location

    return {
        "department":      dept,
        "timestamp":       ts,
        "stress_level":    level,
        "reason_category": reason,
        "floor_x":         floor_x,
        "floor_y":         floor_y,
    }


@bp.route("/api/submit", methods=["POST"])
def submit():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    # Accept a single entry or a batch (list)
    raw_entries = data if isinstance(data, list) else [data]

    if len(raw_entries) > 500:
        return jsonify({"error": "Batch too large (max 500 entries)"}), 400

    saved = 0
    errors = 0
    valid_departments = get_department_ids()
    valid_reasons = get_reason_ids()

    session = db_module.SessionLocal()
    try:
        for raw in raw_entries:
            extracted = _extract_entry(raw, valid_departments, valid_reasons)
            if extracted is None:
                errors += 1
                continue
            session.add(Entry(**extracted))
            saved += 1
        session.commit()
    except Exception as e:
        session.rollback()
        return jsonify({"error": "Database error", "detail": str(e)}), 500
    finally:
        session.close()

    return jsonify({"saved": saved, "errors": errors}), 200
