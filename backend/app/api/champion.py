"""Championship prediction API routes."""
import inspect
import logging
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Tuple

from fastapi import APIRouter, Query, HTTPException
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
):
    """List all teams with current odds and form."""
    adapter = registry.get_odds_instance(provider)
    if not adapter:
        adapter = registry.get_odds_instance("mock_champion_odds")
    if not adapter or not hasattr(adapter, 'get_teams'):
        raise HTTPException(status_code=503, detail="Champion odds data source not available")

    teams = adapter.get_teams()
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
):
    """Get team-level events."""
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
                "team_id": e.team_id,
                "team_name": e.team_name,
                "event_type": e.event_type,
                "title": e.title,
                "description": e.description,
                "timestamp": e.timestamp.isoformat(),
                "severity": e.severity.value,
                "confidence": e.confidence,
            }
            for e in events
        ],
        "total": len(events),
    }


# ── Monte Carlo Champion Prediction ───────────────────

@router.get("/predict", response_model=ChampionPredictionResponse)
async def predict_champion(
    n_simulations: int = Query(default=10000, ge=1000, le=100000),
):
    """
    Monte Carlo simulation for World Cup champion prediction.

    Process:
    1. Get current market odds for all 32 teams
    2. Convert odds to implied probabilities
    3. Add team strength factors (ELO, form, events)
    4. Run N simulations of the tournament
    5. Return champion probability rankings
    """
    adapter = registry.get_odds_instance("mock_champion_odds")
    if not adapter or not hasattr(adapter, 'get_teams'):
        raise HTTPException(status_code=503, detail="Champion odds not available")

    teams = adapter.get_teams()
    if not teams:
        raise HTTPException(status_code=503, detail="No team data available")

    # Build team profiles
    profiles = []
    for t in teams:
        # Market implied probability (with margin correction)
        raw_prob = t["implied_probability"]
        # Simple margin correction: redistribute excess
        profiles.append({
            "team_id": t["team_id"],
            "team_name": t["team_name"],
            "flag_emoji": t["flag_emoji"],
            "elo": t["elo_rating"],
            "market_prob": raw_prob,
            "avg_odds": t["avg_odds"],
            "trend_30d": t["odds_trend_30d"],
            "group": t["group"],
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
):
    """Get odds trend data for selected teams (for line chart)."""
    tid_list = team_ids.split(",")
    result = {}

    if provider == "polymarket":
        # Use Polymarket CLOB price history
        adapter = registry.get_odds_instance("polymarket")
        if adapter and hasattr(adapter, 'get_price_history'):
            for tid in tid_list:
                try:
                    history = await adapter.get_price_history(tid, interval="1w", fidelity=30)
                    if not history:
                        continue
                    info = adapter.POLYMARKET_TEAMS.get(tid, {}) if hasattr(adapter, 'POLYMARKET_TEAMS') else {}
                    result[tid] = {
                        "team_name": info.get("name", tid),
                        "flag_emoji": info.get("flag", ""),
                        "data": [
                            {"timestamp": h["timestamp"], "odds": round(1.0 / max(h["price"], 0.0001), 2),
                             "prob": round(h["price"], 4)}
                            for h in history
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
