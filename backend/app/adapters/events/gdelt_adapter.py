"""GDELT event adapter — global news for World Cup teams."""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

import httpx

from app.adapters.base import EventProviderAdapter
from app.models.champion import TeamEventIn, TeamEventSeverity

logger = logging.getLogger(__name__)

GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# Team name mappings for GDELT queries
TEAM_QUERIES: Dict[str, Dict[str, str]] = {
    "france":       {"name": "法国", "flag": "🇫🇷", "query": '("France" OR "French") AND ("World Cup") AND (football OR soccer)'},
    "argentina":    {"name": "阿根廷", "flag": "🇦🇷", "query": '("Argentina" OR "Argentine") AND ("World Cup") AND (football OR soccer)'},
    "spain":        {"name": "西班牙", "flag": "🇪🇸", "query": '("Spain" OR "Spanish") AND ("World Cup") AND (football OR soccer)'},
    "england":      {"name": "英格兰", "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "query": '("England" OR "English") AND ("World Cup") AND (football OR soccer)'},
    "portugal":     {"name": "葡萄牙", "flag": "🇵🇹", "query": '("Portugal" OR "Portuguese") AND ("World Cup") AND (football OR soccer)'},
    "germany":      {"name": "德国", "flag": "🇩🇪", "query": '("Germany" OR "German") AND ("World Cup") AND (football OR soccer)'},
    "brazil":       {"name": "巴西", "flag": "🇧🇷", "query": '("Brazil" OR "Brazilian") AND ("World Cup") AND (football OR soccer)'},
    "usa":          {"name": "美国", "flag": "🇺🇸", "query": '("USA" OR "United States") AND ("World Cup") AND (football OR soccer)'},
    "japan":        {"name": "日本", "flag": "🇯🇵", "query": '("Japan" OR "Japanese") AND ("World Cup") AND (football OR soccer)'},
    "morocco":      {"name": "摩洛哥", "flag": "🇲🇦", "query": '("Morocco" OR "Moroccan") AND ("World Cup") AND (football OR soccer)'},
}

# Event type classification
SEVERITY_KEYWORDS = {
    TeamEventSeverity.CRITICAL: [
        "injury", "injured", "out of world cup", "ruled out", "broken",
        "suspended", "banned", "scandal", "arrested", "hospital",
        "重伤", "骨折", "缺席", "禁赛", "被捕",
    ],
    TeamEventSeverity.HIGH: [
        "doubt", "doubtful", "knock", "strain", "questionable",
        "miss training", "setback", "blow", "major",
        "受伤", "可能缺席", "恐无缘",
    ],
    TeamEventSeverity.MEDIUM: [
        "squad", "announced", "called up", "named", "selection",
        "transfer", "signed for", "contract", "manager",
        "名单", "入选", "转会", "教练",
    ],
    TeamEventSeverity.LOW: [
        "training", "preparation", "friendly", "warm-up",
        "preview", "analysis", "opinion", "report",
        "训练", "热身", "展望",
    ],
}

EVENT_TYPE_KEYWORDS = {
    "injury": ["injury", "injured", "knock", "strain", "broken", "hospital", "受伤", "骨折"],
    "squad": ["squad", "called up", "named", "selection", "announced", "名单", "入选"],
    "transfer": ["transfer", "signed for", "contract", "joins", "转会", "签约"],
    "manager": ["manager", "coach", "appointed", "sacked", "教练", "下课"],
    "form": ["form", "scored", "hat-trick", "brilliant", "stunning", "进球", "帽子戏法"],
    "preview": ["preview", "analysis", "opinion", "preparation", "展望", "分析"],
}


class GDELTTeamEventAdapter(EventProviderAdapter):
    """GDELT-based team event adapter for World Cup 2026."""

    def __init__(self):
        self.config: dict = {}
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, List[TeamEventIn]] = {}
        self._cache_time: Optional[datetime] = None

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "GDELT Global News",
            "version": "1.0.0",
            "categories": list(EVENT_TYPE_KEYWORDS.keys()),
            "num_teams": len(TEAM_QUERIES),
            "data_source": "GDELT 2.0 API",
            "cache_ttl": "15 minutes",
        }

    async def initialize(self):
        self._client = httpx.AsyncClient(timeout=20.0)

    async def shutdown(self, grace_period: float = 10.0):
        if self._client:
            await self._client.aclose()

    async def health_check(self) -> bool:
        try:
            if not self._client:
                return False
            resp = await self._client.get(
                GDELT_API,
                params={
                    "query": "World Cup football",
                    "mode": "artlist",
                    "format": "json",
                    "maxrecords": 1,
                },
            )
            return resp.status_code == 200
        except Exception:
            return False

    async def fetch_events(
        self,
        entity_id: Optional[str] = None,
        event_type: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        keywords: Optional[List[str]] = None,
    ) -> List[TeamEventIn]:
        """Fetch team events from GDELT."""
        now = datetime.now(timezone.utc)

        # Use cache if fresh (<15 min)
        if self._cache_time and (now - self._cache_time).seconds < 900:
            events = []
            for team_events in self._cache.values():
                events.extend(team_events)
        else:
            events = await self._fetch_all_teams()
            self._cache_time = now

        # Apply filters
        result = events
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
        return list(EVENT_TYPE_KEYWORDS.keys())

    async def _fetch_all_teams(self) -> List[TeamEventIn]:
        """Fetch events for all tracked teams from GDELT."""
        all_events = []
        for i, (team_id, info) in enumerate(TEAM_QUERIES.items()):
            if i > 0:
                await asyncio.sleep(5.0)  # Rate limit: GDELT requires 1 req/5s
            try:
                team_events = await self._fetch_team_events(team_id, info)
                all_events.extend(team_events)
                logger.info(f"GDELT: {team_id} → {len(team_events)} events")
            except Exception as e:
                logger.warning(f"GDELT fetch failed for {team_id}: {e}")
        return all_events

    async def _fetch_team_events(
        self, team_id: str, info: Dict[str, str]
    ) -> List[TeamEventIn]:
        """Fetch GDELT articles for a single team."""
        if not self._client:
            return []

        resp = await self._client.get(
            GDELT_API,
            params={
                "query": info["query"],
                "mode": "artlist",
                "format": "json",
                "maxrecords": 10,
                "sort": "datedesc",
                "timespan": "30d",
            },
        )
        resp.raise_for_status()
        try:
            data = resp.json()
        except Exception:
            logger.warning(f"GDELT empty/invalid response for {team_id}")
            return []

        articles = data.get("articles") or []
        events = []

        for i, article in enumerate(articles):
            title = (article.get("title") or "").strip()
            url = (article.get("url") or "").strip()
            if not title or not url:
                continue  # Skip empty/broken articles
            seendate = article.get("seendate", "")
            sourcecountry = article.get("sourcecountry", "")
            tone = float(article.get("tone", "0"))
            domain = article.get("domain", "")

            # Parse timestamp
            try:
                ts = datetime.strptime(seendate, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)

            # Classify severity
            title_lower = title.lower()
            severity = TeamEventSeverity.LOW
            for sev, keywords_list in SEVERITY_KEYWORDS.items():
                if any(kw in title_lower for kw in keywords_list):
                    severity = sev
                    break

            # Classify event type
            evt_type = "preview"  # default
            for etype, keywords_list in EVENT_TYPE_KEYWORDS.items():
                if any(kw in title_lower for kw in keywords_list):
                    evt_type = etype
                    break

            # Confidence based on source reliability
            confidence = min(0.9, 0.5 + abs(tone) / 20 + (0.15 if domain else 0))

            events.append(TeamEventIn(
                provider="gdelt",
                source_id=f"gdelt_{team_id}_{i}_{article.get('id', '')}",
                event_type=evt_type,
                title=title,
                description=f"来源: {domain} ({sourcecountry}) | Tone: {tone:.1f}",
                timestamp=ts,
                severity=severity,
                confidence=round(confidence, 2),
                source_url=url,
                entities=[
                    {"type": "team", "id": team_id, "name": info["name"]},
                ],
            ))

        return events
