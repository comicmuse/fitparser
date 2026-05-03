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


def link_unlinked_runs(db: RunCoachDB, user_id: int, config) -> int:
    """Match unlinked runs to Strava activities by date and store activity IDs + polylines.

    Returns the number of runs newly linked.
    """
    import datetime

    if not config.strava_client_id:
        return 0

    unlinked = db.get_unlinked_runs(user_id=user_id)
    if not unlinked:
        return 0

    client = StravaClient(config.strava_client_id, config.strava_client_secret)
    access_token = client.get_valid_access_token(db, user_id)
    if not access_token:
        log.warning("Strava: no valid access token for user %d, skipping link step", user_id)
        return 0

    runs_by_date: dict[str, list[dict]] = {}
    for run in unlinked:
        date = (run.get("date") or "")[:10]
        if date:
            runs_by_date.setdefault(date, []).append(run)

    oldest_date = min(runs_by_date.keys())
    after_ts = int(
        datetime.datetime(
            *[int(p) for p in oldest_date.split("-")],
            tzinfo=datetime.timezone.utc,
        ).timestamp()
    ) - 86400

    RUNNING_TYPES = {"Run", "TrailRun", "VirtualRun", "Treadmill"}
    linked = 0
    page = 1
    while True:
        try:
            activities = client.list_activities(access_token, after=after_ts, per_page=100, page=page)
        except Exception as exc:
            log.error("Strava link: error fetching page %d: %s", page, exc)
            break
        if not activities:
            break
        for activity in activities:
            sport = activity.get("sport_type") or activity.get("type", "")
            if sport not in RUNNING_TYPES:
                continue
            act_date = (activity.get("start_date_local") or "")[:10]
            if act_date not in runs_by_date:
                continue
            strava_id = str(activity["id"])
            if db.get_run_by_strava_id(strava_id):
                continue
            polyline = (activity.get("map") or {}).get("summary_polyline") or None
            candidates = [r for r in runs_by_date[act_date] if not r.get("strava_activity_id")]
            if not candidates:
                continue
            run = candidates[-1]
            db.update_run_strava_data(
                run_id=run["id"],
                strava_activity_id=strava_id,
                strava_map_polyline=polyline,
            )
            run["strava_activity_id"] = strava_id
            linked += 1
            log.info("Strava: linked activity %s to run %s (%s)", strava_id, run["id"], act_date)
        if len(activities) < 100:
            break
        page += 1

    return linked


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


def polyline_to_svg_path(coords: list[list[float]], size: int = 52) -> str:
    """
    Convert [lat, lng] pairs to an SVG <polyline> string scaled to fit within size×size
    with 4px padding. Returns empty string if fewer than 2 points.
    """
    if len(coords) < 2:
        return ""
    pad = 4
    inner = size - 2 * pad
    lats = [c[0] for c in coords]
    lngs = [c[1] for c in coords]
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)
    lat_span = max_lat - min_lat or 1e-9
    lng_span = max_lng - min_lng or 1e-9
    scale = inner / max(lat_span, lng_span)
    points = []
    for lat, lng in coords:
        x = pad + (lng - min_lng) * scale
        y = pad + (max_lat - lat) * scale  # invert y so north is up
        points.append(f"{x:.1f},{y:.1f}")
    pts_str = " ".join(points)
    return (
        f'<polyline points="{pts_str}" fill="none" stroke="#fc4c02" '
        f'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
    )
