"""Data persistence cache — SQLite-backed, TTL-based."""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Dict, List

from sqlalchemy import Column, String, DateTime, JSON, Text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base, async_session

logger = logging.getLogger(__name__)


class CacheEntryORM(Base):
    """Cache entries stored in SQLite."""
    __tablename__ = "cache_entries"

    key = Column(String(256), primary_key=True)
    data_type = Column(String(64), nullable=False, index=True)  # "champion_odds", "team_events"
    provider = Column(String(64), nullable=False, index=True)    # "polymarket", "gdelt"
    data_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class CacheManager:
    """Manages data caching with SQLite persistence."""

    def __init__(self):
        self._session: Optional[AsyncSession] = None

    async def _get_session(self) -> AsyncSession:
        return async_session()

    def _make_key(self, provider: str, data_type: str, params: Dict = None) -> str:
        """Generate a deterministic cache key."""
        raw = f"{provider}:{data_type}:{json.dumps(params or {}, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:64]

    async def get(self, provider: str, data_type: str, params: Dict = None) -> Optional[Any]:
        """Get cached data. Returns None if not found."""
        key = self._make_key(provider, data_type, params)
        async with await self._get_session() as session:
            entry = await session.get(CacheEntryORM, key)
            if entry:
                return json.loads(entry.data_json)
        return None

    async def set(
        self, provider: str, data_type: str, data: Any, params: Dict = None
    ) -> None:
        """Store data in cache."""
        key = self._make_key(provider, data_type, params)
        now = datetime.now(timezone.utc)
        async with await self._get_session() as session:
            entry = await session.get(CacheEntryORM, key)
            if entry:
                entry.data_json = json.dumps(data, ensure_ascii=False, default=str)
                entry.updated_at = now
            else:
                entry = CacheEntryORM(
                    key=key,
                    data_type=data_type,
                    provider=provider,
                    data_json=json.dumps(data, ensure_ascii=False, default=str),
                    created_at=now,
                    updated_at=now,
                )
                session.add(entry)
            await session.commit()

    async def has(self, provider: str, data_type: str, params: Dict = None) -> bool:
        """Check if cached data exists."""
        key = self._make_key(provider, data_type, params)
        async with await self._get_session() as session:
            entry = await session.get(CacheEntryORM, key)
            return entry is not None

    async def clear(self, provider: Optional[str] = None, data_type: Optional[str] = None):
        """Clear cache entries. Optional filters by provider and/or data_type."""
        async with await self._get_session() as session:
            stmt = "DELETE FROM cache_entries WHERE 1=1"
            import sqlalchemy as sa
            conditions = []
            if provider:
                conditions.append(CacheEntryORM.provider == provider)
            if data_type:
                conditions.append(CacheEntryORM.data_type == data_type)
            if conditions:
                q = sa.delete(CacheEntryORM).where(sa.and_(*conditions))
            else:
                q = sa.delete(CacheEntryORM)
            await session.execute(q)
            await session.commit()
            logger.info(f"Cache cleared: provider={provider}, type={data_type}")

    async def status(self) -> List[Dict]:
        """Return cache status summary."""
        async with await self._get_session() as session:
            import sqlalchemy as sa
            q = sa.select(
                CacheEntryORM.data_type,
                CacheEntryORM.provider,
                sa.func.count().label("count"),
                sa.func.max(CacheEntryORM.updated_at).label("last_updated"),
            ).group_by(CacheEntryORM.data_type, CacheEntryORM.provider)
            result = await session.execute(q)
            return [
                {
                    "data_type": row.data_type,
                    "provider": row.provider,
                    "entries": row.count,
                    "last_updated": row.last_updated.isoformat() if row.last_updated else None,
                }
                for row in result
            ]


# Global singleton
cache = CacheManager()
