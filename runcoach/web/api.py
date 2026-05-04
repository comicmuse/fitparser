"""REST API endpoints for RunCoach mobile app."""

from __future__ import annotations

import logging
import os
import yaml
from datetime import datetime, timezone, date as date_type
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

from runcoach.auth import (
    create_access_token,
    create_refresh_token,
    verify_token,
    verify_password,
    require_auth,
)
from runcoach.db import RunCoachDB
from runcoach.config import Config
from runcoach.analyzer import _dispatch_llm, build_chat_context
from runcoach.context import build_training_summary


log = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


def get_db() -> RunCoachDB:
    """Get database instance from Flask app config."""
    config: Config = current_app.config["RUNCOACH_CONFIG"]
    return RunCoachDB(config.db_path)


def format_duration(seconds: int | None) -> str:
    """Format duration in seconds as MM:SS or HH:MM:SS."""
    if seconds is None:
        return "—"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def format_run_for_api(run: dict, include_yaml: bool = False) -> dict:
    """Format a run dict for API response."""
    result = {
        "id": run["id"],
        "name": run["name"],
        "date": run["date"],
        "distance_km": round(run["distance_m"] / 1000, 2) if run["distance_m"] else None,
        "distance_m": run["distance_m"],
        "duration_s": run["moving_time_s"],
        "duration_formatted": format_duration(run["moving_time_s"]),
        "avg_power_w": run["avg_power_w"],
        "avg_hr": run["avg_hr"],
        "stryd_rss": run["stryd_rss"],
        "workout_name": run["workout_name"],
        "stage": run["stage"],
        "is_manual_upload": bool(run["is_manual_upload"]),
        "commentary": run["commentary"],
        "analyzed_at": run["analyzed_at"],
        "model_used": run["model_used"],
        "error_message": run["error_message"],
        "strava_activity_id": run.get("strava_activity_id"),
        "stryd_activity_id": run.get("stryd_activity_id"),
        "strava_map_polyline": run.get("strava_map_polyline"),
    }

    # Include full YAML data if requested
    if include_yaml and run["yaml_path"]:
        try:
            yaml_path = Path(run["yaml_path"])
            # If path is relative, make it relative to data directory
            if not yaml_path.is_absolute():
                config: Config = current_app.config["RUNCOACH_CONFIG"]
                yaml_path = config.data_dir / yaml_path

            if yaml_path.exists():
                with open(yaml_path) as f:
                    result["yaml_data"] = yaml.safe_load(f)
            else:
                log.warning(f"YAML file not found for run {run['id']}: {yaml_path}")
                result["yaml_data"] = None
        except Exception as e:
            log.error(f"Failed to load YAML for run {run['id']}: {e}")
            result["yaml_data"] = None

    return result


# ------ Authentication ------

@api_bp.route("/auth/login", methods=["POST"])
def login():
    """
    Authenticate user and return JWT tokens.

    POST /api/v1/auth/login
    Body: {"username": "athlete", "password": "..."}
    Response: {"access_token": "...", "refresh_token": "...", "user_id": 1}
    """
    data = request.get_json()
    if not data or "username" not in data or "password" not in data:
        return jsonify({"error": "Missing username or password"}), 400

    username = data["username"]
    password = data["password"]

    # Get user from database
    db = get_db()
    user = db.get_user_by_username(username)

    if not user or not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid credentials"}), 401

    # Update last login
    db.update_last_login(user["id"])

    # Create tokens
    secret_key = current_app.config["SECRET_KEY"]
    access_token = create_access_token(user["id"], secret_key)
    refresh_token = create_refresh_token(user["id"], secret_key)

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": user["id"],
        "username": user["username"],
    }), 200


@api_bp.route("/auth/refresh", methods=["POST"])
def refresh():
    """
    Refresh access token using refresh token.

    POST /api/v1/auth/refresh
    Body: {"refresh_token": "..."}
    Response: {"access_token": "..."}
    """
    data = request.get_json()
    if not data or "refresh_token" not in data:
        return jsonify({"error": "Missing refresh token"}), 400

    refresh_token = data["refresh_token"]
    secret_key = current_app.config["SECRET_KEY"]

    # Verify refresh token
    payload = verify_token(refresh_token, secret_key, "refresh")
    if not payload:
        return jsonify({"error": "Invalid or expired refresh token"}), 401

    # Create new access token
    access_token = create_access_token(payload["user_id"], secret_key)

    return jsonify({"access_token": access_token}), 200


@api_bp.route("/auth/logout", methods=["POST"])
@require_auth
def logout():
    """
    Logout (client should discard tokens).

    POST /api/v1/auth/logout
    Headers: Authorization: Bearer <access_token>
    Response: {"message": "Logged out successfully"}
    """
    # Since JWTs are stateless, logout is client-side
    # (client discards tokens)
    return jsonify({"message": "Logged out successfully"}), 200


# ------ Runs ------

@api_bp.route("/runs", methods=["GET"])
@require_auth
def list_runs():
    """
    List runs with pagination.

    GET /api/v1/runs?page=1&per_page=20&year=2026&month=4
    Headers: Authorization: Bearer <access_token>
    Response: {
        "runs": [...],
        "pagination": {
            "page": 1,
            "per_page": 20,
            "total": 156,
            "total_pages": 8
        }
    }
    """
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)

    if page < 1:
        page = 1
    if per_page < 1 or per_page > 100:
        per_page = 20

    db = get_db()
    user_id = request.user_id

    total = db.count_runs_filtered(user_id=user_id, year=year, month=month)
    total_pages = (total + per_page - 1) // per_page
    offset = (page - 1) * per_page
    runs = db.get_runs_paginated_filtered(limit=per_page, offset=offset, user_id=user_id, year=year, month=month)

    return jsonify({
        "runs": [format_run_for_api(run) for run in runs],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        }
    }), 200


@api_bp.route("/runs/<int:run_id>", methods=["GET"])
@require_auth
def get_run(run_id: int):
    """
    Get a single run with full details including YAML data.

    GET /api/v1/runs/:id
    Headers: Authorization: Bearer <access_token>
    Response: {
        "id": 123,
        "name": "Morning Run",
        "date": "2026-03-07T06:30:00Z",
        "yaml_data": {...},  // Full workout blocks
        ...
    }
    """
    db = get_db()
    run = db.get_run(run_id, user_id=request.user_id)

    if not run:
        return jsonify({"error": "Run not found"}), 404

    result = format_run_for_api(run, include_yaml=True)

    # Attach the planned workout for this run's date if one exists
    if run.get("date"):
        planned_list = db.get_planned_workout_for_date(run["date"])
        if planned_list:
            p = planned_list[0]
            result["planned_workout"] = {
                "title": p.get("title"),
                "description": p.get("description"),
                "duration_min": round(p["duration_s"] / 60, 1) if p.get("duration_s") else None,
                "distance_km": round(p["distance_m"] / 1000, 2) if p.get("distance_m") else None,
            }

    return jsonify(result), 200


@api_bp.route("/runs/<int:run_id>/chat", methods=["GET"])
@require_auth
def get_run_chat(run_id: int):
    """
    Get chat history for a run.

    GET /api/v1/runs/:id/chat
    Headers: Authorization: Bearer <access_token>
    Response: {"history": [{"role": "user", "message": "...", "created_at": "..."}]}
    """
    db = get_db()
    run = db.get_run(run_id, user_id=request.user_id)
    if not run:
        return jsonify({"error": "Run not found"}), 404
    history = db.get_chat_history(run_id, user_id=request.user_id)
    return jsonify({
        "history": [
            {"role": h["role"], "message": h["message"], "created_at": h["created_at"]}
            for h in history
        ]
    }), 200


@api_bp.route("/runs/<int:run_id>/chat", methods=["POST"])
@require_auth
def post_run_chat(run_id: int):
    """
    Send a chat message and get an AI coach response.

    POST /api/v1/runs/:id/chat
    Headers: Authorization: Bearer <access_token>
    Body: {"message": "How was my power?"}
    Response: {"role": "assistant", "message": "...", "created_at": "..."}
    """
    db = get_db()
    config = current_app.config["config"]
    run = db.get_run(run_id, user_id=request.user_id)
    if not run:
        return jsonify({"error": "Run not found"}), 404

    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400

    history = db.get_chat_history(run_id, user_id=request.user_id)

    try:
        system_msg, user_msg = build_chat_context(
            run=run,
            user_id=request.user_id,
            history=history,
            new_message=message,
            config=config,
            db=db,
        )
        result = _dispatch_llm(system_msg, user_msg, config)
    except Exception as e:
        log.exception("Chat LLM error for run %s: %s", run_id, e)
        return jsonify({"error": "LLM request failed"}), 502

    now = datetime.now(timezone.utc).isoformat()

    db.add_chat_message(run_id, request.user_id, "user", message)
    db.add_chat_message(
        run_id, request.user_id, "assistant",
        result["commentary"],
        model_used=config.active_model,
        prompt_tokens=result.get("prompt_tokens"),
        completion_tokens=result.get("completion_tokens"),
    )

    return jsonify({
        "role": "assistant",
        "message": result["commentary"],
        "model_used": config.active_model,
        "prompt_tokens": result.get("prompt_tokens"),
        "completion_tokens": result.get("completion_tokens"),
        "created_at": now,
    }), 200


@api_bp.route("/runs/upload", methods=["POST"])
@require_auth
def upload_run():
    """
    Upload a FIT file for manual processing.

    POST /api/v1/runs/upload
    Headers: Authorization: Bearer <access_token>
    Body: multipart/form-data with "file" field
    Response: {"run_id": 123, "message": "File uploaded successfully"}
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.lower().endswith(".fit"):
        return jsonify({"error": "Only .fit files are allowed"}), 400

    config: Config = current_app.config["RUNCOACH_CONFIG"]

    # Save file
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = secure_filename(file.filename)
    basename = filename[:-4] if filename.lower().endswith(".fit") else filename
    folder_name = f"{timestamp}_{basename}"

    activities_dir = config.activities_dir
    year = datetime.now().strftime("%Y")
    month = datetime.now().strftime("%m")
    activity_dir = activities_dir / year / month / folder_name
    activity_dir.mkdir(parents=True, exist_ok=True)

    fit_path = activity_dir / f"{folder_name}.fit"
    file.save(str(fit_path))

    # Insert into database
    db = get_db()
    date_iso = datetime.now().isoformat()
    run_id = db.insert_manual_run(
        name=basename,
        date=date_iso,
        fit_path=str(fit_path),
        user_id=request.user_id,
    )

    log.info(f"Manual upload: saved {fit_path}, run_id={run_id}")

    return jsonify({
        "run_id": run_id,
        "message": "File uploaded successfully. Parsing and analysis will begin shortly."
    }), 201


@api_bp.route("/runs/<int:run_id>/analyze", methods=["POST"])
@require_auth
def analyze_run(run_id: int):
    """
    Trigger analysis for a specific run.

    POST /api/v1/runs/:id/analyze
    Headers: Authorization: Bearer <access_token>
    Response: {"message": "Analysis started"}
    """
    db = get_db()
    run = db.get_run(run_id, user_id=request.user_id)

    if not run:
        return jsonify({"error": "Run not found"}), 404

    if run["stage"] != "parsed":
        return jsonify({"error": f"Run must be in 'parsed' stage (currently '{run['stage']}')"}), 400

    # Trigger analysis asynchronously
    from runcoach.analyzer import analyze_and_write
    import threading

    # Capture Flask app context for background thread
    app = current_app._get_current_object()

    def analyze_task():
        with app.app_context():
            try:
                config: Config = app.config["RUNCOACH_CONFIG"]

                # Re-fetch run data within the app context
                fresh_run = db.get_run(run_id)
                if not fresh_run:
                    log.error(f"Run {run_id} not found during analysis")
                    return

                yaml_path = config.data_dir / fresh_run["yaml_path"]
                md_path, result = analyze_and_write(yaml_path, config, db=db)

                # Update database with results
                md_path_rel = str(md_path.relative_to(config.data_dir))
                db.update_analyzed(
                    run_id=fresh_run["id"],
                    md_path=md_path_rel,
                    commentary=result["commentary"],
                    model_used=config.active_model,
                    prompt_tokens=result.get("prompt_tokens"),
                    completion_tokens=result.get("completion_tokens"),
                )
                log.info(f"Analysis complete for run {run_id}")

            except Exception as e:
                log.exception(f"Analysis failed for run {run_id}")  # Use log.exception for full traceback
                db.update_error(run_id, f"Analysis error: {e}")

    thread = threading.Thread(target=analyze_task, daemon=True)
    thread.start()

    return jsonify({"message": "Analysis started"}), 202


# ------ Sync ------

@api_bp.route("/sync", methods=["POST"])
@require_auth
def trigger_sync():
    """
    Trigger Stryd sync.

    POST /api/v1/sync
    Headers: Authorization: Bearer <access_token>
    Response: {"message": "Sync started"}
    """
    scheduler = current_app.config["scheduler"]

    if scheduler.is_syncing:
        return jsonify({"error": "Sync already in progress"}), 409

    scheduler.trigger_now()
    return jsonify({"message": "Sync started"}), 202


@api_bp.route("/sync/status", methods=["GET"])
@require_auth
def sync_status():
    """
    Get sync status.

    GET /api/v1/sync/status
    Headers: Authorization: Bearer <access_token>
    Response: {
        "last_sync": {
            "started_at": "...",
            "finished_at": "...",
            "status": "success",
            "activities_found": 10,
            "activities_new": 2
        },
        "stats": {
            "total_runs": 156,
            "pending_parse": 0,
            "pending_analyze": 3,
            "errors": 0
        }
    }
    """
    db = get_db()
    last_sync = db.get_last_sync(user_id=request.user_id)
    stats = db.get_sync_stats(user_id=request.user_id)

    return jsonify({
        "last_sync": last_sync,
        "stats": stats,
    }), 200


# ------ Athlete Profile ------

@api_bp.route("/athlete/profile", methods=["GET"])
@require_auth
def get_athlete_profile():
    """
    Get the athlete profile for the authenticated user.

    GET /api/v1/athlete/profile
    Headers: Authorization: Bearer <access_token>
    Response: {"profile": "...", "display_name": "...", "username": "...", "strava_athlete_id": "..."|null}
    """
    db = get_db()
    user_id = request.user_id
    user = db.get_user_by_id(user_id)
    profile = db.get_athlete_profile(user_id)
    return jsonify({
        "profile": profile,
        "display_name": user["display_name"] if user and user["display_name"] else "",
        "username": user["username"] if user else "",
        "strava_athlete_id": user.get("strava_athlete_id") if user else None,
    }), 200


@api_bp.route("/athlete/profile", methods=["PUT"])
@require_auth
def update_athlete_profile():
    """
    Update the athlete profile for the authenticated user.

    PUT /api/v1/athlete/profile
    Headers: Authorization: Bearer <access_token>
    Body: {"profile": "...", "display_name": "...", "username": "..."}
    Response: {"profile": "...", "display_name": "...", "username": "..."}

    All fields are optional — only provided fields are updated.
    """
    data = request.get_json()
    if data is None:
        return jsonify({"error": "Missing request body"}), 400

    import re, unicodedata
    _ctrl = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

    db = get_db()
    user_id = request.user_id

    if "profile" in data:
        profile_text = data["profile"]
        if not isinstance(profile_text, str):
            return jsonify({"error": "'profile' must be a string"}), 400
        profile_text = _ctrl.sub("", unicodedata.normalize("NFC", profile_text))[:5_000]
        db.update_athlete_profile(user_id, profile_text.strip())

    if "display_name" in data or "username" in data:
        user = db.get_user_by_id(user_id)
        new_display_name = data.get("display_name", user["display_name"] or "").strip()
        new_username = data.get("username", user["username"]).strip()
        if not new_username:
            return jsonify({"error": "Username cannot be empty"}), 400
        existing = db.get_user_by_username(new_username)
        if existing and existing["id"] != user_id:
            return jsonify({"error": "That username is already taken"}), 409
        db.update_user_info(user_id, new_display_name, new_username)

    user = db.get_user_by_id(user_id)
    profile = db.get_athlete_profile(user_id)
    return jsonify({
        "profile": profile,
        "display_name": user["display_name"] if user and user["display_name"] else "",
        "username": user["username"] if user else "",
        "strava_athlete_id": user.get("strava_athlete_id") if user else None,
    }), 200


@api_bp.route("/dashboard", methods=["GET"])
@require_auth
def dashboard():
    db = get_db()
    user_id = request.user_id

    # Latest run
    runs = db.get_runs_paginated_filtered(limit=1, offset=0, user_id=user_id)
    latest_run = format_run_for_api(runs[0]) if runs else None

    # Next planned workout
    today = date_type.today().isoformat()
    upcoming = db.get_upcoming_planned_workouts(from_date=today, limit=1, user_id=user_id)
    next_workout = None
    if upcoming:
        w = upcoming[0]
        next_workout = {
            "date": w["date"],
            "name": w["title"],
            "description": w.get("description") or "",
        }

    # Training summary
    try:
        summary_data = build_training_summary(db, user_id=user_id)
    except Exception as e:
        return jsonify({"error": f"Failed to build training summary: {e}"}), 500
    ts = summary_data.get("training_summary", {})
    current_rsb_raw = ts.get("current_rsb", {})
    training_summary = {
        "current_rsb": {
            "rsb": current_rsb_raw.get("rsb"),
            "ctl": current_rsb_raw.get("ctl"),
            "atl": current_rsb_raw.get("atl"),
            "interpretation": current_rsb_raw.get("interpretation", "unknown"),
        },
        "rsb_history": [
            {
                "date": h["date"],
                "rsb": h.get("rsb"),
                "ctl": h.get("ctl"),
                "atl": h.get("atl"),
            }
            for h in ts.get("rsb_history", [])
        ],
    }

    return jsonify({
        "latest_run": latest_run,
        "next_workout": next_workout,
        "training_summary": training_summary,
    }), 200
