# Route Suggestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Suggest a Route" button to the Prescribed Workout card that uses the browser's geolocation and OpenRouteService to generate 3 round-trip running routes matching the workout's target distance, rendered on a Leaflet map with Prev/Next cycling.

**Architecture:** A new Flask endpoint `GET /api/route-suggestion` receives lat/lng/distance_m from the client, calls ORS server-side with the `foot-running` round-trip profile (green + quiet weightings), and returns up to 3 polylines as JSON. The template renders them client-side on a Leaflet map — the same Leaflet version already used for Strava route maps.

**Tech Stack:** Python `requests` (already available), Flask, OpenRouteService API, Leaflet.js 1.9.4 (already in project), Jinja2 templates.

---

## File Map

| File | Role |
|---|---|
| `runcoach/config.py` | Add `ors_api_key` field + `from_env()` wiring |
| `.env.example` | Document `ORS_API_KEY` |
| `runcoach/web/routes.py` | Add `GET /api/route-suggestion` endpoint |
| `runcoach/web/templates/run_detail.html` | Add route suggestion UI in prescribed workout card |
| `tests/test_web.py` | Tests for the new endpoint |

---

### Task 1: Add ORS config

**Files:**
- Modify: `runcoach/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Write a failing test for the config field**

In `tests/test_web.py`, add inside `class TestAppCreation`:

```python
def test_ors_api_key_defaults_empty(self, tmp_path):
    config = Config(data_dir=tmp_path / "data")
    assert config.ors_api_key == ""

def test_ors_api_key_from_env(self, tmp_path, monkeypatch):
    monkeypatch.setenv("ORS_API_KEY", "test-ors-key")
    config = Config.from_env()
    assert config.ors_api_key == "test-ors-key"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_web.py::TestAppCreation::test_ors_api_key_defaults_empty tests/test_web.py::TestAppCreation::test_ors_api_key_from_env -v
```

Expected: FAIL — `Config` has no attribute `ors_api_key`

- [ ] **Step 3: Add `ors_api_key` to Config dataclass**

In `runcoach/config.py`, add the field after `strava_webhook_enabled`:

```python
ors_api_key: str = ""
```

In `from_env()`, add inside the `return cls(...)` call after `strava_webhook_enabled=...`:

```python
ors_api_key=os.environ.get("ORS_API_KEY", ""),
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_web.py::TestAppCreation::test_ors_api_key_defaults_empty tests/test_web.py::TestAppCreation::test_ors_api_key_from_env -v
```

Expected: PASS

- [ ] **Step 5: Add ORS_API_KEY to .env.example**

Add at the end of `.env.example`:

```
# OpenRouteService — for round-trip route suggestions
# Get a free key at https://openrouteservice.org/dev/#/signup
ORS_API_KEY=
```

- [ ] **Step 6: Commit**

```bash
git add runcoach/config.py .env.example tests/test_web.py
git commit -m "feat: add ORS_API_KEY config field"
```

---

### Task 2: Add `GET /api/route-suggestion` Flask endpoint

**Files:**
- Modify: `runcoach/web/routes.py`
- Test: `tests/test_web.py`

- [ ] **Step 1: Write failing tests for the endpoint**

Add a new test class at the end of `tests/test_web.py`:

```python
class TestRouteSuggestion:
    """Tests for GET /api/route-suggestion endpoint."""

    ORS_SUCCESS = {
        "features": [
            {
                "geometry": {"coordinates": [[-6.26, 53.35], [-6.27, 53.36], [-6.26, 53.35]]},
                "properties": {"summary": {"distance": 10200}},
            },
            {
                "geometry": {"coordinates": [[-6.26, 53.35], [-6.25, 53.36], [-6.26, 53.35]]},
                "properties": {"summary": {"distance": 9800}},
            },
            {
                "geometry": {"coordinates": [[-6.26, 53.35], [-6.28, 53.37], [-6.26, 53.35]]},
                "properties": {"summary": {"distance": 10500}},
            },
        ]
    }

    def test_missing_params_returns_400(self, client):
        resp = client.get("/api/route-suggestion")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_invalid_lat_returns_400(self, client):
        resp = client.get("/api/route-suggestion?lat=notanumber&lng=-6.26&distance_m=10000")
        assert resp.status_code == 400

    def test_ors_key_not_configured_returns_503(self, client):
        resp = client.get("/api/route-suggestion?lat=53.35&lng=-6.26&distance_m=10000")
        assert resp.status_code == 503
        data = resp.get_json()
        assert "error" in data

    def test_returns_routes_on_success(self, client, app):
        app.config["config"].ors_api_key = "test-key"
        with patch("runcoach.web.routes.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = self.ORS_SUCCESS
            resp = client.get("/api/route-suggestion?lat=53.35&lng=-6.26&distance_m=10000")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "routes" in data
        assert len(data["routes"]) == 3
        assert "coords" in data["routes"][0]
        assert "distance_m" in data["routes"][0]
        # coords are [lat, lng] pairs (note ORS returns [lng, lat] — verify swap)
        assert data["routes"][0]["coords"][0] == [53.35, -6.26]

    def test_ors_error_returns_502(self, client, app):
        app.config["config"].ors_api_key = "test-key"
        with patch("runcoach.web.routes.requests.post") as mock_post:
            mock_post.return_value.status_code = 429
            mock_post.return_value.text = "Rate limit exceeded"
            resp = client.get("/api/route-suggestion?lat=53.35&lng=-6.26&distance_m=10000")
        assert resp.status_code == 502
        data = resp.get_json()
        assert "error" in data
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_web.py::TestRouteSuggestion -v
```

Expected: FAIL — 404 for all (endpoint doesn't exist yet)

- [ ] **Step 3: Add `import requests` to routes.py**

At the top of `runcoach/web/routes.py`, add after the existing stdlib imports:

```python
import requests
```

- [ ] **Step 4: Add the endpoint to routes.py**

Add at the end of `runcoach/web/routes.py`, before any Strava routes or at the end of the file:

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

    cfg: Config = current_app.config["config"]
    if not cfg.ors_api_key:
        return jsonify({"error": "Route suggestions are not configured (ORS_API_KEY missing)"}), 503

    payload = {
        "coordinates": [[lng, lat]],
        "options": {
            "round_trip": {
                "length": distance_m,
                "points": 3,
            }
        },
        "profile_params": {
            "weightings": {
                "green": 1,
                "quiet": 1,
            }
        },
    }

    try:
        resp = requests.post(
            "https://api.openrouteservice.org/v2/directions/foot-running/geojson",
            json=payload,
            headers={
                "Authorization": cfg.ors_api_key,
                "Content-Type": "application/json",
            },
            timeout=10,
        )
    except requests.exceptions.RequestException as exc:
        log.warning("ORS request failed: %s", exc)
        return jsonify({"error": "Route service unavailable"}), 502

    if resp.status_code != 200:
        log.warning("ORS returned %s: %s", resp.status_code, resp.text)
        return jsonify({"error": "Route service error"}), 502

    features = resp.json().get("features", [])
    routes = []
    for feature in features:
        # ORS returns [lng, lat]; Leaflet expects [lat, lng]
        raw_coords = feature["geometry"]["coordinates"]
        coords = [[pt[1], pt[0]] for pt in raw_coords]
        distance = int(feature["properties"]["summary"]["distance"])
        routes.append({"coords": coords, "distance_m": distance})

    return jsonify({"routes": routes})
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_web.py::TestRouteSuggestion -v
```

Expected: all 5 PASS

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
pytest tests/test_web.py -v
```

Expected: all existing tests still PASS

- [ ] **Step 7: Commit**

```bash
git add runcoach/web/routes.py tests/test_web.py
git commit -m "feat: add /api/route-suggestion endpoint using OpenRouteService"
```

---

### Task 3: Add route suggestion UI to the prescribed workout card

**Files:**
- Modify: `runcoach/web/templates/run_detail.html`

This task has no unit tests — it is UI-only. Verify manually per the verification steps at the end of the plan.

- [ ] **Step 1: Ensure Leaflet loads when prescribed distance is present**

Find the block near the top of `run_detail.html` (around line 4):

```html
{% if map_coords %}
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
{% endif %}
```

Replace it with:

```html
{% if map_coords or (prescribed and prescribed|selectattr('distance_m')|list) %}
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
{% endif %}
```

- [ ] **Step 2: Add the route suggestion section inside the prescribed workout card**

Find the end of the prescribed workout card (around line 633):

```html
  {% endfor %}
</div>
{% endif %}
```

Replace with:

```html
  {% endfor %}

  {% set first_pw_distance = prescribed | selectattr('distance_m') | list | first %}
  {% if first_pw_distance and first_pw_distance.distance_m %}
  <div style="border-top: 1px solid var(--border, #333); margin-top: 0.75rem; padding-top: 0.75rem;">
    <div style="font-size: 0.8rem; font-weight: 600; color: #d29922; margin-bottom: 0.5rem;">Suggested Route</div>
    <div id="route-btn-area">
      <button
        onclick="suggestRoute({{ first_pw_distance.distance_m | int }})"
        style="background: #d29922; color: #1a1a1a; border: none; padding: 0.4rem 0.9rem; border-radius: 4px; font-size: 0.82rem; font-weight: 600; cursor: pointer;"
      >📍 Suggest a Route</button>
    </div>
    <div id="route-status" style="display:none; font-size: 0.82rem; color: var(--fg-muted, #888); margin-top: 0.5rem;"></div>
    <div id="route-map-area" style="display:none; margin-top: 0.75rem;">
      <div id="route-map" style="height: 240px; width: 100%; border-radius: 4px;"></div>
      <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 0.5rem;">
        <button onclick="cycleRoute(-1)" style="background: none; border: 1px solid var(--border, #555); color: var(--fg, #e0e0e0); padding: 0.25rem 0.6rem; border-radius: 4px; font-size: 0.75rem; cursor: pointer;">← Prev</button>
        <span id="route-counter" style="font-size: 0.75rem; color: var(--fg-muted, #888);"></span>
        <button onclick="cycleRoute(1)" style="background: none; border: 1px solid var(--border, #555); color: var(--fg, #e0e0e0); padding: 0.25rem 0.6rem; border-radius: 4px; font-size: 0.75rem; cursor: pointer;">Next →</button>
      </div>
    </div>
  </div>

  <script>
  (function() {
    var _routes = [];
    var _currentIdx = 0;
    var _map = null;
    var _polyline = null;

    window.suggestRoute = function(distanceM) {
      var statusEl = document.getElementById('route-status');
      var btnArea = document.getElementById('route-btn-area');

      btnArea.style.display = 'none';
      statusEl.style.display = 'block';
      statusEl.textContent = 'Getting your location…';

      if (!navigator.geolocation) {
        statusEl.textContent = 'Geolocation is not supported by your browser.';
        btnArea.style.display = 'block';
        return;
      }

      navigator.geolocation.getCurrentPosition(
        function(pos) {
          statusEl.textContent = 'Generating routes…';
          var lat = pos.coords.latitude;
          var lng = pos.coords.longitude;
          fetch('/api/route-suggestion?lat=' + lat + '&lng=' + lng + '&distance_m=' + distanceM)
            .then(function(r) { return r.json(); })
            .then(function(data) {
              if (data.error) {
                statusEl.textContent = 'Could not generate route: ' + data.error;
                btnArea.style.display = 'block';
                return;
              }
              _routes = data.routes;
              _currentIdx = 0;
              statusEl.style.display = 'none';
              document.getElementById('route-map-area').style.display = 'block';
              _initMap(lat, lng);
              _drawRoute(0);
            })
            .catch(function() {
              statusEl.textContent = 'Route service unavailable. Please try again.';
              btnArea.style.display = 'block';
            });
        },
        function() {
          statusEl.textContent = 'Location access needed to suggest a route.';
          btnArea.style.display = 'block';
        }
      );
    };

    function _initMap(lat, lng) {
      if (_map) return;
      _map = L.map('route-map', { zoomControl: true, scrollWheelZoom: false });
      L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        maxZoom: 19,
      }).addTo(_map);
      setTimeout(function() { _map.invalidateSize(); }, 200);
    }

    function _drawRoute(idx) {
      var route = _routes[idx];
      if (_polyline) { _map.removeLayer(_polyline); }
      _polyline = L.polyline(route.coords, { color: '#d29922', weight: 3, opacity: 0.9 }).addTo(_map);
      _map.fitBounds(_polyline.getBounds(), { padding: [16, 16] });
      var km = (route.distance_m / 1000).toFixed(1);
      document.getElementById('route-counter').textContent =
        'Route ' + (idx + 1) + ' of ' + _routes.length + ' · ' + km + ' km';
    }

    window.cycleRoute = function(dir) {
      if (!_routes.length) return;
      _currentIdx = (_currentIdx + dir + _routes.length) % _routes.length;
      _drawRoute(_currentIdx);
    };
  })();
  </script>
  {% endif %}

</div>
{% endif %}
```

- [ ] **Step 2: Commit**

```bash
git add runcoach/web/templates/run_detail.html
git commit -m "feat: add route suggestion UI to prescribed workout card"
```

---

## Verification

1. Get a free ORS API key at https://openrouteservice.org/dev/#/signup and add it to `.env` as `ORS_API_KEY=<key>`
2. Start the app: `python -m runcoach.web`
3. Open a planned workout detail page that has a `distance_m` set (check the dashboard calendar for a planned workout with a distance)
4. Scroll to the **Prescribed Workout** card — verify the "📍 Suggest a Route" button appears
5. Click it — allow location when prompted — verify loading message appears then map renders with a yellow polyline
6. Click **Next →** and **← Prev** — verify the polyline changes and the counter updates (e.g. "Route 2 of 3 · 9.8 km")
7. Reload the page and deny location permission — verify the error message "Location access needed to suggest a route." appears and the button resets
8. Temporarily unset `ORS_API_KEY` in `.env` and restart — verify the button leads to a "not configured" error in the UI
9. Run the full test suite: `pytest -v` — all tests should pass
