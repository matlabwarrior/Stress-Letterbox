"""
server/dashboard/routes.py
--------------------------
Admin dashboard routes.
All routes require admin authentication.
"""

import csv
import json
import io
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, make_response
from sqlalchemy import func
from server.models import db as db_module
from server.models.db import Entry, utcnow_naive
from server.config import (
    get_departments, get_reason_categories, get_solution_categories
)
from server.dashboard.auth import require_admin, require_admin_api

bp = Blueprint("dashboard", __name__)


def _build_filters(session, args: dict):
    """Build SQLAlchemy filter conditions from request args."""
    conditions = []
    if dept := args.get("department"):
        conditions.append(Entry.department == dept)
    if level := args.get("stress_level"):
        try:
            conditions.append(Entry.stress_level == int(level))
        except ValueError:
            pass
    if cat := args.get("reason_category"):
        conditions.append(Entry.reason_category == cat)
    if sol := args.get("solution_category"):
        conditions.append(Entry.solution_category == sol)
    if date_from := args.get("date_from"):
        try:
            conditions.append(Entry.timestamp >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to := args.get("date_to"):
        try:
            conditions.append(Entry.timestamp <= datetime.fromisoformat(date_to))
        except ValueError:
            pass
    return conditions


@bp.route("/admin")
@bp.route("/admin/")
@require_admin
def overview():
    db = db_module.SessionLocal()
    try:
        departments = get_departments()
        # The filter form above the charts narrows every figure on the page
        conditions = _build_filters(db, request.args)

        # Total counts
        total = db.query(func.count(Entry.id)).filter(*conditions).scalar()

        # By department
        by_dept = dict(
            db.query(Entry.department, func.count(Entry.id))
            .filter(*conditions)
            .group_by(Entry.department).all()
        )

        # By stress level
        by_level = dict(
            db.query(Entry.stress_level, func.count(Entry.id))
            .filter(*conditions)
            .group_by(Entry.stress_level).all()
        )

        # By reason category
        by_reason = dict(
            db.query(Entry.reason_category, func.count(Entry.id))
            .filter(*conditions, Entry.reason_category.isnot(None))
            .group_by(Entry.reason_category).all()
        )

        # By suggested solution
        by_solution = dict(
            db.query(Entry.solution_category, func.count(Entry.id))
            .filter(*conditions, Entry.solution_category.isnot(None))
            .group_by(Entry.solution_category).all()
        )

        # Trend: entries per day for last 30 days
        thirty_days_ago = utcnow_naive() - timedelta(days=30)
        trend_rows = (
            db.query(
                func.date(Entry.timestamp).label("day"),
                func.count(Entry.id).label("count")
            )
            .filter(*conditions, Entry.timestamp >= thirty_days_ago)
            .group_by(func.date(Entry.timestamp))
            .order_by(func.date(Entry.timestamp))
            .all()
        )
        trend = [{"day": r.day, "count": r.count} for r in trend_rows]

        # Average stress level overall and per dept
        avg_overall = (db.query(func.avg(Entry.stress_level))
                       .filter(*conditions).scalar())
        avg_by_dept = dict(
            db.query(Entry.department, func.avg(Entry.stress_level))
            .filter(*conditions)
            .group_by(Entry.department).all()
        )

        return render_template(
            "dashboard.html",
            total=total,
            departments=departments,
            by_dept=by_dept,
            by_level=by_level,
            by_reason=by_reason,
            by_solution=by_solution,
            trend=json.dumps(trend),
            avg_overall=round(avg_overall or 0, 2),
            avg_by_dept={k: round(v, 2) for k, v in avg_by_dept.items()},
            reason_categories=get_reason_categories(),
            solution_categories=get_solution_categories(),
        )
    finally:
        db.close()


@bp.route("/api/admin/entries")
@require_admin_api
def entries_api():
    """Paginated, filtered entries for the admin table view."""
    db = db_module.SessionLocal()
    try:
        conditions = _build_filters(db, request.args)
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(200, int(request.args.get("per_page", 50)))

        q = db.query(Entry).filter(*conditions).order_by(Entry.timestamp.desc())
        total = q.count()
        entries = q.offset((page - 1) * per_page).limit(per_page).all()

        return jsonify({
            "total": total,
            "page": page,
            "per_page": per_page,
            "entries": [e.to_dict() for e in entries],
        }), 200
    finally:
        db.close()


@bp.route("/api/admin/export")
@require_admin_api
def export():
    """Export filtered entries as CSV or JSON."""
    fmt = request.args.get("format", "csv").lower()
    db = db_module.SessionLocal()
    try:
        conditions = _build_filters(db, request.args)
        entries = db.query(Entry).filter(*conditions)\
                    .order_by(Entry.timestamp.desc()).all()

        if fmt == "json":
            output = json.dumps([e.to_dict() for e in entries], indent=2)
            resp = make_response(output)
            resp.headers["Content-Type"] = "application/json"
            resp.headers["Content-Disposition"] = "attachment; filename=stress_export.json"
            return resp

        # CSV default
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=[
            "id", "department", "timestamp", "stress_level",
            "reason_category", "solution_category"
        ])
        writer.writeheader()
        for e in entries:
            writer.writerow(e.to_dict())
        resp = make_response(buf.getvalue())
        resp.headers["Content-Type"] = "text/csv"
        resp.headers["Content-Disposition"] = "attachment; filename=stress_export.csv"
        return resp
    finally:
        db.close()


@bp.route("/api/admin/reload-config", methods=["POST"])
@require_admin_api
def reload_config_route():
    """Reload config.yaml without restarting the server."""
    from server.config import reload_config
    reload_config()
    return jsonify({"status": "reloaded"}), 200


@bp.route("/admin/entries")
@require_admin
def entries_page():
    """Paginated, filterable entries table — full admin view."""
    return render_template(
        "entries.html",
        departments=get_departments(),
        reason_categories=get_reason_categories(),
        solution_categories=get_solution_categories(),
    )
