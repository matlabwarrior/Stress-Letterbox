"""
server/models/db.py
-------------------
SQLAlchemy models for the central server database.

Schema design principles:
- No user identity of any kind is stored.
- The 'entries' table mirrors exactly the SUBMISSION_FIELDS from shared/constants.py.
- Department is stored as a string ID (not FK) to allow dept renaming without data loss.
"""

import os
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    DateTime, Boolean, Text, event
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ---------------------------------------------------------------------------
# Engine setup
# ---------------------------------------------------------------------------

def get_engine(db_path: str):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    # Enable WAL mode for better concurrent read performance
    @event.listens_for(engine, "connect")
    def set_wal(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA journal_mode=WAL")
    return engine


def utcnow_naive() -> datetime:
    """Current UTC time without tzinfo — matches how the DateTime columns store values."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Entries — the core data table
# ANONYMISATION NOTE: This table stores only the fields in SUBMISSION_FIELDS.
# There is no user_id, session_id, ip_address, or any identity column.
# ---------------------------------------------------------------------------
class Entry(Base):
    __tablename__ = "entries"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    department      = Column(String(64), nullable=False, index=True)
    timestamp       = Column(DateTime, nullable=False, index=True)
    stress_level    = Column(Integer, nullable=False)       # 1–5
    reason_category = Column(String(64), nullable=True)
    # Column kept (not migrated away) so this stays a reversible code-level
    # decision, but it is never populated by new submissions (see
    # server/api/submissions.py) and never exposed by to_dict() below --
    # free text does not belong on the admin side of this app.
    elaboration     = Column(Text, nullable=True)
    floor_x         = Column(Float, nullable=True)          # 0.0–1.0
    floor_y         = Column(Float, nullable=True)          # 0.0–1.0
    received_at     = Column(DateTime, default=utcnow_naive, nullable=False)

    def to_dict(self):
        return {
            "id":               self.id,
            "department":       self.department,
            "timestamp":        self.timestamp.isoformat() if self.timestamp else None,
            "stress_level":     self.stress_level,
            "reason_category":  self.reason_category,
            "floor_x":          self.floor_x,
            "floor_y":          self.floor_y,
        }


# ---------------------------------------------------------------------------
# FloorPlan — uploaded by admin
# ---------------------------------------------------------------------------
class FloorPlan(Base):
    __tablename__ = "floorplans"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    filename    = Column(String(256), nullable=False)
    label       = Column(String(128), nullable=True)   # e.g. "Floor 2 — East Wing"
    is_active   = Column(Boolean, default=False)
    uploaded_at = Column(DateTime, default=utcnow_naive)


# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------

_engine = None
SessionLocal = None


def init_db(db_path: str):
    global _engine, SessionLocal
    _engine = get_engine(db_path)
    Base.metadata.create_all(_engine)
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def get_session():
    if SessionLocal is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
