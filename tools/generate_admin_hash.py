#!/usr/bin/env python3
"""
tools/generate_admin_hash.py
-----------------------------
Utility to generate a bcrypt password hash for the admin account.

Usage:
    python tools/generate_admin_hash.py

Then paste the output into config.yaml under admin.password_hash.

This script is intentionally simple — it's a one-time setup helper.
"""

import getpass
import sys

try:
    import bcrypt
except ImportError:
    print("bcrypt not installed. Run: pip install bcrypt")
    sys.exit(1)


def main():
    print("=" * 55)
    print("  Stress Letterbox — Admin Password Hash Generator")
    print("=" * 55)
    print()
    print("This will generate a bcrypt hash for your admin password.")
    print("The hash is safe to store in config.yaml.")
    print()

    while True:
        password = getpass.getpass("Enter admin password: ")
        if len(password) < 8:
            print("⚠  Password must be at least 8 characters. Try again.\n")
            continue
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("⚠  Passwords do not match. Try again.\n")
            continue
        break

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    print()
    print("=" * 55)
    print("Add this to config.yaml under admin.password_hash:")
    print()
    print(f"  password_hash: \"{hashed}\"")
    print()
    print("=" * 55)
    print("Keep config.yaml out of version control (.gitignored).")


if __name__ == "__main__":
    main()
