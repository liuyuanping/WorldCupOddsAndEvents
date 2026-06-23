"""Database-backed event adapter — manually populated via API or scraper."""
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from sqlalchemy import select, delete

from app.adapters.base import EventProviderAdapter
from app.database import async_session
from app.models.champion import TeamEventORM, TeamEventIn, TeamEventSeverity

logger = logging.getLogger(__name__)


class DatabaseEventAdapter(EventProviderAdapter):
    """Reads team events from the database.

    Events are added via POST /api/v1/champion/events/db endpoint
    (or directly via SQL / scraper), and read back by this adapter.
    """

    def __init__(self):
        self.config: dict = {}

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "数据库离线数据",
            "version": "1.0.0",
            "categories": [
                "injury", "squad", "form", "transfer", "manager",
                "preview", "friendly", "training", "other",
            ],
            "data_source": "SQLite database (manual + scraper)",
        }

    async def initialize(self):
        pass

    async def shutdown(self, grace_period: float = 10.0):
        pass

    async def health_check(self) -> bool:
        return True

    async def fetch_events(
        self,
        entity_id: Optional[str] = None,
        event_type: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        keywords: Optional[List[str]] = None,
    ) -> List[TeamEventIn]:
        """Query events from database with filters."""
        async with async_session() as session:
            stmt = select(TeamEventORM).where(TeamEventORM.provider == "database")
            if entity_id:
                stmt = stmt.where(TeamEventORM.team_id == entity_id)
            if event_type:
                stmt = stmt.where(TeamEventORM.event_type.in_(event_type))
            if start_time:
                stmt = stmt.where(TeamEventORM.timestamp >= start_time)
            if end_time:
                stmt = stmt.where(TeamEventORM.timestamp <= end_time)
            stmt = stmt.order_by(TeamEventORM.timestamp.desc()).limit(500)

            result = await session.execute(stmt)
            rows = result.scalars().all()

            return [
                TeamEventIn(
                    provider="database",
                    source_id=row.source_id,
                    team_id=row.team_id,
                    team_name=row.team_name,
                    event_type=row.event_type,
                    title=row.title,
                    description=row.description or "",
                    timestamp=row.timestamp.replace(tzinfo=timezone.utc),
                    severity=TeamEventSeverity(row.severity),
                    confidence=row.confidence,
                    source_url=row.source_url or "",
                )
                for row in rows
            ]

    async def stream_events(self, filters, on_event=None):
        events = await self.fetch_events()
        for e in events:
            yield e

    def get_event_categories(self) -> List[str]:
        return [
            "injury", "squad", "form", "transfer", "manager",
            "preview", "friendly", "training", "other",
        ]

    async def add_event(self, event: TeamEventIn) -> str:
        """Add a new event to the database. Returns the source_id."""
        source_id = f"db_{event.team_id}_{event.timestamp.strftime('%Y%m%d%H%M%S')}"
        async with async_session() as session:
            entry = TeamEventORM(
                provider="database",
                source_id=source_id,
                team_id=event.team_id,
                team_name=event.team_name,
                event_type=event.event_type,
                title=event.title,
                description=event.description or "",
                timestamp=event.timestamp,
                severity=event.severity.value,
                confidence=event.confidence,
                source_url=event.source_url or "",
            )
            session.add(entry)
            await session.commit()
            logger.info(f"Added database event: {event.title}")
        return source_id

    async def delete_event(self, source_id: str) -> bool:
        """Delete an event by source_id."""
        async with async_session() as session:
            result = await session.execute(
                delete(TeamEventORM).where(TeamEventORM.source_id == source_id)
            )
            await session.commit()
            return result.rowcount > 0
