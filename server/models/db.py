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
    create_engine, Column, Integer, String,
    DateTime, Text, event, inspect, text
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
    solution_category = Column(String(64), nullable=True)  # suggested fix, optional
    # Column kept (not migrated away) so this stays a reversible code-level
    # decision, but it is never populated by new submissions (see
    # server/api/submissions.py) and never exposed by to_dict() below --
    # free text does not belong on the admin side of this app.
    elaboration     = Column(Text, nullable=True)
    received_at     = Column(DateTime, default=utcnow_naive, nullable=False)

    def to_dict(self):
        return {
            "id":               self.id,
            "department":       self.department,
            "timestamp":        self.timestamp.isoformat() if self.timestamp else None,
            "stress_level":     self.stress_level,
            "reason_category":  self.reason_category,
            "solution_category": self.solution_category,
        }


# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------

_engine = None
SessionLocal = None


# Columns added after the first release. create_all() only creates missing
# tables, so a database from an older version gets these via ALTER TABLE.
_LATER_COLUMNS = {
    "entries": {"solution_category": "VARCHAR(64)"},
}


def _add_missing_columns(engine):
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, columns in _LATER_COLUMNS.items():
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, sql_type in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))

        # Floor plan location tagging was removed. Older databases still have
        # the floor_x / floor_y columns; clear any coordinates left in them so
        # no location data outlives the feature.
        entry_columns = {c["name"] for c in insp.get_columns("entries")}
        if {"floor_x", "floor_y"} <= entry_columns:
            conn.execute(text(
                "UPDATE entries SET floor_x = NULL, floor_y = NULL "
                "WHERE floor_x IS NOT NULL OR floor_y IS NOT NULL"
            ))


def init_db(db_path: str):
    global _engine, SessionLocal
    _engine = get_engine(db_path)
    Base.metadata.create_all(_engine)
    _add_missing_columns(_engine)
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def get_session():
    if SessionLocal is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
