"""Odds record data model."""
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, Float, DateTime, JSON, UniqueConstraint, Index,
)
from pydantic import BaseModel, Field

from app.database import Base


# ── Enums ──────────────────────────────────────────────

class OddsFormat(str, Enum):
    DECIMAL = "decimal"
    AMERICAN = "american"
    HONGKONG = "hongkong"
    INDONESIAN = "indonesian"
    MALAY = "malay"


# ── SQLAlchemy ORM ─────────────────────────────────────

class OddsRecordORM(Base):
    __tablename__ = "odds_records"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    provider = Column(String(64), nullable=False, index=True)
    source_id = Column(String(256), nullable=False)
    match_id = Column(String(128), nullable=False, index=True)
    bookmaker = Column(String(128), nullable=False, index=True)
    market = Column(String(32), nullable=False)
    selection = Column(String(64), nullable=False)
    odds_value = Column(Float, nullable=False)
    odds_format = Column(String(16), nullable=False, default="decimal")
    implied_probability = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    received_at = Column(DateTime(timezone=True), nullable=False)
    metadata_ = Column("metadata", JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("provider", "source_id", name="uq_odds_provider_source"),
        Index("idx_odds_match_ts", "match_id", "timestamp"),
        Index("idx_odds_provider_match", "provider", "match_id"),
    )


# ── Pydantic Schemas ───────────────────────────────────

class OddsRecordIn(BaseModel):
    """Input / API response schema for an odds record."""
    provider: str
    source_id: str
    match_id: str
    bookmaker: str
    market: str
    selection: str
    odds_value: float
    odds_format: OddsFormat = OddsFormat.DECIMAL
    implied_probability: Optional[float] = None
    volume: Optional[float] = None
    timestamp: datetime
    received_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OddsRecordOut(OddsRecordIn):
    """Output schema including DB-assigned fields."""
    id: str

    model_config = {"from_attributes": True}


class OddsQueryParams(BaseModel):
    """Parameters for querying odds data."""
    match_id: Optional[str] = None
    provider: Optional[str] = None
    bookmaker: Optional[str] = None
    market: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(default=10000, le=100000)
