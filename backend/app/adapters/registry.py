"""Data source registry — runtime adapter management."""
from typing import Dict, List, Type, Optional, Any
from enum import Enum
import logging

from app.adapters.base import OddsProviderAdapter, EventProviderAdapter

logger = logging.getLogger(__name__)


class AdapterState(str, Enum):
    CREATED = "created"
    REGISTERED = "registered"
    ENABLING = "enabling"
    ACTIVE = "active"
    DEGRADED = "degraded"
    ERROR = "error"
    DISABLING = "disabling"
    DISABLED = "disabled"


class DataSourceRegistry:
    """Central registry for data source adapters."""

    def __init__(self):
        self._odds_classes: Dict[str, Type[OddsProviderAdapter]] = {}
        self._event_classes: Dict[str, Type[EventProviderAdapter]] = {}
        self._odds_instances: Dict[str, OddsProviderAdapter] = {}
        self._event_instances: Dict[str, EventProviderAdapter] = {}
        self._states: Dict[str, AdapterState] = {}
        self._configs: Dict[str, dict] = {}

    # ── Registration ──────────────────────────────────

    def register_odds(self, adapter_class: Type[OddsProviderAdapter], provider_id: str):
        """Register an odds adapter class."""
        self._odds_classes[provider_id] = adapter_class
        self._states[provider_id] = AdapterState.REGISTERED
        logger.info(f"Registered odds adapter: {provider_id}")

    def register_event(self, adapter_class: Type[EventProviderAdapter], provider_id: str):
        """Register an event adapter class."""
        self._event_classes[provider_id] = adapter_class
        self._states[provider_id] = AdapterState.REGISTERED
        logger.info(f"Registered event adapter: {provider_id}")

    # ── Lifecycle ──────────────────────────────────────

    async def enable(self, provider_id: str, config: Optional[dict] = None) -> bool:
        """Enable and instantiate an adapter."""
        if provider_id not in self._states:
            raise ValueError(f"Unknown provider: {provider_id}")

        self._states[provider_id] = AdapterState.ENABLING
        config = config or {}
        self._configs[provider_id] = config

        try:
            if provider_id in self._odds_classes:
                instance = self._odds_classes[provider_id]()
                instance.config = config
                await instance.initialize()
                self._odds_instances[provider_id] = instance
            elif provider_id in self._event_classes:
                instance = self._event_classes[provider_id]()
                instance.config = config
                await instance.initialize()
                self._event_instances[provider_id] = instance
            else:
                return False

            self._states[provider_id] = AdapterState.ACTIVE
            return True
        except Exception as e:
            logger.error(f"Failed to enable {provider_id}: {e}")
            self._states[provider_id] = AdapterState.ERROR
            return False

    async def disable(self, provider_id: str):
        """Disable an adapter."""
        self._states[provider_id] = AdapterState.DISABLING
        instance = self._odds_instances.get(provider_id) or self._event_instances.get(provider_id)
        if instance:
            await instance.shutdown()
        self._states[provider_id] = AdapterState.DISABLED

    # ── Access ─────────────────────────────────────────

    def get_odds_instance(self, provider_id: str) -> Optional[OddsProviderAdapter]:
        return self._odds_instances.get(provider_id)

    def get_event_instance(self, provider_id: str) -> Optional[EventProviderAdapter]:
        return self._event_instances.get(provider_id)

    def get_active_odds_providers(self) -> List[str]:
        return [
            pid for pid, s in self._states.items()
            if pid in self._odds_classes and s == AdapterState.ACTIVE
        ]

    def get_active_event_providers(self) -> List[str]:
        return [
            pid for pid, s in self._states.items()
            if pid in self._event_classes and s == AdapterState.ACTIVE
        ]

    def get_all_providers(self) -> List[Dict[str, Any]]:
        """Return all registered providers with status."""
        result = []
        for pid, cls in {**self._odds_classes, **self._event_classes}.items():
            info = cls().get_provider_info() if hasattr(cls(), 'get_provider_info') else {}
            info.update({
                "id": pid,
                "type": "odds" if pid in self._odds_classes else "event",
                "state": self._states.get(pid, AdapterState.CREATED).value,
                "config": self._configs.get(pid, {}),
            })
            result.append(info)
        return result

    def get_state(self, provider_id: str) -> AdapterState:
        return self._states.get(provider_id, AdapterState.CREATED)


# Global singleton
registry = DataSourceRegistry()
