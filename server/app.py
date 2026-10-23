"""
server/app.py
-------------
Flask application entry point.
Run with: python server/app.py
"""

import os
import sys
import json

# Ensure project root is on path when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import timedelta
from flask import Flask, request
from markupsafe import Markup
from server import config as config_module
from server.extensions import limiter
from server.models.db import init_db
from server.api.submissions import bp as submissions_bp
from server.api.departments import bp as departments_bp
from server.api.floorplan import bp as floorplan_bp
from server.dashboard.auth import bp as auth_bp
from server.dashboard.routes import bp as dashboard_bp


def create_app() -> Flask:
    cfg = config_module.load_config()

    app = Flask(
        __name__,
        template_folder="dashboard/templates",
        static_folder="dashboard/static",
        static_url_path="/static",
    )

    app.config["SECRET_KEY"] = cfg["server"]["secret_key"]
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
    # Browsers won't attach the admin session cookie to POSTs from other
    # sites, which covers every state-changing admin endpoint, not just login.
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

    limiter.init_app(app)

    # Initialise database
    db_path = os.path.abspath(cfg["database"]["path"])
    init_db(db_path)

    # ── Jinja2 filters ─────────────────────────────────────
    @app.template_filter("tojson")
    def tojson_filter(value):
        """JSON serialisation safe for embedding inside a <script> tag.

        Jinja autoescapes filter output by default, which would otherwise
        HTML-entity-escape the JSON's quotes/ampersands (`"` -> `&#34;`) and
        break the embedded JavaScript. Escape the handful of characters that
        matter for script-context safety ourselves (JS unicode escapes, not
        HTML entities) and mark the result safe so autoescaping leaves it alone.
        """
        dumped = json.dumps(value, default=str)
        dumped = (
            dumped.replace("<", "\\u003c")
                  .replace(">", "\\u003e")
                  .replace("&", "\\u0026")
                  .replace("'", "\\u0027")
        )
        return Markup(dumped)

    # ── Template globals ───────────────────────────────────
    @app.context_processor
    def inject_request():
        """Make `request` available in all templates."""
        return {"request": request}

    @app.context_processor
    def inject_floorplan_flag():
        """So base.html can hide the Floor Plan nav link when it's disabled."""
        return {"floorplan_enabled": config_module.is_floorplan_enabled()}

    # Register blueprints
    app.register_blueprint(submissions_bp)
    app.register_blueprint(departments_bp)
    app.register_blueprint(floorplan_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)

    # Redirect root to admin
    @app.route("/")
    def root():
        from flask import redirect, url_for
        return redirect(url_for("auth.login"))

    return app


def main():
    cfg = config_module.load_config()
    app = create_app()
    app.run(
        host=cfg["server"]["host"],
        port=cfg["server"]["port"],
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )


if __name__ == "__main__":
    main()
