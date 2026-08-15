"""ASGI entrypoint: ``uvicorn app.asgi:app``. Reads real settings from the
environment (``get_settings()``) — the deployed process, not a test's
``create_app(Settings(...))`` with an explicit, isolated configuration.
"""

from __future__ import annotations

from app.bootstrap.app import create_app

app = create_app()
