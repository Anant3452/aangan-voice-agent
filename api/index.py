"""Vercel entry point: every request is routed here (see vercel.json) and handled by the FastAPI app."""
from app.main import app  # noqa: F401
