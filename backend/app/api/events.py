"""Event data API routes."""
from fastapi import APIRouter, Query, HTTPException

from app.adapters.registry import registry
from app.models.event import EventRecordOut, EventRecordIn

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("", response_model=list[EventRecordOut])
async def query_events(
    provider: str = Query(default="mock_events"),
    event_type: str | None = Query(default=None),
    severity: int | None = Query(default=None),
):
    """Query events from a specific provider."""
    adapter = registry.get_event_instance(provider)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found or not active")

    event_types = [event_type] if event_type else None
    severities = [severity] if severity is not None else None

    records = await adapter.fetch_events(
        event_type=event_types,
    )

    # Apply severity filter in Python
    if severities:
        records = [r for r in records if r.severity.value in severities]

    # Convert to output format
    import uuid
    return [
        EventRecordOut(
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, r.source_id)),
            provider=r.provider,
            source_id=r.source_id,
            event_type=r.event_type,
            title=r.title,
            description=r.description,
            timestamp=r.timestamp,
            detected_at=r.detected_at,
            severity=r.severity,
            confidence=r.confidence,
            source_url=r.source_url,
            entities=r.entities,
            metadata=r.metadata,
        )
        for r in records
    ]


@router.get("/categories")
async def list_categories(provider: str = Query(default="mock_events")):
    """List supported event categories for a provider."""
    adapter = registry.get_event_instance(provider)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found or not active")
    return {"categories": adapter.get_event_categories()}
