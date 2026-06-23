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
from app.adapters.events.database_event_adapter import DatabaseEventAdapter
from app.api import odds, events, correlations, datasources, champion, cache as cache_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _seed_database_events():
    """Seed initial events if the database table is empty."""
    from sqlalchemy import select, func
    from app.models.champion import TeamEventORM
    from app.database import async_session

    async with async_session() as session:
        result = await session.execute(
            select(func.count()).select_from(TeamEventORM).where(TeamEventORM.provider == "database")
        )
        count = result.scalar()
        if count > 0:
            return  # Already seeded

    # Seed initial events
    adapter = registry.get_event_instance("database")
    if not adapter or not hasattr(adapter, 'add_event'):
        return

    from app.models.champion import TeamEventIn, TeamEventSeverity
    from datetime import timezone

    seeds = [
        TeamEventIn(provider="database", source_id="", team_id="france", team_name="法国",
                    event_type="injury", title="姆巴佩训练中脚踝受伤",
                    description="法国队核心姆巴佩在训练中脚踝扭伤，队医评估需休养2-3周",
                    timestamp=datetime(2026, 6, 20, 10, 30, tzinfo=timezone.utc),
                    severity=TeamEventSeverity.CRITICAL, confidence=0.90),
        TeamEventIn(provider="database", source_id="", team_id="argentina", team_name="阿根廷",
                    event_type="squad", title="阿根廷公布26人最终名单",
                    description="梅西领衔，迪马利亚、阿尔瓦雷斯入选",
                    timestamp=datetime(2026, 6, 22, 14, 0, tzinfo=timezone.utc),
                    severity=TeamEventSeverity.MEDIUM, confidence=1.0),
        TeamEventIn(provider="database", source_id="", team_id="brazil", team_name="巴西",
                    event_type="form", title="巴西热身赛4-0大胜",
                    description="巴西队在最后一场热身赛中4-0击败对手，维尼修斯梅开二度",
                    timestamp=datetime(2026, 6, 18, 20, 0, tzinfo=timezone.utc),
                    severity=TeamEventSeverity.MEDIUM, confidence=0.95),
        TeamEventIn(provider="database", source_id="", team_id="germany", team_name="德国",
                    event_type="injury", title="德国队主力门将训练中受伤",
                    description="诺伊尔在训练中肩部不适，已接受检查",
                    timestamp=datetime(2026, 6, 21, 9, 0, tzinfo=timezone.utc),
                    severity=TeamEventSeverity.HIGH, confidence=0.80),
        TeamEventIn(provider="database", source_id="", team_id="spain", team_name="西班牙",
                    event_type="form", title="西班牙热身赛三连胜",
                    description="西班牙队近期三场热身赛全胜，打进10球仅失1球",
                    timestamp=datetime(2026, 6, 19, 22, 0, tzinfo=timezone.utc),
                    severity=TeamEventSeverity.MEDIUM, confidence=0.95),
    ]
    for event in seeds:
        await adapter.add_event(event)
    logger.info(f"Seeded {len(seeds)} database events")


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
    registry.register_event(DatabaseEventAdapter, "database")
    await registry.enable("mock_odds")
    await registry.enable("mock_champion_odds")
    await registry.enable("polymarket")
    await registry.enable("mock_events")
    await registry.enable("mock_team_events")
    await registry.enable("gdelt")
    await registry.enable("database")

    # Seed initial database events if table is empty
    await _seed_database_events()

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
