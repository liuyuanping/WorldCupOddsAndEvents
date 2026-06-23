"""Odds data API routes."""
from fastapi import APIRouter, Query, HTTPException

from app.adapters.registry import registry
from app.models.odds import OddsRecordIn, OddsRecordOut

router = APIRouter(prefix="/api/v1/odds", tags=["odds"])


@router.get("", response_model=list[OddsRecordOut])
async def query_odds(
    match_id: str = Query(default="wc2026_eng_fra"),
    provider: str = Query(default="mock_odds"),
    bookmaker: str | None = Query(default=None),
    market: str | None = Query(default=None),
):
    """Query odds data from a specific provider."""
    adapter = registry.get_odds_instance(provider)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found or not active")

    records = await adapter.fetch_odds(
        match_id=match_id,
        bookmakers=[bookmaker] if bookmaker else None,
        markets=[market] if market else None,
    )

    # Convert to output format with IDs
    import uuid
    return [
        OddsRecordOut(
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, r.source_id)),
            provider=r.provider,
            source_id=r.source_id,
            match_id=r.match_id,
            bookmaker=r.bookmaker,
            market=r.market,
            selection=r.selection,
            odds_value=r.odds_value,
            odds_format=r.odds_format,
            implied_probability=r.implied_probability,
            volume=r.volume,
            timestamp=r.timestamp,
            received_at=r.received_at,
            metadata=r.metadata,
        )
        for r in records
    ]


@router.get("/bookmakers")
async def list_bookmakers(provider: str = Query(default="mock_odds")):
    """List supported bookmakers for a provider."""
    adapter = registry.get_odds_instance(provider)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found or not active")
    return {"bookmakers": adapter.get_supported_bookmakers()}


@router.get("/markets")
async def list_markets(provider: str = Query(default="mock_odds")):
    """List supported markets for a provider."""
    adapter = registry.get_odds_instance(provider)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found or not active")
    return {"markets": adapter.get_supported_markets()}
