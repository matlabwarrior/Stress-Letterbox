"""
server/config.py
----------------
Loads and validates config.yaml.
All admin-configurable settings are accessed through this module.
"""

import os
import yaml
from functools import lru_cache

CONFIG_PATH = os.environ.get(
    "LETTERBOX_CONFIG",
    os.path.join(os.path.dirname(__file__), "..", "config.yaml")
)


@lru_cache(maxsize=1)
def load_config() -> dict:
    path = os.path.abspath(CONFIG_PATH)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"config.yaml not found at {path}. "
            "Copy config.yaml.example and edit it before starting the server."
        )
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)
    _validate(cfg)
    return cfg


def _validate(cfg: dict):
    required = ["server", "admin", "departments", "reason_categories", "client", "database"]
    for key in required:
        if key not in cfg:
            raise ValueError(f"config.yaml is missing required section: '{key}'")
    if cfg["admin"].get("password_hash", "").startswith("$2b$12$PLACEHOLDER"):
        import warnings
        warnings.warn(
            "⚠️  Admin password is still set to the placeholder. "
            "Generate a real bcrypt hash and update config.yaml before deployment.",
            stacklevel=3
        )


def get_departments() -> list[dict]:
    """Return active departments as a list of {id, name} dicts."""
    return [
        {"id": d["id"], "name": d["name"]}
        for d in load_config()["departments"]
        if d.get("active", True)
    ]


def get_reason_categories() -> list[dict]:
    return load_config()["reason_categories"]


def get_department_ids() -> set[str]:
    """
    Every configured department id, including inactive ones. Submissions are
    validated against this, not just active departments: someone in a retired
    department may still have unsent entries, and those shouldn't be dropped.
    """
    return {d["id"] for d in load_config()["departments"]}


def get_reason_ids() -> set[str]:
    return {r["id"] for r in load_config()["reason_categories"]}


def is_floorplan_enabled() -> bool:
    """
    Single source of truth for whether the floor plan / location-tagging
    feature is turned on. Checked independently by every route that touches
    it (client-facing, admin-facing, and the heatmap dashboard) so there's
    no single place a check can be forgotten.
    """
    return bool(load_config().get("floorplan", {}).get("enabled", True))


def reload_config():
    """Force a config reload (e.g. after admin edits config.yaml)."""
    load_config.cache_clear()
    return load_config()
