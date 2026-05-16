from __future__ import annotations

import logging

log = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    from firebase_admin.messaging import Message, Notification
    _FIREBASE_AVAILABLE = True
except ImportError:
    _FIREBASE_AVAILABLE = False


def _init_firebase_app(service_account_path: str) -> None:
    """Initialise the Firebase Admin app (idempotent)."""
    try:
        firebase_admin.get_app()
    except ValueError:
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred)


def send_analysis_notification(
    run_id: int,
    run_name: str,
    user_id: int,
    db,
    config,
) -> int:
    """
    Send an FCM push notification to all registered devices for the user.

    Returns the number of messages successfully sent. Never raises — a
    notification failure must not affect the caller's control flow.
    """
    if not config.fcm_service_account_path:
        return 0

    if not _FIREBASE_AVAILABLE:
        log.warning(
            "firebase-admin is not installed. "
            "Install it with: pip install -e '.[fcm]'"
        )
        return 0

    tokens = db.get_device_tokens_for_user(user_id)
    if not tokens:
        return 0

    try:
        _init_firebase_app(config.fcm_service_account_path)
    except Exception as e:
        log.error("Failed to initialise Firebase app: %s", e)
        return 0

    sent = 0
    for token_row in tokens:
        token = token_row["token"]
        try:
            message = Message(
                notification=Notification(
                    title="New Analysis Ready",
                    body=f"Your coach has analysed: {run_name}",
                ),
                data={"run_id": str(run_id), "type": "analysis_ready"},
                token=token,
            )
            messaging.send(message)
            sent += 1
            log.info("FCM notification sent for run %s", run_id)
        except messaging.UnregisteredError:
            log.warning("Stale FCM token removed for user %s — open the app to re-register", user_id)
            db.delete_device_token(token)
        except Exception as e:
            log.warning("FCM send failed: %s", e)

    return sent
