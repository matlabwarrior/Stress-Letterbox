"""
client/api/submit.py
--------------------
Server communication and submission payload builder.

╔══════════════════════════════════════════════════════════════════╗
║  ANONYMISATION BOUNDARY                                         ║
║                                                                  ║
║  _build_payload() is the SOLE function that constructs data     ║
║  for transmission to the server. Code review for privacy        ║
║  compliance should focus on this function.                      ║
║                                                                  ║
║  It reads from: entries (local SQLite rows)                     ║
║  It outputs:    a list of dicts containing ONLY these fields:   ║
║    - department, timestamp, stress_level, reason_category,      ║
║      floor_x, floor_y                                          ║
║                                                                  ║
║  It NEVER reads: id, pin_hash, session_token, machine name,     ║
║  IP address, username, description, elaboration, or any other   ║
║  identifying or free-text field.                                ║
╚══════════════════════════════════════════════════════════════════╝
"""

import requests
from shared.constants import SUBMISSION_FIELDS, API_SUBMIT, API_DEPARTMENTS, API_CONFIG, API_FLOORPLAN


def _build_payload(entries: list[dict]) -> list[dict]:
    """
    Build the anonymised submission payload.

    Explicitly constructs each dict by field name.
    This is intentional: adding a new field here requires a conscious decision,
    not an accidental dict spread.
    """
    return [
        {
            "department":      entry["department"],
            "timestamp":       entry["timestamp"],
            "stress_level":    entry["stress_level"],
            "reason_category": entry.get("reason_category"),
            "floor_x":         entry.get("floor_x"),
            "floor_y":         entry.get("floor_y"),
        }
        for entry in entries
    ]


class ServerClient:
    def __init__(self, server_url: str, timeout: int = 10):
        self.base = server_url.rstrip("/")
        self.timeout = timeout

    def submit_entries(self, entries: list[dict]) -> tuple[bool, str]:
        """
        Submit a batch of entries to the central server.
        Returns (success: bool, message: str).
        """
        if not entries:
            return False, "No entries to submit."

        payload = _build_payload(entries)

        try:
            resp = requests.post(
                self.base + API_SUBMIT,
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                return True, f"Submitted {data.get('saved', 0)} entries."
            else:
                return False, f"Server error {resp.status_code}: {resp.text[:120]}"
        except requests.ConnectionError:
            return False, "Could not reach the server. Check your network connection."
        except requests.Timeout:
            return False, "Request timed out. The server may be busy."
        except Exception as e:
            return False, f"Unexpected error: {e}"

    def fetch_config(self) -> dict | None:
        """Fetch departments, reason categories, and client config from server."""
        try:
            resp = requests.get(self.base + API_CONFIG, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def fetch_floorplan(self) -> bytes | None:
        """Fetch the active floor plan image bytes."""
        try:
            resp = requests.get(self.base + API_FLOORPLAN, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.content
        except Exception:
            pass
        return None

    def health_check(self) -> bool:
        """Quick connectivity check."""
        try:
            resp = requests.get(self.base + API_DEPARTMENTS, timeout=5)
            return resp.status_code == 200
        except Exception:
            return False
