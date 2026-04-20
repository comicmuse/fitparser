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
    current_cp: float | None = None,
    user_id: int | None = None,
) -> dict:
    """
    Build a weekly training context summary for the 7 days before run_date.

    Args:
        run_date: The date of the run being analyzed (YYYY-MM-DD)
        data_dir: Path to the data directory
        db: Database instance
        current_cp: The CP from the current run being analyzed (if available)

    Returns a dict suitable for YAML serialisation.
    """
    target = date.fromisoformat(run_date)
    window_start = target - timedelta(days=7)

    # Get all runs in the 7-day window before (not including) the target date
    all_runs = db.get_all_runs(user_id) if user_id is not None else db.get_all_runs(1)
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

    # Find the most recent CP from runs BEFORE the target date (previous CP)
    # This helps us detect if CP changed with the current run
    previous_cp = None
    for run in sorted(all_runs, key=lambda r: r["date"], reverse=True):  # Most recent first
        if run.get("yaml_path") and run["date"] < target.isoformat():
            yaml_path = data_dir / run["yaml_path"]
            if yaml_path.exists():
                try:
                    with open(yaml_path, "r", encoding="utf-8") as f:
                        parsed = yaml.safe_load(f)
                    cp = parsed.get("critical_power")
                    if cp and cp > 0:
                        previous_cp = cp
                        break
                except Exception:
                    continue

    # Use current CP if provided, otherwise fall back to previous CP
    critical_power = current_cp if current_cp else previous_cp

    # Track if CP changed between previous and current
    cp_changed = False
    cp_change_amount = 0
    if previous_cp and current_cp and previous_cp != current_cp:
        cp_changed = True
        cp_change_amount = current_cp - previous_cp

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
        # Use the run's own CP if available, otherwise use previous_cp
        cp = parsed.get("critical_power") or previous_cp or 0
        hr = parsed.get("avg_hr", 0) or 0
        blocks = parsed.get("blocks", {})

        # Note: We don't update previous_cp here since we're looking at historical runs
        # The previous_cp should stay fixed as the CP before the target date

        # Use Stryd RSS if available (most accurate), otherwise calculate it
        stryd_rss = parsed.get("stryd_rss")
        has_power = pwr > 0
        if stryd_rss is not None:
            rss = stryd_rss
            rss_source = "Stryd"
        elif has_power and cp > 0:
            rss = compute_rss(pwr, cp, dur)
            rss_source = "calculated"
        else:
            rss = None
            rss_source = None

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
            "rss_source": rss_source,
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

        # Prefer Stryd RSS if available
        stryd_rss = parsed.get("stryd_rss")
        if stryd_rss is not None:
            chronic_rss += stryd_rss
        else:
            # Fall back to calculated RSS using previous_cp
            pwr = parsed.get("avg_power") or 0
            cp = parsed.get("critical_power") or previous_cp or 0
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

    # Add CP change information if detected
    if cp_changed:
        context["training_context"]["cp_update"] = {
            "previous_cp_w": previous_cp,
            "current_cp_w": current_cp,
            "change_w": cp_change_amount,
            "change_pct": round((cp_change_amount / previous_cp * 100), 1) if previous_cp else 0,
            "note": f"Critical Power {'increased' if cp_change_amount > 0 else 'decreased'} from {previous_cp}W to {current_cp}W"
        }

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


def build_training_summary(
    db: RunCoachDB,
    as_of_date: date | None = None,
    user_id: int | None = None,
) -> dict:
    """
    Compute rolling training summary metrics for 1W, 4W-avg, and 16W-avg windows,
    plus 16-week RSB history for the home page chart.

    Uses DB columns (stryd_rss, distance_m) directly — no YAML I/O — so it is
    safe to call on every page load.
    """
    today = as_of_date or date.today()

    # Fetch one wide window: 154 days = 112d (16-week summary) + 42d (CTL look-back)
    window_start = (today - timedelta(days=154)).isoformat()
    all_runs = db.get_runs_in_date_range(window_start, today.isoformat(), user_id=user_id)
    valid = [r for r in all_runs if r.get("stage") in ("synced", "parsed", "analyzed")]

    def _window_stats(days: int) -> dict:
        cutoff = (today - timedelta(days=days)).isoformat()
        runs_in = [r for r in valid if r["date"] >= cutoff]
        km_total = sum((r.get("distance_m") or 0) / 1000.0 for r in runs_in)
        rss_values = [r["stryd_rss"] for r in runs_in if r.get("stryd_rss") is not None]
        rss_total = sum(rss_values) if rss_values else None
        weeks = days / 7
        return {
            "km": round(km_total / weeks, 1),
            "rss": round(rss_total / weeks, 1) if rss_total is not None else None,
            "runs": round(len(runs_in) / weeks, 1),
        }

    # Current ATL/CTL/RSB (computed as of today)
    atl_cutoff = (today - timedelta(days=7)).isoformat()
    ctl_cutoff = (today - timedelta(days=42)).isoformat()
    atl_rss = [r["stryd_rss"] for r in valid if r["date"] >= atl_cutoff and r.get("stryd_rss") is not None]
    ctl_rss = [r["stryd_rss"] for r in valid if r["date"] >= ctl_cutoff and r.get("stryd_rss") is not None]
    atl = sum(atl_rss) / 7 if atl_rss else None
    ctl = sum(ctl_rss) / 42 if ctl_rss else None
    rsb = round(ctl - atl, 2) if (atl is not None and ctl is not None) else None
    if rsb is None:
        interp = "unknown"
    elif rsb > 5:
        interp = "fresh"
    elif rsb < -10:
        interp = "fatigued"
    else:
        interp = "balanced"

    # 16-week RSB history (oldest → newest for chart)
    rsb_history = []
    for i in range(15, -1, -1):
        week_end = today - timedelta(weeks=i)
        w_atl_cutoff = (week_end - timedelta(days=7)).isoformat()
        w_ctl_cutoff = (week_end - timedelta(days=42)).isoformat()
        w_end_iso = week_end.isoformat()
        w_atl_rss = [r["stryd_rss"] for r in valid
                     if r["date"] >= w_atl_cutoff and r["date"] < w_end_iso
                     and r.get("stryd_rss") is not None]
        w_ctl_rss = [r["stryd_rss"] for r in valid
                     if r["date"] >= w_ctl_cutoff and r["date"] < w_end_iso
                     and r.get("stryd_rss") is not None]
        w_atl = round(sum(w_atl_rss) / 7, 2) if w_atl_rss else None
        w_ctl = round(sum(w_ctl_rss) / 42, 2) if w_ctl_rss else None
        w_rsb = round(w_ctl - w_atl, 2) if (w_atl is not None and w_ctl is not None) else None
        week_monday = week_end - timedelta(days=week_end.weekday())
        rsb_history.append({
            "week_label": week_monday.strftime("%-d %b"),
            "atl": w_atl,
            "ctl": w_ctl,
            "rsb": w_rsb,
        })

    return {
        "training_summary": {
            "as_of": today.isoformat(),
            "windows": {
                "1_week": _window_stats(7),
                "4_week_avg": _window_stats(28),
                "16_week_avg": _window_stats(112),
            },
            "current_rsb": {
                "atl": round(atl, 2) if atl is not None else None,
                "ctl": round(ctl, 2) if ctl is not None else None,
                "rsb": rsb,
                "interpretation": interp,
            },
            "rsb_history": rsb_history,
        }
    }
