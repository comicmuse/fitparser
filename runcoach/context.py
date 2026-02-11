"""Build weekly training context to accompany each run sent to the LLM."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import yaml

from runcoach.db import RunCoachDB

log = logging.getLogger(__name__)


def compute_rss(avg_power: float, critical_power: float, duration_min: float) -> float:
    """
    Compute Running Stress Score (RSS), consistent with Stryd's model.

    RSS = (duration_s / 3600) * (avg_power / CP)^2 * 100

    Uses average power as an approximation where normalised power isn't
    available.  This slightly underestimates RSS for variable-effort runs
    but is consistent across sessions.
    """
    if not critical_power or critical_power <= 0:
        return 0.0
    duration_s = duration_min * 60
    intensity_factor = avg_power / critical_power
    return (duration_s / 3600) * (intensity_factor ** 2) * 100


def _classify_workout_type(name: str, blocks: dict) -> str:
    """Infer a short workout type from the name and block structure."""
    lower = name.lower()
    if "recovery" in lower or "ez " in lower or "easy" in lower:
        return "easy/recovery"
    if "long run" in lower:
        return "long run"
    if "tempo" in lower:
        return "tempo"
    if "interval" in lower:
        return "intervals"
    if "threshold" in lower:
        return "threshold"
    if "race" in lower:
        return "race"
    if "test" in lower:
        return "test"
    # Fallback: count block types
    block_types = [b.get("type", "") for b in blocks.values()] if blocks else []
    if any("active" in t for t in block_types):
        return "structured"
    return "run"


def build_weekly_context(
    run_date: str,
    data_dir: Path,
    db: RunCoachDB,
) -> dict:
    """
    Build a weekly training context summary for the 7 days before run_date.

    Returns a dict suitable for YAML serialisation.
    """
    target = date.fromisoformat(run_date)
    window_start = target - timedelta(days=7)

    # Get all runs in the 7-day window before (not including) the target date
    all_runs = db.get_all_runs()
    week_runs = [
        r for r in all_runs
        if r.get("yaml_path")
        and r["date"] >= window_start.isoformat()
        and r["date"] < target.isoformat()
        and r["stage"] in ("parsed", "analyzed")
    ]
    # Sort chronologically
    week_runs.sort(key=lambda r: r["date"])

    activities = []
    total_distance_km = 0.0
    total_duration_min = 0.0
    total_rss = 0.0
    critical_power = None

    for run in week_runs:
        yaml_path = data_dir / run["yaml_path"]
        if not yaml_path.exists():
            continue
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                parsed = yaml.safe_load(f)
        except Exception:
            log.warning("Could not read %s, skipping", yaml_path)
            continue

        dist = parsed.get("distance_km", 0) or 0
        dur = parsed.get("duration_min", 0) or 0
        pwr = parsed.get("avg_power", 0) or 0
        cp = parsed.get("critical_power", 0) or 0
        hr = parsed.get("avg_hr", 0) or 0
        blocks = parsed.get("blocks", {})

        if cp > 0:
            critical_power = cp

        rss = compute_rss(pwr, cp, dur) if cp > 0 else 0

        workout_type = _classify_workout_type(
            parsed.get("workout_name") or parsed.get("name") or run["name"],
            blocks,
        )

        activity = {
            "date": parsed.get("date") or run["date"],
            "name": parsed.get("workout_name") or parsed.get("name") or run["name"],
            "type": workout_type,
            "distance_km": round(dist, 2),
            "duration_min": round(dur, 1),
            "avg_power_w": round(pwr, 0) if pwr else None,
            "avg_hr_bpm": round(hr, 0) if hr else None,
            "rss": round(rss, 1),
        }
        activities.append(activity)

        total_distance_km += dist
        total_duration_min += dur
        total_rss += rss

    # Also compute a longer 28-day window for chronic training load
    window_28_start = target - timedelta(days=28)
    month_runs = [
        r for r in all_runs
        if r.get("yaml_path")
        and r["date"] >= window_28_start.isoformat()
        and r["date"] < target.isoformat()
        and r["stage"] in ("parsed", "analyzed")
    ]

    monthly_rss = 0.0
    monthly_run_count = 0
    for run in month_runs:
        yaml_path = data_dir / run["yaml_path"]
        if not yaml_path.exists():
            continue
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                parsed = yaml.safe_load(f)
        except Exception:
            continue
        pwr = parsed.get("avg_power", 0) or 0
        cp = parsed.get("critical_power", 0) or 0
        dur = parsed.get("duration_min", 0) or 0
        if cp > 0:
            monthly_rss += compute_rss(pwr, cp, dur)
        monthly_run_count += 1

    # Acute Training Load (ATL) = 7-day average daily RSS
    # Chronic Training Load (CTL) = 28-day average daily RSS
    atl = round(total_rss / 7, 1) if total_rss else 0
    ctl = round(monthly_rss / 28, 1) if monthly_rss else 0
    tsb = round(ctl - atl, 1)  # Training Stress Balance (positive = fresh)

    rest_days = 7 - len(activities)

    context = {
        "training_context": {
            "period": f"{window_start.isoformat()} to {(target - timedelta(days=1)).isoformat()}",
            "days": 7,
            "summary": {
                "total_runs": len(activities),
                "rest_days": rest_days,
                "total_distance_km": round(total_distance_km, 1),
                "total_duration_min": round(total_duration_min, 1),
                "total_rss": round(total_rss, 1),
                "avg_rss_per_run": round(total_rss / len(activities), 1) if activities else 0,
            },
            "training_load": {
                "atl_7d_avg_daily_rss": atl,
                "ctl_28d_avg_daily_rss": ctl,
                "tsb_training_stress_balance": tsb,
                "tsb_interpretation": (
                    "fresh" if tsb > 10
                    else "balanced" if tsb > -10
                    else "fatigued"
                ),
                "runs_in_last_28d": monthly_run_count,
            },
            "activities": activities,
        }
    }

    if critical_power:
        context["training_context"]["critical_power_w"] = critical_power

    return context
