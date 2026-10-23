"""
client/api/client.py
--------------------
Re-exports ServerClient from submit.py so that either import path works:

  from client.api.client import ServerClient
  from client.api.submit import ServerClient

The actual implementation and the anonymisation boundary live in submit.py.
This module exists only for import path consistency with the documented
folder structure.
"""

from client.api.submit import ServerClient  # noqa: F401 — re-export

__all__ = ["ServerClient"]
