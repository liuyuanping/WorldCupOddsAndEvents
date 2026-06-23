"""CUSUM changepoint detection for odds time series."""
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
import numpy as np


@dataclass
class ChangepointResult:
    """A detected changepoint in an odds time series."""
    timestamp: datetime
    confidence: float          # 0-1
    magnitude: float           # relative change magnitude
    direction: str             # "up" | "down"
    pre_mean: float            # mean before changepoint
    post_mean: float           # mean after changepoint
    detection_lag_ms: float = 0.0


class CUSUMDetector:
    """
    Dual-direction CUSUM changepoint detector.

    Maintains two cumulative sums:
    - S_pos: detects upward shifts (odds increasing)
    - S_neg: detects downward shifts (odds decreasing)

    Mathematical foundation:
        S_0 = 0
        S_t = max(0, S_{t-1} + (x_t - μ_0 - k))
        Trigger when S_t > h (control limit)
    """

    def __init__(
        self,
        threshold: float = 4.0,           # h: control limit
        drift: float = 0.5,               # k: allowable drift
        estimation_window: int = 60,      # points for mean estimation
        min_change_magnitude: float = 0.005,  # minimum relative change
    ):
        self.h = threshold
        self.k = drift
        self.estimation_window = estimation_window
        self.min_change = min_change_magnitude

        # State
        self.S_pos = 0.0
        self.S_neg = 0.0
        self.mu_hat: Optional[float] = None
        self.sigma_hat: Optional[float] = None
        self.buffer: List[Tuple[datetime, float]] = []

    def update(self, value: float, timestamp: datetime) -> Optional[ChangepointResult]:
        """Process one data point, return changepoint if detected."""
        self.buffer.append((timestamp, value))

        # Maintain sliding window
        max_buffer = self.estimation_window * 4
        if len(self.buffer) > max_buffer:
            self.buffer = self.buffer[-max_buffer:]

        # Periodically re-estimate mean
        if len(self.buffer) >= self.estimation_window and len(self.buffer) % (self.estimation_window // 2) == 0:
            recent_values = [v for _, v in self.buffer[-self.estimation_window:]]
            self.mu_hat = float(np.mean(recent_values))
            self.sigma_hat = float(np.std(recent_values)) if len(recent_values) > 1 else 0.001

        if self.mu_hat is None or self.sigma_hat is None:
            return None

        # Normalize deviation
        norm_dev = (value - self.mu_hat) / max(self.sigma_hat, 0.001)

        # Update CUSUM statistics
        self.S_pos = max(0.0, self.S_pos + norm_dev - self.k)
        self.S_neg = max(0.0, self.S_neg - norm_dev - self.k)

        # Check triggers
        if self.S_pos > self.h:
            result = self._build_result(value, "up", timestamp)
            self._reset()
            return result

        if self.S_neg > self.h:
            result = self._build_result(value, "down", timestamp)
            self._reset()
            return result

        return None

    def _build_result(self, value: float, direction: str, ts: datetime) -> ChangepointResult:
        """Build changepoint result with pre/post statistics."""
        if len(self.buffer) >= self.estimation_window * 2:
            half = len(self.buffer) // 2
            pre_vals = [v for _, v in self.buffer[-2 * half:-half]]
            post_vals = [v for _, v in self.buffer[-half:]]
            pre_mean = float(np.mean(pre_vals)) if pre_vals else self.mu_hat
            post_mean = float(np.mean(post_vals)) if post_vals else value
        else:
            pre_mean = self.mu_hat or value
            post_mean = value

        magnitude = abs(post_mean - pre_mean) / max(abs(pre_mean), 0.001)

        # Confidence based on how far S exceeded h
        max_S = self.S_pos if direction == "up" else self.S_neg
        confidence = min(max_S / (self.h * 2), 1.0)

        # Penalize tiny changes
        if magnitude < self.min_change:
            confidence *= magnitude / self.min_change

        return ChangepointResult(
            timestamp=ts,
            confidence=confidence,
            magnitude=magnitude,
            direction=direction,
            pre_mean=pre_mean,
            post_mean=post_mean,
        )

    def _reset(self):
        """Reset CUSUM state after detection."""
        self.S_pos = 0.0
        self.S_neg = 0.0


def detect_changepoints(
    odds_series: List[Tuple[datetime, float]],
    threshold: float = 4.0,
) -> List[ChangepointResult]:
    """
    Convenience function: run CUSUM on a complete odds series.

    Args:
        odds_series: List of (timestamp, odds_value) sorted by time.
        threshold: CUSUM control limit.

    Returns:
        List of detected changepoints sorted by time.
    """
    detector = CUSUMDetector(threshold=threshold)
    results = []

    for ts, value in odds_series:
        cp = detector.update(value, ts)
        if cp:
            results.append(cp)

    return results
