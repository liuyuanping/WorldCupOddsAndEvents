"""Event-Odds correlation engine.

Combines multiple detection methods:
1. CUSUM changepoint detection around event times
2. Event window analysis (odds movement in fixed window after event)
3. Weighted scoring and ranking
"""
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import numpy as np

from app.engine.changepoint import CUSUMDetector, ChangepointResult
from app.models.event import EventRecordIn, EventSeverity
from app.models.odds import OddsRecordIn
from app.models.correlation import CorrelationCandidate


@dataclass
class WindowAnalysisResult:
    """Result of event window analysis."""
    event_id: str
    curve_id: str
    pre_event_mean: float
    post_event_max_move: float      # max % change in window
    post_event_mean: float
    direction: str                  # "up", "down", "neutral"
    lag_seconds: Optional[float]    # seconds to max change
    score: float                    # 0-1


class EventOddsCorrelationEngine:
    """
    Main correlation engine.

    For each (event, curve) pair:
    1. Run CUSUM on the odds series around the event time
    2. Analyze the fixed window after the event for odds movement
    3. Fuse scores into a final correlation score
    """

    def __init__(
        self,
        cusum_threshold: float = 4.0,
        event_window_seconds: float = 300.0,  # 5 min window
        pre_event_window_seconds: float = 120.0,  # 2 min baseline
        min_score: float = 0.3,
    ):
        self.cusum_threshold = cusum_threshold
        self.event_window = event_window_seconds
        self.pre_event_window = pre_event_window_seconds
        self.min_score = min_score

    async def detect_correlations(
        self,
        events: List[EventRecordIn],
        odds_series: Dict[str, List[OddsRecordIn]],  # curve_id → odds
        time_window: Tuple[datetime, datetime],
    ) -> List[CorrelationCandidate]:
        """
        Detect correlations between events and odds curves.

        Args:
            events: List of events to analyze.
            odds_series: Dictionary mapping curve_id to odds timeline.
            time_window: Overall analysis time window.

        Returns:
            Ranked list of correlation candidates.
        """
        candidates: List[CorrelationCandidate] = []

        for event in events:
            for curve_id, odds_list in odds_series.items():
                # Extract odds around the event
                nearby_odds = self._extract_window(
                    odds_list,
                    event.timestamp - timedelta(seconds=self.pre_event_window),
                    event.timestamp + timedelta(seconds=self.event_window),
                )

                if len(nearby_odds) < 10:
                    continue  # Not enough data

                # Method 1: CUSUM changepoint
                cp_results = self._run_cusum_around_event(
                    nearby_odds, event.timestamp
                )

                # Method 2: Event window analysis
                window_result = self._event_window_analysis(
                    event, curve_id, nearby_odds
                )

                # Fuse results
                score = self._fuse_scores(
                    cp_results, window_result, event.severity
                )

                if score < self.min_score:
                    continue

                # Determine best lag
                lag = window_result.lag_seconds
                if cp_results:
                    # Use the changepoint closest to the event
                    best_cp = min(cp_results, key=lambda cp: abs(
                        (cp.timestamp - event.timestamp).total_seconds()
                    ))
                    lag = abs((best_cp.timestamp - event.timestamp).total_seconds())

                direction = window_result.direction
                magnitude = window_result.post_event_max_move

                methods = []
                if cp_results:
                    methods.append("changepoint")
                if window_result.score > 0.3:
                    methods.append("event_window")

                candidates.append(CorrelationCandidate(
                    timestamp=event.timestamp,
                    score=round(score, 4),
                    magnitude=round(magnitude, 4),
                    direction=direction,
                    detection_methods=methods,
                    event_id=event.source_id or "unknown",
                    curve_id=curve_id,
                    lag_seconds=int(lag) if lag else None,
                ))

        # Sort by score descending
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates

    def _extract_window(
        self,
        odds_list: List[OddsRecordIn],
        start: datetime,
        end: datetime,
    ) -> List[OddsRecordIn]:
        """Extract odds records within a time window."""
        return [r for r in odds_list if start <= r.timestamp <= end]

    def _run_cusum_around_event(
        self,
        odds_list: List[OddsRecordIn],
        event_time: datetime,
    ) -> List[ChangepointResult]:
        """Run CUSUM detection on odds around an event."""
        detector = CUSUMDetector(threshold=self.cusum_threshold)
        results = []

        # Sort by time
        sorted_odds = sorted(odds_list, key=lambda r: r.timestamp)

        for record in sorted_odds:
            cp = detector.update(record.odds_value, record.timestamp)
            if cp:
                # Only keep changepoints close to the event
                time_diff = abs((cp.timestamp - event_time).total_seconds())
                if time_diff < self.event_window:
                    results.append(cp)

        return results

    def _event_window_analysis(
        self,
        event: EventRecordIn,
        curve_id: str,
        odds_list: List[OddsRecordIn],
    ) -> WindowAnalysisResult:
        """
        Analyze odds movement in the window after an event.

        Compares pre-event baseline to post-event movement.
        """
        sorted_odds = sorted(odds_list, key=lambda r: r.timestamp)

        # Split into pre/post event
        pre_event = [r for r in sorted_odds if r.timestamp < event.timestamp]
        post_event = [r for r in sorted_odds if r.timestamp >= event.timestamp]

        if not pre_event or not post_event:
            return WindowAnalysisResult(
                event_id=event.source_id or "unknown",
                curve_id=curve_id,
                pre_event_mean=0.0,
                post_event_max_move=0.0,
                post_event_mean=0.0,
                direction="neutral",
                lag_seconds=None,
                score=0.0,
            )

        pre_mean = float(np.mean([r.odds_value for r in pre_event[-20:]]))  # Last 20 ticks

        # Find max movement in post-event window
        max_move = 0.0
        max_move_lag = None
        post_values = [r.odds_value for r in post_event]

        for i, val in enumerate(post_values):
            move = abs(val - pre_mean) / max(pre_mean, 0.001)
            if move > max_move:
                max_move = move
                if i < len(post_event):
                    max_move_lag = (post_event[i].timestamp - event.timestamp).total_seconds()

        post_mean = float(np.mean(post_values)) if post_values else pre_mean

        # Determine direction
        if post_mean > pre_mean * 1.005:
            direction = "up"
        elif post_mean < pre_mean * 0.995:
            direction = "down"
        else:
            direction = "neutral"

        # Score: higher for bigger/faster moves
        magnitude_score = min(max_move / 0.05, 1.0)  # normalize: 5% move = full score

        # Latency bonus
        if max_move_lag is not None:
            if max_move_lag <= 30:
                latency_score = 1.0
            elif max_move_lag <= 120:
                latency_score = 0.8
            elif max_move_lag <= 300:
                latency_score = 0.5
            else:
                latency_score = 0.2
        else:
            latency_score = 0.0

        # Severity weight
        severity_weights = {
            EventSeverity.CRITICAL: 1.0,
            EventSeverity.HIGH: 0.8,
            EventSeverity.MEDIUM: 0.5,
            EventSeverity.LOW: 0.2,
        }
        severity_weight = severity_weights.get(event.severity, 0.3)

        score = magnitude_score * 0.5 + latency_score * 0.3 + severity_weight * 0.2

        return WindowAnalysisResult(
            event_id=event.source_id or "unknown",
            curve_id=curve_id,
            pre_event_mean=pre_mean,
            post_event_max_move=max_move,
            post_event_mean=post_mean,
            direction=direction,
            lag_seconds=max_move_lag,
            score=min(score, 1.0),
        )

    def _fuse_scores(
        self,
        cp_results: List[ChangepointResult],
        window_result: WindowAnalysisResult,
        severity: EventSeverity,
    ) -> float:
        """Fuse CUSUM and window analysis scores."""
        cp_score = 0.0
        if cp_results:
            # Take the highest-confidence changepoint
            cp_score = max(cp.confidence * cp.magnitude for cp in cp_results)
            cp_score = min(cp_score / 0.05, 1.0)  # normalize

        win_score = window_result.score

        # Dynamic weights: prefer CUSUM when we have clear changepoints
        if cp_results and cp_score > 0.5:
            w_cp, w_win = 0.6, 0.4
        else:
            w_cp, w_win = 0.3, 0.7

        severity_bonus = {
            EventSeverity.CRITICAL: 1.2,
            EventSeverity.HIGH: 1.1,
            EventSeverity.MEDIUM: 1.0,
            EventSeverity.LOW: 0.9,
        }[severity]

        raw_score = (w_cp * cp_score + w_win * win_score) * severity_bonus
        return min(raw_score, 1.0)
