# conftest.py
# -----------
# Root pytest configuration.
# Ensures the project root is on sys.path so that `client`, `server`,
# and `shared` are importable without installation.
#
# This file is auto-discovered by pytest when run from the project root:
#   pytest tests/

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
