"""Offline event adapter — reads from local JSON file populated by scraper."""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

from app.adapters.base import EventProviderAdapter
from app.models.champion import TeamEventIn, TeamEventSeverity

logger = logging.getLogger(__name__)

DEFAULT_DATA_FILE = Path(__file__).parent.parent.parent.parent / "data" / "team_events.json"


class OfflineEventAdapter(EventProviderAdapter):
    """Reads team events from a local JSON file.

    The JSON file can be manually edited or populated by a web scraper.
    Format:
    [
      {
        "team_id": "france",
        "team_name": "法国",
        "event_type": "injury",
        "title": "...",
        "description": "...",
        "timestamp": "2026-06-20T10:30:00Z",
        "severity": 4,
        "confidence": 0.90,
        "source_url": "..."
      }
    ]
    """

    def __init__(self):
        self.config: dict = {}
        self._events: List[TeamEventIn] = []
        self._data_file: Path = DEFAULT_DATA_FILE
        self._mtime: float = 0

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "离线数据",
            "version": "1.0.0",
            "categories": self.get_event_categories(),
            "data_source": f"本地文件: {self._data_file}",
            "num_events": len(self._events),
        }

    async def initialize(self):
        data_path = self.config.get("data_path", str(DEFAULT_DATA_FILE))
        self._data_file = Path(data_path)
        self._load()

    async def shutdown(self, grace_period: float = 10.0):
        pass

    async def health_check(self) -> bool:
        return self._data_file.exists()

    def _load(self):
        """Load events from JSON file. Auto-reloads if file changed."""
        if not self._data_file.exists():
            logger.warning(f"Offline data file not found: {self._data_file}")
            self._events = []
            return

        try:
            current_mtime = self._data_file.stat().st_mtime
            if current_mtime == self._mtime:
                return  # Already loaded
            self._mtime = current_mtime
        except OSError:
            pass

        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                raw = json.load(f)

            events = []
            for item in raw:
                try:
                    events.append(TeamEventIn(
                        provider="offline",
                        source_id=f"offline_{item.get('team_id', '')}_{item.get('timestamp', '')}",
                        team_id=item.get("team_id", ""),
                        team_name=item.get("team_name", ""),
                        event_type=item.get("event_type", "unknown"),
                        title=item.get("title", ""),
                        description=item.get("description", ""),
                        timestamp=datetime.fromisoformat(
                            item.get("timestamp", "2026-01-01T00:00:00Z")
                        ).replace(tzinfo=timezone.utc),
                        severity=TeamEventSeverity(item.get("severity", 1)),
                        confidence=item.get("confidence", 1.0),
                        source_url=item.get("source_url", ""),
                    ))
                except Exception as e:
                    logger.warning(f"Skipping invalid offline event: {e}")
                    continue

            self._events = events
            logger.info(f"Loaded {len(events)} events from {self._data_file}")
        except Exception as e:
            logger.error(f"Failed to load offline events: {e}")
            self._events = []

    async def fetch_events(
        self,
        entity_id: Optional[str] = None,
        event_type: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        keywords: Optional[List[str]] = None,
    ) -> List[TeamEventIn]:
        """Return filtered offline events."""
        self._load()  # Auto-reload if file changed

        result = self._events
        if entity_id:
            result = [e for e in result if e.team_id == entity_id]
        if event_type:
            result = [e for e in result if e.event_type in event_type]
        if start_time:
            result = [e for e in result if e.timestamp >= start_time]
        if end_time:
            result = [e for e in result if e.timestamp <= end_time]

        return sorted(result, key=lambda e: e.timestamp, reverse=True)

    async def stream_events(self, filters, on_event=None):
        events = await self.fetch_events()
        for e in events:
            yield e

    def get_event_categories(self) -> List[str]:
        self._load()
        return sorted(set(e.event_type for e in self._events))
