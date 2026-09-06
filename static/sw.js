const CACHE_NAME = 'training-diary-v3';
const STATIC_ASSETS = [
    '/static/index.html',
    'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS).catch(() => {}))
    );
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        ).then(() => clients.claim())
    );
});

// Network first для API, cache first для статики
self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);

    // API запросы — только сеть
    if (url.pathname === '/days' || url.pathname.startsWith('/days/') ||
        url.pathname.startsWith('/day/') || url.pathname.startsWith('/log') ||
        url.pathname.startsWith('/progress') || url.pathname.startsWith('/stats') ||
        url.pathname.startsWith('/ai-') || url.pathname.startsWith('/recovery') ||
        url.pathname.startsWith('/check') || url.pathname.startsWith('/last-weight') ||
        url.pathname.startsWith('/exercise') || url.pathname.startsWith('/workout') ||
        url.pathname.startsWith('/compare') || url.pathname.startsWith('/export') ||
        url.pathname.startsWith('/login') || url.pathname.startsWith('/logout')) {
        return; // Не перехватываем API
    }

    // Статика — cache first
    event.respondWith(
        caches.match(event.request).then(cached => {
            if (cached) return cached;
            return fetch(event.request).then(resp => {
                if (resp.ok) {
                    const clone = resp.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
                }
                return resp;
            }).catch(() => {
                // Офлайн — возвращаем кэшированный index.html
                if (event.request.mode === 'navigate') {
                    return caches.match('/static/index.html');
                }
            });
        })
    );
});
