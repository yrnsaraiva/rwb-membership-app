/* Service worker do RWB — PWA instalável (RNF-09) e resiliente a redes móveis instáveis. */
const VERSION = "rwb-{{ version }}";
const STATIC_CACHE = VERSION + "-static";
const PAGE_CACHE = VERSION + "-pages";
const OFFLINE_URL = "/offline/";
const PRECACHE = [OFFLINE_URL, "{{ css_url }}", "{{ js_url }}", "{{ pwa_url }}", "{{ icon_url }}", "{{ components_url }}"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(STATIC_CACHE).then((cache) => Promise.all(PRECACHE.map((u) => cache.add(u).catch(() => null)))).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // Estáticos (mesma origem ou fontes): cache-first
  if (url.pathname.startsWith("/static/") || url.hostname.includes("fonts.g")) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok || res.type === "opaque") {
          const copy = res.clone();
          caches.open(STATIC_CACHE).then((c) => c.put(req, copy));
        }
        return res;
      }))
    );
    return;
  }

  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/painel/") || url.pathname.startsWith("/django-admin/")) return;

  // Páginas: network-first, com cópia em cache para leitura offline (ex.: cartão de membro)
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok && ["/conta/cartao/", "/atividade/", "/eventos/"].includes(url.pathname)) {
            const copy = res.clone();
            caches.open(PAGE_CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req).then((hit) => hit || caches.match(OFFLINE_URL)))
    );
  }
});
