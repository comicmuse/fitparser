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
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-6"
    ollama_base_url: str = ""
    ollama_model: str = "llama3.2"
    ollama_num_ctx: int = 16384
    data_dir: Path = field(default_factory=lambda: Path("data"))
    sync_interval_hours: int = 0
    sync_lookback_days: int = 30
    timezone: str = "Europe/London"
    flask_port: int = 5000
    flask_debug: bool = False
    llm_auto_analyse: bool = True  # if False, skip auto-analysis in pipeline; on-demand still works
    analyze_from: str | None = None  # YYYY-MM-DD; only auto-analyze runs on or after this date
    secret_key: str = ""
    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_webhook_verify_token: str = ""
    strava_webhook_enabled: bool = True

    @property
    def llm_provider(self) -> str:
        """
        Determine which LLM provider to use based on configured credentials.

        Returns "openai", "claude", or "ollama". If more than one provider is
        configured, defaults to OpenAI and emits a prominent warning.
        """
        import logging
        logger = logging.getLogger(__name__)

        configured = []
        if self.openai_api_key:
            configured.append("openai")
        if self.anthropic_api_key:
            configured.append("claude")
        if self.ollama_base_url:
            configured.append("ollama")

        if len(configured) > 1:
            border = "!" * 60
            logger.warning(border)
            logger.warning(
                "MULTIPLE LLM PROVIDERS CONFIGURED: %s", ", ".join(configured)
            )
            logger.warning(
                "Defaulting to OpenAI. Set only one provider's credentials "
                "in .env to suppress this warning."
            )
            logger.warning(border)
            return "openai"

        return configured[0] if configured else "openai"

    @property
    def has_llm(self) -> bool:
        """Return True if any LLM provider is configured."""
        return bool(self.openai_api_key or self.anthropic_api_key or self.ollama_base_url)

    @property
    def active_model(self) -> str:
        """Return the model name for the active LLM provider."""
        provider = self.llm_provider
        if provider == "claude":
            return self.anthropic_model
        if provider == "ollama":
            return self.ollama_model
        return self.openai_model

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

        import secrets
        secret_key = os.environ.get("SECRET_KEY", "")
        if not secret_key:
            import logging
            logging.getLogger(__name__).warning(
                "SECRET_KEY not set — generating a random key. "
                "Sessions will not survive restarts. "
                "Set SECRET_KEY in your .env for persistence."
            )
            secret_key = secrets.token_hex(32)

        return cls(
            stryd_email=os.environ.get("STRYD_EMAIL", ""),
            stryd_password=os.environ.get("STRYD_PASSWORD", ""),
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-6"),
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL", ""),
            ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.2"),
            ollama_num_ctx=int(os.environ.get("OLLAMA_NUM_CTX", "16384")),
            data_dir=Path(os.environ.get("DATA_DIR", "data")),
            sync_interval_hours=int(os.environ.get("SYNC_INTERVAL_HOURS", "0")),
            sync_lookback_days=int(os.environ.get("SYNC_LOOKBACK_DAYS", "30")),
            timezone=os.environ.get("TIMEZONE", "Europe/London"),
            flask_port=int(os.environ.get("FLASK_PORT", "5000")),
            flask_debug=os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "yes"),
            llm_auto_analyse=os.environ.get("LLM_AUTO_ANALYSE", "true").lower() in ("true", "1", "yes"),
            analyze_from=os.environ.get("ANALYZE_FROM") or None,
            secret_key=secret_key,
            strava_client_id=os.environ.get("STRAVA_CLIENT_ID", ""),
            strava_client_secret=os.environ.get("STRAVA_CLIENT_SECRET", ""),
            strava_webhook_verify_token=os.environ.get("STRAVA_WEBHOOK_VERIFY_TOKEN", ""),
            strava_webhook_enabled=os.environ.get("STRAVA_WEBHOOK_ENABLED", "true").lower() in ("true", "1", "yes"),
        )
