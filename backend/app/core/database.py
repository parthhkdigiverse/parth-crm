# backend/app/core/database.py
"""
Legacy Database Module.
The project has migrated to MongoDB (using Beanie).
This file is kept only for backward compatibility where imports might still exist,
but all PostgreSQL/SQLAlchemy logic has been removed.
"""

def init_db():
    """Reserved for future use or legacy sync."""
    pass

def get_db():
    """Stub for legacy dependencies."""
    yield None
