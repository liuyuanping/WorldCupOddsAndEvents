"""Mock champion (outright winner) odds adapter — all 32 teams, 6-month history."""
import math
import random
from datetime import datetime, timedelta
from typing import List, Optional, Callable, AsyncIterator, Dict, Any, Tuple

from app.adapters.base import OddsProviderAdapter
from app.models.champion import ChampionOddsIn


# ── 32 Teams with realistic base odds ──────────────────
TEAMS = [
    # (team_id, team_name, flag, group, base_odds, elo)
    ("brazil", "巴西", "🇧🇷", "A", 5.50, 2120),
    ("france", "法国", "🇫🇷", "B", 5.50, 2105),
    ("england", "英格兰", "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "C", 7.00, 2090),
    ("argentina", "阿根廷", "🇦🇷", "D", 7.50, 2110),
    ("spain", "西班牙", "🇪🇸", "E", 8.00, 2075),
    ("germany", "德国", "🇩🇪", "F", 9.00, 2060),
    ("portugal", "葡萄牙", "🇵🇹", "G", 11.00, 2040),
    ("netherlands", "荷兰", "🇳🇱", "H", 13.00, 2025),
    ("italy", "意大利", "🇮🇹", "A", 15.00, 2010),
    ("belgium", "比利时", "🇧🇪", "B", 17.00, 1995),
    ("uruguay", "乌拉圭", "🇺🇾", "C", 21.00, 1980),
    ("croatia", "克罗地亚", "🇭🇷", "D", 23.00, 1970),
    ("colombia", "哥伦比亚", "🇨🇴", "E", 26.00, 1950),
    ("morocco", "摩洛哥", "🇲🇦", "F", 34.00, 1930),
    ("senegal", "塞内加尔", "🇸🇳", "G", 34.00, 1920),
    ("japan", "日本", "🇯🇵", "H", 41.00, 1910),
    ("usa", "美国", "🇺🇸", "A", 41.00, 1900),
    ("mexico", "墨西哥", "🇲🇽", "B", 51.00, 1890),
    ("south_korea", "韩国", "🇰🇷", "C", 67.00, 1870),
    ("denmark", "丹麦", "🇩🇰", "D", 51.00, 1880),
    ("serbia", "塞尔维亚", "🇷🇸", "E", 67.00, 1860),
    ("switzerland", "瑞士", "🇨🇭", "F", 67.00, 1855),
    ("nigeria", "尼日利亚", "🇳🇬", "G", 81.00, 1840),
    ("egypt", "埃及", "🇪🇬", "H", 101.00, 1830),
    ("australia", "澳大利亚", "🇦🇺", "A", 101.00, 1820),
    ("iran", "伊朗", "🇮🇷", "B", 151.00, 1810),
    ("saudi_arabia", "沙特", "🇸🇦", "C", 201.00, 1790),
    ("qatar", "卡塔尔", "🇶🇦", "D", 201.00, 1785),
    ("canada", "加拿大", "🇨🇦", "E", 151.00, 1800),
    ("costa_rica", "哥斯达黎加", "🇨🇷", "F", 251.00, 1770),
    ("ghana", "加纳", "🇬🇭", "G", 201.00, 1780),
    ("tunisia", "突尼斯", "🇹🇳", "H", 251.00, 1760),
]

BOOKMAKERS = ["Pinnacle", "Bet365", "William Hill", "Betfair"]


class MockChampionOddsAdapter(OddsProviderAdapter):
    """Generates 6 months of weekly champion odds for all 32 teams."""

    def __init__(self):
        self.config: dict = {}
        self._rng = random.Random(42)
        self._cache: List[ChampionOddsIn] = []

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "Mock Champion Odds Provider",
            "version": "2.0.0",
            "supported_markets": ["outright"],
            "supported_bookmakers": BOOKMAKERS,
            "num_teams": len(TEAMS),
            "date_range": "2026-01-01 to 2026-06-23",
        }

    async def fetch_odds(
        self,
        match_id: Optional[str] = None,
        league: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        bookmakers: Optional[List[str]] = None,
        markets: Optional[List[str]] = None,
    ) -> List[ChampionOddsIn]:
        """Fetch champion odds — generate on first call, then filter."""
        if not self._cache:
            self._cache = self._generate_all_odds()

        result = self._cache

        if start_time:
            result = [r for r in result if r.timestamp >= start_time]
        if end_time:
            result = [r for r in result if r.timestamp <= end_time]
        if bookmakers:
            result = [r for r in result if r.bookmaker in bookmakers]
        if match_id:
            # match_id reused as team_id filter for champion context
            result = [r for r in result if r.team_id == match_id]

        return result

    async def stream_odds(self, match_ids, on_update=None):
        if not self._cache:
            self._cache = self._generate_all_odds()
        for r in self._cache:
            if r.team_id in match_ids:
                yield r

    def get_supported_markets(self) -> List[str]:
        return ["outright"]

    def get_supported_bookmakers(self) -> List[str]:
        return BOOKMAKERS

    def get_teams(self) -> List[Dict]:
        """Return team list with latest odds."""
        if not self._cache:
            self._cache = self._generate_all_odds()

        latest_ts = max(r.timestamp for r in self._cache)
        latest = [r for r in self._cache if r.timestamp == latest_ts]

        teams = []
        for tid, name, flag, group, base_odds, elo in TEAMS:
            team_records = [r for r in latest if r.team_id == tid]
            avg_odds = sum(r.odds_value for r in team_records) / max(len(team_records), 1)
            best_odds = min(r.odds_value for r in team_records) if team_records else base_odds
            imp_prob = 1.0 / avg_odds if avg_odds > 0 else 0

            # Calculate 30-day trend
            thirty_days_ago = latest_ts - timedelta(days=30)
            old_records = [
                r for r in self._cache
                if r.team_id == tid and r.timestamp <= thirty_days_ago
            ]
            if old_records:
                old_avg = sum(r.odds_value for r in old_records[-20:]) / min(len(old_records), 20)
                trend_30d = (avg_odds - old_avg) / old_avg * 100 if old_avg > 0 else 0
            else:
                trend_30d = 0

            teams.append({
                "team_id": tid,
                "team_name": name,
                "flag_emoji": flag,
                "group": group,
                "elo_rating": elo,
                "best_odds": round(best_odds, 2),
                "avg_odds": round(avg_odds, 2),
                "implied_probability": round(imp_prob, 4),
                "odds_trend_30d": round(trend_30d, 1),
                "recent_form": "↑ Improving" if trend_30d < -2 else ("↓ Declining" if trend_30d > 2 else "→ Stable"),
            })
        return teams

    # ── Data Generation ──────────────────────────────

    def _generate_all_odds(self) -> List[ChampionOddsIn]:
        """
        Generate weekly champion odds from Jan 1 to Jun 23, 2026.
        - Jan–Mar: bi-weekly snapshots (low activity)
        - Apr–May: weekly (qualifiers, friendlies)
        - Jun: daily (tournament buildup)
        - Event-driven spikes at specific dates
        """
        records = []
        start = datetime(2026, 1, 1, 12, 0, 0)
        end = datetime(2026, 6, 23, 12, 0, 0)

        # Generate data for each team
        for team_id, team_name, flag, group, base_odds, elo in TEAMS:
            # Each team has a "true strength" that evolves over time
            # This determines how the odds drift
            strength_events: List[Tuple[datetime, float]] = self._get_team_events(team_id)

            current = start
            tick = 0
            while current <= end:
                # Determine snapshot frequency
                if current.month <= 3:
                    interval = timedelta(days=7)  # Weekly in Q1
                elif current.month <= 5:
                    interval = timedelta(days=3)  # Every 3 days in Q2
                else:
                    interval = timedelta(days=1)  # Daily in June

                # Base volatility
                volatility = 0.03 if current.month <= 3 else (0.05 if current.month <= 5 else 0.08)

                # Apply strength events
                strength_mult = 1.0
                for evt_date, impact in strength_events:
                    days_since = (current - evt_date).days
                    if 0 <= days_since < 30:
                        # Exponential decay of impact
                        decay = math.exp(-days_since / 10)
                        strength_mult *= (1.0 + impact * decay)

                # Random walk with mean reversion toward base_odds
                distance_from_base = 1.0
                reversion = 0.001 * distance_from_base

                for bm in BOOKMAKERS:
                    bm_bias = {"Pinnacle": 0.98, "Bet365": 1.01, "William Hill": 1.03, "Betfair": 0.99}[bm]
                    noise = self._rng.gauss(0, volatility)
                    walk = math.sin(tick * 0.02 + hash(team_id) % 100) * volatility

                    odds = base_odds * strength_mult * bm_bias * (1 + noise + walk + reversion)
                    odds = max(1.50, min(odds, 1000.0))  # Clamp

                    records.append(ChampionOddsIn(
                        provider="mock_champion_odds",
                        source_id=f"champ_{team_id}_{bm}_{current.strftime('%Y%m%d')}",
                        team_id=team_id,
                        team_name=team_name,
                        bookmaker=bm,
                        odds_value=round(odds, 2),
                        implied_probability=round(1.0 / odds, 4),
                        timestamp=current,
                        received_at=current + timedelta(minutes=self._rng.randint(1, 30)),
                        metadata={"flag": flag, "group": group, "elo": elo},
                    ))

                current += interval
                tick += 1

        return records

    def _get_team_events(self, team_id: str) -> List[Tuple[datetime, float]]:
        """
        Return (date, impact_on_odds) for major team events.
        Positive impact = odds shorten (team improves).
        Negative impact = odds lengthen (team worsens).
        """
        base_events = {
            # Global events affecting all teams
        }

        # Team-specific events — major ones that shift championship odds
        team_events: Dict[str, List[Tuple[str, float]]] = {
            "brazil": [
                ("2026-03-25", -0.08),  # Neymar injury scare
                ("2026-05-10", 0.05),   # Strong Copa America showing
                ("2026-06-01", 0.10),   # Final squad announced — strong
            ],
            "france": [
                ("2026-02-15", -0.12),  # Mbappe training injury doubt
                ("2026-04-20", 0.08),   # Mbappe returns, strong form
                ("2026-06-05", -0.05),  # Key defender injured in friendly
            ],
            "england": [
                ("2026-03-10", 0.06),   # Kane wins Bundesliga golden boot
                ("2026-05-15", 0.10),   # Strong Nations League performance
                ("2026-06-10", -0.03),  # Bellingham minor knock
            ],
            "argentina": [
                ("2026-01-20", 0.04),   # Messi confirms World Cup participation
                ("2026-04-05", -0.06),  # Aging squad concerns
                ("2026-06-02", 0.08),   # Convincing warm-up wins
            ],
            "spain": [
                ("2026-03-15", 0.07),   # Young talents (Yamal) shine in La Liga
                ("2026-05-20", 0.05),   # Strong team cohesion
            ],
            "germany": [
                ("2026-02-01", -0.10),  # Poor Nations League results
                ("2026-04-10", 0.08),   # Coach change brings new system
                ("2026-05-25", 0.06),   # Musiala in phenomenal form
            ],
            "portugal": [
                ("2026-03-01", 0.05),   # Ronaldo still scoring
                ("2026-05-01", -0.04),  # Tough qualifying draw
            ],
            "netherlands": [
                ("2026-04-15", 0.06),   # Strong defensive record
            ],
            "italy": [
                ("2026-03-20", -0.08),  # Failed to qualify concerns
                ("2026-05-10", 0.06),   # Strong Serie A season
            ],
            "belgium": [
                ("2026-02-10", -0.06),  # Golden generation aging
                ("2026-05-01", -0.04),  # De Bruyne injury concern
            ],
            "morocco": [
                ("2026-04-01", 0.12),   # Strong AFCON performance
                ("2026-06-01", 0.08),   # Dark horse buzz
            ],
            "usa": [
                ("2026-03-01", 0.05),   # Home continent advantage talk
                ("2026-05-15", 0.07),   # Strong Gold Cup showing
            ],
            "japan": [
                ("2026-03-20", 0.06),   # Technical squad impressing
            ],
            "croatia": [
                ("2026-01-15", -0.05),  # Modric retirement speculation
                ("2026-04-01", 0.04),   # Modric confirms participation
            ],
        }

        events = []
        for date_str, impact in team_events.get(team_id, []):
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            dt = dt.replace(hour=12)
            events.append((dt, impact))
        return events
