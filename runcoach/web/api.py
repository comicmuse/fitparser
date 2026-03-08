"""REST API endpoints for RunCoach mobile app."""

from __future__ import annotations

import logging
import os
import yaml
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

    GET /api/v1/runs?page=1&per_page=20
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

    # Validate pagination parameters
    if page < 1:
        page = 1
    if per_page < 1 or per_page > 100:
        per_page = 20

    db = get_db()

    # Get total count
    total = db.count_runs()
    total_pages = (total + per_page - 1) // per_page

    # Get paginated runs
    offset = (page - 1) * per_page
    runs = db.get_runs_paginated(limit=per_page, offset=offset)

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
    run = db.get_run(run_id)

    if not run:
        return jsonify({"error": "Run not found"}), 404

    return jsonify(format_run_for_api(run, include_yaml=True)), 200


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
    run = db.get_run(run_id)

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
                    model_used=config.openai_model,
                    prompt_tokens=result.get("prompt_tokens"),
                    completion_tokens=result.get("completion_tokens"),
                )
                log.info(f"Analysis complete for run {run_id}")

                # Send push notification
                try:
                    from runcoach.push import send_analysis_notification
                    run_name = fresh_run.get("workout_name") or fresh_run.get("name") or f"Run #{run_id}"
                    send_analysis_notification(config, db, fresh_run["id"], run_name)
                except Exception as e:
                    log.warning(f"Push notification failed: {e}")

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
    last_sync = db.get_last_sync()
    stats = db.get_sync_stats()

    return jsonify({
        "last_sync": last_sync,
        "stats": stats,
    }), 200


# ------ Push Notifications ------

@api_bp.route("/push/register", methods=["POST"])
@require_auth
def register_push():
    """
    Register push notification subscription (Expo or UnifiedPush).

    POST /api/v1/push/register
    Headers: Authorization: Bearer <access_token>
    Body:
      - Expo: {"token": "ExponentPushToken[xxx]", "platform": "android"}
      - UnifiedPush: {"endpoint": "https://ntfy.sh/up-12345", "topic": "up-12345"}
    Response: {"message": "Push subscription registered"}
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing request body"}), 400

    user_id = request.user_id
    db = get_db()

    # Handle Expo push token
    if "token" in data:
        token = data["token"]
        platform = data.get("platform", "unknown")
        db.save_expo_push_token(user_id, token, platform)
        log.info(f"Registered Expo push token for user {user_id} on {platform}")
        return jsonify({"message": "Push subscription registered"}), 201

    # Handle UnifiedPush subscription
    if "endpoint" in data and "topic" in data:
        endpoint = data["endpoint"]
        topic = data["topic"]
        db.save_unifiedpush_subscription(user_id, endpoint, topic)
        log.info(f"Registered UnifiedPush subscription for user {user_id}: {topic}")
        return jsonify({"message": "Push subscription registered"}), 201

    return jsonify({"error": "Missing token (Expo) or endpoint/topic (UnifiedPush)"}), 400


@api_bp.route("/push/unregister", methods=["POST"])
@require_auth
def unregister_push():
    """
    Unregister UnifiedPush subscription.

    POST /api/v1/push/unregister
    Body: {"endpoint": "https://ntfy.sh/up-12345"}
    Response: {"message": "Push subscription removed"}
    """
    data = request.get_json()
    if not data or "endpoint" not in data:
        return jsonify({"error": "Missing endpoint"}), 400

    endpoint = data["endpoint"]

    db = get_db()
    db.delete_unifiedpush_subscription(endpoint)

    log.info(f"Unregistered UnifiedPush subscription: {endpoint}")

    return jsonify({"message": "Push subscription removed"}), 200


@api_bp.route("/push/test", methods=["POST"])
@require_auth
def test_push():
    """
    Send a test push notification.

    POST /api/v1/push/test
    Headers: Authorization: Bearer <access_token>
    Response: {"message": "Test notification sent"}
    """
    user_id = request.user_id

    db = get_db()
    subscriptions = db.get_unifiedpush_subscriptions_for_user(user_id)

    if not subscriptions:
        return jsonify({"error": "No push subscriptions found"}), 404

    # Send test notification
    from runcoach.push import UnifiedPushNotifier

    notifier = UnifiedPushNotifier()

    for sub in subscriptions:
        try:
            notifier.send_notification(
                topic=sub["topic"],
                title="Test Notification",
                message="RunCoach push notifications are working!",
                click_url="runcoach://home",
            )
        except Exception as e:
            log.error(f"Failed to send test notification: {e}")

    return jsonify({"message": "Test notification sent"}), 200
