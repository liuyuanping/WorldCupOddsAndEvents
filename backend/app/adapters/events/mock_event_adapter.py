"""Mock event adapter with predefined World Cup events."""
from datetime import datetime
from typing import List, Optional, Callable, AsyncIterator, Dict, Any

from app.adapters.base import EventProviderAdapter
from app.models.event import EventRecordIn, EventSeverity, EntityRef


class MockEventAdapter(EventProviderAdapter):
    """
    Mock event data source.

    Provides a predefined set of events for a simulated
    England vs France World Cup match.
    """

    def __init__(self):
        self.config: dict = {}
        self._events: List[EventRecordIn] = self._generate_events()

    # ── Interface ───────────────────────────────────

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "Mock Event Provider",
            "version": "1.0.0",
            "categories": [
                "injury", "starting_xi", "goal", "red_card",
                "yellow_card", "substitution", "halftime",
            ],
            "update_frequency": "on_demand",
        }

    async def fetch_events(
        self,
        entity_id: Optional[str] = None,
        event_type: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        keywords: Optional[List[str]] = None,
    ) -> List[EventRecordIn]:
        """Return filtered events."""
        result = self._events

        if event_type:
            result = [e for e in result if e.event_type in event_type]
        if start_time:
            result = [e for e in result if e.timestamp >= start_time]
        if end_time:
            result = [e for e in result if e.timestamp <= end_time]
        if entity_id:
            result = [
                e for e in result
                if any(ent.id == entity_id for ent in e.entities)
            ]

        return result

    async def stream_events(
        self,
        filters: Dict[str, Any],
        on_event: Callable[[EventRecordIn], None],
    ) -> AsyncIterator[EventRecordIn]:
        """Yield all events — no real streaming for mock."""
        for event in self._events:
            yield event

    def get_event_categories(self) -> List[str]:
        return [
            "injury", "starting_xi", "goal", "red_card",
            "yellow_card", "substitution", "halftime", "fulltime",
        ]

    # ── Data Generation ──────────────────────────────

    def _generate_events(self) -> List[EventRecordIn]:
        """Generate predefined World Cup match events."""
        match_date = "2026-06-23"
        england = EntityRef(type="team", id="england", name="英格兰")
        france = EntityRef(type="team", id="france", name="法国")
        mbappe = EntityRef(type="player", id="mbappe", name="Kylian Mbappé")
        kane = EntityRef(type="player", id="kane", name="Harry Kane")

        events = [
            # Pre-match
            EventRecordIn(
                provider="mock_events",
                source_id="evt_001",
                event_type="injury_announcement",
                title="姆巴佩赛前伤病疑云",
                description="法国队核心姆巴佩在训练中轻伤，出战成疑",
                timestamp=datetime(2026, 6, 23, 10, 32, 0),
                severity=EventSeverity.CRITICAL,
                confidence=0.85,
                entities=[mbappe, france],
            ),
            EventRecordIn(
                provider="mock_events",
                source_id="evt_002",
                event_type="starting_xi_announced",
                title="英格兰首发阵容公布",
                description="凯恩领衔锋线，贝林厄姆坐镇中场",
                timestamp=datetime(2026, 6, 23, 14, 5, 0),
                severity=EventSeverity.MEDIUM,
                confidence=1.0,
                entities=[kane, england],
            ),
            EventRecordIn(
                provider="mock_events",
                source_id="evt_003",
                event_type="starting_xi_announced",
                title="法国首发阵容公布 — 姆巴佩首发！",
                description="尽管有伤病传闻，姆巴佩确认首发出场",
                timestamp=datetime(2026, 6, 23, 14, 8, 0),
                severity=EventSeverity.HIGH,
                confidence=1.0,
                entities=[mbappe, france],
            ),
            # First half
            EventRecordIn(
                provider="mock_events",
                source_id="evt_004",
                event_type="goal",
                title="🏴󠁧󠁢󠁥󠁮󠁧󠁿 英格兰进球！凯恩 1-0",
                description="第23分钟，哈里·凯恩接贝林厄姆传球破门",
                timestamp=datetime(2026, 6, 23, 15, 23, 0),
                severity=EventSeverity.CRITICAL,
                confidence=1.0,
                entities=[kane, england],
            ),
            EventRecordIn(
                provider="mock_events",
                source_id="evt_005",
                event_type="yellow_card",
                title="法国队黄牌 — 琼阿梅尼",
                description="第35分钟，琼阿梅尼战术犯规吃到黄牌",
                timestamp=datetime(2026, 6, 23, 15, 35, 0),
                severity=EventSeverity.LOW,
                confidence=1.0,
                entities=[france],
            ),
            # Half-time
            EventRecordIn(
                provider="mock_events",
                source_id="evt_006",
                event_type="halftime",
                title="半场结束 — 英格兰 1-0 法国",
                description="英格兰凭借凯恩进球领先进入半场",
                timestamp=datetime(2026, 6, 23, 15, 46, 0),
                severity=EventSeverity.MEDIUM,
                confidence=1.0,
                entities=[england, france],
            ),
            # Second half
            EventRecordIn(
                provider="mock_events",
                source_id="evt_007",
                event_type="red_card",
                title="法国队红牌！于帕梅卡诺被罚下",
                description="第62分钟，于帕梅卡诺放倒凯恩被直红罚下",
                timestamp=datetime(2026, 6, 23, 16, 2, 0),
                severity=EventSeverity.CRITICAL,
                confidence=1.0,
                entities=[france],
            ),
            EventRecordIn(
                provider="mock_events",
                source_id="evt_008",
                event_type="substitution",
                title="法国换人调整",
                description="法国队连换两人，加强进攻",
                timestamp=datetime(2026, 6, 23, 16, 10, 0),
                severity=EventSeverity.MEDIUM,
                confidence=1.0,
                entities=[france],
            ),
            EventRecordIn(
                provider="mock_events",
                source_id="evt_009",
                event_type="goal",
                title="🏴󠁧󠁢󠁥󠁮󠁧󠁿 英格兰进球！贝林厄姆 2-0",
                description="第78分钟，贝林厄姆远射锁定胜局",
                timestamp=datetime(2026, 6, 23, 16, 18, 0),
                severity=EventSeverity.CRITICAL,
                confidence=1.0,
                entities=[england],
            ),
            EventRecordIn(
                provider="mock_events",
                source_id="evt_010",
                event_type="fulltime",
                title="全场结束 — 英格兰 2-0 法国",
                description="英格兰2-0战胜10人法国，晋级下一轮",
                timestamp=datetime(2026, 6, 23, 16, 50, 0),
                severity=EventSeverity.HIGH,
                confidence=1.0,
                entities=[england, france],
            ),
        ]

        return events
