"""Web Push notification helper for RunCoach."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runcoach.config import Config
    from runcoach.db import RunCoachDB

log = logging.getLogger(__name__)


def send_analysis_notification(
    config: "Config",
    db: "RunCoachDB",
    run_id: int,
    run_name: str,
) -> int:
    """
    Send a push notification to all subscribers that a run analysis is ready.

    Returns the number of notifications sent successfully.
    """
    if not config.vapid_private_key or not config.vapid_public_key:
        log.debug("VAPID keys not configured, skipping push notification")
        return 0

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        log.warning("pywebpush not installed, skipping push notifications")
        return 0

    subscriptions = db.get_all_push_subscriptions()
    if not subscriptions:
        log.debug("No push subscriptions registered")
        return 0

    payload = json.dumps({
        "title": "Analysis Ready",
        "body": f"Your run \"{run_name}\" has been analyzed",
        "url": f"/run/{run_id}",
        "tag": f"analysis-{run_id}",
    })

    vapid_claims = {"sub": f"mailto:{config.vapid_email}"}
    sent = 0
    stale_endpoints = []

    for sub in subscriptions:
        subscription_info = {
            "endpoint": sub["endpoint"],
            "keys": {
                "p256dh": sub["p256dh"],
                "auth": sub["auth"],
            },
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=config.vapid_private_key,
                vapid_claims=vapid_claims,
            )
            sent += 1
        except WebPushException as e:
            status_code = getattr(e, "response", None)
            if status_code is not None:
                status_code = getattr(status_code, "status_code", None)

            if status_code in (404, 410):
                # Subscription expired or invalid — remove it
                log.info("Removing stale push subscription: %s", sub["endpoint"][:60])
                stale_endpoints.append(sub["endpoint"])
            else:
                log.warning("Push failed for %s: %s", sub["endpoint"][:60], e)
        except Exception as e:
            log.warning("Push failed for %s: %s", sub["endpoint"][:60], e)

    # Clean up stale subscriptions
    for endpoint in stale_endpoints:
        try:
            db.delete_push_subscription(endpoint)
        except Exception:
            pass

    log.info("Sent %d push notifications for run %d (%s)", sent, run_id, run_name)
    return sent
