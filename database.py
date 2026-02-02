"""Compatibility shim for competition scrapers."""
from app.database import SessionLocal  # re-export for competition scripts

__all__ = ["SessionLocal"]
