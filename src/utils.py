"""Shared numerical, calendar and calendar-rule helpers."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
CRORE = 10_000_000
DATA_START = pd.Timestamp("2026-01-01")
DATA_END = pd.Timestamp("2026-06-30")
SUMMER_START = pd.Timestamp("2026-03-01")
SUMMER_END = pd.Timestamp("2026-06-30")
FORECAST_HORIZON_WEEKS = 8


def md_to_timestamp(value: str, year: int = 2026) -> pd.Timestamp:
    month, day = [int(part) for part in value.split("-")]
    return pd.Timestamp(year=year, month=month, day=day)


def week_start(date: pd.Timestamp) -> pd.Timestamp:
    """Monday week-start used by the default scenario calendar."""
    return pd.Timestamp(date).normalize() - pd.Timedelta(days=pd.Timestamp(date).weekday())


WEEKDAY_NUMBERS = {
    "MONDAY": 0,
    "TUESDAY": 1,
    "WEDNESDAY": 2,
    "THURSDAY": 3,
    "FRIDAY": 4,
    "SATURDAY": 5,
    "SUNDAY": 6,
}
WEEKDAY_NAMES = {value: key.title() for key, value in WEEKDAY_NUMBERS.items()}


def weekday_number(name: str) -> int:
    key = str(name).strip().upper()
    if key not in WEEKDAY_NUMBERS:
        raise ValueError(f"Unsupported weekday rule {name!r}; use Monday through Sunday")
    return WEEKDAY_NUMBERS[key]


def week_start_on(date: pd.Timestamp, start_day: str = "Monday") -> pd.Timestamp:
    timestamp = pd.Timestamp(date).normalize()
    return timestamp - pd.Timedelta(days=(timestamp.weekday() - weekday_number(start_day)) % 7)


def next_week_start_on(date: pd.Timestamp, start_day: str = "Monday") -> pd.Timestamp:
    return week_start_on(date, start_day) + pd.Timedelta(days=7)


def week_period_alias(start_day: str = "Monday") -> str:
    """Pandas weekly periods end one day before the next week start."""
    abbreviations = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
    return f"W-{abbreviations[weekday_number(start_day)]}"


def allocate_integer(total: float | int, weights: np.ndarray, minimum: np.ndarray | None = None) -> np.ndarray:
    """Largest-remainder integer apportionment, preserving total exactly."""
    weights = np.asarray(weights, dtype=float)
    if weights.size == 0:
        return np.array([], dtype=int)
    total = int(round(float(total)))
    if total == 0:
        return np.zeros_like(weights, dtype=int)
    if np.any(weights < 0) or weights.sum() <= 0:
        raise ValueError("Weights must be non-negative with a positive sum")
    weights = weights / weights.sum()
    if minimum is None:
        minimum = np.zeros_like(weights, dtype=int)
    else:
        minimum = np.asarray(minimum, dtype=int)
    if minimum.sum() > total:
        raise ValueError("Integer minimums exceed the requested total")
    result = minimum.copy()
    remaining = total - int(result.sum())
    raw = weights * remaining
    additions = np.floor(raw).astype(int)
    result += additions
    residual = remaining - int(additions.sum())
    order = np.argsort(-(raw - additions), kind="stable")
    if residual > 0:
        result[order[:residual]] += 1
    return result


def apportion(
    weights: np.ndarray,
    total: float | int,
    caps: np.ndarray | None = None,
    minimum: np.ndarray | None = None,
) -> np.ndarray:
    """Largest-remainder apportionment with optional minimums and caps."""
    if caps is not None and minimum is not None:
        raise ValueError("Combined minimum/cap apportionment is not supported")
    result = allocate_integer(total, weights, minimum=minimum)
    if caps is None:
        return result
    caps = np.asarray(caps, dtype=float)
    if np.any(result > caps + 1e-9):
        # General capped case: apportion a capped float waterfill, then distribute
        # the residual without breaching an integer cap.
        raw = apportion_with_caps(float(total), weights, caps)
        result = np.minimum(np.floor(raw + 1e-9).astype(int), np.floor(caps + 1e-9).astype(int))
        residual = int(round(float(total))) - int(result.sum())
        order = np.argsort(-(raw - result), kind="stable")
        while residual > 0:
            progressed = False
            for index in order:
                if result[index] + 1 <= caps[index] + 1e-9:
                    result[index] += 1
                    residual -= 1
                    progressed = True
                    if residual == 0:
                        break
            if not progressed:
                raise ValueError("Caps cannot accommodate requested total")
    return result


def allocate_float(total: float, weights: np.ndarray) -> np.ndarray:
    weights = np.asarray(weights, dtype=float)
    if weights.sum() <= 0:
        raise ValueError("Weights must have a positive sum")
    return total * weights / weights.sum()


def apportion_with_caps(total: float, weights: np.ndarray, caps: np.ndarray) -> np.ndarray:
    """Allocate total proportionally up to per-item caps; leave excess unmet."""
    weights = np.asarray(weights, dtype=float)
    caps = np.asarray(caps, dtype=float)
    if weights.shape != caps.shape or np.any(weights < 0) or np.any(caps < 0):
        raise ValueError("Weights and caps must be equal-length non-negative vectors")
    result = np.zeros_like(weights, dtype=float)
    remaining = max(0.0, float(total))
    active = (caps > 0) & (weights > 0)
    for _ in range(len(weights) + 1):
        if remaining <= 1e-9 or not active.any():
            break
        active_weights = weights * active
        proposed = allocate_float(remaining, active_weights)
        over = active & ((result + proposed) > caps + 1e-9)
        if not over.any():
            result += proposed * active
            remaining = 0.0
            break
        for index in np.flatnonzero(over):
            addition = max(0.0, caps[index] - result[index])
            result[index] += addition
            remaining -= addition
            active[index] = False
    return np.minimum(result, caps)


def stable_hash_int(*parts: object) -> int:
    """Entity-stable pseudo-random integer; independent of row ordering."""
    import hashlib

    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "little") % (2**32)


def safe_divide(numerator, denominator, default=0.0):
    if isinstance(denominator, pd.Series):
        return numerator.div(denominator.replace(0, np.nan)).fillna(default)
    return default if abs(float(denominator)) < 1e-12 else numerator / denominator


def ensure_dir(path: str | Path) -> Path:
    output = Path(path)
    output.mkdir(parents=True, exist_ok=True)
    return output


@lru_cache(maxsize=None)
def read_csv(path: str | Path, **kwargs) -> pd.DataFrame:
    return pd.read_csv(path, **kwargs)


def wape(actual: np.ndarray, forecast: np.ndarray) -> float:
    actual = np.asarray(actual, dtype=float)
    forecast = np.asarray(forecast, dtype=float)
    denominator = np.abs(actual).sum()
    return float(np.abs(actual - forecast).sum() / denominator) if denominator else 0.0
