"""
server/api/departments.py
-------------------------
GET /api/departments — serves the department list to clients.
GET /api/config      — serves client configuration (reminder frequency, reason categories, etc.)
"""

from flask import Blueprint, jsonify
from server.config import get_departments, get_reason_categories, load_config

bp = Blueprint("departments", __name__)


@bp.route("/api/departments", methods=["GET"])
def departments():
    return jsonify(get_departments()), 200


@bp.route("/api/config", methods=["GET"])
def client_config():
    """
    Returns client-relevant configuration.
    Does NOT expose admin credentials, secret key, or database path.
    """
    cfg = load_config()
    return jsonify({
        "departments":       get_departments(),
        "reason_categories": get_reason_categories(),
        "reminder_frequency": cfg["client"].get("reminder_frequency", "weekly"),
        "entry_char_limit":   cfg["client"].get("entry_char_limit", 280),
    }), 200
