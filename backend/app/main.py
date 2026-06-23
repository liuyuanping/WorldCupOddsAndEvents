"""FastAPI application entry point."""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.adapters.registry import registry
from app.adapters.odds.mock_odds_adapter import MockOddsAdapter
from app.adapters.odds.mock_champion_odds_adapter import MockChampionOddsAdapter
from app.adapters.odds.polymarket_champion_adapter import PolymarketChampionAdapter
from app.adapters.events.mock_event_adapter import MockEventAdapter
from app.adapters.events.mock_team_event_adapter import MockTeamEventAdapter
from app.adapters.events.gdelt_adapter import GDELTTeamEventAdapter
from app.api import odds, events, correlations, datasources, champion, cache as cache_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # Startup
    logger.info("Starting Odds-Event Correlation API...")
    await init_db()

    # Register and enable adapters
    registry.register_odds(MockOddsAdapter, "mock_odds")
    registry.register_odds(MockChampionOddsAdapter, "mock_champion_odds")
    registry.register_odds(PolymarketChampionAdapter, "polymarket")
    registry.register_event(MockEventAdapter, "mock_events")
    registry.register_event(MockTeamEventAdapter, "mock_team_events")
    registry.register_event(GDELTTeamEventAdapter, "gdelt")
    await registry.enable("mock_odds")
    await registry.enable("mock_champion_odds")
    await registry.enable("polymarket")
    await registry.enable("mock_events")
    await registry.enable("mock_team_events")
    await registry.enable("gdelt")

    logger.info("API ready. Providers: %s", registry.get_all_providers())

    yield

    # Shutdown
    for pid in registry.get_active_odds_providers() + registry.get_active_event_providers():
        await registry.disable(pid)
    logger.info("API shutdown complete.")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount REST routers
app.include_router(odds.router)
app.include_router(events.router)
app.include_router(correlations.router)
app.include_router(datasources.router)
app.include_router(champion.router)
app.include_router(cache_api.router)


# ── WebSocket for real-time odds ──────────────────────

@app.websocket("/ws/realtime")
async def websocket_realtime(websocket: WebSocket):
    """WebSocket endpoint for real-time odds updates."""
    await websocket.accept()
    logger.info("WebSocket client connected")

    try:
        while True:
            # Wait for client messages (subscribe / unsubscribe)
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")

            if action == "subscribe":
                match_id = msg.get("match_id", "wc2026_eng_fra")
                provider = msg.get("provider", "mock_odds")

                adapter = registry.get_odds_instance(provider)
                if not adapter:
                    await websocket.send_json({"error": f"Provider {provider} not active"})
                    continue

                # Stream odds data to the client
                async for record in adapter.stream_odds(match_ids=[match_id], on_update=None):
                    await websocket.send_json({
                        "type": "odds_update",
                        "data": {
                            "match_id": record.match_id,
                            "bookmaker": record.bookmaker,
                            "market": record.market,
                            "selection": record.selection,
                            "odds_value": record.odds_value,
                            "timestamp": record.timestamp.isoformat(),
                        }
                    })
                    # Small delay to simulate real-time streaming
                    await asyncio.sleep(0.05)

            elif action == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


# ── Health check ─────────────────────────────────────

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "providers": registry.get_all_providers(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/")
async def root():
    """Root — API info."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {
            "odds": "/api/v1/odds",
            "events": "/api/v1/events",
            "correlations": "/api/v1/correlations",
            "datasources": "/api/v1/datasources",
            "websocket": "/ws/realtime",
            "champion": "/api/v1/champion",
        },
    }
