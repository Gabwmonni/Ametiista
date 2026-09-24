// Guarda a "casca" do app para abrir na hora (os dados sempre vêm ao vivo) e mostra os avisos
// que chegam por push, mesmo com o app fechado.
// A "casca" (os arquivos do app) é guardada inteira, com um nome que é a impressão digital do conteúdo:
// o publicar_celular.bat recalcula ao publicar. Versão nova = service worker novo = casca nova de uma vez
// (nunca mistura arquivo velho com novo). O app abre na hora, sem esperar a rede.
const CACHE = "ametista-casca-8f29abe279";
const CASCA = ["/", "/estilo.css", "/app.js", "/rosto.js", "/manifest.webmanifest", "/icone-192.png"];
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(CASCA.map((u) => new Request(u, { cache: "reload" })))));
  self.skipWaiting();
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.origin !== location.origin || url.pathname.startsWith("/api/") || e.request.method !== "GET") return;
  e.respondWith(caches.open(CACHE).then(async (c) => {
    const alvo = e.request.mode === "navigate" ? "/" : e.request;   // /?acao=tela abre a mesma casca
    return (await c.match(alvo, { ignoreSearch: true })) || fetch(e.request);
  }));
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
