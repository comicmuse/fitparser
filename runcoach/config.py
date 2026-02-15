from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    stryd_email: str = ""
    stryd_password: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    data_dir: Path = field(default_factory=lambda: Path("data"))
    sync_interval_hours: int = 6
    sync_lookback_days: int = 30
    timezone: str = "Europe/London"
    flask_port: int = 5000
    flask_debug: bool = False
    openai_auto_analyse: bool = True  # if False, skip auto-analysis in pipeline; on-demand still works
    analyze_from: str | None = None  # YYYY-MM-DD; only auto-analyze runs on or after this date
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_email: str = ""

    @property
    def db_path(self) -> Path:
        return self.data_dir / "runcoach.db"

    @property
    def activities_dir(self) -> Path:
        return self.data_dir / "activities"

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> Config:
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()  # loads .env from cwd

        return cls(
            stryd_email=os.environ.get("STRYD_EMAIL", ""),
            stryd_password=os.environ.get("STRYD_PASSWORD", ""),
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
            data_dir=Path(os.environ.get("DATA_DIR", "data")),
            sync_interval_hours=int(os.environ.get("SYNC_INTERVAL_HOURS", "6")),
            sync_lookback_days=int(os.environ.get("SYNC_LOOKBACK_DAYS", "30")),
            timezone=os.environ.get("TIMEZONE", "Europe/London"),
            flask_port=int(os.environ.get("FLASK_PORT", "5000")),
            flask_debug=os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "yes"),
            openai_auto_analyse=os.environ.get("OPENAI_AUTO_ANALYSE", "true").lower() in ("true", "1", "yes"),
            analyze_from=os.environ.get("ANALYZE_FROM") or None,
            vapid_private_key=os.environ.get("VAPID_PRIVATE_KEY", ""),
            vapid_public_key=os.environ.get("VAPID_PUBLIC_KEY", ""),
            vapid_email=os.environ.get("VAPID_EMAIL", ""),
        )
