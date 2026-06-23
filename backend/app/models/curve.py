"""Curve definition model."""
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
import uuid

from sqlalchemy import Column, String, DateTime, JSON, Text
from pydantic import BaseModel, Field

from app.database import Base


# ── Enums ──────────────────────────────────────────────

class CurveType(str, Enum):
    ODDS = "odds"
    SPREAD = "spread"
    VOLATILITY = "volatility"
    DERIVED = "derived"


# ── SQLAlchemy ORM ─────────────────────────────────────

class CurveDefinitionORM(Base):
    __tablename__ = "curve_definitions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String(32), nullable=False, default="odds")
    source_config = Column(JSON, nullable=False)
    calculation = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


# ── Pydantic Schemas ───────────────────────────────────

class CurveSourceConfig(BaseModel):
    """Configuration for a curve's data source."""
    provider: str
    match_id: str
    bookmaker: Optional[str] = None
    market: str = "h2h"
    selection: str = "home"


class CurveDefinitionIn(BaseModel):
    """Input schema for creating / updating a curve."""
    name: str
    description: Optional[str] = None
    type: CurveType = CurveType.ODDS
    source_config: CurveSourceConfig
    calculation: Optional[str] = None


class CurveDefinitionOut(CurveDefinitionIn):
    """Output schema."""
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
