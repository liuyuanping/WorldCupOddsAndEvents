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

    matches = [
        # Round 1
        ("brazil","巴西","serbia","塞尔维亚","2-0","A","2026-06-11T20:00:00Z"),
        ("france","法国","peru","秘鲁","3-1","B","2026-06-12T17:00:00Z"),
        ("argentina","阿根廷","egypt","埃及","2-0","C","2026-06-12T20:00:00Z"),
        ("england","英格兰","iran","伊朗","4-0","D","2026-06-13T17:00:00Z"),
        ("spain","西班牙","japan","日本","2-1","E","2026-06-13T20:00:00Z"),
        ("germany","德国","canada","加拿大","1-1","F","2026-06-14T17:00:00Z"),
        ("portugal","葡萄牙","ghana","加纳","3-0","G","2026-06-14T20:00:00Z"),
        ("netherlands","荷兰","south_korea","韩国","2-0","H","2026-06-15T17:00:00Z"),
        # Round 2
        ("brazil","巴西","switzerland","瑞士","2-1","A","2026-06-16T20:00:00Z"),
        ("france","法国","denmark","丹麦","1-0","B","2026-06-17T17:00:00Z"),
        ("argentina","阿根廷","poland","波兰","3-2","C","2026-06-17T20:00:00Z"),
        ("england","英格兰","usa","美国","1-0","D","2026-06-18T17:00:00Z"),
        ("spain","西班牙","croatia","克罗地亚","0-0","E","2026-06-18T20:00:00Z"),
        ("germany","德国","morocco","摩洛哥","3-1","F","2026-06-19T17:00:00Z"),
        ("portugal","葡萄牙","uruguay","乌拉圭","1-1","G","2026-06-19T20:00:00Z"),
        ("netherlands","荷兰","senegal","塞内加尔","2-1","H","2026-06-20T17:00:00Z"),
        # Round 3
        ("brazil","巴西","mexico","墨西哥","3-0","A","2026-06-22T20:00:00Z"),
        ("france","法国","norway","挪威","2-0","B","2026-06-23T17:00:00Z"),
        ("argentina","阿根廷","colombia","哥伦比亚","1-0","C","2026-06-23T20:00:00Z"),
        ("england","英格兰","scotland","苏格兰","2-1","D","2026-06-24T17:00:00Z"),
        ("spain","西班牙","morocco","摩洛哥","1-0","E","2026-06-24T20:00:00Z"),
    ]
    for hid, hn, aid, an, score, grp, ts in matches:
        hs, aws = score.split("-")
        await adapter.add_event(TeamEventIn(provider="database", source_id="",
            team_id=hid, team_name=hn, event_type="match_result",
            title=f"{hn} {score} {an}",
            description=f"2026世界杯{grp}组 · {hn} {score} {an}",
            timestamp=datetime.fromisoformat(ts), severity=TeamEventSeverity.MEDIUM, confidence=1.0))
        await adapter.add_event(TeamEventIn(provider="database", source_id="",
            team_id=aid, team_name=an, event_type="match_result",
            title=f"{an} {aws}-{hs} {hn}",
            description=f"2026世界杯{grp}组 · {hn} {score} {an}",
            timestamp=datetime.fromisoformat(ts), severity=TeamEventSeverity.MEDIUM, confidence=1.0))

    logger.info(f"Seeded {len(matches)*2} match events + 5 news events")
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
