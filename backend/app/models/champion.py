"""Champion (outright winner) odds and team event models."""
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import IntEnum
import uuid

from sqlalchemy import Column, String, Float, DateTime, JSON, Integer, Text
from pydantic import BaseModel, Field

from app.database import Base


# ── Champion Odds ──────────────────────────────────────

class ChampionOddsRecordORM(Base):
    """Outright winner odds for a team at a point in time."""
    __tablename__ = "champion_odds_records"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    provider = Column(String(64), nullable=False, index=True)
    source_id = Column(String(256), nullable=False)
    team_id = Column(String(64), nullable=False, index=True)
    team_name = Column(String(128), nullable=False)
    bookmaker = Column(String(128), nullable=False, index=True)
    odds_value = Column(Float, nullable=False)
    implied_probability = Column(Float, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    received_at = Column(DateTime(timezone=True), nullable=False)
    metadata_ = Column("metadata", JSON, default=dict)


class ChampionOddsIn(BaseModel):
    provider: str
    source_id: str
    team_id: str
    team_name: str
    bookmaker: str
    odds_value: float
    implied_probability: Optional[float] = None
    timestamp: datetime
    received_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChampionOddsOut(ChampionOddsIn):
    id: str
    model_config = {"from_attributes": True}


# ── Team Event ─────────────────────────────────────────

class TeamEventSeverity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class TeamEventORM(Base):
    """Team-level events affecting championship odds."""
    __tablename__ = "team_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    provider = Column(String(64), nullable=False, index=True)
    source_id = Column(String(256), nullable=False)
    team_id = Column(String(64), nullable=False, index=True)
    team_name = Column(String(128), nullable=False)
    event_type = Column(String(64), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    severity = Column(Integer, nullable=False, default=1)
    confidence = Column(Float, nullable=False, default=1.0)
    source_url = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict)


class TeamEventIn(BaseModel):
    provider: str
    source_id: str
    team_id: str
    team_name: str
    event_type: str
    title: str
    description: Optional[str] = None
    timestamp: datetime
    severity: TeamEventSeverity = TeamEventSeverity.LOW
    confidence: float = 1.0
    source_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TeamEventOut(TeamEventIn):
    id: str
    model_config = {"from_attributes": True}


class TeamEventQueryParams(BaseModel):
    team_id: Optional[str] = None
    event_type: Optional[List[str]] = None
    severity: Optional[List[int]] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(default=500, le=5000)


# ── Champion Prediction ────────────────────────────────

class TeamChampionProfile(BaseModel):
    """Current champion profile for a team."""
    team_id: str
    team_name: str
    flag_emoji: str
    group: str
    elo_rating: int
    best_odds: float                # Best available odds
    avg_odds: float                 # Average across bookmakers
    implied_probability: float      # Market-implied win probability
    odds_trend_30d: float           # % change in last 30 days
    recent_form: str                # "↑ Improving", "→ Stable", "↓ Declining"
    key_events_count: int           # Number of recent significant events
    events_summary: List[str]       # Latest 3 event headlines


class ChampionPredictionRequest(BaseModel):
    n_simulations: int = Field(default=10000, ge=1000, le=100000)
    include_form: bool = True
    include_events: bool = True


class ChampionPredictionResult(BaseModel):
    """Monte Carlo simulation result."""
    team_id: str
    team_name: str
    flag_emoji: str
    market_probability: float       # Market-implied
    sim_probability: float          # Monte Carlo simulated
    value_edge_pct: float           # Positive = undervalued by market
    elo_rating: int
    group: str


class ChampionPredictionResponse(BaseModel):
    """Full prediction response."""
    rankings: List[ChampionPredictionResult]
    total_simulations: int
    timestamp: datetime
    top_pick: ChampionPredictionResult
    value_pick: ChampionPredictionResult  # Team with highest edge
    dark_horse: ChampionPredictionResult  # Best value outside top 5
