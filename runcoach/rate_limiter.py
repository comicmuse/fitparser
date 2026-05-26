"""Per-user daily LLM call quota enforcement."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)


def check_and_consume(db, user_id: int) -> tuple[bool, str | None]:
    """Check whether a user may make an LLM call and, if so, record it.

    Returns (True, None) when the call is allowed (counter has been incremented).
    Returns (False, reset_message) when the daily cap is reached.
    Short-circuits without any DB write when limiting is disabled or the user is an admin.
    """
    if db.get_site_setting("llm_limiting_enabled", default="0") != "1":
        return True, None

    user = db.get_user_by_id(user_id)
    if not user:
        return True, None
    if user.get("is_admin"):
        return True, None

    limit_override = user.get("llm_daily_limit")
    if limit_override is not None:
        limit = int(limit_override)
    else:
        limit = int(db.get_site_setting("llm_daily_limit_default", default="10") or "10")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    incremented, _ = db.check_and_increment_llm_usage(user_id, today, limit)
    if incremented:
        return True, None

    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    delta = tomorrow - now
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes = remainder // 60
    return (
        False,
        f"Daily analysis limit reached. Resets at 00:00 UTC (in {hours}h {minutes}m).",
    )
