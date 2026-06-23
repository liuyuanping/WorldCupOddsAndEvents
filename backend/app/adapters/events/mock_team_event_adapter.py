"""Mock team event adapter — team-level events affecting championship odds."""
from datetime import datetime
from typing import List, Optional, Callable, AsyncIterator, Dict, Any

from app.adapters.base import EventProviderAdapter
from app.models.champion import TeamEventIn, TeamEventSeverity


# Major events for key teams over the 6-month period
TEAM_EVENTS = [
    # ── January 2026 ──
    ("argentina", "argentina", "阿根廷", "squad_announcement",
     "梅西确认参加2026世界杯", "梅西宣布这将是他的最后一届世界杯", "2026-01-20T14:00:00", 3, 0.95),
    ("croatia", "croatia", "克罗地亚", "retirement_rumor",
     "莫德里奇退役传闻", "媒体猜测莫德里奇可能在世界杯后退役", "2026-01-15T10:00:00", 2, 0.70),

    # ── February 2026 ──
    ("france", "france", "法国", "injury_scare",
     "姆巴佩训练中受伤，世界杯参赛成疑", "法国队核心姆巴佩在俱乐部训练中脚踝受伤，初步诊断需休战4-6周", "2026-02-15T09:30:00", 4, 0.88),
    ("germany", "germany", "德国", "poor_results",
     "德国队国家联赛表现不佳", "德国队近5场国家联赛仅1胜，主帅纳格尔斯曼面临压力", "2026-02-01T16:00:00", 2, 0.90),
    ("belgium", "belgium", "比利时", "aging_squad",
     "比利时黄金一代老化担忧", "比利时多名核心球员年龄超过33岁，体能成为隐患", "2026-02-10T11:00:00", 2, 0.75),

    # ── March 2026 ──
    ("england", "england", "英格兰", "player_award",
     "凯恩荣膺德甲金靴", "哈里·凯恩在拜仁慕尼黑打入35球，状态火热", "2026-03-10T15:00:00", 3, 0.95),
    ("brazil", "brazil", "巴西", "injury_scare",
     "内马尔伤病疑虑", "内马尔在俱乐部比赛中被换下，赛前体检结果待公布", "2026-03-25T20:00:00", 4, 0.80),
    ("spain", "spain", "西班牙", "young_talent",
     "亚马尔、加维等新星在西甲大放异彩", "西班牙年轻一代在联赛中展现统治力", "2026-03-15T12:00:00", 2, 0.85),
    ("italy", "italy", "意大利", "qualification_concern",
     "意大利队资格赛表现引担忧", "意大利在世界杯预选赛中表现不稳，连续两场平局", "2026-03-20T18:00:00", 3, 0.85),
    ("usa", "usa", "美国", "home_advantage",
     "主场优势引发关注", "美国作为联合主办国之一，主场作战优势被广泛讨论", "2026-03-01T10:00:00", 2, 0.80),
    ("japan", "japan", "日本", "technical_impress",
     "日本队技术流打法引关注", "日本队在热身赛中展示出高水准的传控足球", "2026-03-20T14:00:00", 2, 0.80),
    ("morocco", "morocco", "摩洛哥", "afcon_performance",
     "摩洛哥非洲杯表现强劲", "摩洛哥在非洲杯半决赛中击败强敌晋级", "2026-04-01T20:00:00", 3, 0.90),

    # ── April 2026 ──
    ("portugal", "portugal", "葡萄牙", "player_form",
     "C罗状态持续，联赛进球数领先", "40岁的C罗在沙特联赛依然保持场均1球的效率", "2026-03-01T08:00:00", 2, 0.85),
    ("france", "france", "法国", "player_return",
     "姆巴佩恢复训练，预计世界杯前完全康复", "法国队医确认姆巴佩恢复进度超出预期", "2026-04-20T11:00:00", 3, 0.90),
    ("germany", "germany", "德国", "coach_change",
     "德国队更换主教练，新体系初见成效", "德国队在新教练带领下两场热身赛均以大比分获胜", "2026-04-10T14:00:00", 3, 0.85),
    ("netherlands", "netherlands", "荷兰", "defensive_record",
     "荷兰队防守记录出色", "荷兰队近10场比赛仅失3球，防守端表现顶级", "2026-04-15T10:00:00", 2, 0.80),
    ("croatia", "croatia", "克罗地亚", "player_confirm",
     "莫德里奇确认参加世界杯", "38岁的莫德里奇正式宣布将参加2026世界杯", "2026-04-01T09:00:00", 3, 0.95),
    ("argentina", "argentina", "阿根廷", "aging_concern",
     "阿根廷阵容老化引担忧", "阿根廷多名2022冠军队成员年龄偏大，体能面临考验", "2026-04-05T12:00:00", 2, 0.70),
    ("brazil", "brazil", "巴西", "copa_america",
     "巴西在美洲杯中展现统治力", "巴西队一路晋级决赛，多名球员表现亮眼", "2026-05-10T22:00:00", 3, 0.90),

    # ── May 2026 ──
    ("england", "england", "英格兰", "nations_league",
     "英格兰国家联赛表现出色", "英格兰队击败强敌进入决赛，年轻阵容令对手胆寒", "2026-05-15T20:00:00", 3, 0.90),
    ("spain", "spain", "西班牙", "team_cohesion",
     "西班牙队内氛围融洽，团队配合日趋成熟", "西班牙教练组强调团队凝聚力是最大武器", "2026-05-20T10:00:00", 2, 0.80),
    ("usa", "usa", "美国", "gold_cup",
     "美国队金杯赛表现强势", "美国队主场作战，一路淘汰多支强队夺冠", "2026-05-15T18:00:00", 3, 0.88),
    ("portugal", "portugal", "葡萄牙", "tough_draw",
     "葡萄牙分组形势严峻", "葡萄牙所在小组包含两支欧洲劲旅，出线压力大", "2026-05-01T14:00:00", 2, 0.75),
    ("belgium", "belgium", "比利时", "injury_concern",
     "德布劳内伤情引发担忧", "德布劳内在俱乐部赛季末受伤，能否参加世界杯存疑", "2026-05-01T16:00:00", 4, 0.82),
    ("germany", "germany", "德国", "musiala_form",
     "穆西亚拉状态爆棚，被誉为本届最具威胁球员之一", "穆西亚拉在俱乐部赛季末连续5场进球", "2026-05-25T12:00:00", 3, 0.90),
    ("italy", "italy", "意大利", "serie_a_form",
     "意甲球员整体状态出色", "多名意大利国脚在联赛收官阶段表现亮眼", "2026-05-10T15:00:00", 2, 0.78),

    # ── June 2026 (Tournament buildup) ──
    ("brazil", "brazil", "巴西", "squad_announcement",
     "巴西公布最终23人名单，阵容豪华", "巴西队正式公布世界杯大名单，攻防两端均有顶级配置", "2026-06-01T10:00:00", 3, 0.98),
    ("argentina", "argentina", "阿根廷", "warmup_win",
     "阿根廷热身赛大胜，进攻端火力全开", "阿根廷在最后一场热身赛中以4-0击败对手", "2026-06-02T20:00:00", 2, 0.90),
    ("france", "france", "法国", "friendly_injury",
     "法国队热身赛再遭打击，主力后卫受伤", "法国队在热身赛中损失一名关键后卫，防线面临重组", "2026-06-05T18:00:00", 4, 0.85),
    ("england", "england", "英格兰", "minor_knock",
     "贝林厄姆轻伤，预计不影响世界杯首战", "英格兰队医确认贝林厄姆仅为轻微撞击，休息即可恢复", "2026-06-10T09:00:00", 1, 0.92),
    ("morocco", "morocco", "摩洛哥", "dark_horse",
     "摩洛哥被多家媒体评为本届最大黑马", "多家博彩公司和媒体将摩洛哥列为本届黑马候选", "2026-06-01T08:00:00", 2, 0.75),
    ("japan", "japan", "日本", "final_squad",
     "日本公布世界杯名单，多名旅欧球员入选", "日本队大名单中有15名旅欧球员，实力不容小觑", "2026-06-05T06:00:00", 2, 0.90),
    ("senegal", "senegal", "塞内加尔", "key_player_out",
     "塞内加尔核心球员马内因伤退出世界杯", "塞内加尔队长萨迪奥·马内确认因伤无缘本届世界杯", "2026-06-12T14:00:00", 4, 0.95),
    ("uruguay", "uruguay", "乌拉圭", "generation_change",
     "乌拉圭完成新老交替，年轻阵容令人期待", "乌拉圭新一代球员在预选赛中表现出色", "2026-06-08T10:00:00", 2, 0.80),
    ("germany", "germany", "德国", "final_prep",
     "德国队备战充分，训练营气氛良好", "德国队提前两周抵达比赛地适应气候和场地", "2026-06-15T12:00:00", 1, 0.85),
    ("netherlands", "netherlands", "荷兰", "injury_recovery",
     "荷兰队关键球员恢复训练", "荷兰队此前受伤的后防核心已恢复全队合练", "2026-06-18T10:00:00", 2, 0.85),
    ("colombia", "colombia", "哥伦比亚", "form_peak",
     "哥伦比亚前锋状态达到巅峰", "哥伦比亚当家前锋在俱乐部赛季打入40球", "2026-06-10T16:00:00", 3, 0.88),
    ("mexico", "mexico", "墨西哥", "goalkeeper_injury",
     "墨西哥主力门将受伤，替补经验不足", "墨西哥队第一门将在训练中受伤", "2026-06-20T11:00:00", 4, 0.90),
]


class MockTeamEventAdapter(EventProviderAdapter):
    """Provides team-level events for all 32 World Cup teams."""

    def __init__(self):
        self.config: dict = {}
        self._events: List[TeamEventIn] = self._generate_events()

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "Mock Team Event Provider",
            "version": "2.0.0",
            "categories": [
                "injury_scare", "player_form", "squad_announcement",
                "coach_change", "warmup_result", "retirement_rumor",
                "player_return", "afcon_performance", "copa_america",
                "nations_league", "tough_draw", "dark_horse",
                "key_player_out", "friendly_injury", "aging_concern",
            ],
            "num_events": len(TEAM_EVENTS),
        }

    async def fetch_events(
        self,
        entity_id: Optional[str] = None,
        event_type: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        keywords: Optional[List[str]] = None,
    ) -> List[TeamEventIn]:
        result = self._events

        if entity_id:
            result = [e for e in result if e.team_id == entity_id]
        if event_type:
            result = [e for e in result if e.event_type in event_type]
        if start_time:
            result = [e for e in result if e.timestamp >= start_time]
        if end_time:
            result = [e for e in result if e.timestamp <= end_time]

        return result

    async def stream_events(self, filters, on_event=None):
        for event in self._events:
            yield event

    def get_event_categories(self) -> List[str]:
        return list(set(e.event_type for e in self._events))

    def get_teams_with_events(self) -> List[str]:
        """Return team_ids that have events."""
        return list(set(e.team_id for e in self._events))

    def _generate_events(self) -> List[TeamEventIn]:
        events = []
        for i, (team_id, _eid, name, etype, title, desc, ts_str, sev, conf) in enumerate(TEAM_EVENTS):
            events.append(TeamEventIn(
                provider="mock_team_events",
                source_id=f"team_evt_{i:03d}",
                team_id=team_id,
                team_name=name,
                event_type=etype,
                title=title,
                description=desc,
                timestamp=datetime.fromisoformat(ts_str),
                severity=TeamEventSeverity(sev),
                confidence=conf,
            ))
        return events
