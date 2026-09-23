"""
Local dev entry point — re-exports the production app so the API contract
has a single source of truth in api/main.py.

Run: uvicorn app.main:app --reload
"""

from api.main import app  # noqa: F401
