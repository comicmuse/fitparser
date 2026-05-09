# Offline Support — PWA Service Worker Design

## Goal

Make the RunCoach Android PWA usable without a network connection. The 10 most recent run detail pages are proactively cached at service worker activation time; any page the user navigates to while online is also cached automatically. An offline fallback page covers uncached URLs.

## Context

- The existing service worker (`runcoach/web/static/service-worker.js`) already:
  - Pre-caches static assets at install
  - Serves static assets cache-first
  - Uses network-first for all HTML pages, but **never stores** successful responses — so the cache fallback path is always empty
- The mobile Flutter app uses JWT auth; the web app uses Flask session cookies. The `/api/v1/runs` endpoint requires JWT, so a new session-cookie-authenticated route is needed for the SW to discover recent run IDs.
- No backend data model changes are needed.

## Design

### New Flask route: `GET /recent-run-ids`

- Registered on the main web blueprint (not the API blueprint)
- Protected by `@_login_required` — returns `401` redirect for unauthenticated requests (SW silently ignores non-200 responses)
- Returns JSON: `{"ids": [42, 41, 40, ...]}`  — the 10 most recent run IDs for the logged-in user, newest first
- Uses existing `db.get_runs_paginated(limit=10, offset=0, user_id=...)` and extracts only the `id` field

### Service worker changes

**Cache names** (both bumped to `-v2` to force eviction of old entries on update):
- `runcoach-static-v2` — pre-cached static assets + offline fallback page
- `runcoach-pages-v2` — HTML page responses, populated dynamically

**Static assets pre-cached at install** (added):
- `/offline` — the offline fallback page

**Fetch handler — HTML pages** (network-first, now with cache population):

```
on fetch (non-static navigation):
  try:
    response = await fetch(request)
    if response.ok:
      cache.put(request, response.clone())   // store for offline use
    return response
  catch NetworkError:
    cached = await cache.match(request)
    return cached ?? cache.match('/offline')
```

**Proactive prefetch on activate:**

```
on activate:
  delete stale caches (existing logic)
  clients.claim()
  try:
    res = await fetch('/recent-run-ids', { credentials: 'include' })
    if res.ok:
      { ids } = await res.json()
      open pages cache
      for each id: fetch('/run/<id>') and cache it
      also fetch('/') and cache it
  catch: silently ignore (user not logged in, or network unavailable)
```

The prefetch is best-effort — failures are caught and swallowed. It runs after `clients.claim()` so the page is not held up.

### New Flask route: `GET /offline`

- No auth required — must be accessible without a session
- Returns a minimal standalone HTML page (no base template dependency) with:
  - Inline CSS matching the app's dark theme (`#0d1117` background, white text)
  - "You're offline" heading and brief message
  - No JS, no external resources — fully self-contained so it renders from cache with zero network requests

### Template

- `runcoach/web/templates/offline.html` — standalone (no `{% extends %}`)

## Files Changed

- **Modify**: `runcoach/web/static/service-worker.js` — bump cache names, add page caching, add prefetch on activate
- **Modify**: `runcoach/web/routes.py` — add `/recent-run-ids` and `/offline` routes
- **Add**: `runcoach/web/templates/offline.html` — offline fallback page

## What Does Not Change

- Flutter mobile app — untouched
- Database schema — untouched
- API blueprint (`api.py`) — untouched
- Existing static assets — untouched
- Auth flow — untouched

## Testing

- Unit test: `GET /recent-run-ids` returns correct IDs for authenticated user; returns 302 for unauthenticated
- Unit test: `GET /offline` returns 200 with offline page content for any user (no auth required)
- Manual: install PWA on Android, visit several run pages, go offline, verify those pages load; verify homepage loads; verify `/offline` page appears for unvisited URLs
