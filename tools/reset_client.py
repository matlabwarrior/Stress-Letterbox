#!/usr/bin/env python3
"""
tools/reset_client.py
---------------------
IT admin utility: reset a user's local letterbox when they have
forgotten their PIN and cannot access their entries.

IMPORTANT PRIVACY NOTE:
This tool resets the PIN and session — it does NOT read, copy, or expose
any entry content. It is the equivalent of breaking the lock on a safe
and replacing it with a new one. The contents are preserved but
immediately re-protected by a new PIN set by the user.

Usage:
    python tools/reset_client.py [--db PATH]

    --db PATH   Path to the user's letterbox.db file.
                If omitted, the tool looks in the default OS location.

What this does:
    1. Clears the PIN hash (removes old lock)
    2. Clears the session token (forces re-login)
    3. Does NOT touch entries, department, or any other setting

After running this tool, the user should:
    1. Launch the client application
    2. They will be prompted to create a new PIN (first-launch flow re-triggers)
    3. Their entries and department are preserved

What this does NOT do:
    - Read any entry content
    - Change the department setting
    - Delete any entries
    - Connect to the server
"""

import argparse
import os
import sqlite3
import sys
import getpass


def find_default_db() -> str | None:
    """Locate the default letterbox.db for the current OS user."""
    try:
        from appdirs import user_data_dir
        path = os.path.join(user_data_dir("StressLetterbox", "YourOrg"), "letterbox.db")
        return path if os.path.exists(path) else None
    except ImportError:
        # appdirs not available — try common locations
        home = os.path.expanduser("~")
        candidates = [
            # Linux
            os.path.join(home, ".local", "share", "StressLetterbox", "letterbox.db"),
            # Windows (APPDATA)
            os.path.join(os.environ.get("APPDATA", ""), "YourOrg", "StressLetterbox", "letterbox.db"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None


def reset_pin(db_path: str) -> None:
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at: {db_path}")
        print("Use --db to specify the correct path.")
        sys.exit(1)

    print("=" * 60)
    print("  Stress Letterbox — PIN Reset Utility")
    print("=" * 60)
    print()
    print(f"Database: {db_path}")
    print()

    # Confirm with the admin
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Show current state without exposing any entry content
        settings = dict(conn.execute(
            "SELECT key, value FROM settings"
        ).fetchall() or [])

        dept = settings.get("department", "(not set)")
        has_pin = "pin_hash" in settings and settings["pin_hash"]
        has_session = "session_token" in settings and settings["session_token"]

        entry_count = conn.execute(
            "SELECT COUNT(*) FROM entries WHERE submitted = 0"
        ).fetchone()[0]

        submitted_count = conn.execute(
            "SELECT COUNT(*) FROM entries WHERE submitted = 1"
        ).fetchone()[0]

        print(f"Department:         {dept}")
        print(f"PIN set:            {'Yes' if has_pin else 'No'}")
        print(f"Session active:     {'Yes' if has_session else 'No'}")
        print(f"Pending entries:    {entry_count}  (will be preserved)")
        print(f"Submitted entries:  {submitted_count}  (will be preserved)")
        print()
        print("This will clear the PIN and session token.")
        print("All entries will be preserved.")
        print()
    finally:
        conn.close()

    confirm = input("Proceed with PIN reset? [yes/no]: ").strip().lower()
    if confirm != "yes":
        print("Aborted.")
        sys.exit(0)

    # Perform the reset
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM settings WHERE key = 'pin_hash'")
        conn.execute("DELETE FROM settings WHERE key = 'session_token'")
        conn.commit()
        print()
        print("PIN and session cleared successfully.")
        print()
        print("Next steps for the user:")
        print("  1. Launch the Stress Letterbox application")
        print("  2. They will be prompted to create a new PIN")
        print("  3. Their entries and department setting are intact")
        print()
        print("Note: The user should set their new PIN themselves.")
        print("Do not set a PIN on their behalf.")
    except Exception as e:
        conn.rollback()
        print(f"ERROR during reset: {e}")
        sys.exit(1)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Reset a user's Stress Letterbox PIN (IT admin tool)"
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        help="Path to the user's letterbox.db. If omitted, uses the default OS location.",
    )
    args = parser.parse_args()

    db_path = args.db
    if not db_path:
        db_path = find_default_db()
        if not db_path:
            print("Could not locate letterbox.db automatically.")
            print("Specify the path with: --db /path/to/letterbox.db")
            print()
            print("Common locations:")
            print("  Linux:   ~/.local/share/StressLetterbox/letterbox.db")
            print("  Windows: %APPDATA%\\YourOrg\\StressLetterbox\\letterbox.db")
            sys.exit(1)

    reset_pin(db_path)


if __name__ == "__main__":
    main()
