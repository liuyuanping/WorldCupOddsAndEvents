"""Data source management API routes."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.adapters.registry import registry

router = APIRouter(prefix="/api/v1/datasources", tags=["datasources"])


class DataSourceEnableRequest(BaseModel):
    provider_id: str
    config: dict = {}


@router.get("")
async def list_datasources():
    """List all registered data sources with their status."""
    return {"providers": registry.get_all_providers()}


@router.get("/{provider_id}")
async def get_datasource(provider_id: str):
    """Get details for a specific data source."""
    state = registry.get_state(provider_id)
    instance = registry.get_odds_instance(provider_id) or registry.get_event_instance(provider_id)

    info = {}
    if instance:
        info = instance.get_provider_info()

    return {
        "id": provider_id,
        "state": state.value,
        "info": info,
    }


@router.post("/enable")
async def enable_datasource(req: DataSourceEnableRequest):
    """Enable a data source."""
    success = await registry.enable(req.provider_id, req.config)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to enable {req.provider_id}")
    return {"status": "ok", "provider_id": req.provider_id}


@router.post("/{provider_id}/disable")
async def disable_datasource(provider_id: str):
    """Disable a data source."""
    await registry.disable(provider_id)
    return {"status": "ok", "provider_id": provider_id}
