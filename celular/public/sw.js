// Guarda a "casca" do app para abrir rápido (os dados sempre vêm ao vivo).
const CACHE = "ametista-v1";
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
