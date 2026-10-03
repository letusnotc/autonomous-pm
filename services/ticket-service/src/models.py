"""
models.py – SQLAlchemy ORM for the tickets and ticket_events tables.
Uses canonical string enums so the DB stores human-readable values.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, Integer, SmallInteger
from .database import Base


def _now():
    return datetime.now(timezone.utc)


class Ticket(Base):
    __tablename__ = "tickets"
    # Never reuse IDs of deleted tickets – commits/PRs reference them as APM-x
    __table_args__ = {"sqlite_autoincrement": True}

    id            = Column(Integer, primary_key=True, autoincrement=True, index=True)
    title            = Column(String(200), nullable=False)
    description      = Column(Text, nullable=True)

    # Canonical enums – MUST match VALID_* sets in schemas.py
    ticket_type      = Column(String(50),  nullable=False, default="task")
    status           = Column(String(50),  nullable=False, default="Open")
    priority         = Column(String(20),  nullable=False, default="Medium")
    priority_score   = Column(SmallInteger, nullable=True)

    assignee         = Column(String(100), nullable=True)
    reported_by      = Column(String(100), nullable=True)
    source           = Column(String(50),  nullable=True, default="api")
    channel          = Column(String(50),  nullable=True)
    slack_message_ts = Column(String(50),  nullable=True)

    # Links to other tickets (numeric ids; exposed as APM-x)
    parent_id        = Column(Integer, nullable=True, index=True)
    duplicate_of     = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    @property
    def ticket_id(self) -> str:
        return f"APM-{self.id}"


class TicketEvent(Base):
    """Append-only activity log behind the ticket timeline."""
    __tablename__ = "ticket_events"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id  = Column(Integer, nullable=False, index=True)
    kind       = Column(String(50),  nullable=False)
    actor      = Column(String(100), nullable=True)
    summary    = Column(Text, nullable=False)
    data       = Column(Text, nullable=True)   # JSON-encoded details
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
