"""Cache management API routes."""
from fastapi import APIRouter, Query

from app.cache import cache

router = APIRouter(prefix="/api/v1/cache", tags=["cache"])


@router.get("/status")
async def cache_status():
    """Show cache contents and freshness."""
    return {"entries": await cache.status()}


@router.post("/refresh")
async def refresh_cache():
    """Clear all cache — next requests will fetch from external sources."""
    await cache.clear()
    return {"status": "ok", "message": "Cache cleared. Next requests will fetch fresh data."}


@router.delete("/{provider}")
async def clear_provider_cache(provider: str):
    """Clear cache for a specific provider."""
    await cache.clear(provider=provider)
    return {"status": "ok", "message": f"Cache cleared for {provider}"}
