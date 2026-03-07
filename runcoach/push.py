"""Web Push and UnifiedPush notification helpers for RunCoach."""

from __future__ import annotations

import json
import logging
import requests
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runcoach.config import Config
    from runcoach.db import RunCoachDB

log = logging.getLogger(__name__)


class UnifiedPushNotifier:
    """
    UnifiedPush notification sender using ntfy.sh or compatible server.
    """

    def __init__(self, server_url: str = "https://ntfy.sh"):
        self.server_url = server_url.rstrip("/")

    def send_notification(
        self,
        topic: str,
        title: str,
        message: str,
        click_url: str | None = None,
        data: dict | None = None,
        priority: str = "default",
    ) -> bool:
        """
        Send a UnifiedPush notification via ntfy.sh.

        Args:
            topic: The UnifiedPush topic (from endpoint like https://ntfy.sh/up-12345)
            title: Notification title
            message: Notification message body
            click_url: Deep link URL to open on tap (e.g., "runcoach://run/123")
            data: Additional JSON data to include
            priority: Notification priority ("min", "low", "default", "high", "urgent")

        Returns:
            True if sent successfully, False otherwise
        """
        url = f"{self.server_url}/{topic}"

        headers = {
            "Title": title,
            "Priority": priority,
            "Tags": "runner",  # Emoji tag for notifications
        }

        if click_url:
            headers["Click"] = click_url

        # Include data as JSON in message body if provided
        body = message
        if data:
            # ntfy.sh doesn't have a separate data field, so we encode it
            # The mobile app will parse this
            body = json.dumps({
                "message": message,
                "data": data,
            })
            headers["Content-Type"] = "application/json"

        try:
            response = requests.post(url, data=body, headers=headers, timeout=10)
            response.raise_for_status()
            log.info(f"Sent UnifiedPush notification to {topic}: {title}")
            return True
        except requests.RequestException as e:
            log.error(f"Failed to send UnifiedPush notification to {topic}: {e}")
            return False


def send_analysis_notification(
    config: "Config",
    db: "RunCoachDB",
    run_id: int,
    run_name: str,
) -> int:
    """
    Send a push notification to all subscribers that a run analysis is ready.
    Supports both Web Push (VAPID) and UnifiedPush.

    Returns the number of notifications sent successfully.
    """
    total_sent = 0

    # Send Web Push notifications
    if config.vapid_private_key and config.vapid_public_key:
        total_sent += _send_web_push_notifications(config, db, run_id, run_name)

    # Send UnifiedPush notifications
    total_sent += _send_unifiedpush_notifications(db, run_id, run_name)

    return total_sent


def _send_web_push_notifications(
    config: "Config",
    db: "RunCoachDB",
    run_id: int,
    run_name: str,
) -> int:
    """Send Web Push (VAPID) notifications."""
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        log.warning("pywebpush not installed, skipping Web Push notifications")
        return 0

    subscriptions = db.get_all_push_subscriptions()
    if not subscriptions:
        log.debug("No Web Push subscriptions registered")
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
                log.info("Removing stale Web Push subscription: %s", sub["endpoint"][:60])
                stale_endpoints.append(sub["endpoint"])
            else:
                log.warning("Web Push failed for %s: %s", sub["endpoint"][:60], e)
        except Exception as e:
            log.warning("Web Push failed for %s: %s", sub["endpoint"][:60], e)

    # Clean up stale subscriptions
    for endpoint in stale_endpoints:
        try:
            db.delete_push_subscription(endpoint)
        except Exception:
            pass

    if sent > 0:
        log.info("Sent %d Web Push notifications for run %d (%s)", sent, run_id, run_name)

    return sent


def _send_unifiedpush_notifications(
    db: "RunCoachDB",
    run_id: int,
    run_name: str,
) -> int:
    """Send UnifiedPush notifications."""
    subscriptions = db.get_all_unifiedpush_subscriptions()
    if not subscriptions:
        log.debug("No UnifiedPush subscriptions registered")
        return 0

    notifier = UnifiedPushNotifier()
    sent = 0

    for sub in subscriptions:
        success = notifier.send_notification(
            topic=sub["topic"],
            title="Analysis Ready",
            message=f"Your run \"{run_name}\" has been analyzed",
            click_url=f"runcoach://run/{run_id}",
            data={
                "type": "analysis_complete",
                "run_id": run_id,
                "run_name": run_name,
            },
        )
        if success:
            sent += 1

    if sent > 0:
        log.info("Sent %d UnifiedPush notifications for run %d (%s)", sent, run_id, run_name)

    return sent
