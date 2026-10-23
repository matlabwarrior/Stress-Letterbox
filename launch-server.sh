#!/usr/bin/env bash
# ============================================================
# Stress Letterbox — Server Launcher (development / manual)
# ============================================================
# For production, use systemd or Docker (see docs/deployment.md).
# This script is for quick manual starts during setup/testing.
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

if [ ! -f "config.yaml" ]; then
    echo "ERROR: config.yaml not found."
    echo "Run: cp config.yaml.example config.yaml"
    echo "Then edit config.yaml with your settings."
    exit 1
fi

echo "Starting Stress Letterbox server..."
echo "Admin dashboard: http://localhost:5000/admin"
echo "Press Ctrl+C to stop."
echo ""

python server/app.py
