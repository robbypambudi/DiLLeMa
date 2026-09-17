"""ASGI entrypoint: uvicorn app.main:app."""

from app.application import create_app

app = create_app()
