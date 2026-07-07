// Service worker de Transport BCN: cachea la carcasa de la app para que
// arranque al instante y funcione la interfaz sin red. Los datos en tiempo
// real (TMB, TRAM, Overpass) y los tiles del mapa NUNCA se cachean.
const CACHE = 'transport-bcn-v4';
const SHELL = ['./', './index.html', './icon.svg', './manifest.webmanifest', './assets/logo_donut.png'];

self.addEventListener('install', e => {
    e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).catch(() => {}));
    self.skipWaiting();
});

self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', e => {
    const url = new URL(e.request.url);

    // Navegación: red primero (para recibir actualizaciones), caché de respaldo
    if (e.request.mode === 'navigate') {
        e.respondWith(
            fetch(e.request).then(res => {
                const copy = res.clone();
                caches.open(CACHE).then(c => c.put('./index.html', copy));
                return res;
            }).catch(() => caches.match('./index.html'))
        );
        return;
    }

    // Recursos propios y librerías CDN: caché primero (son versionados/estables)
    const isShellAsset = url.origin === location.origin || url.hostname === 'unpkg.com' || url.hostname === 'cdn-icons-png.flaticon.com';
    if (isShellAsset && e.request.method === 'GET') {
        e.respondWith(
            caches.match(e.request).then(hit => hit || fetch(e.request).then(res => {
                if (res.ok || res.type === 'opaque') {
                    const copy = res.clone();
                    caches.open(CACHE).then(c => c.put(e.request, copy));
                }
                return res;
            }))
        );
    }
    // Todo lo demás (APIs, tiles) va directo a red
});
