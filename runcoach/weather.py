"""Weather-based running score calculator."""
from __future__ import annotations

import logging
import requests
from datetime import datetime, timedelta

log = logging.getLogger(__name__)


def _next_midnight(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)


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


def fetch_forecast(lat: float, lng: float, tz: str, days: int = 2) -> dict:
    """Fetch hourly forecast from Open-Meteo (no API key required)."""
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lng,
            "hourly": "temperature_2m,precipitation_probability,relativehumidity_2m,windspeed_10m",
            "daily": "sunrise,sunset",
            "forecast_days": days,
            "timezone": tz,
        },
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()

    hourly = data["hourly"]
    daily = data["daily"]
    sunrises = [datetime.fromisoformat(s) for s in daily["sunrise"]]
    sunsets = [datetime.fromisoformat(s) for s in daily["sunset"]]

    hours = []
    for i, time_str in enumerate(hourly["time"]):
        hours.append({
            "hour": int(time_str[11:13]),
            "dt": datetime.fromisoformat(time_str),
            "temp_c": float(hourly["temperature_2m"][i]),
            "rain_pct": float(hourly["precipitation_probability"][i] or 0),
            "humidity_pct": float(hourly["relativehumidity_2m"][i]),
            "wind_kmh": float(hourly["windspeed_10m"][i]),
        })

    return {"hours": hours, "sunrise": sunrises, "sunset": sunsets}


def score_forecast(forecast: dict, now: datetime) -> dict:
    """Score hours within the actionable window and build the API response payload."""
    sunrises = forecast["sunrise"]
    sunsets = forecast["sunset"]
    today_sunrise = sunrises[0]
    today_sunset = sunsets[0]

    now_snapped = now.replace(minute=0, second=0, microsecond=0)
    today_window_end = _next_midnight(now_snapped)

    today_hours = [
        h for h in forecast["hours"]
        if h["dt"].date() == today_sunrise.date()
        and h["dt"] >= now_snapped
        and h["dt"] < today_window_end
    ]

    if len(today_hours) < 3 and len(sunrises) > 1:
        is_tomorrow = True
        tomorrow_sunrise = sunrises[1]
        tomorrow_sunset = sunsets[1]
        tomorrow_start = tomorrow_sunrise.replace(minute=0, second=0, microsecond=0)
        tomorrow_window_end = _next_midnight(tomorrow_sunrise)
        window_hours = [
            h for h in forecast["hours"]
            if h["dt"].date() == tomorrow_sunrise.date()
            and h["dt"] >= tomorrow_start
            and h["dt"] < tomorrow_window_end
        ]
        day_sunrise = tomorrow_sunrise
        day_sunset = tomorrow_sunset
    else:
        is_tomorrow = False
        window_hours = today_hours
        day_sunrise = today_sunrise
        day_sunset = today_sunset

    scored_hours = []
    for h in window_hours:
        s = score_hour(
            temp_c=h["temp_c"],
            rain_pct=h["rain_pct"],
            humidity_pct=h["humidity_pct"],
            wind_kmh=h["wind_kmh"],
            dt=h["dt"],
            sunrise=day_sunrise,
            sunset=day_sunset,
        )
        scored_hours.append({
            "hour": h["hour"],
            "score": s,
            "temp_c": round(h["temp_c"], 1),
            "rain_pct": int(h["rain_pct"]),
            "humidity_pct": int(h["humidity_pct"]),
            "wind_kmh": round(h["wind_kmh"], 1),
        })

    if not scored_hours:
        date_val = (sunrises[1] if is_tomorrow else today_sunrise).date()
        return {
            "date": date_val.isoformat(),
            "hours": [],
            "best_hour": 0,
            "best_score": 0,
            "day_label": "No forecast available",
            "is_tomorrow": is_tomorrow,
        }

    best = max(scored_hours, key=lambda x: x["score"])
    best_score = best["score"]
    best_hour = best["hour"]
    date_val = (sunrises[1] if is_tomorrow else today_sunrise).date()

    if best_score >= 4:
        suffix = "am" if best_hour < 12 else "pm"
        display = best_hour % 12 or 12
        day_label = f"Best window: {display}{suffix} · {best_score}/10"
    else:
        day_label = "No good windows tomorrow" if is_tomorrow else "No good windows today"

    return {
        "date": date_val.isoformat(),
        "hours": scored_hours,
        "best_hour": best_hour,
        "best_score": best_score,
        "day_label": day_label,
        "is_tomorrow": is_tomorrow,
    }
