# Next Run Detail Screen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a drill-down workout detail screen accessible from the home screen's Next Activity card, showing the full description, a power zone breakdown, and up to 3 route suggestions.

**Architecture:** Backend exposes new fields (`id`, `distance_m`, `duration_s`, `intensity_zones`) on the existing `next_workout` dashboard response and adds a JWT-authenticated `POST /api/v1/route-suggestion` endpoint backed by a shared ORS helper module. Flutter gains a new `WorkoutDetailScreen` (tabbed, matching `RunDetailScreen` pattern), a `PowerZoneBar` widget, and an updated `NextWorkoutCard` that truncates descriptions and navigates via GoRouter `extra`.

**Tech Stack:** Python/Flask (backend), Dart/Flutter, Riverpod, GoRouter, flutter_map, geolocator

**Note for subagents:** The Python venv is already activated — never use `python3` or `pip` from global; never activate the venv yourself. Run Python commands directly. Run Dart/Flutter commands from `mobile/` directory.

---

## File Map

| File | Action |
|---|---|
| `runcoach/web/ors.py` | Create — shared ORS route-fetching helper |
| `runcoach/web/routes.py` | Modify — delegate ORS call to `ors.py`, remove unused imports |
| `runcoach/web/api.py` | Modify — extend dashboard `next_workout`, add `POST /api/v1/route-suggestion` |
| `tests/test_api.py` | Modify — add tests for new endpoint + new dashboard fields |
| `mobile/lib/models/planned_workout.dart` | Modify — add 4 new fields |
| `mobile/test/models/planned_workout_test.dart` | Create — model unit tests |
| `mobile/lib/widgets/power_zone_bar.dart` | Create — stacked horizontal zone bar |
| `mobile/test/widgets/power_zone_bar_test.dart` | Create — widget tests |
| `mobile/pubspec.yaml` | Modify — add `geolocator` |
| `mobile/android/app/src/main/AndroidManifest.xml` | Modify — location permissions |
| `mobile/lib/services/api_service.dart` | Modify — add `postRouteSuggestion()` |
| `mobile/lib/screens/workout_detail_screen.dart` | Create — tabbed detail screen |
| `mobile/lib/widgets/next_workout_card.dart` | Modify — truncation + chevron + navigation |
| `mobile/test/widgets/next_workout_card_test.dart` | Create — widget tests |
| `mobile/lib/app.dart` | Modify — register `/workout-detail` route |

---

## Task 1: Create ORS helper + refactor routes.py

**Files:**
- Create: `runcoach/web/ors.py`
- Modify: `runcoach/web/routes.py`

- [ ] **Step 1: Write the failing test for the JWT route suggestion endpoint**

Add this class to `tests/test_api.py`:

```python
class TestRouteSuggestion:
    def test_requires_auth(self, client):
        resp = client.post(
            "/api/v1/route-suggestion",
            json={"lat": 51.5, "lng": -0.1, "distance_m": 5000},
        )
        assert resp.status_code == 401

    def test_missing_ors_key_returns_503(self, client, auth_headers):
        resp = client.post(
            "/api/v1/route-suggestion",
            json={"lat": 51.5, "lng": -0.1, "distance_m": 5000},
            headers=auth_headers,
        )
        # Config has no ORS key in test fixture
        assert resp.status_code == 503

    def test_returns_routes_with_mocked_ors(self, client, auth_headers, app, monkeypatch):
        from runcoach.config import Config
        app.config["config"] = Config(
            openai_api_key="test-key",
            openai_model="gpt-4o",
            data_dir=app.config["config"].data_dir,
            timezone="Europe/London",
            secret_key="test-secret-key",
            ors_api_key="fake-ors-key",
        )
        fake_response = {
            "features": [{
                "geometry": {"coordinates": [[-0.1, 51.5], [-0.11, 51.51]]},
                "properties": {"summary": {"distance": 5012}},
            }]
        }
        import unittest.mock as mock
        with mock.patch("runcoach.web.ors.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = fake_response
            resp = client.post(
                "/api/v1/route-suggestion",
                json={"lat": 51.5, "lng": -0.1, "distance_m": 5000},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "routes" in data
        assert len(data["routes"]) >= 1
        assert "coords" in data["routes"][0]
        assert "distance_m" in data["routes"][0]
```

- [ ] **Step 2: Run tests to verify they fail (endpoint doesn't exist yet)**

```bash
cd /home/colm/git/fitparser
pytest tests/test_api.py::TestRouteSuggestion -v
```

Expected: FAIL — `POST /api/v1/route-suggestion` returns 404

- [ ] **Step 3: Create `runcoach/web/ors.py` with the shared ORS helper**

```python
"""Shared OpenRouteService helper used by both session-auth and JWT-auth endpoints."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

log = logging.getLogger(__name__)


def fetch_routes(lat: float, lng: float, distance_m: int, ors_api_key: str) -> list[dict]:
    """Fetch up to 3 round-trip routes from ORS in parallel. Returns empty list on total failure."""

    def _fetch_one(seed: int) -> dict | None:
        payload = {
            "coordinates": [[lng, lat]],
            "options": {
                "round_trip": {
                    "length": distance_m,
                    "points": 3,
                    "seed": seed,
                },
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
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_fetch_one, seed): seed for seed in range(3)}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                routes.append(result)
    return routes
```

- [ ] **Step 4: Refactor `routes.py` to use the shared helper**

In `runcoach/web/routes.py`:

1. Add this import near the top (after the existing imports):
```python
from runcoach.web.ors import fetch_routes as _ors_fetch_routes
```

2. Remove the now-unused imports from `routes.py`:
   - Remove `from concurrent.futures import ThreadPoolExecutor, as_completed` (line 7)
   - Remove `import requests` (line 27)

3. Replace the body of `route_suggestion()` (lines 1283–1355) with:

```python
@bp.route("/api/route-suggestion")
@_login_required
def route_suggestion():
    try:
        lat = float(request.args["lat"])
        lng = float(request.args["lng"])
        distance_m = int(request.args["distance_m"])
    except (KeyError, ValueError):
        return jsonify({"error": "lat, lng, and distance_m are required numeric parameters"}), 400

    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return jsonify({"error": "lat/lng out of range"}), 400
    if distance_m <= 0:
        return jsonify({"error": "distance_m must be positive"}), 400

    cfg: Config = current_app.config["config"]
    if not cfg.ors_api_key:
        return jsonify({"error": "Route suggestions are not configured (ORS_API_KEY missing)"}), 503

    routes = _ors_fetch_routes(lat, lng, distance_m, cfg.ors_api_key)
    if not routes:
        return jsonify({"error": "Route service unavailable"}), 502

    return jsonify({"routes": routes})
```

- [ ] **Step 5: Add `POST /api/v1/route-suggestion` to `api.py`**

Add at the end of `runcoach/web/api.py` (after the dashboard route):

```python
@api_bp.route("/route-suggestion", methods=["POST"])
@require_auth
def api_route_suggestion():
    body = request.get_json(silent=True) or {}
    try:
        lat = float(body["lat"])
        lng = float(body["lng"])
        distance_m = int(body["distance_m"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "lat, lng, and distance_m are required numeric fields"}), 400

    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return jsonify({"error": "lat/lng out of range"}), 400
    if distance_m <= 0:
        return jsonify({"error": "distance_m must be positive"}), 400

    cfg: Config = current_app.config["config"]
    if not cfg.ors_api_key:
        return jsonify({"error": "Route suggestions are not configured (ORS_API_KEY missing)"}), 503

    from runcoach.web.ors import fetch_routes
    routes = fetch_routes(lat, lng, distance_m, cfg.ors_api_key)
    if not routes:
        return jsonify({"error": "Route service unavailable"}), 502

    return jsonify({"routes": routes})
```

- [ ] **Step 6: Run the tests and make sure they pass**

```bash
cd /home/colm/git/fitparser
pytest tests/test_api.py::TestRouteSuggestion -v
```

Expected: all 3 tests PASS

- [ ] **Step 7: Run the full test suite to check for regressions**

```bash
cd /home/colm/git/fitparser
pytest tests/test_api.py tests/test_web.py -v
```

Expected: all tests PASS

- [ ] **Step 8: Commit**

```bash
cd /home/colm/git/fitparser
git add runcoach/web/ors.py runcoach/web/api.py runcoach/web/routes.py tests/test_api.py
git commit -m "feat: extract ORS helper and add JWT route-suggestion endpoint"
```

---

## Task 2: Extend dashboard API with new next_workout fields

**Files:**
- Modify: `runcoach/web/api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_api.py`, inside `class TestDashboard`, add:

```python
def test_dashboard_next_workout_includes_new_fields(self, client, auth_headers, app):
    import json as json_mod
    from datetime import date, timedelta
    db = app.config["db"]
    user_id = db.get_default_user_id()
    future_date = (date.today() + timedelta(days=1)).isoformat()
    db.upsert_planned_workout(
        date=future_date,
        title="Interval Session",
        description="Hard effort",
        duration_s=2400.0,
        distance_m=6292.8,
        intensity_zones=json_mod.dumps([2340, 0, 0, 60, 0]),
        user_id=user_id,
    )
    resp = client.get("/api/v1/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    nw = resp.get_json()["next_workout"]
    assert nw["id"] is not None
    assert nw["distance_m"] == pytest.approx(6292.8)
    assert nw["duration_s"] == pytest.approx(2400.0)
    assert nw["intensity_zones"] == [2340, 0, 0, 60, 0]

def test_dashboard_next_workout_intensity_zones_null_when_unset(self, client, auth_headers, app):
    from datetime import date, timedelta
    db = app.config["db"]
    user_id = db.get_default_user_id()
    future_date = (date.today() + timedelta(days=2)).isoformat()
    db.upsert_planned_workout(
        date=future_date,
        title="Easy Run",
        description="Keep it easy",
        user_id=user_id,
    )
    resp = client.get("/api/v1/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    nw = resp.get_json()["next_workout"]
    assert nw["intensity_zones"] is None
    assert nw["distance_m"] is None
    assert nw["duration_s"] is None
```

Note: `pytest` is already imported at the top of `test_api.py`; add `import pytest` if it's missing.

- [ ] **Step 2: Run to verify it fails**

```bash
cd /home/colm/git/fitparser
pytest tests/test_api.py::TestDashboard::test_dashboard_next_workout_includes_new_fields -v
```

Expected: FAIL — `nw["id"]` KeyError

- [ ] **Step 3: Extend the dashboard endpoint**

In `runcoach/web/api.py`, add `import json` to the existing imports block at the top.

Then replace the `next_workout` dict in `dashboard()` (currently lines 619–623):

```python
    next_workout = None
    if upcoming:
        w = upcoming[0]
        raw_zones = w.get("intensity_zones")
        next_workout = {
            "id": w["id"],
            "date": w["date"],
            "name": w["title"],
            "description": w.get("description") or "",
            "distance_m": w.get("distance_m"),
            "duration_s": w.get("duration_s"),
            "intensity_zones": json.loads(raw_zones) if raw_zones else None,
        }
```

- [ ] **Step 4: Run tests**

```bash
cd /home/colm/git/fitparser
pytest tests/test_api.py::TestDashboard -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd /home/colm/git/fitparser
git add runcoach/web/api.py tests/test_api.py
git commit -m "feat: extend dashboard next_workout with id, distance_m, duration_s, intensity_zones"
```

---

## Task 3: Update PlannedWorkout Dart model

**Files:**
- Modify: `mobile/lib/models/planned_workout.dart`
- Create: `mobile/test/models/planned_workout_test.dart`

- [ ] **Step 1: Write the failing tests**

Create `mobile/test/models/planned_workout_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import '../../lib/models/planned_workout.dart';

void main() {
  group('PlannedWorkout.fromJson', () {
    Map<String, dynamic> baseJson() => {
      'id': 784,
      'date': '2026-05-09',
      'name': 'Easy Run / Strides #01',
      'description': 'Keep it easy',
      'distance_m': 6292.8,
      'duration_s': 2400.0,
      'intensity_zones': [2340, 0, 0, 60, 0],
    };

    test('parses all new fields', () {
      final w = PlannedWorkout.fromJson(baseJson());
      expect(w.id, 784);
      expect(w.distanceM, closeTo(6292.8, 0.01));
      expect(w.durationS, closeTo(2400.0, 0.01));
      expect(w.intensityZones, [2340, 0, 0, 60, 0]);
    });

    test('null optional fields are accepted', () {
      final json = baseJson()
        ..['id'] = null
        ..['distance_m'] = null
        ..['duration_s'] = null
        ..['intensity_zones'] = null;
      final w = PlannedWorkout.fromJson(json);
      expect(w.id, isNull);
      expect(w.distanceM, isNull);
      expect(w.durationS, isNull);
      expect(w.intensityZones, isNull);
    });

    test('existing fields still parse correctly', () {
      final w = PlannedWorkout.fromJson(baseJson());
      expect(w.date, '2026-05-09');
      expect(w.name, 'Easy Run / Strides #01');
      expect(w.description, 'Keep it easy');
    });

    test('intensityZones elements are int', () {
      final w = PlannedWorkout.fromJson(baseJson());
      expect(w.intensityZones!.every((e) => e is int), isTrue);
    });
  });
}
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/colm/git/fitparser/mobile
flutter test test/models/planned_workout_test.dart
```

Expected: FAIL — new fields not defined

- [ ] **Step 3: Update the model**

Replace `mobile/lib/models/planned_workout.dart` entirely:

```dart
class PlannedWorkout {
  final int? id;
  final String date;
  final String name;
  final String description;
  final double? distanceM;
  final double? durationS;
  final List<int>? intensityZones;

  const PlannedWorkout({
    this.id,
    required this.date,
    required this.name,
    required this.description,
    this.distanceM,
    this.durationS,
    this.intensityZones,
  });

  factory PlannedWorkout.fromJson(Map<String, dynamic> json) => PlannedWorkout(
    id: json['id'] as int?,
    date: json['date'] as String,
    name: json['name'] as String? ?? '',
    description: json['description'] as String? ?? '',
    distanceM: (json['distance_m'] as num?)?.toDouble(),
    durationS: (json['duration_s'] as num?)?.toDouble(),
    intensityZones: json['intensity_zones'] != null
        ? (json['intensity_zones'] as List<dynamic>)
            .map((e) => (e as num).toInt())
            .toList()
        : null,
  );
}
```

- [ ] **Step 4: Run tests**

```bash
cd /home/colm/git/fitparser/mobile
flutter test test/models/planned_workout_test.dart
```

Expected: all PASS

- [ ] **Step 5: Run all Flutter tests to check for regressions**

```bash
cd /home/colm/git/fitparser/mobile
flutter test
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
cd /home/colm/git/fitparser
git add mobile/lib/models/planned_workout.dart mobile/test/models/planned_workout_test.dart
git commit -m "feat: extend PlannedWorkout model with id, distanceM, durationS, intensityZones"
```

---

## Task 4: PowerZoneBar widget

**Files:**
- Create: `mobile/lib/widgets/power_zone_bar.dart`
- Create: `mobile/test/widgets/power_zone_bar_test.dart`

- [ ] **Step 1: Write the failing widget tests**

Create `mobile/test/widgets/power_zone_bar_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../lib/widgets/power_zone_bar.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  group('PowerZoneBar', () {
    testWidgets('shows nothing when zones are null', (tester) async {
      await tester.pumpWidget(_wrap(const PowerZoneBar(zones: null)));
      expect(find.text('POWER ZONES'), findsNothing);
    });

    testWidgets('shows nothing when all zones are zero', (tester) async {
      await tester.pumpWidget(
        _wrap(const PowerZoneBar(zones: [0, 0, 0, 0, 0])),
      );
      expect(find.text('POWER ZONES'), findsNothing);
    });

    testWidgets('renders header when at least one zone is non-zero', (tester) async {
      await tester.pumpWidget(
        _wrap(const PowerZoneBar(zones: [2340, 0, 0, 60, 0])),
      );
      expect(find.text('POWER ZONES'), findsOneWidget);
    });

    testWidgets('formats seconds as MM:SS label', (tester) async {
      await tester.pumpWidget(
        _wrap(const PowerZoneBar(zones: [2340, 0, 0, 60, 0])),
      );
      // 2340s = 39:00, 60s = 1:00
      expect(find.textContaining('Z1 39:00'), findsOneWidget);
      expect(find.textContaining('Z4 1:00'), findsOneWidget);
    });

    testWidgets('suppresses zero-zone labels', (tester) async {
      await tester.pumpWidget(
        _wrap(const PowerZoneBar(zones: [2340, 0, 0, 60, 0])),
      );
      expect(find.textContaining('Z2'), findsNothing);
      expect(find.textContaining('Z3'), findsNothing);
      expect(find.textContaining('Z5'), findsNothing);
    });

    testWidgets('renders all non-zero zones', (tester) async {
      await tester.pumpWidget(
        _wrap(const PowerZoneBar(zones: [600, 1200, 300, 0, 0])),
      );
      expect(find.textContaining('Z1'), findsOneWidget);
      expect(find.textContaining('Z2'), findsOneWidget);
      expect(find.textContaining('Z3'), findsOneWidget);
      expect(find.textContaining('Z4'), findsNothing);
    });
  });
}
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/colm/git/fitparser/mobile
flutter test test/widgets/power_zone_bar_test.dart
```

Expected: FAIL — file not found

- [ ] **Step 3: Create the widget**

Create `mobile/lib/widgets/power_zone_bar.dart`:

```dart
import 'package:flutter/material.dart';

class PowerZoneBar extends StatelessWidget {
  final List<int>? zones;
  const PowerZoneBar({required this.zones, super.key});

  static const _colors = [
    Color(0xFF4ade80), // Z1
    Color(0xFFa3e635), // Z2
    Color(0xFFfacc15), // Z3
    Color(0xFFf97316), // Z4
    Color(0xFFef4444), // Z5
  ];

  String _fmt(int seconds) {
    final m = seconds ~/ 60;
    final s = (seconds % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    if (zones == null) return const SizedBox.shrink();
    final total = zones!.fold(0, (a, b) => a + b);
    if (total == 0) return const SizedBox.shrink();

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'POWER ZONES',
              style: TextStyle(
                fontSize: 10,
                color: Color(0xFF888888),
                letterSpacing: 1,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(5),
              child: Row(
                children: zones!.asMap().entries
                    .where((e) => e.value > 0)
                    .map((e) => Expanded(
                          flex: e.value,
                          child: Container(height: 12, color: _colors[e.key]),
                        ))
                    .toList(),
              ),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 12,
              runSpacing: 4,
              children: zones!.asMap().entries
                  .where((e) => e.value > 0)
                  .map((e) => Text(
                        'Z${e.key + 1} ${_fmt(e.value)}',
                        style: TextStyle(
                          fontSize: 11,
                          color: _colors[e.key],
                          fontWeight: FontWeight.w600,
                        ),
                      ))
                  .toList(),
            ),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 4: Run tests**

```bash
cd /home/colm/git/fitparser/mobile
flutter test test/widgets/power_zone_bar_test.dart
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd /home/colm/git/fitparser
git add mobile/lib/widgets/power_zone_bar.dart mobile/test/widgets/power_zone_bar_test.dart
git commit -m "feat: add PowerZoneBar widget"
```

---

## Task 5: Add geolocator + ApiService.postRouteSuggestion

**Files:**
- Modify: `mobile/pubspec.yaml`
- Modify: `mobile/android/app/src/main/AndroidManifest.xml`
- Modify: `mobile/lib/services/api_service.dart`

- [ ] **Step 1: Add geolocator to pubspec.yaml**

In `mobile/pubspec.yaml`, add to the `dependencies:` block (after `url_launcher`):

```yaml
  geolocator: ^13.0.0
```

- [ ] **Step 2: Add Android location permissions**

In `mobile/android/app/src/main/AndroidManifest.xml`, add these two lines after `<uses-permission android:name="android.permission.INTERNET"/>`:

```xml
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION"/>
```

- [ ] **Step 3: Run flutter pub get**

```bash
cd /home/colm/git/fitparser/mobile
flutter pub get
```

Expected: resolves successfully, no errors

- [ ] **Step 4: Add postRouteSuggestion to ApiService**

In `mobile/lib/services/api_service.dart`, add this method to the `ApiService` class (after `getAthleteProfile()`):

```dart
  Future<List<Map<String, dynamic>>> postRouteSuggestion({
    required double lat,
    required double lng,
    required int distanceM,
  }) async {
    final resp = await _dio.post(
      '/route-suggestion',
      data: {'lat': lat, 'lng': lng, 'distance_m': distanceM},
    );
    final routes = resp.data['routes'] as List<dynamic>;
    return routes.map((e) => e as Map<String, dynamic>).toList();
  }
```

- [ ] **Step 5: Run all Flutter tests**

```bash
cd /home/colm/git/fitparser/mobile
flutter test
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
cd /home/colm/git/fitparser
git add mobile/pubspec.yaml mobile/pubspec.lock mobile/android/app/src/main/AndroidManifest.xml mobile/lib/services/api_service.dart
git commit -m "feat: add geolocator dependency and postRouteSuggestion API method"
```

---

## Task 6: WorkoutDetailScreen

**Files:**
- Create: `mobile/lib/screens/workout_detail_screen.dart`

- [ ] **Step 1: Create the screen**

Create `mobile/lib/screens/workout_detail_screen.dart`:

```dart
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:geolocator/geolocator.dart';
import '../models/planned_workout.dart';
import '../providers/auth_provider.dart';
import '../widgets/power_zone_bar.dart';

class WorkoutDetailScreen extends ConsumerStatefulWidget {
  final PlannedWorkout workout;
  const WorkoutDetailScreen({required this.workout, super.key});

  @override
  ConsumerState<WorkoutDetailScreen> createState() =>
      _WorkoutDetailScreenState();
}

class _WorkoutDetailScreenState extends ConsumerState<WorkoutDetailScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs;

  List<Map<String, dynamic>>? _routes;
  int _routeIndex = 0;
  bool _loadingRoutes = false;
  String? _routeError;
  bool _routeTabVisited = false;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    _tabs.addListener(_onTabChanged);
  }

  void _onTabChanged() {
    if (_tabs.index == 1 && !_routeTabVisited) {
      setState(() => _routeTabVisited = true);
      _fetchRoutes();
    }
  }

  Future<void> _fetchRoutes() async {
    setState(() {
      _loadingRoutes = true;
      _routeError = null;
    });
    try {
      LocationPermission permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        setState(() {
          _loadingRoutes = false;
          _routeError = 'location_denied';
        });
        return;
      }

      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
        ),
      ).timeout(const Duration(seconds: 15));

      final api = ref.read(apiServiceProvider);
      final routes = await api.postRouteSuggestion(
        lat: position.latitude,
        lng: position.longitude,
        distanceM: widget.workout.distanceM?.toInt() ?? 5000,
      );

      if (!mounted) return;
      setState(() {
        _routes = routes;
        _routeIndex = 0;
        _loadingRoutes = false;
      });
    } on TimeoutException {
      if (!mounted) return;
      setState(() {
        _loadingRoutes = false;
        _routeError = 'error';
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loadingRoutes = false;
        _routeError = 'error';
      });
    }
  }

  @override
  void dispose() {
    _tabs.removeListener(_onTabChanged);
    _tabs.dispose();
    super.dispose();
  }

  String _formatDate(String isoDate) {
    try {
      final dt = DateTime.parse(isoDate);
      const months = [
        'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
      ];
      const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      return '${days[dt.weekday - 1]} ${dt.day} ${months[dt.month - 1]}';
    } catch (_) {
      return isoDate;
    }
  }

  String _buildSubtitle() {
    final parts = <String>[];
    if (widget.workout.durationS != null) {
      parts.add('${(widget.workout.durationS! / 60).round()} min');
    }
    if (widget.workout.distanceM != null) {
      parts.add('${(widget.workout.distanceM! / 1000).toStringAsFixed(1)} km');
    }
    return parts.join(' · ');
  }

  @override
  Widget build(BuildContext context) {
    final subtitle = _buildSubtitle();
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        surfaceTintColor: Colors.transparent,
        iconTheme: const IconThemeData(color: Colors.white),
        flexibleSpace: Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              stops: [0.0, 0.5, 1.0],
              colors: [
                Color(0xFF1c1917),
                Color(0xFF9a3412),
                Color(0xFFea580c),
              ],
            ),
          ),
        ),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              _formatDate(widget.workout.date),
              style: const TextStyle(fontSize: 11, color: Color(0xFFFFD9B0)),
            ),
            Text(
              widget.workout.name,
              style: const TextStyle(
                fontWeight: FontWeight.w700,
                fontSize: 16,
                color: Colors.white,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            if (subtitle.isNotEmpty)
              Text(
                subtitle,
                style: const TextStyle(fontSize: 11, color: Color(0xFFFFD9B0)),
              ),
          ],
        ),
        bottom: TabBar(
          controller: _tabs,
          labelColor: Colors.white,
          unselectedLabelColor: const Color(0xFFFFD9B0),
          indicatorColor: Colors.white,
          tabs: const [Tab(text: 'Overview'), Tab(text: 'Route')],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: [
          _OverviewTab(workout: widget.workout),
          _RouteTab(
            routes: _routes,
            loading: _loadingRoutes,
            error: _routeError,
            routeIndex: _routeIndex,
            onPrev:
                _routeIndex > 0 ? () => setState(() => _routeIndex--) : null,
            onNext: _routes != null && _routeIndex < _routes!.length - 1
                ? () => setState(() => _routeIndex++)
                : null,
            onRetry: _fetchRoutes,
          ),
        ],
      ),
    );
  }
}

class _OverviewTab extends StatelessWidget {
  final PlannedWorkout workout;
  const _OverviewTab({required this.workout});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
      children: [
        if (workout.description.isNotEmpty)
          Text(
            workout.description,
            style: const TextStyle(fontSize: 14, height: 1.6),
          ),
        const SizedBox(height: 8),
        PowerZoneBar(zones: workout.intensityZones),
      ],
    );
  }
}

class _RouteTab extends StatelessWidget {
  final List<Map<String, dynamic>>? routes;
  final bool loading;
  final String? error;
  final int routeIndex;
  final VoidCallback? onPrev;
  final VoidCallback? onNext;
  final VoidCallback onRetry;

  const _RouteTab({
    required this.routes,
    required this.loading,
    required this.error,
    required this.routeIndex,
    required this.onPrev,
    required this.onNext,
    required this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (error == 'location_denied') {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text(
            'Location access needed for route suggestions',
            textAlign: TextAlign.center,
            style: TextStyle(color: Color(0xFF888888)),
          ),
        ),
      );
    }

    if (error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text(
              "Couldn't load route suggestions",
              style: TextStyle(color: Color(0xFF888888)),
            ),
            const SizedBox(height: 16),
            OutlinedButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      );
    }

    if (routes == null) return const SizedBox.shrink();

    if (routes!.isEmpty) {
      return const Center(
        child: Text(
          "Couldn't load route suggestions",
          style: TextStyle(color: Color(0xFF888888)),
        ),
      );
    }

    final route = routes![routeIndex];
    final rawCoords = route['coords'] as List<dynamic>;
    final points = rawCoords.map((c) {
      final pt = c as List<dynamic>;
      return LatLng((pt[0] as num).toDouble(), (pt[1] as num).toDouble());
    }).toList();

    return Column(
      children: [
        Expanded(
          child: FlutterMap(
            options: MapOptions(
              initialCameraFit: CameraFit.coordinates(
                coordinates: points,
                padding: const EdgeInsets.all(32),
              ),
              interactionOptions: const InteractionOptions(
                flags: InteractiveFlag.none,
              ),
            ),
            children: [
              TileLayer(
                urlTemplate:
                    'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.runcoach.app',
              ),
              PolylineLayer(
                polylines: [
                  Polyline(
                    points: points,
                    color: const Color(0xFFea580c),
                    strokeWidth: 3,
                  ),
                ],
              ),
              if (points.isNotEmpty)
                MarkerLayer(
                  markers: [
                    Marker(
                      point: points.first,
                      child: const Icon(
                        Icons.circle,
                        color: Color(0xFF4ADE80),
                        size: 12,
                      ),
                    ),
                  ],
                ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              TextButton.icon(
                onPressed: onPrev,
                icon: const Icon(Icons.chevron_left),
                label: const Text('Prev'),
              ),
              Text(
                'Route ${routeIndex + 1} of ${routes!.length}',
                style: const TextStyle(
                  fontSize: 13,
                  color: Color(0xFF888888),
                ),
              ),
              TextButton.icon(
                onPressed: onNext,
                icon: const Icon(Icons.chevron_right),
                label: const Text('Next'),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd /home/colm/git/fitparser/mobile
flutter analyze lib/screens/workout_detail_screen.dart
```

Expected: no errors

- [ ] **Step 3: Run all Flutter tests**

```bash
cd /home/colm/git/fitparser/mobile
flutter test
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
cd /home/colm/git/fitparser
git add mobile/lib/screens/workout_detail_screen.dart
git commit -m "feat: add WorkoutDetailScreen with Overview and Route tabs"
```

---

## Task 7: Update NextWorkoutCard + register /workout-detail route + widget tests

**Files:**
- Modify: `mobile/lib/widgets/next_workout_card.dart`
- Create: `mobile/test/widgets/next_workout_card_test.dart`
- Modify: `mobile/lib/app.dart`

- [ ] **Step 1: Write failing widget tests**

Create `mobile/test/widgets/next_workout_card_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../lib/models/planned_workout.dart';
import '../../lib/widgets/next_workout_card.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

PlannedWorkout _workout({String description = ''}) => PlannedWorkout(
  date: '2026-05-09',
  name: 'Easy Run',
  description: description,
);

void main() {
  group('NextWorkoutCard', () {
    testWidgets('shows workout name', (tester) async {
      await tester.pumpWidget(_wrap(NextWorkoutCard(workout: _workout())));
      expect(find.text('Easy Run'), findsOneWidget);
    });

    testWidgets('shows chevron_right icon', (tester) async {
      await tester.pumpWidget(_wrap(NextWorkoutCard(workout: _workout())));
      expect(find.byIcon(Icons.chevron_right), findsOneWidget);
    });

    testWidgets('truncates description to first paragraph', (tester) async {
      final w = _workout(
        description: 'First paragraph.\n\nSecond paragraph.',
      );
      await tester.pumpWidget(_wrap(NextWorkoutCard(workout: w)));
      expect(find.text('First paragraph.'), findsOneWidget);
      expect(find.text('Second paragraph.'), findsNothing);
    });

    testWidgets('shows full description when no double newline', (tester) async {
      final w = _workout(description: 'Single paragraph text here.');
      await tester.pumpWidget(_wrap(NextWorkoutCard(workout: w)));
      expect(find.text('Single paragraph text here.'), findsOneWidget);
    });

    testWidgets('hides description section when empty', (tester) async {
      await tester.pumpWidget(_wrap(NextWorkoutCard(workout: _workout())));
      // No description text should appear
      expect(find.byType(Text), findsNWidgets(2)); // label + name only
    });
  });
}
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/colm/git/fitparser/mobile
flutter test test/widgets/next_workout_card_test.dart
```

Expected: FAIL — chevron icon not found

- [ ] **Step 3: Update NextWorkoutCard**

Replace `mobile/lib/widgets/next_workout_card.dart` entirely:

```dart
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../models/planned_workout.dart';

class NextWorkoutCard extends StatelessWidget {
  final PlannedWorkout workout;
  const NextWorkoutCard({required this.workout, super.key});

  String _formatDate(String isoDate) {
    try {
      final dt = DateTime.parse(isoDate);
      const months = [
        'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
      ];
      const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      return '${days[dt.weekday - 1]} ${dt.day} ${months[dt.month - 1]}';
    } catch (_) {
      return isoDate;
    }
  }

  @override
  Widget build(BuildContext context) {
    final firstPara = workout.description.split('\n\n').first;
    return GestureDetector(
      onTap: () => context.push('/workout-detail', extra: workout),
      child: Card(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        child: Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: const Border(
              left: BorderSide(color: Color(0xFFF59E0B), width: 3),
            ),
          ),
          padding: const EdgeInsets.all(14),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'NEXT · ${_formatDate(workout.date)}'.toUpperCase(),
                      style: const TextStyle(
                        fontSize: 10,
                        color: Color(0xFF888888),
                        letterSpacing: 1,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      workout.name,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    if (firstPara.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        firstPara,
                        style: const TextStyle(
                          fontSize: 12,
                          color: Color(0xFFB45309),
                        ),
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 8),
              const Icon(
                Icons.chevron_right,
                color: Color(0xFF888888),
                size: 20,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
```

- [ ] **Step 4: Run widget tests**

```bash
cd /home/colm/git/fitparser/mobile
flutter test test/widgets/next_workout_card_test.dart
```

Expected: all PASS

- [ ] **Step 5: Register /workout-detail route in app.dart**

In `mobile/lib/app.dart`:

1. Add import at the top:
```dart
import 'screens/workout_detail_screen.dart';
```

2. Add the new route to the `routes` list of `GoRouter`, as a sibling to the `ShellRoute` (add it before `ShellRoute`):

```dart
      GoRoute(
        path: '/workout-detail',
        parentNavigatorKey: _rootNavKey,
        builder: (context, state) => WorkoutDetailScreen(
          workout: state.extra as PlannedWorkout,
        ),
      ),
```

Also add the `PlannedWorkout` import if not already imported:
```dart
import 'models/planned_workout.dart';
```

- [ ] **Step 6: Analyze for compilation errors**

```bash
cd /home/colm/git/fitparser/mobile
flutter analyze lib/app.dart lib/widgets/next_workout_card.dart lib/screens/workout_detail_screen.dart
```

Expected: no errors

- [ ] **Step 7: Run all Flutter tests**

```bash
cd /home/colm/git/fitparser/mobile
flutter test
```

Expected: all PASS

- [ ] **Step 8: Run Python tests to confirm no regressions**

```bash
cd /home/colm/git/fitparser
pytest tests/ -q
```

Expected: all PASS

- [ ] **Step 9: Commit**

```bash
cd /home/colm/git/fitparser
git add mobile/lib/widgets/next_workout_card.dart \
        mobile/test/widgets/next_workout_card_test.dart \
        mobile/lib/app.dart
git commit -m "feat: NextWorkoutCard truncates description, adds chevron, navigates to WorkoutDetailScreen"
```

---

## Self-Review

### Spec coverage check

| Spec requirement | Task |
|---|---|
| Truncate description to first `\n\n` paragraph | Task 7 |
| Chevron right on NextWorkoutCard | Task 7 |
| Navigate to `/workout-detail` via GoRouter extra | Task 7 |
| Dashboard exposes `id`, `distance_m`, `duration_s`, `intensity_zones` | Task 2 |
| `PlannedWorkout` model has new fields | Task 3 |
| `WorkoutDetailScreen` gradient header `#1c1917 → #ea580c` | Task 6 |
| Header shows date, name, subtitle (duration · distance) | Task 6 |
| Two tabs: Overview \| Route | Task 6 |
| Overview tab: full description + PowerZoneBar | Task 6 |
| Route tab: lazy on first entry | Task 6 |
| Route tab: requests location, calls API | Task 6 |
| Route tab: Prev/Next navigation | Task 6 |
| Route tab: ephemeral state, no provider | Task 6 |
| `PowerZoneBar`: stacked bar, zone colors, MM:SS labels | Task 4 |
| `PowerZoneBar`: hidden when null/all-zeros | Task 4 |
| `/workout-detail` GoRouter route via `extra` | Task 7 |
| `POST /api/v1/route-suggestion` JWT endpoint | Task 1 |
| Shared ORS helper extracted | Task 1 |
| Error: location denied → no retry | Task 6 |
| Error: timeout/fetch failure → retry button | Task 6 |
| Error: all zones zero → zone bar hidden | Task 4 |
| Unit test: `PlannedWorkout.fromJson()` round-trips | Task 3 |
| Widget test: `PowerZoneBar` proportional segments | Task 4 |
| Widget test: `PowerZoneBar` suppresses zero zones | Task 4 |
| Widget test: `NextWorkoutCard` truncation + chevron | Task 7 |
| Python test: 401 without JWT on route-suggestion | Task 1 |
| Python test: 200 with valid JWT on route-suggestion | Task 1 |

All requirements covered.

### Placeholder scan

No TBDs, TODOs, or incomplete steps found.

### Type consistency check

- `PlannedWorkout.intensityZones` declared as `List<int>?` in Task 3; used as `List<int>?` in `PowerZoneBar` Task 4 ✓
- `PlannedWorkout.distanceM` is `double?` in Task 3; `.toInt()` called in Task 6 ✓
- `routes` in `_WorkoutDetailScreenState` is `List<Map<String, dynamic>>?`; `_RouteTab` receives the same type ✓
- `fetch_routes()` returns `list[dict]` in Python; `routes` field in JSON response is `list` ✓
- `WorkoutDetailScreen` receives `PlannedWorkout` in Task 6; GoRouter passes it as `state.extra as PlannedWorkout` in Task 7 ✓
