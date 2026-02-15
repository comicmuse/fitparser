from __future__ import annotations

import logging
import threading

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
import markdown as md

from runcoach.analyzer import analyze_and_write
from runcoach.config import Config

log = logging.getLogger(__name__)

bp = Blueprint("main", __name__)


def _db():
    return current_app.config["db"]


def _scheduler():
    return current_app.config["scheduler"]


@bp.route("/")
def index():
    db = _db()
    runs = db.get_all_runs()
    stats = db.get_sync_stats()
    last_sync = db.get_last_sync()
    return render_template(
        "index.html",
        runs=runs,
        stats=stats,
        last_sync=last_sync,
        syncing=_scheduler().is_syncing,
    )


@bp.route("/run/<int:run_id>")
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
        commentary_html = md.markdown(
            run["commentary"],
            extensions=["tables", "fenced_code"],
        )

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

    return render_template(
        "run_detail.html",
        run=run,
        commentary_html=commentary_html,
        workout_data=workout_data,
    )


@bp.route("/sync", methods=["POST"])
def sync():
    _scheduler().trigger_now()
    flash("Sync started in background")
    return redirect(url_for("main.index"))


@bp.route("/run/<int:run_id>/analyze", methods=["POST"])
def analyze_run_route(run_id: int):
    db = _db()
    config: Config = current_app.config["config"]
    run = db.get_run(run_id)

    if run is None:
        flash("Run not found")
        return redirect(url_for("main.index"))

    if not config.openai_api_key:
        flash("No OPENAI_API_KEY configured")
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
                    model_used=config.openai_model,
                    prompt_tokens=result.get("prompt_tokens"),
                    completion_tokens=result.get("completion_tokens"),
                )
                log.info("Analysis complete for run %s", run_id)
                # Send push notification
                try:
                    from runcoach.push import send_analysis_notification
                    send_analysis_notification(
                        config, db, run["id"],
                        run.get("workout_name") or run.get("name") or f"Run #{run_id}",
                    )
                except Exception as e:
                    log.warning("Push notification failed: %s", e)
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


@bp.route("/push/vapid-key")
def vapid_key():
    """Return the public VAPID key for push subscription."""
    config: Config = current_app.config["config"]
    return jsonify(vapid_public_key=config.vapid_public_key or None)


@bp.route("/push/subscribe", methods=["POST"])
def push_subscribe():
    """Store a push subscription from the client."""
    db = _db()
    data = request.get_json(silent=True)
    if not data or not data.get("endpoint") or not data.get("keys"):
        return jsonify(error="Invalid subscription data"), 400

    db.save_push_subscription(
        endpoint=data["endpoint"],
        p256dh=data["keys"]["p256dh"],
        auth=data["keys"]["auth"],
    )
    return jsonify(ok=True)


@bp.route("/upload", methods=["POST"])
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
        yaml_path = parse_and_write(fit_path, timezone=config.timezone, manual_upload=True)
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
