"""
server/dashboard/auth.py
------------------------
Admin authentication for the dashboard.
Only one admin account exists (configured in config.yaml).
There are no user-facing accounts on the server.
"""

import hmac
import secrets
from functools import wraps

import bcrypt
from flask import (
    Blueprint, render_template, request, session, redirect, url_for, flash, jsonify
)
from server.config import load_config
from server.extensions import limiter

bp = Blueprint("auth", __name__)


def _csrf_token() -> str:
    """Per-session token embedded in the login form and checked on POST."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def _csrf_valid() -> bool:
    sent = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    return bool(expected) and hmac.compare_digest(sent, expected)


def _password_matches(password: bytes, stored_hash: str) -> bool:
    # A placeholder or malformed hash in config.yaml makes bcrypt raise;
    # treat that as a failed login rather than a 500.
    try:
        return bcrypt.checkpw(password, stored_hash.encode("utf-8"))
    except ValueError:
        return False


def require_admin(f):
    """Guards HTML admin pages — redirects to the login page when unauthenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def require_admin_api(f):
    """Guards JSON /api/admin/* endpoints — returns 401 instead of an HTML redirect."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return jsonify({"error": "Unauthorised"}), 401
        return f(*args, **kwargs)
    return decorated


@bp.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if request.method == "POST":
        if not _csrf_valid():
            flash("Your login form expired. Please try again.")
            return render_template("login.html", csrf_token=_csrf_token()), 400

        cfg = load_config()
        username = request.form.get("username", "")
        password = request.form.get("password", "").encode("utf-8")

        if (username == cfg["admin"]["username"] and
                _password_matches(password, cfg["admin"]["password_hash"])):
            # Fresh session on login, so a pre-login session id can't be reused.
            session.clear()
            session["admin_logged_in"] = True
            session.permanent = True
            return redirect(url_for("dashboard.overview"))
        flash("Invalid credentials.")
    return render_template("login.html", csrf_token=_csrf_token())


@bp.route("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
