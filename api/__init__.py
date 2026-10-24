"""
Ancient Nerds Map API.

High-performance FastAPI backend for 1.7M+ archaeological site records.

Run with:
    uvicorn api.main:app --reload --port 8000
"""

from api.main import app

__version__ = "1.0.0"

__all__ = ["app"]
