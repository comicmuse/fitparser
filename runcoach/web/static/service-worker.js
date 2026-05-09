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
