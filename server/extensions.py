"""
server/extensions.py
---------------------
Shared Flask extension instances, defined here (not in app.py) so that
blueprint modules can import and use them without a circular import back
to app.py. Call `.init_app(app)` on each from `create_app()`.
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# In-memory storage by default — correct for a single worker process.
# If this is ever scaled to multiple gunicorn workers, point storage_uri
# at a shared backend (e.g. Redis), or the per-worker counters won't agree.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per hour"],
    storage_uri="memory://",
)
