// O rosto 3D de verdade num navegador (Chromium com WebGL por software): o modelo e as texturas carregam, os olhos
// têm a íris azul-lilás e ela some ao piscar, a boca abre ao falar, a cabeça vira, nada dá erro; e, sem WebGL,
// entra o rosto de reserva.
// Uso: node tests/checar_rosto_3d.mjs      (precisa do pacote playwright; no CI: npm install playwright)
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const { chromium } = await import(process.env.PLAYWRIGHT || "playwright");
const TIPOS = { ".js": "text/javascript", ".glb": "model/gltf-binary", ".webp": "image/webp", ".html": "text/html" };
const PAGINA = `<!doctype html><body style="margin:0;background:#1c1328">
<canvas id="rosto" data-transparente="1" style="width:232px;height:352px;display:block"></canvas>
<script src="/static/rosto.js"></script></body>`;

const srv = http.createServer((q, r) => {
  const u = decodeURIComponent(q.url.split("?")[0]);
  if (u === "/") { r.writeHead(200, { "content-type": "text/html" }); r.end(PAGINA); return; }
  const f = path.join(RAIZ, "web", u.replace(/^\/static\//, ""));
  fs.readFile(f, (e, d) => {
    if (e) { r.writeHead(404); r.end(); return; }
    r.writeHead(200, { "content-type": TIPOS[path.extname(f)] || "application/octet-stream" }); r.end(d);
  });
});
await new Promise((ok) => srv.listen(0, "127.0.0.1", ok));
const URL = `http://127.0.0.1:${srv.address().port}/`;
const nav = await chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"] });
let falhas = 0;
const ok = (cond, msg) => { console.log(`${cond ? "ok   " : "FALHA"} ${msg}`); if (!cond) falhas++; };

// ---- com WebGL
{
  const p = await nav.newPage({ viewport: { width: 232, height: 352 } });
  const erros = [];
  p.on("pageerror", (e) => erros.push(String(e)));
  p.on("console", (m) => {
    if ((m.type() === "error" || m.type() === "warning") && !/willReadFrequently/.test(m.text())) erros.push(m.text());
  });
  await p.goto(URL);
  await p.waitForFunction(() => window.Rosto && Rosto.estado.malha, null, { timeout: 30000 }).catch(() => {});
  const malha = await p.evaluate(() => Rosto.estado.malha);
  ok(malha && malha.triangulos > 10000, `modelo carregado (${malha && malha.triangulos} triângulos)`);
  const contar = (forcar, modo = "ocioso") => p.evaluate(async ([f, m]) => {
    Rosto.modo(m); Rosto.emocao("neutra"); Rosto.forcar(Object.assign({ quieto: true, quadro: [0, 0.69, 0.3] }, f));
    // (a íris é contada numa faixa em volta dos olhos: os cristais também são lilases)
    await new Promise((r) => setTimeout(r, 700));
    const c = document.getElementById("rosto");
    const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
    let iris = 0, boca = 0, pintados = 0, claro = 0, soma = 0;
    for (let i = 0; i < d.length; i += 4) {
      const [r, g, b, a] = [d[i], d[i + 1], d[i + 2], d[i + 3]];
      const px = (i / 4) % c.width, py = Math.floor(i / 4 / c.width);
      const miolo = px > c.width * 0.12 && px < c.width * 0.88 && py > c.height * 0.12 && py < c.height * 0.88;
      const faixaOlhos = miolo && Math.abs(py - c.height / 2) < c.height * 0.12;
      if (a < 230) continue;                                                  // só o que é opaco (não o brilho em volta)
      pintados++;
      if (faixaOlhos && b > 170 && b - r > 35 && b - g > 30) iris++;         // o azul-lilás da íris
      if (r > 30 && r < 150 && g < 55 && b < 75 && r > b + 4) boca++;         // o escuro da boca por dentro
      const lum = (r + g + b) / 3;
      if (r > 150 && g > 120 && b > 150) claro++;                            // a pele e o cabelo claros
      soma += lum;
    }
    return { iris, boca, pintados, claro, total: d.length / 4 };
  }, [forcar, modo]);
  const OLHOS = [0, 0.718, 0.25];                         // os dois olhos no meio do quadro
  const aberto = await contar({ piscar: 0, boca: 0, olhar: [0, 0] });
  const olhosAbertos = await contar({ piscar: 0, boca: 0, olhar: [0, 0], quadro: OLHOS });
  ok(aberto.pintados > aberto.total * 0.55, `a moldura e ela aparecem (${aberto.pintados} de ${aberto.total} pixels)`);
  ok(olhosAbertos.iris > 120, `olhos abertos: íris azul (${olhosAbertos.iris} pixels)`);
  const fechado = await contar({ piscar: 1, boca: 0, olhar: [0, 0], quadro: OLHOS });
  ok(fechado.iris < olhosAbertos.iris * 0.15, `piscando: a íris some (${olhosAbertos.iris} → ${fechado.iris} pixels)`);
  const falando = await contar({ piscar: 0, boca: 1, olhar: [0, 0] }, "falando");
  ok(falando.boca > aberto.boca + 25, `falando: a boca abre (${aberto.boca} → ${falando.boca} pixels escuros)`);
  ok(aberto.claro > aberto.total * 0.25, `a pele e o cabelo claros dela aparecem (${aberto.claro} pixels)`);
  const virada = await contar({ piscar: 0, boca: 0, olhar: [0, 0], cabeca: { yaw: 0.35, pitch: 0, roll: 0 } });
  ok(virada.iris > 30 && Math.abs(virada.claro - aberto.claro) < aberto.claro * 0.35,
     `a cabeça vira e ela continua inteira (íris ${virada.iris}, claros ${virada.claro})`);
  ok(!erros.length, `sem erros no navegador ${erros.length ? JSON.stringify(erros.slice(0, 3)) : ""}`);
  await p.close();
}

// ---- sem WebGL: o rosto de reserva (a ilustração animada)
{
  const p = await nav.newPage({ viewport: { width: 232, height: 352 } });
  await p.addInitScript(() => {
    const orig = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (t, o) { return /webgl/.test(t) ? null : orig.call(this, t, o); };
  });
  const pedidos = [];
  p.on("request", (r) => pedidos.push(r.url()));
  await p.goto(URL);
  await p.waitForTimeout(1500);
  ok(pedidos.some((u) => u.endsWith("/rosto2d.js")) && pedidos.some((u) => u.endsWith("/ametista-retrato.webp")),
     "sem WebGL: carrega o rosto de reserva e a ilustração");
  ok(!pedidos.some((u) => u.endsWith(".glb")), "sem WebGL: nem baixa o modelo 3D");
  const modo = await p.evaluate(() => { Rosto.modo("falando"); return Rosto.estado.modo; });
  ok(modo === "falando", "o rosto de reserva responde");
  await p.close();
}

await nav.close();
srv.close();
if (falhas) { console.log(`FALHOU: ${falhas} verificação(ões)`); process.exit(1); }
console.log("OK: rosto 3D funcionando no navegador");
