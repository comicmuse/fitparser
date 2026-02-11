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
    db = _db()
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

    return render_template("run_detail.html", run=run, commentary_html=commentary_html)


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
