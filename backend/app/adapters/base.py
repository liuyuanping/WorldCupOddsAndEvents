"""Abstract adapter interfaces for data sources."""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Dict, Any, Callable, AsyncIterator

from app.models.odds import OddsRecordIn
from app.models.event import EventRecordIn


class OddsProviderAdapter(ABC):
    """Abstract base class for all odds data source adapters."""

    @abstractmethod
    def get_provider_info(self) -> Dict[str, Any]:
        """Return metadata: name, supported markets, latency, etc."""
        ...

    @abstractmethod
    async def fetch_odds(
        self,
        match_id: Optional[str] = None,
        league: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        bookmakers: Optional[List[str]] = None,
        markets: Optional[List[str]] = None,
    ) -> List[OddsRecordIn]:
        """Fetch odds data with optional filters."""
        ...

    @abstractmethod
    async def stream_odds(
        self,
        match_ids: List[str],
        on_update: Callable[[OddsRecordIn], None],
    ) -> AsyncIterator[OddsRecordIn]:
        """Stream real-time odds updates."""
        ...

    @abstractmethod
    def get_supported_markets(self) -> List[str]:
        """Return list of supported market types."""
        ...

    @abstractmethod
    def get_supported_bookmakers(self) -> List[str]:
        """Return list of covered bookmakers."""
        ...

    async def initialize(self):
        """Optional: one-time setup when adapter is enabled."""
        pass

    async def health_check(self) -> bool:
        """Check if the data source is reachable."""
        return True

    async def shutdown(self, grace_period: float = 10.0):
        """Optional: graceful shutdown."""
        pass


class EventProviderAdapter(ABC):
    """Abstract base class for all event data source adapters."""

    @abstractmethod
    def get_provider_info(self) -> Dict[str, Any]:
        """Return metadata about the event source."""
        ...

    @abstractmethod
    async def fetch_events(
        self,
        entity_id: Optional[str] = None,
        event_type: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        keywords: Optional[List[str]] = None,
    ) -> List[EventRecordIn]:
        """Fetch event data with optional filters."""
        ...

    @abstractmethod
    async def stream_events(
        self,
        filters: Dict[str, Any],
        on_event: Callable[[EventRecordIn], None],
    ) -> AsyncIterator[EventRecordIn]:
        """Stream real-time event updates."""
        ...

    @abstractmethod
    def get_event_categories(self) -> List[str]:
        """Return list of supported event categories."""
        ...

    async def initialize(self):
        """Optional: one-time setup."""
        pass

    async def health_check(self) -> bool:
        """Check if the data source is reachable."""
        return True

    async def shutdown(self, grace_period: float = 10.0):
        """Optional: graceful shutdown."""
        pass
