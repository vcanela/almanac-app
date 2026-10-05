// Almanac service worker: keeps the app usable offline without holding back updates.
//
// The app's own files (page, decks, icons) are network first: ask GitHub,
// and fall back to the stored copy only when offline or after a few seconds
// of poor signal. `cache: 'no-cache'` makes the phone check with GitHub
// rather than reuse its 10-minute HTTP copy, so a deploy appears on the next
// launch. Google Fonts never change, so they are cache first.

const CACHE = 'almanac-v1';
const NETWORK_TIMEOUT = 4000; // ms before giving up and using the stored copy
const SHELL = [
  './',
  'index.html',
  'manifest.webmanifest',
  'icons/icon-192.png',
  'icons/icon-512.png',
  'icons/apple-touch-icon.png',
  'decks/index.json',
];

// `reload` skips the HTTP cache, so installing never stores a stale copy.
const fresh = url => new Request(url, { cache: 'reload' });

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await cache.addAll(SHELL.map(fresh));
    // Cache every deck listed, so the first offline launch has them all.
    try {
      const ids = await (await fetch(fresh('decks/index.json'))).json();
      await cache.addAll(ids.map(id => fresh(`decks/${id}.json`)));
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
  if (url.origin === location.origin) {
    networkFirst(event, req);
  } else if (url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') {
    event.respondWith(cacheFirst(req));
  }
});

function networkFirst(event, req) {
  const network = fetch(req, { cache: 'no-cache' }).then(res => {
    if (res.ok) {
      const copy = res.clone();
      caches.open(CACHE).then(cache => cache.put(req, copy));
    }
    return res;
  });
  // Keep the worker alive so a slow response still refreshes the cache.
  event.waitUntil(network.catch(() => {}));

  const timeout = new Promise((_, reject) => setTimeout(reject, NETWORK_TIMEOUT));
  event.respondWith(
    Promise.race([network, timeout]).catch(async () => {
      const hit = await caches.match(req, { ignoreSearch: true });
      return hit || network.catch(() => Response.error());
    })
  );
}

async function cacheFirst(req) {
  const hit = await caches.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok || res.type === 'opaque') {
    const copy = res.clone();
    caches.open(CACHE).then(cache => cache.put(req, copy));
  }
  return res;
}
