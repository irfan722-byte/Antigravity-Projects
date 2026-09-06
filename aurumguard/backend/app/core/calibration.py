"""Probability calibration from recorded validation outcomes.

The MVP uses a transparent frequentist method: the strategy's out-of-sample
(or paper) win frequency in the score bucket that contains the current score,
reported as a Wilson 95% interval. No number is produced without a recorded
sample, and the sample size is always shown next to the range.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

CALIBRATION_VERSION = "calibration-wilson-v1"
MIN_TOTAL_SAMPLE = 30
MIN_BUCKET_SAMPLE = 10


@dataclass(frozen=True)
class CalibrationResult:
    low: float
    high: float
    point: float
    sample_size: int
    method: str
    in_range: bool
    reason: str
    bucket: str | None = None
    brier: float | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n <= 0:
        return 0.0, 1.0, 0.5
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half), p


def bucket_for(score: float) -> str:
    lo = int(score // 10 * 10)
    return f"{lo}-{lo + 10}"


def calibrated_probability(validation: dict | None, score: float) -> CalibrationResult:
    """``validation`` shape (written by the backtest/validation pipeline):
    {"sample_size": n, "wins": w, "buckets": {"70-80": {"n": .., "wins": ..}, ...}, "brier": 0.23, "label": "OOS"}
    """
    if not validation or not validation.get("sample_size"):
        return CalibrationResult(0.0, 1.0, 0.5, 0, CALIBRATION_VERSION, False, "no recorded validation sample for this strategy", brier=None)
    n = int(validation["sample_size"])
    w = int(validation.get("wins", 0))
    b = bucket_for(score)
    buckets = validation.get("buckets") or {}
    if b in buckets and buckets[b].get("n", 0) >= MIN_BUCKET_SAMPLE:
        bn, bw = int(buckets[b]["n"]), int(buckets[b]["wins"])
        lo, hi, p = wilson(bw, bn)
        return CalibrationResult(round(lo, 3), round(hi, 3), round(p, 3), bn, f"{CALIBRATION_VERSION}:bucket", n >= MIN_TOTAL_SAMPLE, f"bucket {b} of {validation.get('label', 'validation')} sample", b, validation.get("brier"))
    lo, hi, p = wilson(w, n)
    in_range = n >= MIN_TOTAL_SAMPLE
    reason = f"overall {validation.get('label', 'validation')} sample (score bucket {b} has too few observations)" if in_range else f"sample {n} < minimum {MIN_TOTAL_SAMPLE}"
    return CalibrationResult(round(lo, 3), round(hi, 3), round(p, 3), n, f"{CALIBRATION_VERSION}:overall", in_range, reason, b, validation.get("brier"))


def brier_score(pairs: list[tuple[float, int]]) -> float | None:
    if not pairs:
        return None
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)
