"""Strava OAuth 2.0 client, API helpers, and utility functions."""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import requests

if TYPE_CHECKING:
    from runcoach.db import RunCoachDB

log = logging.getLogger(__name__)

STRAVA_AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_DEAUTH_URL = "https://www.strava.com/oauth/deauthorize"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

# Scopes needed: read athlete profile + all activities (including private)
STRAVA_SCOPES = "read,activity:read_all"


class StravaClient:
    """Lightweight Strava OAuth 2.0 client."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    def get_authorize_url(self, redirect_uri: str, state: str = "") -> str:
        """Return the URL the user should be redirected to for OAuth consent."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "approval_prompt": "auto",
            "scope": STRAVA_SCOPES,
            "state": state,
        }
        return f"{STRAVA_AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(self, code: str) -> dict:
        """Exchange an authorization code for tokens. Returns the full Strava response."""
        resp = requests.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def refresh_tokens(self, refresh_token: str) -> dict:
        """Refresh an expired access token. Returns new token data."""
        resp = requests.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def deauthorize(self, access_token: str) -> None:
        """Revoke access on Strava's side (best-effort)."""
        try:
            requests.post(
                STRAVA_DEAUTH_URL,
                data={"access_token": access_token},
                timeout=10,
            )
        except Exception as exc:
            log.warning("Strava deauthorize call failed: %s", exc)

    def register_webhook(self, callback_url: str, verify_token: str) -> dict | None:
        """
        Register (or confirm) a Strava webhook subscription.

        Returns:
            dict with ``{"id": <subscription_id>}`` on success,
            dict with ``{"already_registered": True}`` if a subscription
            already exists (HTTP 409), or None on failure.

        The callback_url must be publicly reachable by Strava's servers.
        Strava will make a GET request to it immediately as part of
        the registration handshake.
        """
        try:
            resp = requests.post(
                "https://www.strava.com/api/v3/push_subscriptions",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "callback_url": callback_url,
                    "verify_token": verify_token,
                },
                timeout=15,
            )
            if resp.status_code == 409:
                log.info("Strava webhook already registered (409 Conflict)")
                return {"already_registered": True}
            resp.raise_for_status()
            data = resp.json()
            log.info("Strava webhook registered with subscription ID %s", data.get("id"))
            return data
        except Exception as exc:
            log.warning("Strava webhook registration failed: %s", exc)
            return None

    def get_webhook_subscription(self) -> dict | None:
        """Look up the current webhook subscription for this app (if any)."""
        try:
            resp = requests.get(
                "https://www.strava.com/api/v3/push_subscriptions",
                params={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=10,
            )
            resp.raise_for_status()
            subs = resp.json()
            return subs[0] if subs else None
        except Exception as exc:
            log.warning("Could not fetch Strava webhook subscription: %s", exc)
            return None

    def get_activity(self, activity_id: int | str, access_token: str) -> dict:
        """Fetch a single detailed activity by Strava activity ID."""
        resp = requests.get(
            f"{STRAVA_API_BASE}/activities/{int(activity_id)}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def list_activities(
        self,
        access_token: str,
        after: int | None = None,
        before: int | None = None,
        per_page: int = 100,
        page: int = 1,
    ) -> list[dict]:
        """Fetch a page of activities from the athlete's activity list.

        Parameters map directly to Strava's ``GET /athlete/activities`` API.
        ``after`` and ``before`` are Unix epoch timestamps (inclusive).
        Returns an empty list when no more activities exist.
        """
        params: dict = {"per_page": per_page, "page": page}
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before
        resp = requests.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_valid_access_token(self, db: RunCoachDB, user_id: int) -> str | None:
        """
        Return a valid access token for the user, automatically refreshing
        if it has expired or is expiring within 5 minutes.
        Returns None if the user has no Strava tokens.
        """
        tokens = db.get_strava_tokens(user_id)
        if not tokens or not tokens.get("strava_access_token"):
            return None

        expires_at = tokens.get("strava_token_expires_at") or 0
        if time.time() >= expires_at - 300:
            # Token expired or expiring soon — refresh
            try:
                new_tokens = self.refresh_tokens(tokens["strava_refresh_token"])
                db.save_strava_tokens(
                    user_id=user_id,
                    access_token=new_tokens["access_token"],
                    refresh_token=new_tokens["refresh_token"],
                    expires_at=new_tokens["expires_at"],
                )
                return new_tokens["access_token"]
            except Exception as exc:
                log.error("Strava token refresh failed for user %s: %s", user_id, exc)
                return None

        return tokens["strava_access_token"]


def decode_polyline(encoded: str) -> list[list[float]]:
    """
    Decode a Google-encoded polyline string into a list of [lat, lng] pairs.
    Returns an empty list for empty/None input.
    """
    if not encoded:
        return []
    coords: list[list[float]] = []
    index = 0
    lat = 0
    lng = 0
    n = len(encoded)
    while index < n:
        # Decode latitude delta
        result, shift = 0, 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lat += -(result >> 1) if (result & 1) else (result >> 1)
        # Decode longitude delta
        result, shift = 0, 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lng += -(result >> 1) if (result & 1) else (result >> 1)
        coords.append([lat * 1e-5, lng * 1e-5])
    return coords
