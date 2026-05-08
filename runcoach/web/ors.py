"""Shared OpenRouteService helper used by both session-auth and JWT-auth endpoints."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

log = logging.getLogger(__name__)


def fetch_routes(lat: float, lng: float, distance_m: int, ors_api_key: str) -> list[dict]:
    """Fetch 5 round-trip route variations from ORS in parallel. Returns empty list on total failure."""

    def _fetch_one(seed: int) -> dict | None:
        payload = {
            "coordinates": [[lng, lat]],
            "options": {
                "round_trip": {
                    "length": distance_m,
                    "seed": seed,
                },
                "avoid_features": ["fords", "ferries"],
                "profile_params": {"weightings": {"green": 1, "quiet": 1}},
            },
        }
        try:
            r = requests.post(
                "https://api.openrouteservice.org/v2/directions/foot-walking/geojson",
                params={"api_key": ors_api_key},
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, application/geo+json",
                },
                timeout=10,
            )
        except requests.exceptions.RequestException as exc:
            log.warning("ORS request (seed=%d) failed: %s", seed, exc)
            return None
        if r.status_code != 200:
            log.warning("ORS (seed=%d) returned %s: %s", seed, r.status_code, r.text)
            return None
        features = r.json().get("features", [])
        if not features:
            return None
        feature = features[0]
        raw_coords = feature["geometry"]["coordinates"]
        # ORS returns [lng, lat]; callers expect [lat, lng]
        coords = [[pt[1], pt[0]] for pt in raw_coords]
        distance = int(feature["properties"]["summary"]["distance"])
        return {"coords": coords, "distance_m": distance}

    routes: list[dict] = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_fetch_one, seed): seed for seed in range(5)}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                routes.append(result)
    return routes
