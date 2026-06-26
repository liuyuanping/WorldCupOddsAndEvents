"""Championship prediction API routes."""
import inspect
import json
import logging
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
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
                "provider": getattr(e, 'provider', ''),
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
    """Search news about teams using DuckDuckGo."""
    from ddgs import DDGS

    tid_list = team_ids.split(",") if team_ids else []
    results = []
    ENG_NAMES = {"france":"France","argentina":"Argentina","spain":"Spain","england":"England",
        "portugal":"Portugal","germany":"Germany","netherlands":"Netherlands","brazil":"Brazil",
        "usa":"USA","norway":"Norway","japan":"Japan","morocco":"Morocco","colombia":"Colombia",
        "mexico":"Mexico","belgium":"Belgium","switzerland":"Switzerland","croatia":"Croatia",
        "canada":"Canada","ivory_coast":"Ivory Coast","south_korea":"South Korea","senegal":"Senegal"}

    # Build injury/doubt keywords
    INJURY_KWS = ["injury","injured","hurt","doubt","knock","strain","骨折","受伤","伤"]

    for tid in tid_list[:3]:  # Max 3 teams
        eng = ENG_NAMES.get(tid, tid.capitalize())
        search_query = f"{eng} 2026 World Cup football"
        if query:
            search_query = f"{eng} {query} 2026 World Cup"

        try:
            with DDGS() as ddgs:
                ddgs_results = list(ddgs.text(search_query, max_results=limit))
        except Exception as e:
            logger.warning(f"DuckDuckGo search failed for {tid}: {e}")
            continue

        for r in ddgs_results[:limit]:
            title = (r.get("title") or "").strip()
            href = (r.get("href") or "").strip()
            body = (r.get("body") or "")[:200]
            if not title:
                continue

            title_lower = title.lower()
            evt_type = "injury" if any(k in title_lower for k in INJURY_KWS) else "other"
            severity = 3 if any(k in title_lower for k in INJURY_KWS) else 2

            team_name = ENG_NAMES.get(tid, tid.capitalize())
            results.append(SearchResultItem(
                title=title,
                description=body,
                source_url=href,
                team_id=tid,
                team_name=team_name,
                event_type=evt_type,
                severity=severity,
                timestamp=datetime.now(timezone.utc).isoformat(),
                confidence=0.6,
            ))

    return {"results": results, "total": len(results), "source": "duckduckgo"}


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


class AIAnalyzeRequest(BaseModel):
    team_id: str
    team_name: str
    start_time: str = ""
    end_time: str = ""
    trend_data: list = []
    search_results: list = []

    class Config:
        extra = "allow"


@router.post("/ai-analyze")
async def ai_analyze(req: AIAnalyzeRequest):
    """AI analysis: use LLM to analyze trend + news → structured event."""
    from openai import OpenAI

    # Load LLM settings from database
    llm_key = ""
    llm_url = "https://api.deepseek.com"
    llm_model = "deepseek-v4-flash"
    try:
        from sqlalchemy import select
        from app.database import async_session
        from app.models.champion import TeamEventORM

        async with async_session() as session:
            for k in ("llm_api_key", "llm_base_url", "llm_model"):
                stmt = select(TeamEventORM).where(TeamEventORM.provider == "__llm__", TeamEventORM.event_type == k)
                result = await session.execute(stmt)
                if row := result.scalar_one_or_none():
                    val = row.title
                    if k == "llm_api_key":
                        llm_key = val
                    elif k == "llm_base_url":
                        llm_url = val or "https://api.deepseek.com"
                    elif k == "llm_model":
                        llm_model = val or "deepseek-v4-flash"
    except Exception as e:
        logger.warning(f"Failed to load LLM settings from DB: {e}")

    if not llm_key:
        return {"error": "请先在设置页面配置 LLM API Key", "title": "", "description": "", "event_type": "other", "severity": 1, "confidence": 0, "source_url": "", "timestamp": datetime.now(timezone.utc).isoformat()}

    # Prepare trend summary
    trend_summary = "无趋势数据"
    if req.trend_data and len(req.trend_data) >= 2:
        first = req.trend_data[0].get("prob", 0) if isinstance(req.trend_data[0], dict) else 0
        last = req.trend_data[-1].get("prob", 0) if isinstance(req.trend_data[-1], dict) else 0
        first_pct = first * 100
        last_pct = last * 100
        direction = "上升" if last_pct > first_pct else ("下降" if last_pct < first_pct else "平稳")
        change = abs(last_pct - first_pct)
        trend_summary = (
            f"{req.team_name}夺冠概率从{first_pct:.1f}%变化到{last_pct:.1f}%（{direction}，变动{change:.1f}个百分点）"
        )
        if len(req.trend_data) > 2:
            trend_summary += f"，共{len(req.trend_data)}个数据点"

    # Prepare news summary
    news_lines = []
    for r in (req.search_results or []):
        title = r.get("title", "") if isinstance(r, dict) else ""
        if title:
            news_lines.append(f"- {title[:120]}")
    news_summary = "\n".join(news_lines[:5]) or "无相关新闻"

    # Build LLM prompt
    system_prompt = """你是一个专业的足球赛事分析师。你需要根据提供的赔率趋势数据和新闻信息，生成一个结构化的球队事件。

请按以下JSON格式回复，必须只返回JSON，不要包含任何其他内容（不要markdown、不要代码块标记）：
{
  "title": "事件标题（中文，简洁概括）",
  "description": "事件描述（中文，包含趋势变化、具体数据、新闻依据，150-300字）",
  "event_type": "事件类型（只能从以下选一个：injury/squad/form/transfer/manager/record/elimination/upset/suspension/other）",
  "severity": 严重程度（1-4的整数，1=低 2=中 3=高 4=严重）
}"""

    user_prompt = f"""请分析以下数据：

【球队】{req.team_name}（{req.team_id}）
【分析时段】{req.start_time} 至 {req.end_time}

【胜率趋势】
{trend_summary}

【相关新闻】
{news_summary}

请分析该球队夺冠概率的变化趋势和原因，生成一个事件。"""

    try:
        client = OpenAI(api_key=llm_key, base_url=llm_url)
        response = client.chat.completions.create(
            model=llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        content = response.choices[0].message.content.strip()
        # Strip markdown code block if present
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            content = content.rsplit("```", 1)[0].strip()
            if content.startswith("json"):
                content = content[4:].strip()
        result = json.loads(content)
        title = result.get("title", f"{req.team_name}趋势分析")
        description = result.get("description", "")
        evt_type = result.get("event_type", "other")
        severity = int(result.get("severity", 2))
        severity = max(1, min(4, severity))

    except Exception as e:
        logger.warning(f"LLM analysis failed, falling back to rule-based: {e}")
        # Fallback: simple rule-based
        first_prob = 0
        last_prob = 0
        if req.trend_data and len(req.trend_data) >= 2:
            first_prob = (req.trend_data[0].get("prob", 0) or 0) * 100 if isinstance(req.trend_data[0], dict) else 0
            last_prob = (req.trend_data[-1].get("prob", 0) or 0) * 100 if isinstance(req.trend_data[-1], dict) else 0
        direction = "上升" if last_prob > first_prob else ("下降" if last_prob < first_prob else "平稳")
        title = f"{req.team_name}夺冠概率{direction}"
        description = f"AI分析：{req.team_name}近期夺冠概率呈{direction}趋势。"
        if last_prob != first_prob and first_prob > 0:
            description += f"从{first_prob:.1f}%变动至{last_prob:.1f}%。"
        evt_type = "other"
        severity = 2

    # Timestamp from end_time
    try:
        event_ts = datetime.fromisoformat(req.end_time.replace("Z", "+00:00")) if req.end_time else datetime.now(timezone.utc)
    except (ValueError, AttributeError):
        event_ts = datetime.now(timezone.utc)

    return {
        "title": title,
        "description": description,
        "event_type": evt_type,
        "severity": severity,
        "confidence": 0.85,
        "source_url": "",
        "timestamp": event_ts.isoformat(),
    }


# ── LLM Settings ─────────────────────────────────────

@router.get("/llm-settings")
async def get_llm_settings():
    """Get current LLM configuration (key masked)."""
    from sqlalchemy import select
    from app.database import async_session
    from app.models.champion import TeamEventORM

    result = {"base_url": "https://api.deepseek.com", "model": "deepseek-v4-flash", "has_key": False}
    async with async_session() as session:
        for k in ("llm_api_key", "llm_base_url", "llm_model"):
            stmt = select(TeamEventORM).where(TeamEventORM.provider == "__llm__", TeamEventORM.event_type == k)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row:
                if k == "llm_api_key":
                    result["has_key"] = bool(row.title)
                elif k == "llm_base_url":
                    result["base_url"] = row.title or "https://api.deepseek.com"
                elif k == "llm_model":
                    result["model"] = row.title or "deepseek-v4-flash"
    return result


class LLMSettingsRequest(BaseModel):
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"


@router.post("/llm-settings")
async def set_llm_settings(req: LLMSettingsRequest):
    """Save LLM configuration to database."""
    from sqlalchemy import select
    from app.database import async_session
    from app.models.champion import TeamEventORM
    from datetime import timezone

    async with async_session() as s:
        now = datetime.now(timezone.utc)
        for key, val in [("llm_api_key", req.api_key), ("llm_base_url", req.base_url), ("llm_model", req.model)]:
            stmt = select(TeamEventORM).where(TeamEventORM.provider == "__llm__", TeamEventORM.event_type == key)
            row = (await s.execute(stmt)).scalar_one_or_none()
            if row:
                row.title = val
            else:
                s.add(TeamEventORM(
                    provider="__llm__", source_id=f"llm_{key}",
                    team_id="__system__", team_name="System",
                    event_type=key, title=val, description="",
                    timestamp=now,
                ))
        await s.commit()
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
