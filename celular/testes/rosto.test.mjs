// Rosto 3D: roda o motor de verdade (leitura do .glb, shape keys, animação) num WebGL e num canvas falsos,
// com o modelo de verdade (web/ametista.glb). O desenho em si é conferido no navegador pelo CI (checar_rosto_3d).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const GLB = readFileSync(new URL("../../web/ametista.glb", import.meta.url));

function carregarRosto({ semWebGL = false, modeloFalta = false } = {}) {
  const nada = () => {};
  const ctx2d = new Proxy({}, { get: (_, k) => (typeof k === "string" && k.endsWith("Gradient"))
    ? () => ({ addColorStop: nada }) : nada, set: () => true });
  const gl = { chamadas: { subData: 0, draw: 0 } };
  const glProxy = new Proxy(gl, {
    get(alvo, k) {
      if (k in alvo) return alvo[k];
      if (k === "getShaderParameter" || k === "getProgramParameter") return (_, p) => (p === "ACTIVE_UNIFORMS" ? 0 : true);
      if (k === "bufferSubData") return () => { gl.chamadas.subData++; };
      if (k === "drawElements" || k === "drawArrays") return () => { gl.chamadas.draw++; };
      if (typeof k === "string" && /^[A-Z_0-9]+$/.test(k)) return k;       // constantes
      if (k === "getExtension") return () => ({});
      return () => ({});
    },
  });
  const scripts = [];
  const novoCanvas = () => ({ dataset: {}, width: 0, height: 0, clientWidth: 0, clientHeight: 0,
    getContext: (t) => (t === "2d" ? ctx2d : semWebGL ? null : glProxy), addEventListener: nada });
  const canvas = { ...novoCanvas(), dataset: { transparente: "1" }, clientWidth: 116, clientHeight: 176 };
  const quadros = [];
  let agora = 0;
  const janela = {
    document: {
      getElementById: () => canvas, createElement: (t) => (t === "script" ? { tipo: t } : novoCanvas()),
      addEventListener: nada, hidden: false, currentScript: { src: "http://pc/static/rosto.js" },
      head: { appendChild: (s) => scripts.push(s) },
    },
    addEventListener: (tipo, f) => { if (tipo === "resize") janela.redimensionou = f; },
    devicePixelRatio: 1, innerWidth: 116, innerHeight: 176,
    performance: { now: () => agora },
    requestAnimationFrame: (f) => (quadros.push(f), quadros.length),
    cancelAnimationFrame: nada,
    setTimeout: (f) => (quadros.push(() => f()), 1), clearTimeout: nada, Math, console: { warn: nada, log: nada },
    TextDecoder, DataView, Float32Array, Uint8Array, Uint16Array, Uint32Array, Int8Array, Int16Array, JSON,
    fetch: async (url) => {
      janela.pediu = url;
      if (modeloFalta) return { ok: false, status: 404 };
      return { ok: true, arrayBuffer: async () => GLB.buffer.slice(GLB.byteOffset, GLB.byteOffset + GLB.byteLength) };
    },
  };
  janela.window = janela;
  vm.runInNewContext(readFileSync(new URL("../../web/rosto.js", import.meta.url), "utf8"), janela);
  const rodar = (segundos) => {                        // avança o relógio e roda os quadros agendados
    for (let i = 0; i < segundos * 60; i++) {
      agora += 1000 / 60;
      const f = quadros.shift();
      if (f) f(agora);
    }
  };
  const esperarModelo = async () => { for (let i = 0; i < 50 && !janela.Rosto.estado.malha && !scripts.length; i++) await new Promise((r) => setTimeout(r, 5)); };
  return { Rosto: janela.Rosto, rodar, janela, canvas, gl, scripts, esperarModelo, pendentes: () => quadros.length };
}

const LILAS = [203, 178, 248];
const perto = (cor, alvo) => cor.every((v, i) => Math.abs(v - alvo[i]) < 6);

test("lê o modelo de verdade: malha, cabeça e todas as expressões", async () => {
  const { Rosto, esperarModelo, janela, scripts } = carregarRosto();
  await esperarModelo();
  assert.equal(janela.pediu, "http://pc/static/ametista.glb", "o modelo vem da mesma pasta do rosto.js");
  assert.equal(scripts.length, 0, "não precisou do rosto de reserva");
  const m = Rosto.estado.malha;
  assert.ok(m && m.triangulos > 10000 && m.triangulos < 40000, `triângulos: ${m && m.triangulos}`);
  assert.ok(m.cabeca, "tem o nó Cabeca (o pescoço)");
  for (const nome of ["piscar_direito", "piscar_esquerdo", "olhos_felizes", "arregalar", "olhar_esquerda",
    "olhar_direita", "olhar_cima", "olhar_baixo", "boca_a", "boca_e", "boca_i", "boca_o", "boca_u", "sorriso",
    "triste", "bravo", "sobrancelhas_cima", "sobrancelhas_bravas", "sobrancelhas_tristes", "sobrancelha_pensativa"])
    assert.ok(m.expressoes.includes(nome), `falta a shape key ${nome}`);
});

test("pisca, fala e sorri mexendo as shape keys (só recalcula o que muda)", async () => {
  const { Rosto, rodar, esperarModelo, gl } = carregarRosto();
  await esperarModelo();
  Rosto.modo("ocioso");
  rodar(2);
  assert.ok(Rosto.estado.fechar < 0.05, "acordada: olhos abertos");
  const antes = gl.chamadas.subData;
  Rosto.forcar({ piscar: 1 });
  rodar(0.2);
  assert.ok(Rosto.estado.pesos.piscar_direito > 0.99 && Rosto.estado.pesos.piscar_esquerdo > 0.99);
  assert.ok(gl.chamadas.subData > antes, "os olhos foram recalculados");
  Rosto.forcar(null);
  Rosto.modo("falando"); Rosto.voz(0.8);
  rodar(1);
  const bocas = ["boca_a", "boca_e", "boca_i", "boca_o", "boca_u"].map((n) => Rosto.estado.pesos[n] || 0);
  const soma = bocas.reduce((a, b) => a + b, 0);                 // (na troca de vogal, a abertura se divide)
  assert.ok(Rosto.estado.boca > 0.6 && soma > 0.6, `falando: a boca abre (${Rosto.estado.boca}; ${bocas})`);
  Rosto.voz(0); Rosto.modo("ocioso"); Rosto.emocao("feliz");
  rodar(2);
  assert.ok(Rosto.estado.pesos.sorriso > 0.7 && Rosto.estado.pesos.blush > 0.7, "feliz: sorri e cora");
  // parada, sem nada mudando: nada é enviado de novo para a placa
  Rosto.forcar({ piscar: 0, boca: 0, sorriso: 0.5, olhar: [0, 0] });
  rodar(0.5);
  const parado = gl.chamadas.subData;
  rodar(1);
  assert.equal(gl.chamadas.subData, parado, "nada muda, nada é recalculado");
  assert.ok(gl.chamadas.draw > 100, "desenhou");
});

test("o brilho volta ao lilás depois de alerta e de ouvir, e a cor volta depois de ficar sem internet", async () => {
  const { Rosto, rodar, esperarModelo } = carregarRosto();
  await esperarModelo();
  Rosto.modo("ocioso");
  rodar(2);
  assert.ok(perto(Rosto.estado.brilho, LILAS), "começa lilás");
  for (const estado of ["alerta", "ouvindo"]) {
    Rosto.modo(estado);
    rodar(3);
    assert.ok(!perto(Rosto.estado.brilho, LILAS), `${estado} muda o brilho`);
    Rosto.modo("ocioso");
    rodar(3);
    assert.ok(perto(Rosto.estado.brilho, LILAS), `depois de ${estado} volta ao lilás: ${Rosto.estado.brilho}`);
  }
  Rosto.modo("offline");
  rodar(3);
  assert.ok(Rosto.estado.cinza > 0.5, "sem internet: fica sem cor");
  Rosto.modo("ocioso");
  rodar(3);
  assert.ok(Rosto.estado.cinza < 0.05, `a cor volta: cinza ${Rosto.estado.cinza}`);
  for (const g of ["acenar", "negar", "inclinar"]) { Rosto.gesto(g); rodar(1.2); assert.equal(Rosto.estado.gesto, null, g); }
  Rosto.modo("dormindo");
  rodar(3);
  assert.ok(Rosto.estado.pesos.piscar_direito > 0.95, "dormindo: olhos fechados");
});

test("para de desenhar quando fica escondido", async () => {
  const { Rosto, rodar, janela, pendentes, esperarModelo } = carregarRosto();
  await esperarModelo();
  Rosto.modo("falando");
  Rosto.voz(0.8);
  rodar(1);
  assert.ok(pendentes() > 0, "falando: continua desenhando");
  janela.document.hidden = true;
  rodar(1);
  assert.equal(pendentes(), 0, "escondido: nenhum quadro agendado");
});

test("sem WebGL, ou sem o modelo, usa o rosto de reserva (a ilustração)", async () => {
  for (const caso of [{ semWebGL: true }, { modeloFalta: true }]) {
    const { scripts, esperarModelo, Rosto } = carregarRosto(caso);
    Rosto.modo("ouvindo");
    await esperarModelo();
    assert.equal(scripts.length, 1, JSON.stringify(caso));
    assert.equal(scripts[0].src, "http://pc/static/rosto2d.js");
  }
});
