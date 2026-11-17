/* Propali Kladioničari – service worker.
   Pages always come from the network (they are login-gated and dynamic), so users
   never see stale data. Only static files are cached; offline shows a friendly page. */
const VERSION = 'klada-v2';
const PRECACHE = [
  '/static/offline.html',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(VERSION).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;                       // never touch form posts
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;        // CDN libs etc. go straight to the network

  // Page navigations: network first, offline page as fallback
  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(() => caches.match('/static/offline.html')));
    return;
  }

  // Static files: stale-while-revalidate
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.open(VERSION).then(cache =>
        cache.match(req).then(hit => {
          const net = fetch(req).then(res => {
            if (res && res.ok) cache.put(req, res.clone());
            return res;
          }).catch(() => hit);
          return hit || net;
        })
      )
    );
  }
  // everything else (/chart-data, /api/*, ...) is network only
});

/* ── Web Push ─────────────────────────────────────────────────────────── */
self.addEventListener('push', event => {
  let d = {};
  try { d = event.data ? event.data.json() : {}; }
  catch (e) { d = { body: event.data ? event.data.text() : '' }; }
  event.waitUntil(self.registration.showNotification(d.title || 'Kladionica', {
    body: d.body || '',
    icon: '/static/icons/icon-192.png',
    tag: d.tag || undefined,          // same tag = replaces the older notification instead of stacking
    renotify: !!d.tag,
    data: { url: d.url || '/' }
  }));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const target = new URL((event.notification.data && event.notification.data.url) || '/', self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      for (const c of list) {
        if (new URL(c.url).origin === self.location.origin && 'focus' in c) {
          return c.focus().then(w => (w && 'navigate' in w) ? w.navigate(target) : null);
        }
      }
      return self.clients.openWindow(target);
    })
  );
});
