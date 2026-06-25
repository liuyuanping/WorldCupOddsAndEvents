"""Championship prediction API routes."""
import inspect
import logging
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Tuple

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
import numpy as np

logger = logging.getLogger(__name__)

from app.adapters.registry import registry
from app.models.champion import (
    ChampionOddsOut, TeamEventOut,
    ChampionPredictionResponse, ChampionPredictionResult,
)

router = APIRouter(prefix="/api/v1/champion", tags=["champion"])


# ── Team Profiles ─────────────────────────────────────

@router.get("/teams")
async def list_teams(
    provider: str = Query(default="polymarket", description="Data source: polymarket or mock_champion_odds"),
    online: bool = Query(default=False, description="Force fetch from external, bypass cache"),
):
    """List all teams with current odds and form."""
    adapter = registry.get_odds_instance(provider)
    if not adapter:
        adapter = registry.get_odds_instance("mock_champion_odds")
    if not adapter or not hasattr(adapter, 'get_teams'):
        raise HTTPException(status_code=503, detail="Champion odds data source not available")

    teams = adapter.get_teams(online=online)
    if inspect.iscoroutine(teams):
        teams = await teams
    teams.sort(key=lambda t: t.get("implied_probability", t.get("avg_odds", 999)), reverse=True)
    return {"teams": teams, "total": len(teams), "provider": provider}


# ── Champion Odds ─────────────────────────────────────

@router.get("/odds")
async def get_champion_odds(
    team_ids: str | None = Query(default=None, description="Comma-separated team IDs"),
    bookmaker: str | None = Query(default=None),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
):
    """Get champion odds for specified teams."""
    adapter = registry.get_odds_instance("mock_champion_odds")
    if not adapter:
        raise HTTPException(status_code=503, detail="Champion odds data source not available")

    team_id_list = team_ids.split(",") if team_ids else None

    records = await adapter.fetch_odds(
        bookmakers=[bookmaker] if bookmaker else None,
        start_time=datetime.fromisoformat(start_time) if start_time else None,
        end_time=datetime.fromisoformat(end_time) if end_time else None,
    )

    if team_id_list:
        records = [r for r in records if r.team_id in team_id_list]

    # Group by team_id
    result = defaultdict(list)
    for r in records:
        result[r.team_id].append({
            "team_name": r.team_name,
            "bookmaker": r.bookmaker,
            "odds_value": r.odds_value,
            "implied_probability": r.implied_probability,
            "timestamp": r.timestamp.isoformat(),
        })

    # For each team, return Pinnacle's odds timeline + latest snapshot
    output = {}
    for tid, items in result.items():
        pinnacle_items = [i for i in items if i["bookmaker"] == "Pinnacle"]
        pinnacle_items.sort(key=lambda x: x["timestamp"])
        latest = max(items, key=lambda x: x["timestamp"])
        output[tid] = {
            "team_name": latest["team_name"],
            "timeline": pinnacle_items,
            "latest": {b: round(i["odds_value"], 2)
                       for b in ["Pinnacle", "Bet365", "William Hill", "Betfair"]
                       for i in items if i["bookmaker"] == b and i["timestamp"] == max(
                    j["timestamp"] for j in items if j["bookmaker"] == b
                )},
            "latest_avg": round(sum(i["odds_value"] for i in items
                                    if i["timestamp"] == latest["timestamp"]) /
                                max(len([i for i in items if i["timestamp"] == latest["timestamp"]]), 1), 2),
        }

    return {"odds": output, "teams_count": len(output)}


# ── Team Events ────────────────────────────────────────

@router.get("/events")
async def get_team_events(
    team_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    provider: str = Query(default="mock_team_events"),
):
    """Get team-level events."""
    adapter = registry.get_event_instance(provider)
    if not adapter:
        adapter = registry.get_event_instance("mock_team_events")
    if not adapter:
        raise HTTPException(status_code=503, detail="Team event data source not available")

    events = await adapter.fetch_events(
        entity_id=team_id,
        event_type=[event_type] if event_type else None,
    )

    events.sort(key=lambda e: e.timestamp, reverse=True)
    events = events[:limit]

    return {
        "events": [
            {
                "source_id": getattr(e, 'source_id', ''),
                "team_id": e.team_id,
                "team_name": e.team_name,
                "event_type": e.event_type,
                "title": e.title,
                "description": e.description,
                "timestamp": e.timestamp.isoformat(),
                "severity": e.severity.value,
                "confidence": e.confidence,
                "source_url": getattr(e, 'source_url', ''),
            }
            for e in events
        ],
        "total": len(events),
    }


# ── Information Search ──────────────────────────────

class SearchResultItem(BaseModel):
    title: str
    description: str
    source_url: str = ""
    team_id: str = ""
    team_name: str = ""
    event_type: str = "other"
    severity: int = 2
    timestamp: str = ""
    confidence: float = 0.7


@router.get("/search")
async def search_news(
    query: str = Query(default="", description="Search keywords"),
    team_ids: str = Query(default="", description="Comma-separated team IDs"),
    limit: int = Query(default=10, le=30),
):
    """Search news from GDELT API for selected teams."""
    import httpx
    from app.adapters.events.gdelt_adapter import TEAM_QUERIES as GDELT_QUERIES, SEVERITY_KEYWORDS, EVENT_TYPE_KEYWORDS

    tid_list = team_ids.split(",") if team_ids else []
    results = []

    # Build GDELT query: simple English-only query
    team_names = {}
    team_query_parts = []
    # English names for GDELT queries
    ENG_NAMES = {"france":"France","argentina":"Argentina","spain":"Spain","england":"England",
        "portugal":"Portugal","germany":"Germany","netherlands":"Netherlands","brazil":"Brazil",
        "usa":"United States","norway":"Norway","japan":"Japan","morocco":"Morocco",
        "colombia":"Colombia","mexico":"Mexico","belgium":"Belgium","switzerland":"Switzerland",
        "croatia":"Croatia","canada":"Canada","ivory_coast":"Ivory Coast","south_korea":"South Korea",
        "senegal":"Senegal","australia":"Australia","austria":"Austria","egypt":"Egypt",
        "sweden":"Sweden","italy":"Italy","uruguay":"Uruguay","paraguay":"Paraguay",
        "czechia":"Czechia","denmark":"Denmark","tunisia":"Tunisia","serbia":"Serbia"}
    for tid in tid_list:
        info = GDELT_QUERIES.get(tid)
        if info:
            eng_name = ENG_NAMES.get(tid, tid.capitalize())
            team_query_parts.append(eng_name)
            team_names[tid] = info["name"]

    if not team_query_parts:
        return {"results": [], "total": 0, "source": "gdelt"}

    # Simple query: team names + World Cup
    team_query = " OR ".join(team_query_parts[:3])  # limit to 3 teams per query
    gdelt_query = f'({team_query}) World Cup football'
    if query:
        gdelt_query = f'({team_query}) World Cup {query}'

    logger.info(f"GDELT search: {gdelt_query[:200]}")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={
                    "query": gdelt_query,
                    "mode": "ArtList",
                    "format": "json",
                    "maxrecords": str(limit),
                    "sort": "datedesc",
                    "timespan": "90d",
                },
            )
            if resp.status_code == 429:
                # Fall back to database search
                logger.info("GDELT rate limited, falling back to database search")
                return await _search_database(tid_list, limit)

            resp.raise_for_status()
            try:
                data = resp.json()
            except Exception:
                return {"results": [], "total": 0, "source": "gdelt", "error": "parse_error"}

            articles = data.get("articles") or []
            for article in articles[:limit]:
                title = (article.get("title") or "").strip()
                url = (article.get("url") or "").strip()
                if not title:
                    continue

                seendate = article.get("seendate", "")
                try:
                    ts = datetime.strptime(seendate, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    ts = datetime.now(timezone.utc)

                # Classify event type / severity by title keywords
                title_lower = title.lower()
                evt_type = "other"
                for etype, kws in EVENT_TYPE_KEYWORDS.items():
                    if any(kw in title_lower for kw in kws):
                        evt_type = etype
                        break
                severity = 2
                for sev, kws in SEVERITY_KEYWORDS.items():
                    if any(kw in title_lower for kw in kws):
                        severity = sev.value
                        break

                # Try to match article to a team
                matched_tid = ""
                matched_name = ""
                for tid, info in GDELT_QUERIES.items():
                    if info["name"] in title or tid.capitalize() in title:
                        matched_tid = tid
                        matched_name = info["name"]
                        break

                results.append(SearchResultItem(
                    title=title[:200],
                    description=url[:200],
                    source_url=url,
                    team_id=matched_tid,
                    team_name=matched_name,
                    event_type=evt_type,
                    severity=severity,
                    timestamp=ts.isoformat(),
                    confidence=0.7,
                ))

    except Exception as e:
        logger.warning(f"GDELT search failed: {e}")
        return {"results": [], "total": 0, "source": "gdelt", "error": str(e)}

    return {"results": results, "total": len(results), "source": "gdelt"}


async def _search_database(tid_list: list, limit: int) -> dict:
    """Fallback: search local database events."""
    from sqlalchemy import select
    from app.database import async_session
    from app.models.champion import TeamEventORM

    async with async_session() as session:
        stmt = select(TeamEventORM).where(TeamEventORM.provider == "database")
        if tid_list:
            stmt = stmt.where(TeamEventORM.team_id.in_(tid_list))
        stmt = stmt.order_by(TeamEventORM.timestamp.desc()).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        results = [
            SearchResultItem(
                title=row.title,
                description=(row.description or "")[:200],
                team_id=row.team_id,
                team_name=row.team_name,
                event_type=row.event_type,
                severity=row.severity,
                timestamp=row.timestamp.isoformat(),
                confidence=row.confidence,
            ) for row in rows
        ]
    return {"results": results, "total": len(results), "source": "database"}


# ── Database Event CRUD ──────────────────────────────

class AddEventRequest(BaseModel):
    team_id: str
    team_name: str
    event_type: str
    title: str
    description: str = ""
    timestamp: str  # ISO format
    severity: int = 1  # 1-4
    confidence: float = 1.0
    source_url: str = ""


@router.post("/events/db")
async def add_database_event(req: AddEventRequest):
    """Add an event to the offline database."""
    from app.models.champion import TeamEventIn, TeamEventSeverity

    adapter = registry.get_event_instance("database")
    if not adapter or not hasattr(adapter, 'add_event'):
        raise HTTPException(status_code=503, detail="Database event adapter not available")

    event = TeamEventIn(
        provider="database",
        source_id="",
        team_id=req.team_id,
        team_name=req.team_name,
        event_type=req.event_type,
        title=req.title,
        description=req.description,
        timestamp=datetime.fromisoformat(req.timestamp),
        severity=TeamEventSeverity(req.severity),
        confidence=req.confidence,
        source_url=req.source_url,
    )
    source_id = await adapter.add_event(event)
    return {"status": "ok", "source_id": source_id}


@router.delete("/events/db/{source_id}")
async def delete_database_event(source_id: str):
    """Delete an event from the offline database."""
    adapter = registry.get_event_instance("database")
    if not adapter or not hasattr(adapter, 'delete_event'):
        raise HTTPException(status_code=503, detail="Database event adapter not available")

    deleted = await adapter.delete_event(source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"status": "ok"}


# ── Monte Carlo Champion Prediction ───────────────────

@router.get("/predict", response_model=ChampionPredictionResponse)
async def predict_champion(
    n_simulations: int = Query(default=10000, ge=1000, le=100000),
    provider: str = Query(default="polymarket"),
):
    """
    Monte Carlo simulation for World Cup champion prediction.

    Process:
    1. Get current market odds for all teams from selected provider
    2. Convert odds to implied probabilities
    3. Add team strength factors (ELO, form, events)
    4. Run N simulations of the tournament
    5. Return champion probability rankings
    """
    adapter = registry.get_odds_instance(provider)
    if not adapter or not hasattr(adapter, 'get_teams'):
        adapter = registry.get_odds_instance("mock_champion_odds")
    if not adapter or not hasattr(adapter, 'get_teams'):
        raise HTTPException(status_code=503, detail="Champion odds not available")

    teams = adapter.get_teams()
    if inspect.iscoroutine(teams):
        teams = await teams
    if not teams:
        raise HTTPException(status_code=503, detail="No team data available")

    # Build team profiles
    profiles = []
    for t in teams:
        raw_prob = t.get("implied_probability", 0)
        profiles.append({
            "team_id": t.get("team_id", ""),
            "team_name": t.get("team_name", ""),
            "flag_emoji": t.get("flag_emoji", ""),
            "elo": t.get("elo_rating", 2000),
            "market_prob": raw_prob,
            "avg_odds": t.get("avg_odds", 999),
            "trend_30d": t.get("odds_trend_30d", 0),
            "group": t.get("group", "TBD"),
        })

    # Normalize market probabilities to sum to 1
    total_mp = sum(p["market_prob"] for p in profiles)
    for p in profiles:
        p["market_prob"] = p["market_prob"] / total_mp

    # Calculate team strength score (combining ELO + market + trend + events)
    event_adapter = registry.get_event_instance("mock_team_events")
    events_by_team = defaultdict(list)
    if event_adapter:
        all_events = await event_adapter.fetch_events()
        for e in all_events:
            events_by_team[e.team_id].append(e)

    max_elo = max(p["elo"] for p in profiles)
    min_elo = min(p["elo"] for p in profiles)
    elo_range = max(max_elo - min_elo, 1)

    for p in profiles:
        # ELO component (normalized)
        elo_score = (p["elo"] - min_elo) / elo_range

        # Market component
        market_score = p["market_prob"] * 20  # Amplify differences

        # Trend component: improving teams get bonus
        trend_score = -p["trend_30d"] / 100  # Negative trend (odds shortening) = positive

        # Event component: recent positive events
        recent_events = [e for e in events_by_team.get(p["team_id"], [])
                         if e.timestamp > datetime(2026, 6, 1)]
        event_impact = 0
        for e in recent_events:
            sev = e.severity.value
            # Determine if event is positive or negative based on description
            desc = (e.description or "").lower() + (e.title or "").lower()
            is_positive = any(w in desc for w in ["复出", "恢复", "强", "胜", "好", "佳", "出色", "确认", "回归", "lead", "win", "recover", "return"])
            is_negative = any(w in desc for w in ["伤", "退", "疑", "担心", "不佳", "损失", "停赛", "injury", "out", "concern", "lose"])
            if is_positive:
                event_impact += 0.003 * sev
            elif is_negative:
                event_impact -= 0.003 * sev

        # Combined strength
        strength = 0.35 * elo_score + 0.50 * market_score + 0.10 * trend_score + 0.05 * event_impact
        p["strength"] = max(strength, 0.001)

    # Normalize strengths to probabilities
    total_s = sum(p["strength"] for p in profiles)
    for p in profiles:
        p["sim_prob_raw"] = p["strength"] / total_s

    # Monte Carlo simulation
    rng = np.random.RandomState(42)
    champion_counts = defaultdict(int)

    for _ in range(n_simulations):
        # Sample champion using Dirichlet-like noise on probabilities
        probs = np.array([p["sim_prob_raw"] for p in profiles])
        # Add controlled randomness
        noise = rng.dirichlet(np.ones(len(profiles)) * 0.1)  # Small noise
        probs = 0.95 * probs + 0.05 * noise
        probs = probs / probs.sum()

        winner_idx = rng.choice(len(profiles), p=probs)
        champion_counts[winner_idx] += 1

    # Build results
    results = []
    for i, p in enumerate(profiles):
        sim_prob = champion_counts[i] / n_simulations
        market_prob = p["market_prob"]
        edge = sim_prob - market_prob
        results.append(ChampionPredictionResult(
            team_id=p["team_id"],
            team_name=p["team_name"],
            flag_emoji=p["flag_emoji"],
            market_probability=round(market_prob * 100, 2),
            sim_probability=round(sim_prob * 100, 2),
            value_edge_pct=round(edge * 100, 3),
            elo_rating=p["elo"],
            group=p["group"],
        ))

    results.sort(key=lambda r: r.sim_probability, reverse=True)

    # Picks
    top_pick = results[0]
    value_pick = max(results, key=lambda r: r.value_edge_pct)
    dark_horse = max(
        [r for r in results if r.sim_probability < top_pick.sim_probability / 2],
        key=lambda r: r.value_edge_pct,
        default=results[-1]
    )

    return ChampionPredictionResponse(
        rankings=results,
        total_simulations=n_simulations,
        timestamp=datetime.utcnow(),
        top_pick=top_pick,
        value_pick=value_pick,
        dark_horse=dark_horse,
    )


# ── Price History (Polymarket) ────────────────────────

@router.get("/price-history/{team_id}")
async def get_price_history(
    team_id: str,
    provider: str = Query(default="polymarket"),
    interval: str = Query(default="1w"),
    fidelity: int = Query(default=30),
):
    """Get price history for a team from Polymarket CLOB."""
    adapter = registry.get_odds_instance(provider)
    if not adapter or not hasattr(adapter, 'get_price_history'):
        raise HTTPException(status_code=503, detail="Price history not available for this provider")

    history = await adapter.get_price_history(team_id, interval=interval, fidelity=fidelity)
    info = adapter._fetch_live_prices.__doc__  # just get team info
    team_info = {"team_id": team_id}

    return {
        "team_id": team_id,
        "interval": interval,
        "history": history,
    }


# ── Odds Trend (for charting) ─────────────────────────

@router.get("/trend")
async def get_odds_trend(
    team_ids: str = Query(default="brazil,france,england,argentina"),
    bookmaker: str = Query(default="Pinnacle"),
    provider: str = Query(default="polymarket"),
    interval: str = Query(default="1m", description="1h, 6h, 1d, 1w, 1m, all (CLOB retains ~30 days)"),
):
    """Get odds trend data for selected teams (for line chart)."""
    tid_list = team_ids.split(",")
    result = {}

    if provider == "polymarket":
        # Use Polymarket CLOB price history
        adapter = registry.get_odds_instance("polymarket")
        if adapter and hasattr(adapter, 'get_price_history'):
            # Fidelity + startTs gives full history from market creation (~2025-07-01).
            # Lower fidelity = more data points. 720 ≈ ~700 pts/year, 60 ≈ ~15K pts/year.
            fidelity_map = {"1h": 60, "6h": 120, "1d": 360, "1w": 720, "1m": 720, "all": 720}
            fidelity = fidelity_map.get(interval, 20)

            for tid in tid_list:
                try:
                    history = await adapter.get_price_history(tid, interval=interval, fidelity=fidelity)
                    if not history:
                        continue
                    info = adapter.POLYMARKET_TEAMS.get(tid, {}) if hasattr(adapter, 'POLYMARKET_TEAMS') else {}
                    # Downsample if too many points (>500): keep first, last, and evenly spaced
                    pts = history
                    if len(pts) > 500:
                        step = len(pts) / 500
                        pts = [pts[0]] + [pts[int(i * step)] for i in range(1, 500)] + [pts[-1]]
                    result[tid] = {
                        "team_name": info.get("name", tid),
                        "flag_emoji": info.get("flag", ""),
                        "data": [
                            {"timestamp": h["timestamp"], "odds": round(1.0 / max(h["price"], 0.0001), 2),
                             "prob": round(h["price"], 4)}
                            for h in pts
                        ],
                    }
                except Exception as e:
                    logger.warning(f"Failed to get price history for {tid}: {e}")
                    continue

        if result:
            return {"series": result}

    # Fallback to mock data
    adapter = registry.get_odds_instance("mock_champion_odds")
    if not adapter:
        raise HTTPException(status_code=503, detail="Not available")

    records = await adapter.fetch_odds(bookmakers=[bookmaker])

    for tid in tid_list:
        team_records = [r for r in records if r.team_id == tid]
        team_records.sort(key=lambda r: r.timestamp)
        if team_records:
            result[tid] = {
                "team_name": team_records[0].team_name,
                "flag_emoji": team_records[0].metadata.get("flag", ""),
                "data": [
                    {"timestamp": r.timestamp.isoformat(), "odds": r.odds_value, "prob": r.implied_probability}
                    for r in team_records
                ],
            }

    return {"series": result}
