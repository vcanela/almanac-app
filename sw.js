// Almanac service worker: keeps the app usable offline.
// Strategy: stale-while-revalidate. Answer from the cache at once, then refresh
// the cache from the network in the background, so a deploy shows up on the
// second launch after it goes live.

const CACHE = 'almanac-v1';
const SHELL = [
  './',
  'index.html',
  'manifest.webmanifest',
  'icons/icon-192.png',
  'icons/icon-512.png',
  'icons/apple-touch-icon.png',
  'decks/index.json',
];

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await cache.addAll(SHELL);
    // Cache every deck listed, so the first offline launch has them all.
    try {
      const ids = await (await fetch('decks/index.json')).json();
      await cache.addAll(ids.map(id => `decks/${id}.json`));
    } catch { /* they will be cached on first use instead */ }
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key !== CACHE) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  const ours = url.origin === location.origin;
  const fonts = url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com';
  if (!ours && !fonts) return;

  const fresh = fetch(req).then(res => {
    if (res.ok || res.type === 'opaque') {
      const copy = res.clone();
      caches.open(CACHE).then(cache => cache.put(req, copy));
    }
    return res;
  }).catch(() => null);

  event.waitUntil(fresh);
  event.respondWith(
    caches.match(req, { ignoreSearch: ours })
      .then(hit => hit || fresh.then(res => res || Response.error()))
  );
});
