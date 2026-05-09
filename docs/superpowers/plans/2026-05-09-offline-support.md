# Offline Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the RunCoach Android PWA usable offline by caching the homepage, the 10 most recent run detail pages, and any page the user visits, with a fallback offline page for uncached URLs.

**Architecture:** The service worker is updated to (1) cache HTML page responses on every successful network-first fetch, (2) proactively prefetch the 10 most recent run pages at activation time via a new session-authenticated `/recent-run-ids` Flask route, and (3) fall back to a pre-cached `/offline` page for uncached navigation failures. Cache names are bumped to `-v2` to evict old entries.

**Tech Stack:** Vanilla JS service worker, Flask (Python), Jinja2, pytest, `flask` test client.

---

## Files

- **Modify**: `runcoach/web/static/service-worker.js` — cache names, page caching on fetch, prefetch on activate
- **Modify**: `runcoach/web/routes.py` — add `/recent-run-ids` and `/offline` routes
- **Create**: `runcoach/web/templates/offline.html` — standalone offline fallback page
- **Modify**: `tests/test_web.py` — unit tests for the two new routes

---

### Task 1: Unit tests for the two new routes (TDD)

Write failing tests first. The routes don't exist yet.

**Files:**
- Modify: `tests/test_web.py`

- [ ] **Step 1: Add a new test class at the end of `tests/test_web.py`**

```python
class TestOfflineRoutes:
    def test_recent_run_ids_authenticated(self, client, app):
        db = app.config["db"]
        # Insert 12 runs — expect only the 10 most recent IDs returned
        ids = []
        for i in range(12):
            run_id = db.insert_run(
                stryd_activity_id=i + 1,
                name=f"Run {i}",
                date=f"2026-0{(i % 9) + 1}-01",
                fit_path=f"activities/run{i}.fit",
            )
            ids.append(run_id)

        response = client.get("/recent-run-ids")
        assert response.status_code == 200
        data = response.get_json()
        assert "ids" in data
        assert len(data["ids"]) == 10
        # Most recent 10 runs (last inserted = highest IDs)
        assert set(data["ids"]) == set(ids[-10:])

    def test_recent_run_ids_unauthenticated(self, app):
        # Fresh client with no session
        c = app.test_client()
        response = c.get("/recent-run-ids")
        assert response.status_code == 302  # redirect to login

    def test_recent_run_ids_empty(self, client):
        # No runs in DB — should return empty list
        response = client.get("/recent-run-ids")
        assert response.status_code == 200
        data = response.get_json()
        assert data["ids"] == []

    def test_offline_page_no_auth_required(self, app):
        # /offline must work without a session (SW serves it from cache)
        c = app.test_client()
        response = c.get("/offline")
        assert response.status_code == 200
        assert b"offline" in response.data.lower()

    def test_offline_page_has_no_external_deps(self, app):
        c = app.test_client()
        response = c.get("/offline")
        html = response.data.decode()
        # Must not load any external URLs (fonts, CDN, etc.)
        assert "http" not in html or all(
            ref.startswith("/static/") or "http" not in ref
            for ref in html.split("src=")[1:]
        )
        # Must be self-contained — no base template extends
        assert "{% extends" not in html
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_web.py::TestOfflineRoutes -v
```

Expected: 5 failures — routes don't exist yet.

---

### Task 2: `/offline` route and template

**Files:**
- Modify: `runcoach/web/routes.py`
- Create: `runcoach/web/templates/offline.html`

- [ ] **Step 1: Add the `/offline` route to `routes.py`**

Find the block of routes near the bottom of the file (after `/status`, before `/login`). Add:

```python
@bp.route("/offline")
def offline():
    return render_template("offline.html"), 200
```

No `@_login_required` — this must work without a session.

- [ ] **Step 2: Create `runcoach/web/templates/offline.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>RunCoach — Offline</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #0d1117;
      color: #e2e8f0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 32px 16px;
    }
    .icon { font-size: 48px; margin-bottom: 16px; }
    h1 { font-size: 22px; font-weight: 700; margin-bottom: 8px; }
    p { font-size: 14px; color: #888; line-height: 1.6; max-width: 280px; margin: 0 auto; }
  </style>
</head>
<body>
  <div>
    <div class="icon">📵</div>
    <h1>You're offline</h1>
    <p>This page isn't available without a connection. Pages you've visited recently will still load.</p>
  </div>
</body>
</html>
```

- [ ] **Step 3: Run the offline route tests**

```bash
pytest tests/test_web.py::TestOfflineRoutes::test_offline_page_no_auth_required tests/test_web.py::TestOfflineRoutes::test_offline_page_has_no_external_deps -v
```

Expected: both pass.

- [ ] **Step 4: Commit**

```bash
git add runcoach/web/routes.py runcoach/web/templates/offline.html tests/test_web.py
git commit -m "feat: add /offline fallback page (no auth required)"
```

---

### Task 3: `/recent-run-ids` route

**Files:**
- Modify: `runcoach/web/routes.py`

- [ ] **Step 1: Add the `/recent-run-ids` route to `routes.py`**

Add immediately after the `/offline` route:

```python
@bp.route("/recent-run-ids")
@_login_required
def recent_run_ids():
    runs = _db().get_runs_paginated(limit=10, offset=0, user_id=_current_user_id())
    return jsonify({"ids": [r["id"] for r in runs]})
```

`get_runs_paginated` is already imported via `_db()` and returns runs newest-first. `jsonify` is already imported at the top of `routes.py`.

- [ ] **Step 2: Run the remaining three route tests**

```bash
pytest tests/test_web.py::TestOfflineRoutes -v
```

Expected: all 5 pass.

- [ ] **Step 3: Run the full test suite**

```bash
pytest -v
```

Expected: all tests pass, no regressions.

- [ ] **Step 4: Commit**

```bash
git add runcoach/web/routes.py
git commit -m "feat: add /recent-run-ids endpoint for SW prefetch"
```

---

### Task 4: Update the service worker

**Files:**
- Modify: `runcoach/web/static/service-worker.js`

Replace the entire contents of `runcoach/web/static/service-worker.js` with:

```js
const STATIC_CACHE = 'runcoach-static-v2';
const PAGES_CACHE = 'runcoach-pages-v2';

const STATIC_ASSETS = [
  '/static/manifest.json',
  '/static/app.js',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/offline',
];

// Install: pre-cache static assets + offline page
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate: delete stale caches, claim clients, prefetch recent runs
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k !== STATIC_CACHE && k !== PAGES_CACHE)
            .map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
      .then(() => prefetchRecentRuns())
  );
});

async function prefetchRecentRuns() {
  let ids;
  try {
    const res = await fetch('/recent-run-ids', { credentials: 'include' });
    if (!res.ok) return; // not logged in yet — skip silently
    ({ ids } = await res.json());
  } catch {
    return; // offline at activate time — skip silently
  }

  const cache = await caches.open(PAGES_CACHE);
  const urls = ['/', ...ids.map((id) => `/run/${id}`)];
  await Promise.allSettled(
    urls.map(async (url) => {
      try {
        const res = await fetch(url, { credentials: 'include' });
        if (res.ok) await cache.put(url, res);
      } catch {
        // individual page fetch failed — skip it
      }
    })
  );
}

// Fetch: static assets cache-first; HTML pages network-first with cache population
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Only handle same-origin requests
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith('/static/')) {
    // Cache-first for static assets
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request))
    );
    return;
  }

  // Network-first for HTML pages — cache successful responses, fall back to cache
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          if (res.ok) {
            caches.open(PAGES_CACHE).then((cache) => cache.put(event.request, res.clone()));
          }
          return res;
        })
        .catch(() =>
          caches.match(event.request).then(
            (cached) => cached || caches.match('/offline')
          )
        )
    );
  }
});
```

- [ ] **Step 1: Replace the service worker file** with the content above.

- [ ] **Step 2: Verify the full test suite still passes** (the SW is pure JS — no Python tests — but we confirm nothing broke)

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add runcoach/web/static/service-worker.js
git commit -m "feat: offline caching — cache pages on visit, prefetch 10 most recent runs

Closes #16"
```

---

### Task 5: E2E smoke test

**Files:**
- Modify: `tests/e2e/test_offline.py` (create)

The offline behaviour is hard to test end-to-end in CI (no real browser going offline), so this task adds a lightweight Playwright test that verifies the service worker registers successfully and the `/offline` page is reachable.

- [ ] **Step 1: Create `tests/e2e/test_offline.py`**

```python
import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e


def test_offline_page_reachable(page: Page, live_server_url: str):
    """The /offline page loads without auth and contains expected text."""
    page.goto(f"{live_server_url}/offline")
    assert "offline" in page.title().lower() or "offline" in page.content().lower()


def test_service_worker_registers(page: Page, live_server_url: str, seeded_run_id: int):
    """After loading the app, the service worker is registered."""
    # Log in via the login page
    page.goto(f"{live_server_url}/login")
    page.fill('input[name="email"]', "test@example.com")
    page.fill('input[name="password"]', "testpassword")
    page.click('button[type="submit"]')
    page.wait_for_url(f"{live_server_url}/")

    # Check SW is registered
    sw_registered = page.evaluate(
        """async () => {
            if (!('serviceWorker' in navigator)) return false;
            const reg = await navigator.serviceWorker.getRegistration('/');
            return !!reg;
        }"""
    )
    assert sw_registered
```

- [ ] **Step 2: Run the E2E tests**

```bash
pytest -m e2e --no-cov -v tests/e2e/test_offline.py
```

Expected: both tests pass.

- [ ] **Step 3: Run the full E2E suite to check for regressions**

```bash
pytest -m e2e --no-cov -v
```

Expected: all E2E tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_offline.py
git commit -m "test(e2e): smoke tests for offline page and service worker registration"
```

---

## Self-Review

**Spec coverage:**
- ✅ Cache visited run pages — network-first fetch handler stores successful responses in `runcoach-pages-v2`
- ✅ Proactively cache most recent 10 runs — `prefetchRecentRuns()` called on activate
- ✅ Homepage cached — `/` included in prefetch URL list
- ✅ `/recent-run-ids` session-authenticated route — Task 3
- ✅ `/offline` route, no auth required — Task 2
- ✅ `offline.html` standalone, no external deps — Task 2
- ✅ Cache names bumped to `-v2` — old entries evicted on activate
- ✅ Unit tests for both new routes — Task 1
- ✅ E2E smoke tests — Task 5
- ✅ No Flutter/mobile changes
- ✅ No DB schema changes

**Placeholder scan:** None found.

**Type consistency:** `get_runs_paginated(limit=10, offset=0, user_id=...)` used in Task 3 matches the actual signature in `db.py:712`. `_db()`, `_login_required`, `_current_user_id()`, `jsonify` all already imported in `routes.py`.
