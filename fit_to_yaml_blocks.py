#!/usr/bin/env python3
"""
Convert a Garmin structured workout FIT file into a block-based YAML summary.

- Assumes the FIT file comes from a structured workout (e.g. Stryd → Garmin).
- Maps workout steps to laps by index (step 0 → lap 0, etc.).
- For each block/lap:
    - duration, distance, avg HR, avg power
    - if step has power target: % time below / in / above target band
- Outputs YAML to stdout (or to a file if you uncomment the write section).

This is designed as a starting point:
- You can tweak block naming/classification logic.
- You can plug it into Home Assistant / Pyscript later.
"""

from __future__ import annotations

import sys
import math
import statistics
import yaml
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

from fitparse import FitFile


# ---------- Data structures ----------

@dataclass
class BlockStats:
    name: str
    type: str  # "warmup", "work", "float", "cooldown", "other"
    start_utc: Optional[str]
    end_utc: Optional[str]
    duration_min: Optional[float]
    distance_km: Optional[float]
    avg_hr: Optional[float]
    avg_power: Optional[float]

    target_min_w: Optional[float] = None
    target_max_w: Optional[float] = None
    pct_time_below: Optional[float] = None
    pct_time_in_range: Optional[float] = None
    pct_time_above: Optional[float] = None
    hr_drift_pct: Optional[float] = None
    hr_first5s_to_last5s_delta: Optional[float] = None


# ---------- Helper functions ----------

def _round(x: Optional[float], n: int = 1) -> Optional[float]:
    if x is None:
        return None
    try:
        return round(float(x), n)
    except Exception:
        return None


def load_fit(path: Path) -> FitFile:
    ff = FitFile(str(path))
    ff.parse()
    return ff


def extract_laps(ff: FitFile):
    """
    Extract lap messages with key fields.
    Returns a list of dicts preserving order in file.
    """
    laps = []
    for lap in ff.get_messages("lap"):
        d = {}
        for field in lap:
            d[field.name] = field.value
        laps.append(d)
    return laps


def extract_workout_steps(ff: FitFile):
    """
    Extract workout_step messages with key fields.
    Returns a list of dicts in order.
    """
    steps = []
    for step in ff.get_messages("workout_step"):
        d = {}
        for field in step:
            d[field.name] = field.value
        steps.append(d)
    return steps


def extract_records(ff: FitFile):
    """
    Extract record messages (per-sample data).
    Each record includes timestamp, power, HR and a set of running-dynamics
    metrics when available. This function is defensive: missing fields are
    represented as `None` and obviously-bogus values (0, NaN, Inf) are
    filtered out.
    """
    records = []
    for rec in ff.get_messages("record"):
        r = {}
        for field in rec:
            r[field.name] = field.value

        # timestamp required
        ts = r.get("timestamp")
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        # Helper: safely convert to float when possible
        def _f(name):
            v = r.get(name)
            if v is None:
                return None
            try:
                return float(v)
            except Exception:
                return None

        # Capture a broad set of running-dynamics fields (defensive)
        # Power is Stryd's field. Garmin's equivalent is power.
        # ChatGPT suggested _f("Power") or _f("power"), but we only need Stryd's version
        power = _f("Power")
        form_power = _f("Form Power") or _f("form_power")
        # Leg spring stiffness (raw or normalized)
        lss = _f("Leg Spring Stiffness") or _f("leg_spring_stiffness") or _f("leg_spring_stiffness_norm")
        # Air power (absolute) and possible percent field
        air_power = _f("Air Power") or _f("air_power")
        air_power_pct = _f("Air Power Percent") or _f("air_power_pct")
        # Vertical oscillation
        vert_osc = _f("vertical_oscillation") or _f("Vertical Oscillation")
        # Ground contact / stance time
        gct = _f("ground_contact_time") or _f("stance_time")
        # Cadence
        cadence = _f("cadence") or _f("fractional_cadence")
        # Step length
        step_length = _f("step_length")
        # form power ratio (may not be present) - if missing, compute form_power / power when available
        form_power_ratio = _f("form_power_ratio")

        # Normalize some obviously-bogus values to None (ignore zeros for metrics that shouldn't be zero)
        def _valid(x, allow_zero=False):
            if x is None:
                return None
            if not allow_zero and x == 0:
                return None
            if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
                return None
            return x

        form_power = _valid(form_power)
        lss = _valid(lss)
        air_power = _valid(air_power)
        air_power_pct = _valid(air_power_pct)
        vert_osc = _valid(vert_osc)
        gct = _valid(gct)
        cadence = _valid(cadence)
        step_length = _valid(step_length)
        form_power_ratio = _valid(form_power_ratio)

        # compute derived fields when missing
        if form_power_ratio is None and form_power is not None and power is not None and power != 0:
            try:
                form_power_ratio = float(form_power) / float(power)
            except Exception:
                form_power_ratio = None

        # air_power_pct: compute if we have absolute air_power and total power
        if air_power_pct is None and air_power is not None and power is not None and power != 0:
            try:
                air_power_pct = 100.0 * float(air_power) / float(power)
            except Exception:
                air_power_pct = None

        records.append({
            "timestamp": ts,
            "power": power,
            "heart_rate": r.get("heart_rate"),
            # running dynamics
            "form_power": form_power,
            "lss": lss,
            "air_power": air_power,
            "air_power_pct": air_power_pct,
            "vert_osc": vert_osc,
            "gct": gct,
            "cadence": cadence,
            "step_length": step_length,
            "form_power_ratio": form_power_ratio,
        })
    # Ensure sorted by time
    records.sort(key=lambda x: x["timestamp"])
    return records


def extract_hr_zones(ff, lthr_bpm: Optional[float] = None) -> Optional[dict]:
    """
    Extract HR zone boundaries from hr_zone messages or unknown_216 vendor fields.
    Returns a dict with zone definitions or None if not available.
    """
    try:
        zones_raw = []
        
        # First try standard hr_zone messages
        hr_zone_msgs = list(ff.get_messages("hr_zone"))
        if hr_zone_msgs:
            for msg in hr_zone_msgs:
                high = None
                for field in msg:
                    if field.name == "high_bpm":
                        high = field.value
                        break
                if high is not None:
                    zones_raw.append(high)
        
        # Fallback: Check unknown_216 field unknown_6 for Garmin/Stryd zone boundaries
        # This field contains a tuple of HR zone upper bounds
        if not zones_raw:
            for msg in ff.get_messages("unknown_216"):
                for field in msg:
                    if field.name == "unknown_6" and field.value is not None:
                        # field.value is a tuple like (91, 134, 151, 159, 172, 189)
                        if isinstance(field.value, (list, tuple)):
                            zones_raw = list(field.value)
                            break
                if zones_raw:
                    break
        
        if not zones_raw:
            return None
        
        # Sort by high_bpm ascending
        zones_raw.sort()
        
        # Build contiguous zones
        zones = {}
        min_bpm = 0
        for i, high_bpm in enumerate(zones_raw):
            zone_label = f"Z{i+1}"
            zones[zone_label] = {
                "min_bpm": min_bpm,
                "max_bpm": high_bpm
            }
            min_bpm = high_bpm + 1
        
        result = {
            "source": "garmin",
            "system": f"Garmin_{len(zones)}_zone",
            "zones": zones
        }
        
        if lthr_bpm is not None:
            result["lthr_bpm"] = lthr_bpm
        
        return result
    except Exception:
        return None


def hr_zone_label(hr_zone_def: dict, hr_bpm: float) -> Optional[str]:
    """
    Classify a heart rate value into a zone label (Z1, Z2, etc.).
    Returns the zone label or None if no match.
    """
    if hr_zone_def is None or hr_bpm is None:
        return None
    
    zones = hr_zone_def.get("zones", {})
    for zone_label, bounds in zones.items():
        if bounds["min_bpm"] <= hr_bpm <= bounds["max_bpm"]:
            return zone_label
    
    return None


def compute_zone_distribution(records: list, zone_def: dict, value_key: str, 
                              zone_classifier) -> Optional[dict]:
    """
    Compute time-in-zone distribution for a set of records.
    
    Args:
        records: List of record dicts
        zone_def: Zone definition dict (hr_zone_definition)
        value_key: Key to extract value from record ("heart_rate" or "power")
        zone_classifier: Function to classify value into zone (hr_zone_label or power_zone_label)
    
    Returns:
        Dict with {Z1_pct: ..., Z2_pct: ..., ...} or None if no data
    """
    if zone_def is None:
        return None
    
    zone_counts = {}
    zones = zone_def.get("zones", {})
    
    # Initialize counts
    for zone_label in zones.keys():
        zone_counts[zone_label] = 0
    
    # Count samples per zone
    for record in records:
        value = record.get(value_key)
        if value is None or value == 0:
            continue
        
        zone = zone_classifier(zone_def, value)
        if zone and zone in zone_counts:
            zone_counts[zone] += 1
    
    total = sum(zone_counts.values())
    if total == 0:
        return None
    
    # Compute percentages
    result = {}
    for zone_label, count in zone_counts.items():
        pct_key = f"{zone_label}_pct"
        result[pct_key] = round(100.0 * count / total, 1)
    
    return result


def compute_hr_drift_pct(block_records: list) -> Optional[float]:
    """
    Compute HR drift (aerobic decoupling) for a block using first-half vs second-half HR.
    
    Returns drift percentage (e.g. 3.8 for +3.8%) or None if insufficient data.
    Formula: drift_pct = (HR2 / HR1 - 1) * 100
    
    Args:
        block_records: List of record dicts from records_for_lap()
    
    Returns:
        Drift percentage rounded to 2 decimals, or None
    """
    if not block_records:
        return None
    
    # Extract records with valid timestamps and HR
    valid_records = []
    for r in block_records:
        ts = r.get("timestamp")
        hr = r.get("heart_rate")
        if ts is not None and hr is not None and hr > 0:
            valid_records.append({"timestamp": ts, "heart_rate": hr})
    
    if len(valid_records) < 20:  # Need minimum samples
        return None
    
    # Sort by timestamp
    valid_records.sort(key=lambda x: x["timestamp"])
    
    # Calculate total duration
    t0 = valid_records[0]["timestamp"]
    t_end = valid_records[-1]["timestamp"]
    total_duration_s = (t_end - t0).total_seconds()
    
    # Require at least 8 minutes (480 seconds)
    if total_duration_s < 480:
        return None
    
    # Calculate midpoint
    midpoint_s = total_duration_s / 2.0
    
    # Split into first and second half
    first_half_hrs = []
    second_half_hrs = []
    
    for r in valid_records:
        elapsed_s = (r["timestamp"] - t0).total_seconds()
        if elapsed_s <= midpoint_s:
            first_half_hrs.append(r["heart_rate"])
        else:
            second_half_hrs.append(r["heart_rate"])
    
    # Check we have enough samples in each half
    if len(first_half_hrs) < 10 or len(second_half_hrs) < 10:
        return None
    
    # Compute averages
    hr1 = statistics.mean(first_half_hrs)
    hr2 = statistics.mean(second_half_hrs)
    
    if hr1 <= 0:
        return None
    
    # Calculate drift percentage
    drift_pct = (hr2 / hr1 - 1.0) * 100.0
    
    return round(drift_pct, 2)


def compute_hr_first5s_to_last5s_delta(block_records: list) -> Optional[float]:
    """
    Compute the change in HR between first 5s and last 5s of a segment.
    
    Returns delta in BPM (last 5s avg - first 5s avg) or None if insufficient data.
    
    Args:
        block_records: List of record dicts from records_for_lap()
    
    Returns:
        HR delta rounded to 1 decimal, or None
    """
    if not block_records:
        return None
    
    # Extract records with valid timestamps and HR
    valid_records = []
    for r in block_records:
        ts = r.get("timestamp")
        hr = r.get("heart_rate")
        if ts is not None and hr is not None and hr > 0:
            valid_records.append({"timestamp": ts, "heart_rate": hr})
    
    if len(valid_records) < 4:  # Need minimum samples
        return None
    
    # Sort by timestamp
    valid_records.sort(key=lambda x: x["timestamp"])
    
    # Calculate total duration
    t0 = valid_records[0]["timestamp"]
    t_end = valid_records[-1]["timestamp"]
    total_duration_s = (t_end - t0).total_seconds()
    
    # Require at least 30 seconds
    if total_duration_s < 30:
        return None
    
    # Get first 5s and last 5s
    first_5s_hrs = []
    last_5s_hrs = []
    
    for r in valid_records:
        elapsed_s = (r["timestamp"] - t0).total_seconds()
        if elapsed_s <= 5.0:
            first_5s_hrs.append(r["heart_rate"])
        if elapsed_s >= total_duration_s - 5.0:
            last_5s_hrs.append(r["heart_rate"])
    
    # Check we have samples in each window
    if len(first_5s_hrs) < 1 or len(last_5s_hrs) < 1:
        return None
    
    # Compute averages
    hr_first = statistics.mean(first_5s_hrs)
    hr_last = statistics.mean(last_5s_hrs)
    
    # Calculate delta (last - first)
    delta = hr_last - hr_first
    
    return round(delta, 1)


def classify_block_type(step: dict, lap_index: int, total_laps: int) -> str:
    """
    Best-effort guess of block type from workout_step + lap position.
    You can tune this based on what Stryd names/labels its steps.

    Heuristics:
      - first lap → warmup (if not obviously work)
      - last lap → cooldown (if not obviously work)
      - if step["intensity"] hints: map accordingly
      - else: treat as "work" and let higher-level logic decide.
    """
    intensity = (step.get("intensity") or "").lower()
    step_name = (step.get("step_name") or step.get("custom_target_value_high") or "")
    step_text = str(step_name).lower()

    if "warm" in step_text or "wu" in step_text or intensity == "warmup":
        return "warmup"
    if "cool" in step_text or "cd" in step_text or intensity == "cooldown":
        return "cooldown"
    if "rest" in step_text or "recover" in step_text or intensity in ("recovery", "rest"):
        return "float"

    # Fallback position-based:
    if lap_index == 0:
        return "warmup"
    if lap_index == total_laps - 1:
        return "cooldown"

    # Default: some kind of work
    return "work"


def extract_power_target(step: dict) -> tuple[Optional[float], Optional[float]]:
    """
    Try to get power target band from workout_step.

    Common fields in workout_step for power targets:
      - target_type (enum; for power, "power" or a numeric code)
      - custom_target_power_low (watts)
      - custom_target_power_high (watts)

    NOTE: Values are in watts from Stryd/Garmin power workouts.
    """
    target_type = step.get("target_type")
    
    # Try custom_target_power_low/high first (most common for power workouts)
    low = step.get("custom_target_power_low")
    high = step.get("custom_target_power_high")
    
    # Fall back to generic custom_target_value_low/high if power-specific not found
    if low is None or high is None:
        low = step.get("custom_target_value_low")
        high = step.get("custom_target_value_high")

    # We need both values and target_type to be power
    if low is None or high is None:
        return None, None
    
    if target_type is not None and str(target_type).lower() != "power":
        return None, None

    # Convert to float
    low_f = float(low)
    high_f = float(high)

    # Heuristic sanity check: if values are extremely big/small, maybe scaled.
    # If it looks like deciwatts (e.g. 2200–2400 for a 220–240 W range)
    if low_f > 1000 and low_f < 10000:
        low_f /= 10.0
        high_f /= 10.0
    # If it looks like centiwatts (22000–24000)
    elif low_f > 10000 and low_f < 100000:
        low_f /= 100.0
        high_f /= 100.0

    return low_f, high_f


def records_for_lap(records: List[dict], lap: dict) -> List[dict]:
    """
    Select records whose timestamps fall within this lap's time range.
    Uses lap.start_time and lap.total_timer_time.
    """
    start = lap.get("start_time")
    duration = lap.get("total_timer_time")

    if start is None or duration is None:
        return []

    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    end = start + timedelta(seconds=float(duration))

    in_lap = [r for r in records if start <= r["timestamp"] < end]
    return in_lap


def compute_power_band_stats(block_records: List[dict], target_min_w: float, target_max_w: float) -> Dict[str, float]:
    """
    Count % of time below / in / above target range based on power samples.

    Assumes (roughly) uniform sampling rate, so we can use sample counts
    as a proxy for time.
    """
    if not block_records:
        return {"below": 0.0, "in": 0.0, "above": 0.0}

    below = in_range = above = 0
    for r in block_records:
        p = r.get("power")
        if p is None:
            continue
        try:
            p = float(p)
        except Exception:
            continue
        if p < target_min_w:
            below += 1
        elif p > target_max_w:
            above += 1
        else:
            in_range += 1

    total = below + in_range + above
    if total == 0:
        return {"below": 0.0, "in": 0.0, "above": 0.0}

    return {
        "below": round(100.0 * below / total, 1),
        "in": round(100.0 * in_range / total, 1),
        "above": round(100.0 * above / total, 1),
    }


def build_blocks_from_fit(path: Path, tz_name: str = "Europe/London") -> Dict[str, Any]:
    """
    Main function:
      - loads FIT
      - extracts session-level fields
      - builds block stats from laps + workout_step
      - returns a YAML-ready dict
    """
    ff = load_fit(path)
    laps = extract_laps(ff)
    steps = extract_workout_steps(ff)
    records = extract_records(ff)

    # File ID serial (use as canonical id if present)
    file_serial = None
    for m in ff.get_messages("file_id"):
        d = {field.name: field.value for field in m}
        if d.get("serial_number"):
            file_serial = d.get("serial_number")
            break

    # User profile weight (kg) and resting heart rate (bpm)
    actual_weight = None
    resting_hr = None
    for m in ff.get_messages("user_profile"):
        d = {field.name: field.value for field in m}
        weight = d.get("weight")
        if weight is not None:
            actual_weight = float(weight)
        rhr = d.get("resting_heart_rate")
        if rhr is not None:
            resting_hr = int(rhr)
        if actual_weight is not None and resting_hr is not None:
            break

    # Workout block name (if present)
    workout_block_name = None
    for m in ff.get_messages("workout"):
        d = {field.name: field.value for field in m}
        # common field name in workout message for name is 'wkt_name'
        workout_block_name = d.get("wkt_name") or workout_block_name

    # Compute session-level avg/max power from record samples if available
    power_samples = [float(r["power"]) for r in records if r.get("power") is not None]
    session_avg_power = None
    session_max_power = None
    if power_samples:
        session_avg_power = sum(power_samples) / len(power_samples)
        session_max_power = max(power_samples)

    if not laps:
        raise RuntimeError("No laps found in FIT (is this a structured workout?)")

    # Session-level info (take from first session message)
    sport = None
    session_start_utc = None
    total_distance_m = None
    total_timer_s = None
    total_ascent_m = None
    avg_hr_session = None
    avg_power_session = None
    max_hr_session = None
    max_power_session = None
    calories = None
    workout_name = None

    # Additional activity metrics we want to surface
    aerobic_te = None
    anaerobic_te = None
    lthr = None
    vo2_max = None
    recovery_time_min = None
    critical_power = None
    avg_temperature = None
    baseline_humidity = None
    

    for msg in ff.get_messages("session"):
        d = {field.name: field.value for field in msg}
        sport = (d.get("sport") or d.get("sub_sport") or sport)
        st = d.get("start_time")
        if st and session_start_utc is None:
            if st.tzinfo is None:
                st = st.replace(tzinfo=timezone.utc)
            session_start_utc = st
        total_distance_m = total_distance_m or d.get("total_distance")
        total_timer_s = total_timer_s or d.get("total_timer_time")
        total_ascent_m = total_ascent_m or d.get("total_ascent")
        avg_hr_session = avg_hr_session or d.get("avg_heart_rate")
        max_hr_session = max_hr_session or d.get("max_heart_rate")
        avg_power_session = avg_power_session or d.get("avg_power")
        max_power_session = max_power_session or d.get("max_power")
        calories = calories or d.get("total_calories")
        workout_name = workout_name or d.get("sport_profile_name") or d.get("workout_name")

        # Training effect fields
        aerobic_te = aerobic_te or d.get("total_training_effect") or d.get("training_effect")
        anaerobic_te = anaerobic_te or d.get("total_anaerobic_training_effect") or d.get("anaerobic_training_effect")
        
        # Critical Power
        critical_power = critical_power or d.get("CP")
        
        # Environmental conditions
        avg_temperature = avg_temperature or d.get("avg_temperature")
        baseline_humidity = baseline_humidity or d.get("Baseline Humidity")

    # VO2 max sometimes lives in a vendor message: unknown_140 field 7
    # Vendor/developer mapping (observed in this FIT file):
    # - message type: `unknown_140` (vendor message)
    # - field index 7  -> `unknown_7`  : raw VO2 value (unitless) ; scale to VO2max using
    #                                vo2_max = raw * 3.5 / 65536.0
    # - field index 9  -> `unknown_9`  : recovery time in minutes (integer)
    # These mappings are vendor-specific (Garmin/STRYD in this file) and may not exist
    # in other FIT files. Keep `recovery_time_min` as the raw minutes integer to preserve
    # the original data, and add a human-readable `recovery_time_readable` below.
    try:
        for m in ff.get_messages("unknown_140"):
            for field in m:
                # Field 7: VO2 max (scaled fixed-point)
                if field.name == "unknown_7":
                    raw = field.value
                    if raw is not None:
                        try:
                            vo2_max = float(raw) * 3.5 / 65536.0
                        except Exception:
                            vo2_max = None
                # Field 9: recovery time (in minutes)
                if field.name == "unknown_9":
                    raw = field.value
                    if raw is not None:
                        try:
                            recovery_time_min = int(raw)
                        except Exception:
                            recovery_time_min = None
            if vo2_max is not None and recovery_time_min is not None:
                break
    except Exception:
        vo2_max = None
        recovery_time_min = None

    # LTHR (Lactate Threshold Heart Rate) lives in unknown_216 field 13
    # Discovery: searched all FIT messages for values ~174 (expected LTHR) and found
    # unknown_216: unknown_13 = 174. The unknown_216 message contains heart rate thresholds:
    # - unknown_12: resting_hr (49, matches user_profile.resting_heart_rate)
    # - unknown_13: LTHR in bpm (174)
    # - unknown_11: likely max threshold (189)
    # - unknown_6: tuple of 6 HR zone boundaries (91, 134, 151, 159, 172, 189)
    try:
        for m in ff.get_messages("unknown_216"):
            for field in m:
                if field.name == "unknown_13":
                    raw = field.value
                    if raw is not None:
                        try:
                            lthr = int(raw)
                        except Exception:
                            lthr = None
                        break
            if lthr is not None:
                break
    except Exception:
        lthr = None

    # Extract HR zone definitions from FIT file
    hr_zone_definition = extract_hr_zones(ff, lthr_bpm=lthr)

    # Provide a human-readable recovery time (e.g. "2d 09:45" or "9:45").
    def _format_minutes_readable(mins: Optional[int]) -> Optional[str]:
        if mins is None:
            return None
        try:
            mins = int(mins)
        except Exception:
            return None
        days = mins // 1440
        rem = mins % 1440
        hours = rem // 60
        minutes = rem % 60
        if days > 0:
            return f"{days}d {hours}:{minutes:02d}"
        return f"{hours}:{minutes:02d}"

    recovery_time_readable = _format_minutes_readable(recovery_time_min)

    # Local time
    tz = timezone.utc if tz_name is None else None
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc

    if session_start_utc is not None:
        start_local = session_start_utc.astimezone(tz)
    else:
        start_local = None

    # Build blocks
    blocks: Dict[str, BlockStats] = {}
    # Keep mapping of block key -> lap dict so we can re-select records for each block
    block_laps: Dict[str, dict] = {}
    total_laps = len(laps)
    step_count = len(steps)

    # Build a step-to-lap mapping that handles repeat structures
    # Scan for repeat steps and build the full execution sequence
    step_sequence = []
    i = 0
    while i < len(steps):
        step = steps[i]
        duration_type = str(step.get("duration_type") or "").lower()
        
        if "repeat" in duration_type:
            # Found a repeat marker - figure out what to repeat
            # The "repeat_steps" field tells us how many steps to repeat
            # The "duration_step" field tells us which step to go back to
            repeat_steps = step.get("repeat_steps", 2)
            duration_step = step.get("duration_step")
            
            if duration_step is not None:
                # duration_step is the step index to jump back to
                repeat_block_start = int(duration_step)
                repeat_block_end = i
            else:
                # Fallback: repeat the previous N steps
                repeat_block_start = max(0, i - repeat_steps)
                repeat_block_end = i
            
            repeat_block = list(range(repeat_block_start, repeat_block_end))
            
            # The repeat marker tells us to cycle through previous steps
            # We need to figure out how many times based on remaining laps
            # For now, we'll handle this dynamically when mapping laps
            step_sequence.append(("repeat", repeat_block))
            i += 1
        else:
            step_sequence.append(("step", i))
            i += 1
    
    # Now map laps to steps, expanding repeats as needed
    # Strategy: consume laps by matching them to step durations
    lap_to_step = []
    seq_idx = 0
    
    for lap_idx in range(len(laps)):
        lap = laps[lap_idx]
        lap_duration = lap.get("total_timer_time", 0)
        
        if seq_idx >= len(step_sequence):
            # Ran out of step sequence, use last step
            if lap_to_step:
                lap_to_step.append(lap_to_step[-1])
            else:
                lap_to_step.append(len(steps) - 1)
            continue
        
        seq_item_type, seq_item_data = step_sequence[seq_idx]
        
        if seq_item_type == "repeat":
            # This is a repeat marker - it tells us to repeat the block
            # But we need to look ahead to see when to exit the repeat
            # For now, just skip the repeat marker and let the next lap decide
            seq_idx += 1
            # Re-process this lap with the next sequence item
            if seq_idx < len(step_sequence):
                seq_item_type, seq_item_data = step_sequence[seq_idx]
        
        if seq_item_type == "step":
            step = steps[seq_item_data]
            step_duration = step.get("duration_time", 0)
            
            # Check if this lap matches this step's duration (within 10 seconds)
            if abs(lap_duration - step_duration) < 10:
                # Match! Use this step for this lap
                lap_to_step.append(seq_item_data)
                
                # Move to next step ONLY if the next item is not a repeat
                # or if we're not in a repeat block
                if seq_idx + 1 < len(step_sequence):
                    next_type, next_data = step_sequence[seq_idx + 1]
                    if next_type != "repeat":
                        seq_idx += 1
                    # else: stay on this step, the repeat will be processed next lap
                else:
                    seq_idx += 1
            else:
                # Duration mismatch - might be in a repeat cycle
                # Try to find a matching step by duration in the nearby steps
                found = False
                for check_idx in range(max(0, seq_idx - 5), min(len(step_sequence), seq_idx + 5)):
                    if step_sequence[check_idx][0] == "step":
                        check_step = steps[step_sequence[check_idx][1]]
                        check_duration = check_step.get("duration_time", 0)
                        if abs(lap_duration - check_duration) < 10:
                            lap_to_step.append(step_sequence[check_idx][1])
                            found = True
                            break
                
                if not found:
                    # Fallback: use current step
                    lap_to_step.append(seq_item_data)
    
    # Check if we need to exit repeat mode when we see enough laps
    # The last non-repeat step should be the cooldown
    # Adjust: if there are more steps after the repeat, we need to exit repeat mode
    if len(step_sequence) > 1:
        last_seq_item = step_sequence[-1]
        if last_seq_item[0] == "step":
            # There's a step after the repeat (likely cooldown)
            # We need to figure out when to stop repeating and use that final step
            # Count backwards from total laps to find when cooldown should start
            cooldown_step_idx = last_seq_item[1]
            cooldown_step = steps[cooldown_step_idx]
            if cooldown_step.get("intensity") == "cooldown":
                # Find last lap with significant duration (>30s)
                last_real_lap_idx = len(laps) - 1
                while last_real_lap_idx > 0:
                    dur = laps[last_real_lap_idx].get("total_timer_time")
                    if dur and float(dur) >= 30:
                        break
                    last_real_lap_idx -= 1
                # Map that lap to cooldown step
                if last_real_lap_idx < len(lap_to_step):
                    lap_to_step[last_real_lap_idx] = cooldown_step_idx
    
    for i, lap in enumerate(laps):
        step_idx = lap_to_step[i] if i < len(lap_to_step) else (len(steps) - 1)
        step = steps[step_idx] if step_idx < len(steps) else {}
        block_type = classify_block_type(step, i, total_laps)

        start = lap.get("start_time")
        dur_s = lap.get("total_timer_time")
        dist_m = lap.get("total_distance")
        
        # Skip only the final segment if it's very short (less than 30 seconds) - likely post-workout artifact
        # Keep all other short segments as they may be legitimate workout intervals
        is_last_lap = (i == total_laps - 1)
        if is_last_lap and dur_s is not None and float(dur_s) < 30:
            continue

        # Name blocks consistently
        if block_type == "warmup":
            key = "warmup"
        elif block_type == "cooldown":
            key = "cooldown"
        elif block_type == "float":
            key = f"float_{i}"  # you can re-label later (float_1, float_2...)
        else:  # work / other
            key = f"active_{i}"

        avg_hr = lap.get("avg_heart_rate")
        # Use "Lap Power" field from Stryd (falls back to avg_power if not present)
        avg_power = lap.get("Lap Power") or lap.get("avg_power")

        if start is not None and start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        end = None
        if start is not None and dur_s is not None:
            end = start + timedelta(seconds=float(dur_s))

        distance_km = None
        if dist_m is not None:
            distance_km = float(dist_m) / 1000.0

        block = BlockStats(
            name=key,
            type=block_type,
            start_utc=start.isoformat() if start else None,
            end_utc=end.isoformat() if end else None,
            duration_min=_round((float(dur_s) / 60.0) if dur_s is not None else None, 1),
            distance_km=_round(distance_km, 2),
            avg_hr=_round(avg_hr, 0),
            avg_power=_round(avg_power, 0),
        )

        # Attach power target if present
        tmin, tmax = extract_power_target(step)
        if tmin is not None and tmax is not None:
            block.target_min_w = _round(tmin, 0)
            block.target_max_w = _round(tmax, 0)

            # Compute time in band from record samples
            recs = records_for_lap(records, lap)
            band_stats = compute_power_band_stats(recs, tmin, tmax)
            block.pct_time_below = band_stats["below"]
            block.pct_time_in_range = band_stats["in"]
            block.pct_time_above = band_stats["above"]

        blocks[key] = block
        block_laps[key] = lap

    # Build top-level summary
    distance_km_total = None if total_distance_m is None else total_distance_m / 1000.0
    duration_min_total = None if total_timer_s is None else total_timer_s / 60.0

    # Build the top-level summary dictionary (without blocks yet)
    summary: Dict[str, Any] = {
        "source_file": str(path),
        # prefer FIT file serial_number if present
        "id": str(file_serial) if file_serial is not None else path.stem,
        "name": workout_name or (workout_block_name or "Activity"),
        "hr_zone_definition": hr_zone_definition,
        # expose workout block name explicitly when present
        "workout_name": workout_block_name,
        # date in YYYY-MM-DD (derived from session start)
        "date": session_start_utc.date().isoformat() if session_start_utc else None,
        "sport": str(sport).lower() if sport else None,
        "start_utc": session_start_utc.isoformat() if session_start_utc else None,
        "start_local": start_local.isoformat() if start_local else None,
        "distance_km": _round(distance_km_total, 2),
        "duration_min": _round(duration_min_total, 1),
        "elev_gain_m": _round(total_ascent_m, 0) if total_ascent_m is not None else None,
        "avg_hr": _round(avg_hr_session, 0),
        "max_hr": _round(max_hr_session, 0),
        # prefer computed session values from record samples
        "avg_power": _round(session_avg_power or avg_power_session, 0),
        "max_power": _round(session_max_power or max_power_session, 0),
        "calories_kcal": _round(calories, 0) if calories is not None else None,
        "aerobic_te": _round(aerobic_te, 1) if aerobic_te is not None else None,
        "anaerobic_te": _round(anaerobic_te, 1) if anaerobic_te is not None else None,
        "vo2_max": _round(vo2_max, 4) if vo2_max is not None else None,
        "recovery_time_min": recovery_time_min,
        "recovery_time_readable": recovery_time_readable,
        "critical_power": critical_power,
        "avg_temperature": avg_temperature,
        "baseline_humidity": baseline_humidity,
        "actual_weight": _round(actual_weight, 1) if actual_weight is not None else None,
        "resting_hr": resting_hr,
        "lthr": lthr,
    }

    # Helper: aggregate a list with median/mean and return None if empty
    def _median_or_none(samples: List[float]) -> Optional[float]:
        if not samples:
            return None
        try:
            return float(statistics.median(samples))
        except Exception:
            return None

    def _mean_or_none(samples: List[float]) -> Optional[float]:
        if not samples:
            return None
        try:
            return float(statistics.mean(samples))
        except Exception:
            return None

    # Unit conversion helpers
    def _step_length_mm_to_m(mm: Optional[float]) -> Optional[float]:
        """Convert step length from mm to meters."""
        if mm is None:
            return None
        try:
            return float(mm) / 1000.0
        except Exception:
            return None

    def _cadence_per_leg_to_spm(per_leg: Optional[float]) -> Optional[float]:
        """Convert cadence from per-leg (one foot) to steps per minute (both feet)."""
        if per_leg is None:
            return None
        try:
            return float(per_leg) * 2.0
        except Exception:
            return None

    def _vert_osc_mm_to_cm(mm: Optional[float]) -> Optional[float]:
        """Convert vertical oscillation from mm to cm."""
        if mm is None:
            return None
        try:
            return float(mm) / 10.0
        except Exception:
            return None

    # Build per-block output including running_dynamics
    blocks_out: Dict[str, Any] = {}
    for name, b in blocks.items():
        lap = block_laps.get(name)
        recs = records_for_lap(records, lap) if lap is not None else []

        # Gather samples for this block
        samples = {
            "form_power": [],
            "lss": [],
            "gct": [],
            "vert_osc": [],
            "step_length": [],
            "cadence": [],
            "air_power_pct": [],
            "form_power_ratio": [],
        }
        for r in recs:
            if r.get("form_power") is not None:
                samples["form_power"].append(r["form_power"])
            if r.get("lss") is not None:
                samples["lss"].append(r["lss"])
            if r.get("gct") is not None:
                samples["gct"].append(r["gct"])
            if r.get("vert_osc") is not None:
                samples["vert_osc"].append(r["vert_osc"])
            if r.get("step_length") is not None:
                samples["step_length"].append(r["step_length"])
            if r.get("cadence") is not None:
                samples["cadence"].append(r["cadence"])
            if r.get("air_power_pct") is not None:
                samples["air_power_pct"].append(r["air_power_pct"])
            if r.get("form_power_ratio") is not None:
                samples["form_power_ratio"].append(r["form_power_ratio"])

        # Compute medians and apply unit conversions
        step_length_med = _median_or_none(samples["step_length"])
        cadence_med = _median_or_none(samples["cadence"])
        vert_osc_med = _median_or_none(samples["vert_osc"])
        
        running_dynamics: Dict[str, Optional[float]] = {
            "form_power_med": _median_or_none(samples["form_power"]),
            "lss_med": _median_or_none(samples["lss"]),
            "gct_med": _median_or_none(samples["gct"]),
            "vert_osc_med": _round(_vert_osc_mm_to_cm(vert_osc_med), 1),  # mm → cm
            "step_length_med": _round(_step_length_mm_to_m(step_length_med), 3),  # mm → m
            "cadence_med": _round(_cadence_per_leg_to_spm(cadence_med), 0),  # per-leg → spm (both feet)
            "air_power_pct_mean": _round(_mean_or_none(samples["air_power_pct"]), 2),
            "form_power_ratio_mean": _round(_mean_or_none(samples["form_power_ratio"]), 2),
        }

        # Compute HR zone distribution for this block
        hr_zones = compute_zone_distribution(
            recs, hr_zone_definition, "heart_rate", hr_zone_label
        )

        # Compute HR drift for eligible blocks
        hr_drift_pct = None
        if recs and b.duration_min is not None and b.duration_min >= 8 and b.type in ("warmup", "work", "float"):
            hr_drift_pct = compute_hr_drift_pct(recs)

        # Compute HR 5s delta for segments longer than 30s
        hr_first5s_to_last5s_delta = None
        if recs and b.duration_min is not None and b.duration_min * 60 > 30:
            hr_first5s_to_last5s_delta = compute_hr_first5s_to_last5s_delta(recs)

        blocks_out[name] = {
            "type": b.type,
            "start_utc": b.start_utc,
            "end_utc": b.end_utc,
            "duration_min": b.duration_min,
            "distance_km": b.distance_km,
            "avg_hr": b.avg_hr,
            "avg_power": b.avg_power,
            "hr_drift_pct": hr_drift_pct,
            "hr_first5s_to_last5s_delta": hr_first5s_to_last5s_delta,
            "target_power": (
                {
                    "min_w": b.target_min_w,
                    "max_w": b.target_max_w,
                    "pct_time_below": b.pct_time_below,
                    "pct_time_in_range": b.pct_time_in_range,
                    "pct_time_above": b.pct_time_above,
                }
                if b.target_min_w is not None and b.target_max_w is not None
                else None
            ),
            "running_dynamics": running_dynamics,
            "hr_zones": hr_zones,
        }

    # Run-wide running dynamics (aggregate across all records in the run)
    all_samples = {
        "form_power": [r["form_power"] for r in records if r.get("form_power") is not None],
        "lss": [r["lss"] for r in records if r.get("lss") is not None],
        "gct": [r["gct"] for r in records if r.get("gct") is not None],
        "vert_osc": [r["vert_osc"] for r in records if r.get("vert_osc") is not None],
        "step_length": [r["step_length"] for r in records if r.get("step_length") is not None],
        "cadence": [r["cadence"] for r in records if r.get("cadence") is not None],
        "air_power_pct": [r["air_power_pct"] for r in records if r.get("air_power_pct") is not None],
        "form_power_ratio": [r["form_power_ratio"] for r in records if r.get("form_power_ratio") is not None],
    }

    # Compute run-wide medians and apply unit conversions
    step_length_med_all = _median_or_none(all_samples["step_length"])
    cadence_med_all = _median_or_none(all_samples["cadence"])
    vert_osc_med_all = _median_or_none(all_samples["vert_osc"])
    
    running_dynamics_summary = {
        "form_power_med": _median_or_none(all_samples["form_power"]),
        "lss_med": _median_or_none(all_samples["lss"]),
        "gct_med": _median_or_none(all_samples["gct"]),
        "vert_osc_med": _round(_vert_osc_mm_to_cm(vert_osc_med_all), 1),  # mm → cm
        "step_length_med": _round(_step_length_mm_to_m(step_length_med_all), 3),  # mm → m
        "cadence_med": _round(_cadence_per_leg_to_spm(cadence_med_all), 0),  # per-leg → spm (both feet)
        "air_power_pct_mean": _round(_mean_or_none(all_samples["air_power_pct"]), 2),
        "form_power_ratio_mean": _round(_mean_or_none(all_samples["form_power_ratio"]), 2),
    }

    # Compute session-level (whole-run) HR zone distribution
    session_hr_zones = compute_zone_distribution(
        records, hr_zone_definition, "heart_rate", hr_zone_label
    )

    # Attach blocks and run-wide summary to top-level summary
    summary["blocks"] = blocks_out
    summary["running_dynamics_summary"] = running_dynamics_summary
    summary["session_hr_zones"] = session_hr_zones

    return summary


# ---------- CLI entrypoint ----------

def main(argv: List[str]) -> None:
    if len(argv) < 2:
        print(f"Usage: {argv[0]} ACTIVITY.fit [Europe/London]", file=sys.stderr)
        sys.exit(1)

    fit_path = Path(argv[1])
    if not fit_path.exists():
        print(f"File not found: {fit_path}", file=sys.stderr)
        sys.exit(1)

    tz_name = argv[2] if len(argv) > 2 else "Europe/London"

    summary = build_blocks_from_fit(fit_path, tz_name=tz_name)

    # Write to YAML file alongside the FIT file
    out_path = fit_path.with_suffix(".yaml")
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(summary, f, sort_keys=False, allow_unicode=True)
    print(f"Wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv)

