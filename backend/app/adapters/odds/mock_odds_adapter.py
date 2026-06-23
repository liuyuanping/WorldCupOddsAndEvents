"""Mock odds adapter that generates realistic synthetic data."""
import math
import random
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Callable, AsyncIterator, Dict, Any

from app.adapters.base import OddsProviderAdapter
from app.models.odds import OddsRecordIn, OddsFormat


class MockOddsAdapter(OddsProviderAdapter):
    """
    Mock odds data source.

    Generates realistic-looking odds timelines for World Cup matches.
    Simulates: pre-match drift, in-play volatility, event-driven jumps.
    """

    def __init__(self):
        self.config: dict = {}
        self._rng = random.Random(42)
        self._match_cache: Dict[str, List[OddsRecordIn]] = {}

    # ── Interface ───────────────────────────────────

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "Mock Odds Provider",
            "version": "1.0.0",
            "supported_markets": ["h2h", "over_under", "asian_handicap"],
            "supported_bookmakers": ["Pinnacle", "Bet365", "William Hill", "Betfair"],
            "update_frequency": "simulated",
            "latency_ms": 10,
            "documentation_url": "https://mock.local",
        }

    async def fetch_odds(
        self,
        match_id: Optional[str] = None,
        league: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        bookmakers: Optional[List[str]] = None,
        markets: Optional[List[str]] = None,
    ) -> List[OddsRecordIn]:
        """Fetch odds — generate on demand if not cached."""
        if match_id and match_id in self._match_cache:
            records = self._match_cache[match_id]
        else:
            records = self._generate_match_odds(match_id or "wc2026_eng_fra")
            if match_id:
                self._match_cache[match_id] = records

        # Apply filters
        result = records
        if start_time:
            result = [r for r in result if r.timestamp >= start_time]
        if end_time:
            result = [r for r in result if r.timestamp <= end_time]
        if bookmakers:
            result = [r for r in result if r.bookmaker in bookmakers]
        if markets:
            result = [r for r in result if r.market in markets]
        return result

    async def stream_odds(
        self,
        match_ids: List[str],
        on_update: Callable[[OddsRecordIn], None],
    ) -> AsyncIterator[OddsRecordIn]:
        """Simulate streaming by yielding cached records."""
        for match_id in match_ids:
            records = await self.fetch_odds(match_id=match_id)
            for record in records:
                yield record

    def get_supported_markets(self) -> List[str]:
        return ["h2h", "over_under", "asian_handicap"]

    def get_supported_bookmakers(self) -> List[str]:
        return ["Pinnacle", "Bet365", "William Hill", "Betfair"]

    # ── Data Generation ──────────────────────────────

    def _generate_match_odds(self, match_id: str) -> List[OddsRecordIn]:
        """
        Generate a 6-hour odds timeline for a match.

        Simulates:
        - Pre-match period (6h to 30min before kickoff): slow drift
        - Pre-match buildup (30min to kickoff): moderate volatility
        - First half: high volatility, event spikes
        - Half-time break: adjustment period
        - Second half: high volatility, event spikes
        """
        records = []
        kickoff = datetime(2026, 6, 23, 15, 0, 0)
        bookmakers = ["Pinnacle", "Bet365", "William Hill", "Betfair"]
        markets = ["h2h", "over_under"]

        # Base odds for England vs France
        base_home = 2.80    # England
        base_draw = 3.20
        base_away = 2.60    # France
        base_ou25 = 1.90    # Over 2.5 goals

        # Generate every 30 seconds from 6h before to 2h after kickoff
        start = kickoff - timedelta(hours=6)
        end = kickoff + timedelta(hours=2)
        current = start
        tick = 0

        while current <= end:
            minutes_to_kickoff = (current - kickoff).total_seconds() / 60.0
            is_in_play = minutes_to_kickoff >= 0

            # Volatility regime
            if minutes_to_kickoff < -120:
                volatility = 0.0003   # Very low
            elif minutes_to_kickoff < -30:
                volatility = 0.0008   # Moderate buildup
            elif minutes_to_kickoff < 0:
                volatility = 0.002    # Pre-kickoff excitement
            elif minutes_to_kickoff < 45:
                volatility = 0.005    # First half
            elif minutes_to_kickoff < 60:
                volatility = 0.003    # Half-time
            else:
                volatility = 0.005    # Second half

            # Simulate event-driven shock at specific times
            shock = 1.0
            # 10:32 - Mbappe injury rumor (the example from the design doc)
            if abs((current - datetime(2026, 6, 23, 10, 32, 0)).total_seconds()) < 60:
                shock = 1.12  # France odds drift up (worsen)
                volatility *= 3
            # 14:05 - Starting XI announced
            if abs((current - datetime(2026, 6, 23, 14, 5, 0)).total_seconds()) < 120:
                volatility *= 2
            # 15:23 - Goal scored (in-play)
            if abs((current - datetime(2026, 6, 23, 15, 23, 0)).total_seconds()) < 30:
                shock = 0.85  # Big market move
                volatility *= 8
            # 16:02 - Red card
            if abs((current - datetime(2026, 6, 23, 16, 2, 0)).total_seconds()) < 30:
                shock = 1.25
                volatility *= 10

            for bm in bookmakers:
                bm_bias = {"Pinnacle": 1.00, "Bet365": 1.01, "William Hill": 1.02, "Betfair": 0.99}[bm]

                # h2h market
                for sel, base in [("home", base_home), ("draw", base_draw), ("away", base_away)]:
                    noise = self._rng.gauss(0, volatility)
                    walk = math.sin(tick * 0.001 + hash(sel) % 100) * volatility * 2
                    value = base * shock * bm_bias * (1 + noise + walk)
                    value = max(1.05, min(value, 100.0))

                    records.append(OddsRecordIn(
                        provider="mock_odds",
                        source_id=f"mock_{bm}_{sel}_{tick}",
                        match_id=match_id,
                        bookmaker=bm,
                        market="h2h",
                        selection=sel,
                        odds_value=round(value, 3),
                        odds_format=OddsFormat.DECIMAL,
                        implied_probability=round(1.0 / value, 4),
                        timestamp=current,
                        received_at=current + timedelta(milliseconds=self._rng.randint(50, 500)),
                    ))

                # over_under market
                for sel, base_ou in [("over_2.5", base_ou25), ("under_2.5", 1 / (1 - 1/base_ou25 + 1e-9))]:
                    noise = self._rng.gauss(0, volatility)
                    value = base_ou * bm_bias * (1 + noise)
                    value = max(1.05, min(value, 50.0))

                    records.append(OddsRecordIn(
                        provider="mock_odds",
                        source_id=f"mock_{bm}_{sel}_{tick}",
                        match_id=match_id,
                        bookmaker=bm,
                        market="over_under",
                        selection=sel,
                        odds_value=round(value, 3),
                        odds_format=OddsFormat.DECIMAL,
                        implied_probability=round(1.0 / value, 4),
                        timestamp=current,
                        received_at=current + timedelta(milliseconds=self._rng.randint(50, 500)),
                    ))

            # Advance time
            if is_in_play:
                current += timedelta(seconds=15)  # Higher frequency in-play
            else:
                current += timedelta(seconds=30)
            tick += 1

        return records
