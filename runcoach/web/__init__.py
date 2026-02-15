from __future__ import annotations

import logging

from flask import Flask
from flask_wtf.csrf import CSRFProtect

from runcoach.config import Config
from runcoach.db import RunCoachDB
from runcoach.scheduler import Scheduler

csrf = CSRFProtect()


def create_app(config: Config | None = None) -> Flask:
    if config is None:
        config = Config.from_env()

    config.data_dir.mkdir(parents=True, exist_ok=True)
    db = RunCoachDB(config.db_path)

    app = Flask(__name__)
    app.secret_key = config.secret_key
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB
    app.config["config"] = config
    app.config["db"] = db

    csrf.init_app(app)

    scheduler = Scheduler(config, db)
    app.config["scheduler"] = scheduler

    from runcoach.web.routes import bp
    app.register_blueprint(bp)

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
