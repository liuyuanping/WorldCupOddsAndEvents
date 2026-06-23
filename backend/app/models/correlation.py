"""Event-Odds correlation model."""
from datetime import datetime
from typing import Optional, Dict, Any, List
import uuid

from sqlalchemy import (
    Column, String, Float, DateTime, JSON, Integer, ForeignKey, Index, Text,
)
from pydantic import BaseModel, Field

from app.database import Base


# ── SQLAlchemy ORM ─────────────────────────────────────

class EventOddsCorrelationORM(Base):
    __tablename__ = "event_odds_correlations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String, ForeignKey("events.id"), nullable=False, index=True)
    odds_id = Column(String, nullable=True)  # optional direct reference
    curve_id = Column(String, ForeignKey("curve_definitions.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    correlation_score = Column(Float, nullable=False)
    lag_seconds = Column(Integer, nullable=True)
    magnitude = Column(Float, nullable=True)
    direction = Column(String(8), nullable=True)
    detection_method = Column(String(32), nullable=False)
    confidence = Column(Float, nullable=False, default=0.0)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_corr_event", "event_id"),
        Index("idx_corr_curve", "curve_id"),
        Index("idx_corr_score", "correlation_score"),
    )


# ── Pydantic Schemas ───────────────────────────────────

class CorrelationCandidate(BaseModel):
    """A detected correlation candidate."""
    timestamp: datetime
    score: float
    magnitude: float
    direction: str  # "up" | "down" | "neutral"
    detection_methods: List[str]
    event_id: str
    curve_id: str
    lag_seconds: Optional[int] = None


class EventOddsCorrelationIn(BaseModel):
    """Input schema for a correlation record."""
    event_id: str
    odds_id: Optional[str] = None
    curve_id: str
    timestamp: datetime
    correlation_score: float
    lag_seconds: Optional[int] = None
    magnitude: Optional[float] = None
    direction: Optional[str] = None
    detection_method: str = "manual"
    confidence: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EventOddsCorrelationOut(EventOddsCorrelationIn):
    """Output schema."""
    id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CorrelationQueryParams(BaseModel):
    """Parameters for querying correlations."""
    event_id: Optional[str] = None
    curve_id: Optional[str] = None
    min_score: Optional[float] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(default=500, le=5000)
