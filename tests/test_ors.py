"""Tests for runcoach.web.ors helper functions."""
from __future__ import annotations
import pytest
from runcoach.web.ors import haversine_m, filter_routes_by_proximity, deduplicate_routes


class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine_m(51.5, -0.1, 51.5, -0.1) == pytest.approx(0.0, abs=0.1)

    def test_known_distance(self):
        # London to Paris ≈ 340 km
        d = haversine_m(51.5074, -0.1278, 48.8566, 2.3522)
        assert 330_000 < d < 350_000

    def test_short_distance(self):
        # 0.001° latitude ≈ 111m
        d = haversine_m(51.5, -0.1, 51.501, -0.1)
        assert 100 < d < 120


class TestFilterRoutesByProximity:
    def _route(self, start_lat, start_lng, distance_m, **extra):
        return {
            "coords": [[start_lat, start_lng], [start_lat + 0.001, start_lng + 0.001]],
            "distance_m": distance_m,
            **extra,
        }

    def test_includes_nearby_matching_distance(self):
        route = self._route(51.5001, -0.1001, 5000)
        result = filter_routes_by_proximity([route], 51.5, -0.1, 5000)
        assert len(result) == 1

    def test_excludes_route_too_far_away(self):
        route = self._route(51.51, -0.1, 5000)  # ~1.1 km from user
        result = filter_routes_by_proximity([route], 51.5, -0.1, 5000)
        assert len(result) == 0

    def test_excludes_route_wrong_distance(self):
        route = self._route(51.5001, -0.1001, 10000)  # 10 km, target is 5 km
        result = filter_routes_by_proximity([route], 51.5, -0.1, 5000)
        assert len(result) == 0

    def test_includes_route_at_distance_boundary(self):
        # 999m offset from target — should be included (max_dist_offset_m=1000)
        route = self._route(51.5001, -0.1001, 5999)
        result = filter_routes_by_proximity([route], 51.5, -0.1, 5000)
        assert len(result) == 1

    def test_excludes_route_just_over_distance_boundary(self):
        route = self._route(51.5001, -0.1001, 6001)
        result = filter_routes_by_proximity([route], 51.5, -0.1, 5000)
        assert len(result) == 0

    def test_empty_input(self):
        result = filter_routes_by_proximity([], 51.5, -0.1, 5000)
        assert result == []

    def test_route_with_no_coords_is_skipped(self):
        result = filter_routes_by_proximity(
            [{"coords": [], "distance_m": 5000}], 51.5, -0.1, 5000
        )
        assert result == []


class TestDeduplicateRoutes:
    def _route(self, start_lat, start_lng, name):
        return {
            "coords": [[start_lat, start_lng], [start_lat + 0.001, start_lng]],
            "distance_m": 5000,
            "name": name,
        }

    def test_keeps_first_when_two_routes_same_start(self):
        r1 = self._route(51.5, -0.1, "First")
        r2 = self._route(51.5001, -0.1001, "Second")  # ~13m away — same cluster
        result = deduplicate_routes([r1, r2])
        assert len(result) == 1
        assert result[0]["name"] == "First"

    def test_keeps_both_when_starts_far_apart(self):
        r1 = self._route(51.5, -0.1, "Loop A")
        r2 = self._route(51.503, -0.1, "Loop B")  # ~330m away — different cluster
        result = deduplicate_routes([r1, r2])
        assert len(result) == 2

    def test_empty_input(self):
        assert deduplicate_routes([]) == []

    def test_route_with_no_coords_is_preserved(self):
        r = {"coords": [], "distance_m": 5000, "name": "Empty"}
        result = deduplicate_routes([r])
        assert len(result) == 1
