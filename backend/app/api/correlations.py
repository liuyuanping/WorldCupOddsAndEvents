"""Correlation analysis API routes."""
from datetime import datetime
from fastapi import APIRouter, Query, HTTPException

from app.adapters.registry import registry
from app.engine.correlation import EventOddsCorrelationEngine
from app.models.correlation import CorrelationCandidate

router = APIRouter(prefix="/api/v1/correlations", tags=["correlations"])

# Singleton engine
_engine = EventOddsCorrelationEngine()


@router.get("", response_model=list[CorrelationCandidate])
async def detect_correlations(
    match_id: str = Query(default="wc2026_eng_fra"),
    odds_provider: str = Query(default="mock_odds"),
    event_provider: str = Query(default="mock_events"),
    min_score: float = Query(default=0.3, ge=0.0, le=1.0),
):
    """
    Detect correlations between events and odds curves.

    Runs both CUSUM changepoint detection and event window analysis,
    then fuses results into ranked correlation candidates.
    """
    odds_adapter = registry.get_odds_instance(odds_provider)
    event_adapter = registry.get_event_instance(event_provider)

    if not odds_adapter:
        raise HTTPException(status_code=404, detail=f"Odds provider '{odds_provider}' not active")
    if not event_adapter:
        raise HTTPException(status_code=404, detail=f"Event provider '{event_provider}' not active")

    # Fetch data
    events = await event_adapter.fetch_events()
    odds_records = await odds_adapter.fetch_odds(match_id=match_id)

    # Build odds series per bookmaker (each bookmaker = a "curve")
    from collections import defaultdict
    odds_by_bookmaker = defaultdict(list)
    for r in odds_records:
        curve_id = f"{r.bookmaker}_{r.market}_{r.selection}"
        odds_by_bookmaker[curve_id].append(r)

    # Run detection
    time_window = (
        datetime(2026, 6, 23, 0, 0, 0),
        datetime(2026, 6, 23, 23, 59, 59),
    )

    engine = EventOddsCorrelationEngine(min_score=min_score)
    candidates = await engine.detect_correlations(
        events=events,
        odds_series=dict(odds_by_bookmaker),
        time_window=time_window,
    )

    return candidates


@router.get("/detail/{event_id}")
async def get_correlation_detail(
    event_id: str,
    odds_provider: str = Query(default="mock_odds"),
    event_provider: str = Query(default="mock_events"),
):
    """Get detailed correlation analysis for a specific event."""
    odds_adapter = registry.get_odds_instance(odds_provider)
    event_adapter = registry.get_event_instance(event_provider)

    if not odds_adapter or not event_adapter:
        raise HTTPException(status_code=404, detail="Provider not found")

    events = await event_adapter.fetch_events()
    event = next((e for e in events if e.source_id == event_id), None)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    odds_records = await odds_adapter.fetch_odds(match_id="wc2026_eng_fra")

    # Build per-bookmaker series
    from collections import defaultdict
    odds_by_curve = defaultdict(list)
    for r in odds_records:
        curve_id = f"{r.bookmaker}_{r.market}_{r.selection}"
        odds_by_curve[curve_id].append(r)

    engine = EventOddsCorrelationEngine(min_score=0.0)
    candidates = await engine.detect_correlations(
        events=[event],
        odds_series=dict(odds_by_curve),
        time_window=(datetime(2026, 6, 23, 0, 0, 0), datetime(2026, 6, 23, 23, 59, 59)),
    )

    return {
        "event": {
            "title": event.title,
            "type": event.event_type,
            "severity": event.severity.value,
            "timestamp": event.timestamp.isoformat(),
        },
        "correlations": [
            {
                "curve_id": c.curve_id,
                "score": c.score,
                "magnitude": c.magnitude,
                "direction": c.direction,
                "lag_seconds": c.lag_seconds,
                "methods": c.detection_methods,
            }
            for c in candidates
        ],
    }
