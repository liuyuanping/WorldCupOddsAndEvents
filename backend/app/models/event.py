"""Event record data model."""
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import IntEnum
import uuid

from sqlalchemy import Column, String, Float, DateTime, JSON, Integer, Text, Index
from pydantic import BaseModel, Field

from app.database import Base


# ── Enums ──────────────────────────────────────────────

class EventSeverity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


# ── SQLAlchemy ORM ─────────────────────────────────────

class EventRecordORM(Base):
    __tablename__ = "events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    provider = Column(String(64), nullable=False, index=True)
    source_id = Column(String(256), nullable=False)
    event_type = Column(String(64), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    detected_at = Column(DateTime(timezone=True), nullable=False)
    severity = Column(Integer, nullable=False, default=1)
    confidence = Column(Float, nullable=False, default=1.0)
    source_url = Column(Text, nullable=True)
    entities = Column(JSON, default=list)
    metadata_ = Column("metadata", JSON, default=dict)

    __table_args__ = (
        Index("idx_events_ts", "timestamp"),
        Index("idx_events_type", "event_type", "timestamp"),
    )


# ── Pydantic Schemas ───────────────────────────────────

class EntityRef(BaseModel):
    """Reference to a related entity (team, player, etc.)."""
    type: str  # "team", "player", "match"
    id: str
    name: str


class EventRecordIn(BaseModel):
    """Input / API response schema for an event record."""
    provider: str
    source_id: str
    event_type: str
    title: str
    description: Optional[str] = None
    timestamp: datetime
    detected_at: Optional[datetime] = None
    severity: EventSeverity = EventSeverity.LOW
    confidence: float = 1.0
    source_url: Optional[str] = None
    entities: List[EntityRef] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EventRecordOut(EventRecordIn):
    """Output schema including DB-assigned fields."""
    id: str
    related_odds_ids: List[str] = Field(default_factory=list)
    related_curves: List[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class EventQueryParams(BaseModel):
    """Parameters for querying events."""
    event_type: Optional[List[str]] = None
    severity: Optional[List[int]] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    entity_id: Optional[str] = None
    limit: int = Field(default=1000, le=10000)
