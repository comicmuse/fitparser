"""Weather-based running score calculator."""
from __future__ import annotations

import logging
from datetime import datetime

log = logging.getLogger(__name__)


def _piecewise(val: float, breakpoints: list[tuple[float, float]]) -> float:
    if val <= breakpoints[0][0]:
        return breakpoints[0][1]
    if val >= breakpoints[-1][0]:
        return breakpoints[-1][1]
    for i in range(len(breakpoints) - 1):
        x0, y0 = breakpoints[i]
        x1, y1 = breakpoints[i + 1]
        if x0 <= val <= x1:
            return y0 + (val - x0) / (x1 - x0) * (y1 - y0)
    return breakpoints[-1][1]


def _temp_factor(temp_c: float) -> float:
    return _piecewise(temp_c, [
        (-5, 0.10), (4, 0.40), (11, 1.00), (18, 0.85), (28, 0.10),
    ])


def _rain_factor(rain_pct: float) -> float:
    return _piecewise(rain_pct, [
        (0, 1.00), (20, 1.00), (50, 0.50), (80, 0.15), (100, 0.10),
    ])


def _humidity_factor(humidity_pct: float) -> float:
    return _piecewise(humidity_pct, [
        (0, 1.00), (50, 1.00), (70, 0.85), (85, 0.50), (100, 0.10),
    ])


def _wind_factor(wind_kmh: float) -> float:
    return _piecewise(wind_kmh, [
        (0, 1.00), (15, 1.00), (30, 0.70), (50, 0.25), (60, 0.10),
    ])


def _daylight_factor(dt: datetime, sunrise: datetime, sunset: datetime) -> float:
    after = (dt - sunrise).total_seconds() / 60
    before = (sunset - dt).total_seconds() / 60
    if after < 30:
        return _piecewise(after, [(-60, 0.30), (0, 0.75), (30, 1.00)])
    if before < 30:
        return _piecewise(before, [(-60, 0.30), (0, 0.75), (30, 1.00)])
    return 1.00


def score_hour(
    temp_c: float,
    rain_pct: float,
    humidity_pct: float,
    wind_kmh: float,
    dt: datetime,
    sunrise: datetime,
    sunset: datetime,
) -> int:
    raw = (
        _temp_factor(temp_c)
        * _rain_factor(rain_pct)
        * _humidity_factor(humidity_pct)
        * _wind_factor(wind_kmh)
        * _daylight_factor(dt, sunrise, sunset)
    )
    return max(1, min(10, round(raw * 10)))
