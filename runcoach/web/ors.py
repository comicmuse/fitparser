"""Shared OpenRouteService helper used by both session-auth and JWT-auth endpoints."""

from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

log = logging.getLogger(__name__)


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return the great-circle distance in metres between two WGS84 lat/lng points."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def filter_routes_by_proximity(
    routes: list[dict],
    user_lat: float,
    user_lng: float,
    target_distance_m: float,
    max_start_m: float = 500,
    max_dist_offset_m: float = 1000,
) -> list[dict]:
    """Return routes whose start point is within max_start_m of (user_lat, user_lng)
    and whose distance is within max_dist_offset_m of target_distance_m."""
    result = []
    for route in routes:
        coords = route.get("coords") or []
        if not coords:
            continue
        start_lat, start_lng = coords[0][0], coords[0][1]
        if haversine_m(user_lat, user_lng, start_lat, start_lng) > max_start_m:
            continue
        route_dist = route.get("distance_m") or 0
        if abs(route_dist - target_distance_m) > max_dist_offset_m:
            continue
        result.append(route)
    return result


def deduplicate_routes(routes: list[dict], min_separation_m: float = 200) -> list[dict]:
    """Remove routes whose start point is within min_separation_m of an already-kept route.
    Preserves order (first occurrence wins)."""
    kept: list[dict] = []
    for route in routes:
        coords = route.get("coords") or []
        if not coords:
            kept.append(route)
            continue
        lat, lng = coords[0][0], coords[0][1]
        too_close = any(
            (k_coords := (k.get("coords") or [])) and
            haversine_m(lat, lng, k_coords[0][0], k_coords[0][1]) < min_separation_m
            for k in kept
            if (k.get("coords") or [])
        )
        if not too_close:
            kept.append(route)
    return kept


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
