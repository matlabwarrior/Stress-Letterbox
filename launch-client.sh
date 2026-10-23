#!/usr/bin/env bash
# ============================================================
# Stress Letterbox — Linux Client Launcher
# ============================================================
# Make executable: chmod +x launch-client.sh
# For autostart on login, add this script to your desktop
# environment's autostart (see docs/deployment.md).
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv if present
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "Warning: No venv found. Using system Python."
    echo "Run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements-client.txt"
fi

# Launch client (detached so the terminal can close)
nohup python client/main.py >/dev/null 2>&1 &
echo "Stress Letterbox started (PID $!)"
