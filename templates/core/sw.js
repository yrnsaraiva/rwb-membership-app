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

  // Páginas: network-first com limite de espera. Em redes móveis fracas, se a rede demora mais de NETWORK_TIMEOUT_MS
  // e há cópia guardada, mostra-a; sem rede, mostra a cópia ou a página «Sem ligação».
  if (req.mode === "navigate") {
    event.respondWith(networkFirst(req, url));
  }
});

const NETWORK_TIMEOUT_MS = 4000;
const MAX_CACHED_PAGES = 40;
// Páginas de leitura úteis offline (o cartão de membro é a principal). Formulários, login e painel ficam de fora.
const CACHEABLE = [/^\/atividade\/$/, /^\/atividade\/(corridas|pontos)\/$/, /^\/eventos\/$/, /^\/eventos\/[\w-]+\/$/,
  /^\/ranking\/$/, /^\/conta\/(cartao|perfil)\/$/, /^\/loja\/$/, /^\/loja\/[\w-]+\/$/, /^\/premium\/$/];
const NOT_CACHEABLE = [/^\/loja\/(carrinho|checkout|encomendas)\//, /^\/eventos\/(novo|inscricoes)\//];
const isCacheable = (url) => CACHEABLE.some((r) => r.test(url.pathname)) && !NOT_CACHEABLE.some((r) => r.test(url.pathname));

async function remember(req, res) {
  const cache = await caches.open(PAGE_CACHE);
  await cache.put(req, res);
  const keys = await cache.keys();
  for (const k of keys.slice(0, Math.max(0, keys.length - MAX_CACHED_PAGES))) await cache.delete(k);  // descarta as mais antigas
}

// Marca as respostas vindas da cache (Server-Timing) para a página poder avisar o membro
function fromCache(res) {
  const headers = new Headers(res.headers);
  headers.append("Server-Timing", "rwb-cache");
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
}

async function networkFirst(req, url) {
  const cached = await caches.match(req, { cacheName: PAGE_CACHE });
  const network = fetch(req).then((res) => {
    // Só guarda respostas normais (não redirecções, ex.: para o login quando a sessão expirou)
    if (res.ok && !res.redirected && isCacheable(url)) remember(req, res.clone());
    return res;
  });
  try {
    if (!cached) return await network;
    return await Promise.race([network, new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), NETWORK_TIMEOUT_MS))]);
  } catch (e) {
    return cached ? fromCache(cached) : (await caches.match(OFFLINE_URL)) || Response.error();
  }
}

// --- Notificações push --------------------------------------------------------------------
self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { body: event.data ? event.data.text() : "" }; }
  event.waitUntil(self.registration.showNotification(data.title || "RunWithBroto", {
    body: data.body || "",
    icon: "{{ icon_url }}",
    badge: "{{ badge_url }}",
    tag: data.tag || undefined,
    data: { url: data.url || "/" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  let target = new URL("/", self.location.origin);
  try {
    const u = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin);
    if (u.origin === self.location.origin) target = u;  // nunca navega para fora do site
  } catch (e) {}
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      const open = list[0];
      if (open && "focus" in open) {
        return open.focus().then(() => ("navigate" in open ? open.navigate(target.href) : null)).catch(() => self.clients.openWindow(target.href));
      }
      return self.clients.openWindow(target.href);
    })
  );
});
