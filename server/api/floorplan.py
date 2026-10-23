"""
server/api/floorplan.py
-----------------------
GET  /api/floorplan        — serves the active floor plan image to clients
POST /api/floorplan/upload — admin uploads a new floor plan (requires admin session)
GET  /api/floorplan/list   — list all floor plans (admin only)
POST /api/floorplan/activate/<id> — set active floor plan (admin only)
"""

import os
from flask import Blueprint, jsonify, send_file, request, session, current_app
from werkzeug.utils import secure_filename
from server.config import is_floorplan_enabled
from server.models import db as db_module
from server.models.db import FloorPlan

bp = Blueprint("floorplan", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "svg"}
FLOORPLAN_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "floorplans")


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _require_admin():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorised"}), 401
    return None


def _require_enabled():
    """404, not 403 -- when disabled, this feature doesn't exist for this deployment."""
    if not is_floorplan_enabled():
        return jsonify({"error": "Floor plan feature is disabled"}), 404
    return None


@bp.route("/api/floorplan", methods=["GET"])
def get_floorplan():
    """Serve the active floor plan image to clients."""
    err = _require_enabled()
    if err:
        return err
    db = db_module.SessionLocal()
    try:
        fp = db.query(FloorPlan).filter_by(is_active=True).first()
        if not fp:
            return jsonify({"error": "No active floor plan"}), 404
        path = os.path.join(FLOORPLAN_DIR, fp.filename)
        if not os.path.exists(path):
            return jsonify({"error": "Floor plan file not found on server"}), 404
        return send_file(path)
    finally:
        db.close()


@bp.route("/api/floorplan/upload", methods=["POST"])
def upload_floorplan():
    """Admin: upload a new floor plan image."""
    err = _require_enabled() or _require_admin()
    if err:
        return err

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    label = request.form.get("label", "").strip() or "Floor Plan"

    if not _allowed(file.filename):
        return jsonify({"error": "Invalid file type. Use PNG, JPG, or SVG."}), 400

    os.makedirs(FLOORPLAN_DIR, exist_ok=True)
    filename = secure_filename(file.filename)
    # Prevent overwrite collisions
    base, ext = os.path.splitext(filename)
    import time
    filename = f"{base}_{int(time.time())}{ext}"
    file.save(os.path.join(FLOORPLAN_DIR, filename))

    db = db_module.SessionLocal()
    try:
        # Deactivate all existing
        db.query(FloorPlan).update({"is_active": False})
        new_fp = FloorPlan(filename=filename, label=label, is_active=True)
        db.add(new_fp)
        db.commit()
        return jsonify({"id": new_fp.id, "label": label, "active": True}), 201
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@bp.route("/api/floorplan/list", methods=["GET"])
def list_floorplans():
    err = _require_enabled() or _require_admin()
    if err:
        return err
    db = db_module.SessionLocal()
    try:
        plans = db.query(FloorPlan).order_by(FloorPlan.uploaded_at.desc()).all()
        return jsonify([
            {"id": p.id, "label": p.label, "filename": p.filename,
             "is_active": p.is_active, "uploaded_at": p.uploaded_at.isoformat()}
            for p in plans
        ]), 200
    finally:
        db.close()


@bp.route("/api/floorplan/activate/<int:fp_id>", methods=["POST"])
def activate_floorplan(fp_id: int):
    err = _require_enabled() or _require_admin()
    if err:
        return err
    db = db_module.SessionLocal()
    try:
        db.query(FloorPlan).update({"is_active": False})
        fp = db.query(FloorPlan).filter_by(id=fp_id).first()
        if not fp:
            return jsonify({"error": "Not found"}), 404
        fp.is_active = True
        db.commit()
        return jsonify({"activated": fp_id}), 200
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
