// Guarda a "casca" do app para abrir rápido (os dados sempre vêm ao vivo) e mostra os avisos
// que chegam por push, mesmo com o app fechado.
const CACHE = "ametista-v2";
const CASCA = ["/", "/index.html", "/estilo.css", "/app.js", "/rosto.js", "/manifest.webmanifest", "/icone-192.png"];
self.addEventListener("install", (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(CASCA))); self.skipWaiting(); });
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/") || e.request.method !== "GET") return;
  // rede primeiro (para pegar atualizações), cache se estiver sem internet
  e.respondWith(fetch(e.request).then((r) => {
    const copia = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copia)); return r;
  }).catch(() => caches.match(e.request)));
});

// ------------------------------------------------------------------ push
self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = { texto: e.data ? e.data.text() : "" }; }
  e.waitUntil((async () => {
    const janelas = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    if (janelas.some((c) => c.visibilityState === "visible")) return;   // o app aberto já mostra o aviso
    await self.registration.showNotification(d.titulo || "Ametista", {
      body: d.texto || "", icon: "/icone-192.png", badge: "/icone-192.png",
      tag: "ametista-" + (d.quando || Date.now()), data: { url: "/" }, vibrate: [120, 60, 120],
    });
  })());
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil((async () => {
    const janelas = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of janelas) if ("focus" in c) return c.focus();
    return self.clients.openWindow((e.notification.data && e.notification.data.url) || "/");
  })());
});
