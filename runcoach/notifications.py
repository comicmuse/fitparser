from __future__ import annotations

import logging
import warnings

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


def _build_message(target: str, kind: str, notification, data: dict):
    """Build an FCM message addressed by FID or by legacy registration token.

    firebase-admin 7.7 deprecates ``Message(token=...)`` in favour of
    ``fid``. Rows registered by app builds from before the FID migration
    still hold tokens, so keep sending to them (silencing only that
    warning) until those devices re-register with an FID.
    """
    if kind == "fid":
        return Message(notification=notification, data=data, fid=target)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="Message.token is deprecated", category=DeprecationWarning
        )
        return Message(notification=notification, data=data, token=target)


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
        kind = token_row.get("kind") or "token"
        try:
            message = _build_message(
                token,
                kind,
                Notification(
                    title="New Analysis Ready",
                    body=f"Your coach has analysed: {run_name}",
                ),
                {"run_id": str(run_id), "type": "analysis_ready"},
            )
            messaging.send(message)
            sent += 1
            log.info("FCM notification sent for run %s (%s)", run_id, kind)
        except messaging.UnregisteredError:
            log.warning(
                "Stale FCM %s removed for user %s — open the app to re-register",
                kind, user_id,
            )
            db.delete_device_token(token)
        except Exception as e:
            log.warning("FCM send failed: %s", e)

    return sent
