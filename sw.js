/* seb-metrics — service worker
   Stratégie : network-first pour la page (données fraîches), fallback cache
   hors-ligne ; stale-while-revalidate pour les assets (fonts, icônes).

   La version du cache est bumpée à chaque changement du plan pour forcer
   Safari iOS à jeter la version précédente : le network-first ne suffit pas
   quand l'iPhone est en tunnel/lockscreen et sert son cache indéfiniment. */
const CACHE = 'seb-metrics-v3-2026-08-23';

self.addEventListener('install', (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(['./'])));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);

  // Page principale : réseau d'abord, cache en secours (mode avion, tunnel…)
  if (e.request.mode === 'navigate' || url.pathname.endsWith('/index.html')) {
    e.respondWith(
      fetch(e.request)
        .then((r) => {
          const copy = r.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
          return r;
        })
        .catch(() => caches.match(e.request).then((m) => m || caches.match('./')))
    );
    return;
  }

  // Assets : cache d'abord, refresh en arrière-plan
  e.respondWith(
    caches.match(e.request).then((m) => {
      const refresh = fetch(e.request)
        .then((r) => {
          if (r.ok) {
            const copy = r.clone();
            caches.open(CACHE).then((c) => c.put(e.request, copy));
          }
          return r;
        })
        .catch(() => m);
      return m || refresh;
    })
  );
});
