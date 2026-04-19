from __future__ import annotations

import logging
import threading
import time

import hashlib
import hmac
import re
import unicodedata
from datetime import date
from functools import wraps

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
import markdown as md
import nh3

from runcoach.analyzer import analyze_and_write
from runcoach.auth import verify_password
from runcoach.config import Config
from runcoach.pipeline import run_full_pipeline
from runcoach.web import csrf

log = logging.getLogger(__name__)

bp = Blueprint("main", __name__)

_PROFILE_MAX_LEN = 5_000
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_profile(text: str) -> str:
    """Strip control characters and enforce a maximum length."""
    # Normalise unicode (NFC) then remove C0/C1 control chars except \t, \n, \r
    text = unicodedata.normalize("NFC", text)
    text = _CONTROL_CHAR_RE.sub("", text)
    return text[:_PROFILE_MAX_LEN]


def _login_required(f):
    """Redirect to login if the session is not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("main.login", next=request.path))
        return f(*args, **kwargs)
    return decorated

# Tags and attributes that the markdown library legitimately produces.
_ALLOWED_TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "br", "hr",
    "ul", "ol", "li",
    "strong", "em", "b", "i", "u", "s", "del",
    "a", "code", "pre",
    "blockquote",
    "table", "thead", "tbody", "tr", "th", "td",
    "img",
    "div", "span",
    "sup", "sub",
}
_ALLOWED_ATTRIBUTES: dict[str, set[str]] = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title"},
    "td": {"align"},
    "th": {"align"},
}


def _safe_markdown(text: str) -> str:
    """Convert markdown to HTML and sanitize the output."""
    raw_html = md.markdown(text, extensions=["tables", "fenced_code"])
    return nh3.clean(
        raw_html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
    )


# FIT file magic: bytes 8–11 must be ".FIT" (ASCII 0x2E 0x46 0x49 0x54).
_FIT_MAGIC = b".FIT"
_FIT_MAGIC_OFFSET = 8
_FIT_HEADER_MIN_SIZE = 12


def _db():
    return current_app.config["db"]


def _scheduler():
    return current_app.config["scheduler"]


@bp.route("/")
@_login_required
def index():
    from datetime import date as _date, timedelta

    db = _db()
    today = _date.today()

    # Build a 3-week calendar: previous Mon–Sun + current Mon–Sun + next Mon–Sun
    # Find Monday of the current week
    current_monday = today - timedelta(days=today.weekday())
    prev_monday = current_monday - timedelta(days=7)
    next_sunday_plus1 = current_monday + timedelta(days=21)  # exclusive end (3 weeks)

    # Fetch planned workouts and actual runs for the 3-week window
    cal_start = prev_monday.isoformat()
    cal_end = next_sunday_plus1.isoformat()
    planned = db.get_planned_workouts_in_range(cal_start, cal_end)
    actual = db.get_runs_in_date_range(cal_start, cal_end)

    # Index by date for easy template lookup
    planned_by_date = {}
    for pw in planned:
        planned_by_date.setdefault(pw["date"], []).append(pw)
    actual_by_date = {}
    for run in actual:
        actual_by_date.setdefault(run["date"], []).append(run)

    # Generate calendar days
    calendar_days = []
    for i in range(21):
        d = prev_monday + timedelta(days=i)
        ds = d.isoformat()
        calendar_days.append({
            "date": ds,
            "day": d.day,
            "weekday": d.strftime("%a"),
            "is_today": d == today,
            "is_past": d < today,
            "week": i // 7,  # 0 = prev, 1 = current, 2 = next
            "planned": planned_by_date.get(ds, []),
            "actual": actual_by_date.get(ds, []),
        })

    stats = db.get_sync_stats()
    last_sync = db.get_last_sync()
    recent_runs = db.get_runs_paginated(limit=5)

    return render_template(
        "index.html",
        calendar_days=calendar_days,
        prev_monday=prev_monday,
        current_monday=current_monday,
        recent_runs=recent_runs,
        stats=stats,
        last_sync=last_sync,
        syncing=_scheduler().is_syncing,
    )


@bp.route("/workouts")
@_login_required
def workouts():
    """Full paginated list of past and upcoming planned workouts."""
    from datetime import date as _date

    db = _db()
    today = _date.today().isoformat()
    per_page = 10

    past_page = request.args.get("past_page", 1, type=int)
    upcoming_page = request.args.get("upcoming_page", 1, type=int)

    past_total = db.count_past_planned_workouts(today)
    upcoming_total = db.count_upcoming_planned_workouts(today)

    past = db.get_past_planned_workouts(today, limit=per_page, offset=(past_page - 1) * per_page)
    upcoming = db.get_upcoming_planned_workouts_paged(today, limit=per_page, offset=(upcoming_page - 1) * per_page)

    runs_page = request.args.get("runs_page", 1, type=int)
    runs_total = db.count_runs()
    runs = db.get_runs_paginated(limit=per_page, offset=(runs_page - 1) * per_page)

    import math
    return render_template(
        "workouts.html",
        past_workouts=past,
        upcoming_workouts=upcoming,
        runs=runs,
        past_page=past_page,
        past_pages=math.ceil(past_total / per_page),
        past_total=past_total,
        upcoming_page=upcoming_page,
        upcoming_pages=math.ceil(upcoming_total / per_page),
        upcoming_total=upcoming_total,
        runs_page=runs_page,
        runs_pages=math.ceil(runs_total / per_page),
        runs_total=runs_total,
        stats=db.get_sync_stats(),
        syncing=_scheduler().is_syncing,
    )


@bp.route("/run/<int:run_id>")
@_login_required
def run_detail(run_id: int):
    import yaml as _yaml
    
    db = _db()
    config: Config = current_app.config["config"]
    run = db.get_run(run_id)
    if run is None:
        flash("Run not found")
        return redirect(url_for("main.index"))

    commentary_html = ""
    if run.get("commentary"):
        commentary_html = _safe_markdown(run["commentary"])

    # Load YAML data for visualizations
    workout_data = None
    if run.get("yaml_path"):
        yaml_path = config.data_dir / run["yaml_path"]
        if yaml_path.exists():
            try:
                with open(yaml_path, "r", encoding="utf-8") as f:
                    workout_data = _yaml.safe_load(f)
            except Exception:
                pass

    # Load prescribed workout for this date
    prescribed = db.get_planned_workout_for_date(run["date"])

    # Stryd athlete UUID for external link
    default_uid = db.get_default_user_id()
    stryd_athlete_id = db.get_stryd_athlete_id(default_uid) if default_uid else None

    # Strava map polyline — fetch lazily if we have an activity ID but no stored polyline
    map_coords: list | None = None
    if run.get("strava_map_polyline"):
        from runcoach.strava import decode_polyline
        map_coords = decode_polyline(run["strava_map_polyline"])
    elif run.get("strava_activity_id") and default_uid:
        config_obj: Config = current_app.config["config"]
        if config_obj.strava_client_id:
            try:
                from runcoach.strava import StravaClient, decode_polyline
                client = StravaClient(config_obj.strava_client_id, config_obj.strava_client_secret)
                token = client.get_valid_access_token(db, default_uid)
                if token:
                    activity = client.get_activity(run["strava_activity_id"], token)
                    polyline = (activity.get("map") or {}).get("summary_polyline") or None
                    if polyline:
                        db.update_run_strava_data(run_id=run["id"], strava_map_polyline=polyline)
                        map_coords = decode_polyline(polyline)
            except Exception as exc:
                log.warning("Could not fetch Strava polyline for run %s: %s", run_id, exc)

    return render_template(
        "run_detail.html",
        run=run,
        commentary_html=commentary_html,
        workout_data=workout_data,
        prescribed=prescribed,
        stryd_athlete_id=stryd_athlete_id,
        map_coords=map_coords,
    )


@bp.route("/sync", methods=["POST"])
@_login_required
def sync():
    _scheduler().trigger_now()
    flash("Sync started in background")
    return redirect(url_for("main.index"))


@bp.route("/run/<int:run_id>/analyze", methods=["POST"])
@_login_required
def analyze_run_route(run_id: int):
    db = _db()
    config: Config = current_app.config["config"]
    run = db.get_run(run_id)

    if run is None:
        flash("Run not found")
        return redirect(url_for("main.index"))

    if not config.has_llm:
        flash("No LLM provider configured")
        return redirect(url_for("main.run_detail", run_id=run_id))

    if run["stage"] not in ("parsed", "analyzed"):
        flash(f"Run must be parsed first (current stage: {run['stage']})")
        return redirect(url_for("main.run_detail", run_id=run_id))

    def _do_analyze(app, run_id, config):
        with app.app_context():
            db = _db()
            run = db.get_run(run_id)
            try:
                yaml_path = config.data_dir / run["yaml_path"]
                md_path, result = analyze_and_write(yaml_path, config, db=db)
                md_path_rel = str(md_path.relative_to(config.data_dir))
                db.update_analyzed(
                    run_id=run["id"],
                    md_path=md_path_rel,
                    commentary=result["commentary"],
                    model_used=config.active_model,
                    prompt_tokens=result.get("prompt_tokens"),
                    completion_tokens=result.get("completion_tokens"),
                )
                log.info("Analysis complete for run %s", run_id)
            except Exception as e:
                log.exception("Analysis failed for run %s: %s", run_id, e)
                db.update_error(run["id"], f"Analysis error: {e}")

    t = threading.Thread(
        target=_do_analyze,
        args=(current_app._get_current_object(), run_id, config),
        daemon=True,
    )
    t.start()
    flash("Analysis started in background")
    return redirect(url_for("main.run_detail", run_id=run_id))


@bp.route("/status")
def status():
    db = _db()
    stats = db.get_sync_stats()
    last_sync = db.get_last_sync()
    return jsonify(
        syncing=_scheduler().is_syncing,
        last_sync=last_sync,
        **stats,
    )


@bp.route("/run/<int:run_id>/status")
@_login_required
def run_status(run_id: int):
    """Return JSON status of a single run (for polling)."""
    db = _db()
    run = db.get_run(run_id)
    if run is None:
        return jsonify(error="not found"), 404
    return jsonify(
        stage=run["stage"],
        analyzed_at=run.get("analyzed_at"),
    )


@bp.route("/upload", methods=["POST"])
@_login_required
def upload():
    """Handle manual FIT file upload."""
    import re
    from datetime import datetime
    from pathlib import Path

    from runcoach.parser import parse_and_write

    config: Config = current_app.config["config"]
    db = _db()

    if "fit_file" not in request.files:
        flash("No file provided")
        return redirect(url_for("main.index"))

    fit_file = request.files["fit_file"]
    if not fit_file.filename:
        flash("No file selected")
        return redirect(url_for("main.index"))

    if not fit_file.filename.lower().endswith(".fit"):
        flash("File must be a .fit file")
        return redirect(url_for("main.index"))

    # Validate FIT magic bytes before accepting the file
    header = fit_file.read(_FIT_HEADER_MIN_SIZE)
    fit_file.seek(0)
    if (
        len(header) < _FIT_HEADER_MIN_SIZE
        or header[_FIT_MAGIC_OFFSET : _FIT_MAGIC_OFFSET + len(_FIT_MAGIC)] != _FIT_MAGIC
    ):
        flash("File does not appear to be a valid FIT file")
        return redirect(url_for("main.index"))

    # Get activity name from form or derive from filename
    activity_name = request.form.get("activity_name", "").strip()
    if not activity_name:
        activity_name = fit_file.filename.rsplit(".", 1)[0].replace("_", " ").title()

    # Sanitize name for filesystem
    clean_name = activity_name.lower().replace(" ", "_").replace("/", "_")
    clean_name = re.sub(r"[^a-z0-9_-]", "", clean_name)

    # Get date from form or use today
    activity_date = request.form.get("activity_date", "")
    if activity_date:
        try:
            dt = datetime.strptime(activity_date, "%Y-%m-%d")
        except ValueError:
            flash("Invalid date format")
            return redirect(url_for("main.index"))
    else:
        dt = datetime.now()

    date_str = dt.strftime("%Y-%m-%d")
    date_prefix = dt.strftime("%Y%m%d")
    dir_name = f"{date_prefix}_{clean_name}"

    # Build directory: data/activities/YYYY/MM/YYYYMMDD_name/
    activity_dir = (
        config.activities_dir
        / dt.strftime("%Y")
        / dt.strftime("%m")
        / dir_name
    )
    activity_dir.mkdir(parents=True, exist_ok=True)

    # Save FIT file
    fit_path = activity_dir / f"{dir_name}.fit"
    fit_file.save(str(fit_path))

    # Store path relative to data_dir
    fit_path_rel = str(fit_path.relative_to(config.data_dir))

    # Check if already exists
    if db.get_run_by_fit_path(fit_path_rel):
        flash("A run with this file already exists")
        return redirect(url_for("main.index"))

    # Parse the FIT file immediately to get distance/duration
    try:
        # Get planned workout title for this date to use full name (FIT truncates at 32 chars)
        planned_workout_title = None
        planned_workouts = db.get_planned_workout_for_date(date_str)
        if planned_workouts:
            planned_workout_title = planned_workouts[0]["title"]

        yaml_path = parse_and_write(
            fit_path,
            timezone=config.timezone,
            manual_upload=True,
            planned_workout_title=planned_workout_title,
        )
        yaml_path_rel = str(yaml_path.relative_to(config.data_dir))

        # Read back parsed summary for DB fields
        import yaml as _yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            parsed = _yaml.safe_load(f)

        # Insert as manual run
        run_id = db.insert_manual_run(
            name=activity_name,
            date=date_str,
            fit_path=fit_path_rel,
            distance_m=parsed.get("distance_km", 0) * 1000 if parsed.get("distance_km") else None,
            moving_time_s=int(parsed.get("duration_min", 0) * 60) if parsed.get("duration_min") else None,
        )

        # Update as parsed
        db.update_parsed(
            run_id=run_id,
            yaml_path=yaml_path_rel,
            avg_power_w=parsed.get("avg_power"),
            avg_hr=parsed.get("avg_hr"),
            workout_name=parsed.get("workout_name"),
        )

        flash(f"Uploaded and parsed: {activity_name}")
        return redirect(url_for("main.run_detail", run_id=run_id))

    except Exception as e:
        log.exception("Failed to parse uploaded FIT file: %s", e)
        # Still insert the run even if parsing failed
        run_id = db.insert_manual_run(
            name=activity_name,
            date=date_str,
            fit_path=fit_path_rel,
        )
        db.update_error(run_id, f"Parse error: {e}")
        flash(f"Uploaded but failed to parse: {e}")
        return redirect(url_for("main.index"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Session login for the web UI."""
    if request.method == "POST":
        password = request.form.get("password", "")
        db = _db()
        user_id = db.get_default_user_id()
        if user_id is not None:
            row = db.get_user_password_hash(user_id)
            if row and verify_password(password, row):
                session["logged_in"] = True
                session.permanent = False
                next_url = request.form.get("next") or url_for("main.index")
                # Guard against open-redirect: only allow relative paths
                if not next_url.startswith("/") or next_url.startswith("//"):
                    next_url = url_for("main.index")
                return redirect(next_url)
        flash("Incorrect password.")
    next_url = request.args.get("next", "")
    return render_template("login.html", next=next_url)


@bp.route("/logout", methods=["POST"])
def logout():
    """Clear session and redirect to login."""
    session.clear()
    return redirect(url_for("main.login"))


@bp.route("/athlete-profile", methods=["GET"])
@_login_required
def athlete_profile():
    """Display the athlete profile page."""
    db = _db()
    config: Config = current_app.config["config"]
    user_id = db.get_default_user_id()
    profile = db.get_athlete_profile(user_id) if user_id else ""
    stryd_athlete_id = db.get_stryd_athlete_id(user_id) if user_id else None
    display_name = db.get_display_name(user_id) if user_id else ""
    user_row = db.get_user_by_id(user_id) if user_id else None
    username = user_row["username"] if user_row else ""
    race_goal = db.get_race_goal(user_id) if user_id else {"race_date": None, "race_distance": None}
    strava_connected = bool(
        user_id and db.get_strava_tokens(user_id)
    ) if config.strava_client_id else False
    strava_athlete_id = None
    strava_webhook_id = None
    if strava_connected and user_id:
        tokens = db.get_strava_tokens(user_id)
        strava_athlete_id = tokens.get("strava_athlete_id") if tokens else None
        strava_webhook_id = db.get_strava_webhook_subscription_id(user_id)
    return render_template(
        "athlete_profile.html",
        profile=profile,
        display_name=display_name,
        username=username,
        race_goal=race_goal,
        stryd_athlete_id=stryd_athlete_id,
        strava_connected=strava_connected,
        strava_athlete_id=strava_athlete_id,
        strava_webhook_id=strava_webhook_id,
        strava_enabled=bool(config.strava_client_id),
    )


@bp.route("/athlete-profile", methods=["POST"])
@_login_required
def athlete_profile_save():
    """Save the athlete profile."""
    db = _db()
    user_id = db.get_default_user_id()
    if user_id is None:
        flash("No user account found. Cannot save profile.")
        return redirect(url_for("main.athlete_profile"))

    raw = request.form.get("profile", "")
    profile_text = _sanitize_profile(raw).strip()
    db.update_athlete_profile(user_id, profile_text)
    flash("Athlete profile saved.")
    return redirect(url_for("main.athlete_profile"))


@bp.route("/athlete-profile/stryd-id", methods=["POST"])
@_login_required
def stryd_athlete_id_save():
    """Save the Stryd athlete UUID."""
    db = _db()
    user_id = db.get_default_user_id()
    if user_id is None:
        flash("No user account found.")
        return redirect(url_for("main.athlete_profile"))
    stryd_id = request.form.get("stryd_athlete_id", "").strip()
    db.update_stryd_athlete_id(user_id, stryd_id)
    flash("Stryd athlete ID saved.")
    return redirect(url_for("main.athlete_profile"))


@bp.route("/athlete-profile/user-info", methods=["POST"])
@_login_required
def user_info_save():
    """Save the athlete's display name and login username."""
    db = _db()
    user_id = db.get_default_user_id()
    if user_id is None:
        flash("No user account found.")
        return redirect(url_for("main.athlete_profile"))
    display_name = request.form.get("display_name", "").strip()
    new_username = request.form.get("username", "").strip()
    if not new_username:
        flash("Username cannot be empty.")
        return redirect(url_for("main.athlete_profile"))
    # Check if new username conflicts with another user
    existing = db.get_user_by_username(new_username)
    if existing and existing["id"] != user_id:
        flash("That username is already taken.")
        return redirect(url_for("main.athlete_profile"))
    db.update_user_info(user_id, display_name, new_username)
    flash("User info saved.")
    return redirect(url_for("main.athlete_profile"))


@bp.route("/athlete-profile/race-goal", methods=["POST"])
@_login_required
def race_goal_save():
    """Save the athlete's race goal (date + distance)."""
    from runcoach.analyzer import RACE_DISTANCES
    db = _db()
    user_id = db.get_default_user_id()
    if user_id is None:
        flash("No user account found.")
        return redirect(url_for("main.athlete_profile"))

    race_date_raw = request.form.get("race_date", "").strip()
    race_distance_raw = request.form.get("race_distance", "").strip()

    # Validate race date (must be a valid future date)
    race_date: str | None = None
    if race_date_raw:
        try:
            parsed_date = date.fromisoformat(race_date_raw)
            if parsed_date <= date.today():
                flash("Race date must be in the future.")
                return redirect(url_for("main.athlete_profile"))
            race_date = parsed_date.isoformat()
        except ValueError:
            flash("Invalid race date format.")
            return redirect(url_for("main.athlete_profile"))

    # Validate race distance
    race_distance: str | None = None
    if race_distance_raw:
        if race_distance_raw not in RACE_DISTANCES:
            flash("Invalid race distance selected.")
            return redirect(url_for("main.athlete_profile"))
        race_distance = race_distance_raw

    db.update_race_goal(user_id, race_date, race_distance)
    if race_date and race_distance:
        flash("Race goal saved.")
    else:
        flash("Race goal cleared.")
    return redirect(url_for("main.athlete_profile"))


# ---------------------------------------------------------------------------
# Strava OAuth & webhook
# ---------------------------------------------------------------------------

@bp.route("/strava/connect")
@_login_required
def strava_connect():
    """Initiate the Strava OAuth flow."""
    from runcoach.strava import StravaClient
    config: Config = current_app.config["config"]
    if not config.strava_client_id:
        flash("Strava integration is not configured (STRAVA_CLIENT_ID missing).")
        return redirect(url_for("main.athlete_profile"))
    client = StravaClient(config.strava_client_id, config.strava_client_secret)
    redirect_uri = url_for("main.strava_callback", _external=True)
    return redirect(client.get_authorize_url(redirect_uri=redirect_uri))


@bp.route("/strava/callback")
@_login_required
def strava_callback():
    """Handle the OAuth callback from Strava."""
    from runcoach.strava import StravaClient
    config: Config = current_app.config["config"]
    db = _db()

    error = request.args.get("error")
    if error:
        flash(f"Strava authorization failed: {error}")
        return redirect(url_for("main.athlete_profile"))

    code = request.args.get("code")
    if not code:
        flash("No authorization code received from Strava.")
        return redirect(url_for("main.athlete_profile"))

    try:
        client = StravaClient(config.strava_client_id, config.strava_client_secret)
        token_data = client.exchange_code(code)
    except Exception as exc:
        log.error("Strava token exchange failed: %s", exc)
        flash("Failed to connect to Strava. Please try again.")
        return redirect(url_for("main.athlete_profile"))

    user_id = db.get_default_user_id()
    if user_id is None:
        flash("No user account found.")
        return redirect(url_for("main.athlete_profile"))

    athlete = token_data.get("athlete", {})
    strava_athlete_id = str(athlete.get("id", "")) if athlete.get("id") else None
    db.save_strava_tokens(
        user_id=user_id,
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        expires_at=token_data["expires_at"],
        strava_athlete_id=strava_athlete_id,
    )
    athlete_name = " ".join(filter(None, [
        athlete.get("firstname", ""), athlete.get("lastname", "")
    ]))

    # Attempt to register the webhook subscription automatically.
    # This is a per-app operation — we only need it once, but it's safe to
    # retry (Strava returns 409 Conflict if already registered).
    webhook_msg = ""
    if not config.strava_webhook_enabled:
        webhook_msg = " (Webhook registration skipped — STRAVA_WEBHOOK_ENABLED=false.)"
    elif config.strava_webhook_verify_token:
        callback_url = url_for("main.strava_webhook", _external=True)
        result = client.register_webhook(
            callback_url=callback_url,
            verify_token=config.strava_webhook_verify_token,
        )
        if result and not result.get("already_registered") and result.get("id"):
            db.save_strava_webhook_subscription_id(user_id, result["id"])
            webhook_msg = " Webhook registered."
        elif result and result.get("already_registered"):
            # Fetch existing subscription ID to keep it stored
            existing = client.get_webhook_subscription()
            if existing and existing.get("id"):
                db.save_strava_webhook_subscription_id(user_id, existing["id"])
            webhook_msg = " Webhook already active."
        else:
            webhook_msg = " Webhook registration failed — check that this server is publicly reachable."
    else:
        webhook_msg = " Set STRAVA_WEBHOOK_VERIFY_TOKEN to enable automatic sync."

    flash(f"Connected to Strava{' as ' + athlete_name if athlete_name else ''}!{webhook_msg}")
    return redirect(url_for("main.athlete_profile"))


@bp.route("/strava/backfill", methods=["POST"])
@_login_required
def strava_backfill():
    """
    Backfill Strava activity IDs and route polylines for historical runs
    that were parsed before Strava was connected.

    Fetches the athlete's Strava activity list and matches each running
    activity to an unlinked run record by date (``start_date_local``).
    """
    import datetime
    from runcoach.strava import StravaClient

    config: Config = current_app.config["config"]
    db = _db()
    user_id = db.get_default_user_id()
    if not user_id or not config.strava_client_id:
        flash("Strava is not configured.")
        return redirect(url_for("main.athlete_profile"))

    client = StravaClient(config.strava_client_id, config.strava_client_secret)
    access_token = client.get_valid_access_token(db, user_id)
    if not access_token:
        flash("No valid Strava token. Please reconnect Strava.")
        return redirect(url_for("main.athlete_profile"))

    unlinked = db.get_unlinked_runs()
    if not unlinked:
        flash("All runs already have a Strava activity linked.")
        return redirect(url_for("main.athlete_profile"))

    # Group unlinked runs by date for fast lookup.
    runs_by_date: dict[str, list[dict]] = {}
    for run in unlinked:
        date = (run.get("date") or "")[:10]
        if date:
            runs_by_date.setdefault(date, []).append(run)

    # Fetch Strava activities starting from just before the oldest unlinked run.
    oldest_date = min(runs_by_date.keys())
    after_ts = int(
        datetime.datetime(
            *[int(p) for p in oldest_date.split("-")],
            tzinfo=datetime.timezone.utc,
        ).timestamp()
    ) - 86400  # one day buffer

    RUNNING_TYPES = {"Run", "TrailRun", "VirtualRun", "Treadmill"}
    linked = 0
    page = 1
    while True:
        try:
            activities = client.list_activities(
                access_token, after=after_ts, per_page=100, page=page
            )
        except Exception as exc:
            log.error("Strava backfill: error fetching page %d: %s", page, exc)
            flash(f"Backfill stopped early — Strava API error: {exc}")
            break
        if not activities:
            break
        for activity in activities:
            sport = activity.get("sport_type") or activity.get("type", "")
            if sport not in RUNNING_TYPES:
                continue
            act_date = (activity.get("start_date_local") or "")[:10]
            if act_date not in runs_by_date:
                continue
            strava_id = str(activity["id"])
            if db.get_run_by_strava_id(strava_id):
                continue  # already linked
            polyline = (activity.get("map") or {}).get("summary_polyline") or None
            candidates = [r for r in runs_by_date[act_date] if not r.get("strava_activity_id")]
            if not candidates:
                continue
            run = candidates[-1]
            db.update_run_strava_data(
                run_id=run["id"],
                strava_activity_id=strava_id,
                strava_map_polyline=polyline,
            )
            run["strava_activity_id"] = strava_id  # prevent double-linking in same run
            linked += 1
            log.info(
                "Backfilled Strava activity %s to run %s (%s)",
                strava_id, run["id"], act_date,
            )
        if len(activities) < 100:
            break  # last page
        page += 1

    if linked:
        flash(f"Backfill complete — linked {linked} run{'s' if linked != 1 else ''} to Strava activities.")
    else:
        flash("Backfill complete — no new matches found.")
    return redirect(url_for("main.athlete_profile"))


@bp.route("/strava/disconnect", methods=["POST"])
@_login_required
def strava_disconnect():
    """Revoke Strava access and remove stored tokens."""
    from runcoach.strava import StravaClient
    config: Config = current_app.config["config"]
    db = _db()
    user_id = db.get_default_user_id()
    if user_id:
        tokens = db.get_strava_tokens(user_id)
        if tokens and tokens.get("strava_access_token") and config.strava_client_id:
            client = StravaClient(config.strava_client_id, config.strava_client_secret)
            client.deauthorize(tokens["strava_access_token"])
        db.clear_strava_tokens(user_id)
    flash("Disconnected from Strava.")
    return redirect(url_for("main.athlete_profile"))


@bp.route("/strava/webhook", methods=["GET"])
def strava_webhook_verify():
    """
    Strava webhook subscription verification (hub challenge).
    Strava sends GET with hub.challenge and hub.verify_token query params.
    """
    config: Config = current_app.config["config"]
    verify_token = request.args.get("hub.verify_token", "")
    challenge = request.args.get("hub.challenge", "")
    if not config.strava_webhook_verify_token or verify_token != config.strava_webhook_verify_token:
        return jsonify(error="Invalid verify token"), 403
    return jsonify({"hub.challenge": challenge})


@bp.route("/strava/webhook", methods=["POST"])
def strava_webhook():
    """
    Receive Strava webhook events.
    On activity create/update, trigger the sync pipeline and attempt to
    fetch the route polyline for the map.
    """
    config: Config = current_app.config["config"]
    if config.strava_client_secret:
        sig_header = request.headers.get("X-Hub-Signature", "")
        raw_body = request.get_data()
        expected = "sha256=" + hmac.new(
            config.strava_client_secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig_header, expected):
            return jsonify(error="Invalid signature"), 403

    data = request.get_json(silent=True) or {}
    object_type = data.get("object_type")
    aspect_type = data.get("aspect_type")
    activity_id = data.get("object_id")

    # Acknowledge immediately — Strava expects <2s response
    if object_type != "activity" or aspect_type not in ("create", "update"):
        return jsonify(ok=True)

    db = _db()
    app = current_app._get_current_object()

    def _handle_webhook(app, activity_id):
        with app.app_context():
            from runcoach.strava import StravaClient
            db = _db()
            config: Config = current_app.config["config"]

            # --- Fetch Strava activity first so we can filter sport type
            # before triggering any sync work at all. ---
            if not config.strava_client_id:
                log.debug("Strava not configured, skipping webhook handler")
                return
            user_id = db.get_default_user_id()
            if not user_id:
                return
            client = StravaClient(config.strava_client_id, config.strava_client_secret)
            access_token = client.get_valid_access_token(db, user_id)
            if not access_token:
                log.warning("No valid Strava access token for webhook handler")
                return
            try:
                activity = client.get_activity(activity_id, access_token)
            except Exception as exc:
                log.warning("Could not fetch Strava activity %s: %s", activity_id, exc)
                return

            sport_type = activity.get("sport_type", "") or activity.get("type", "")
            if sport_type not in ("Run", "TrailRun", "VirtualRun", "Treadmill"):
                log.debug("Ignoring Strava activity %s with sport_type=%s", activity_id, sport_type)
                return

            polyline = (activity.get("map", {}) or {}).get("summary_polyline") or None
            strava_id_str = str(activity_id)
            start_date = (activity.get("start_date_local") or "")[:10]  # YYYY-MM-DD

            def _try_link_run() -> bool:
                """Try to match the Strava activity to a run in the DB.

                Returns True if the run was found and updated, False otherwise.
                """
                existing = db.get_run_by_strava_id(strava_id_str)
                if existing:
                    db.update_run_strava_data(
                        run_id=existing["id"],
                        strava_map_polyline=polyline,
                    )
                    log.info(
                        "Linked Strava activity %s to run %s (by strava_id)",
                        strava_id_str, existing["id"],
                    )
                    return True

                if start_date:
                    runs_today = db.get_runs_on_date(start_date)
                    unlinked = [r for r in runs_today if not r.get("strava_activity_id")]
                    if unlinked:
                        db.update_run_strava_data(
                            run_id=unlinked[-1]["id"],
                            strava_activity_id=strava_id_str,
                            strava_map_polyline=polyline,
                        )
                        log.info(
                            "Linked Strava activity %s to run %s (by date %s)",
                            strava_id_str, unlinked[-1]["id"], start_date,
                        )
                        return True
                return False

            # --- Run the Stryd sync pipeline synchronously so we can check
            # whether the matching run arrived before deciding to retry. ---
            log.info(
                "Webhook: triggering pipeline for Strava activity %s (%s)",
                strava_id_str, sport_type,
            )
            run_full_pipeline(config, db)

            if _try_link_run():
                return

            # The Stryd FIT file may not have synced yet (Stryd's upload can
            # lag a minute or two). Retry at +30 s then +2 min.
            for delay in (30, 120):
                log.info(
                    "Strava activity %s not yet matched; retrying pipeline in %ds",
                    strava_id_str, delay,
                )
                time.sleep(delay)
                run_full_pipeline(config, db)
                if _try_link_run():
                    return

            log.warning(
                "Strava activity %s could not be matched to a Stryd run after retries",
                strava_id_str,
            )

    t = threading.Thread(
        target=_handle_webhook,
        args=(app, activity_id),
        daemon=True,
    )
    t.start()
    return jsonify(ok=True)


# Exempt Strava webhook endpoints from CSRF — they are called by Strava's
# servers (no session/cookie), not from HTML forms.
csrf.exempt(strava_webhook_verify)
csrf.exempt(strava_webhook)
