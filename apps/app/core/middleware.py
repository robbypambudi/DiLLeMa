"""Compatibility import for endpoint dependency injection.

Keep synchronous endpoints synchronous so FastAPI executes database and model
work in its worker thread pool. Repository context managers own their sessions;
there is no request-level session to close here.
"""

from dependency_injector.wiring import inject

__all__ = ["inject"]
