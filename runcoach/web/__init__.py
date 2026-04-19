from __future__ import annotations

import logging
import os

from flask import Flask
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from runcoach.config import Config
from runcoach.db import RunCoachDB
from runcoach.scheduler import Scheduler
from runcoach.auth import hash_password

csrf = CSRFProtect()


def _ensure_default_user(db: RunCoachDB, config: Config) -> None:
    """Ensure default user exists and seed Stryd credentials from env on first run."""
    username = os.environ.get("RUNCOACH_USERNAME", "athlete")
    password = os.environ.get("RUNCOACH_PASSWORD", "runcoach123")
    password_hash = hash_password(password)
    user_id = db.ensure_default_user(username, password_hash)

    # Seed Stryd credentials from env vars if not already stored
    stryd_email = os.environ.get("STRYD_EMAIL", "")
    stryd_password = os.environ.get("STRYD_PASSWORD", "")
    if stryd_email:
        existing = db.get_stryd_credentials(user_id)
        if not existing.get("stryd_email"):
            db.update_stryd_credentials(user_id, stryd_email, stryd_password)
            logging.getLogger(__name__).info(
                "Seeded Stryd credentials for user '%s' from environment", username
            )

    logging.getLogger(__name__).info(
        "Default user '%s' ready (ID: %d)", username, user_id
    )


def create_app(config: Config | None = None) -> Flask:
    if config is None:
        config = Config.from_env()

    config.data_dir.mkdir(parents=True, exist_ok=True)
    db = RunCoachDB(config.db_path)

    # Ensure default user exists for API auth
    _ensure_default_user(db, config)

    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    app.secret_key = config.secret_key
    app.config["SECRET_KEY"] = config.secret_key  # For JWT
    app.config["RUNCOACH_CONFIG"] = config  # For API blueprint
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB
    app.config["config"] = config
    app.config["db"] = db

    # CSRF protection for HTML forms only (not API)
    csrf.init_app(app)

    scheduler = Scheduler(config, db)
    app.config["scheduler"] = scheduler

    # Register blueprints
    from runcoach.web.routes import bp
    app.register_blueprint(bp)

    from runcoach.web.api import api_bp
    csrf.exempt(api_bp)  # Exempt API from CSRF (uses JWT instead)
    app.register_blueprint(api_bp)

    scheduler.start()

    return app


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="RunCoach web server")
    parser.add_argument("--port", type=int, default=None, help="Port to listen on (overrides FLASK_PORT, default: 5000)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = Config.from_env()
    if args.port is not None:
        config.flask_port = args.port
    app = create_app(config)
    app.run(host="0.0.0.0", port=config.flask_port, debug=config.flask_debug)


if __name__ == "__main__":
    main()
