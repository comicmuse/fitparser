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
    """Ensure default user exists for API authentication."""
    username = "athlete"
    password = os.environ.get("RUNCOACH_PASSWORD", "runcoach123")

    # Hash password and create/update user
    password_hash = hash_password(password)
    user_id = db.ensure_default_user(username, password_hash)

    if user_id:
        logging.getLogger(__name__).info(
            f"Default user '{username}' ready (ID: {user_id})"
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = Config.from_env()
    app = create_app(config)
    app.run(host="0.0.0.0", port=config.flask_port, debug=config.flask_debug)


if __name__ == "__main__":
    main()
