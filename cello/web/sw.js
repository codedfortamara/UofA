// Offline support. The whole app is static, so a cache first strategy for the
// shell is both simple and correct: a tuner must work in a practice room with
// no signal. The version string is bumped by the build, which is what causes
// old caches to be dropped.

const VERSION = 'claudecello-v1';
const ASSETS = [
  './',
  'index.html',
  'app.css',
  'curriculum.json',
  'manifest.webmanifest',
  'js/app.js',
  'js/audio.js',
  'js/pitch.js',
  'js/music.js',
  'js/analysis.js',
  'js/tuner.js',
  'js/lessons.js',
  'js/tone.js',
  'js/store.js',
  'worklet/capture.js',
  'icons/icon.svg',
  'icons/icon-192.png',
  'icons/icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(VERSION).then((c) =>
      // addAll fails the whole install if any single asset 404s, so add them
      // individually and tolerate a miss. An app that refuses to install
      // because an icon moved is worse than one missing an icon.
      Promise.all(ASSETS.map((a) => c.add(new Request(a, { cache: 'reload' })).catch(() => null)))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  e.respondWith(
    caches.match(req, { ignoreSearch: true }).then((hit) => {
      if (hit) {
        // Refresh in the background so an update lands on the next visit.
        e.waitUntil(
          fetch(req).then((res) => {
            if (res && res.ok) return caches.open(VERSION).then((c) => c.put(req, res.clone()));
          }).catch(() => null)
        );
        return hit;
      }
      return fetch(req)
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            e.waitUntil(caches.open(VERSION).then((c) => c.put(req, copy)));
          }
          return res;
        })
        .catch(() => caches.match('index.html'));
    })
  );
});
