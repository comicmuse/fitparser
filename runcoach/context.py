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
    
    # First, find the most recent critical power from any run (including beyond 7 days)
    # to use as fallback when individual runs don't have CP
    critical_power = None
    for run in reversed(all_runs):  # Most recent first
        if run.get("yaml_path"):
            yaml_path = data_dir / run["yaml_path"]
            if yaml_path.exists():
                try:
                    with open(yaml_path, "r", encoding="utf-8") as f:
                        parsed = yaml.safe_load(f)
                    cp = parsed.get("critical_power")
                    if cp and cp > 0:
                        critical_power = cp
                        break
                except Exception:
                    continue

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
        pwr = parsed.get("avg_power") or 0
        cp = parsed.get("critical_power") or critical_power or 0  # Use fallback CP
        hr = parsed.get("avg_hr", 0) or 0
        blocks = parsed.get("blocks", {})

        # Update critical_power if this run has a valid one
        if parsed.get("critical_power") and parsed.get("critical_power") > 0:
            critical_power = parsed.get("critical_power")

        # Compute RSS if we have power and CP
        has_power = pwr > 0
        rss = compute_rss(pwr, cp, dur) if (has_power and cp > 0) else None

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
            "rss": round(rss, 1) if rss is not None else None,
            "rss_note": None if has_power else "no power data",
        }
        activities.append(activity)

        total_distance_km += dist
        total_duration_min += dur
        if rss is not None:
            total_rss += rss

    # Also compute a longer 42-day window for chronic training load (Stryd RSB model)
    window_42_start = target - timedelta(days=42)
    chronic_runs = [
        r for r in all_runs
        if r.get("yaml_path")
        and r["date"] >= window_42_start.isoformat()
        and r["date"] < target.isoformat()
        and r["stage"] in ("parsed", "analyzed")
    ]

    chronic_rss = 0.0
    chronic_run_count = 0
    for run in chronic_runs:
        yaml_path = data_dir / run["yaml_path"]
        if not yaml_path.exists():
            continue
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                parsed = yaml.safe_load(f)
        except Exception:
            continue
        pwr = parsed.get("avg_power") or 0
        cp = parsed.get("critical_power") or critical_power or 0  # Use fallback CP
        dur = parsed.get("duration_min", 0) or 0
        if pwr > 0 and cp > 0:
            chronic_rss += compute_rss(pwr, cp, dur)
        chronic_run_count += 1

    # Stryd RSB Model:
    # ATL (Acute Training Load) = 7-day average daily RSS
    # CTL (Chronic Training Load) = 42-day average daily RSS
    # RSB (Running Stress Balance) = CTL - ATL (positive = fresh, negative = fatigued)
    atl = round(total_rss / 7, 1) if total_rss else 0
    ctl = round(chronic_rss / 42, 1) if chronic_rss else 0
    rsb = round(ctl - atl, 1)  # Running Stress Balance (positive = fresh)

    rest_days = 7 - len(activities)
    runs_with_power = sum(1 for a in activities if a.get("avg_power_w") is not None)
    runs_without_power = len(activities) - runs_with_power

    context = {
        "training_context": {
            "period": f"{window_start.isoformat()} to {(target - timedelta(days=1)).isoformat()}",
            "days": 7,
            "summary": {
                "total_runs": len(activities),
                "runs_with_power_data": runs_with_power,
                "runs_without_power_data": runs_without_power,
                "rest_days": rest_days,
                "total_distance_km": round(total_distance_km, 1),
                "total_duration_min": round(total_duration_min, 1),
                "total_rss": round(total_rss, 1) if runs_with_power > 0 else None,
                "avg_rss_per_run": round(total_rss / runs_with_power, 1) if runs_with_power > 0 else None,
                "rss_note": None if runs_without_power == 0 else f"{runs_without_power} run(s) missing power data, RSS incomplete",
            },
            "training_load": {
                "atl_7d_avg_daily_rss": atl,
                "ctl_42d_avg_daily_rss": ctl,
                "rsb_running_stress_balance": rsb,
                "rsb_interpretation": (
                    "fresh" if rsb > 10
                    else "balanced" if rsb > -10
                    else "fatigued"
                ),
                "runs_in_last_42d": chronic_run_count,
            },
            "activities": activities,
        }
    }

    if critical_power:
        context["training_context"]["critical_power_w"] = critical_power

    # ---- Prescribed workout (from Stryd training plan) ----
    planned = db.get_planned_workout_for_date(target.isoformat())
    if planned:
        prescriptions = []
        for pw in planned:
            rx: dict = {
                "title": pw["title"],
                "type": pw.get("workout_type") or None,
            }
            if pw.get("description"):
                rx["description"] = pw["description"]
            if pw.get("duration_s"):
                rx["planned_duration_min"] = round(pw["duration_s"] / 60, 1)
            if pw.get("distance_m"):
                rx["planned_distance_km"] = round(pw["distance_m"] / 1000, 2)
            if pw.get("stress"):
                rx["planned_stress"] = round(pw["stress"], 1)
            prescriptions.append(rx)
        context["training_context"]["prescribed_workout"] = (
            prescriptions[0] if len(prescriptions) == 1 else prescriptions
        )

    # ---- Next 2 upcoming scheduled workouts ----
    next_day = (target + timedelta(days=1)).isoformat()
    upcoming = db.get_upcoming_planned_workouts(from_date=next_day, limit=2)
    if upcoming:
        next_sessions = []
        for pw in upcoming:
            ns: dict = {
                "date": pw["date"],
                "title": pw["title"],
                "type": pw.get("workout_type") or None,
            }
            if pw.get("description"):
                ns["description"] = pw["description"]
            if pw.get("duration_s"):
                ns["planned_duration_min"] = round(pw["duration_s"] / 60, 1)
            if pw.get("distance_m"):
                ns["planned_distance_km"] = round(pw["distance_m"] / 1000, 2)
            if pw.get("stress"):
                ns["planned_stress"] = round(pw["stress"], 1)
            next_sessions.append(ns)
        context["training_context"]["next_scheduled_workouts"] = next_sessions

    return context
