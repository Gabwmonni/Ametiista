// Rosto: roda o laço de desenho de verdade num canvas falso e confere as cores entre os estados.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

function carregarRosto() {
  const nada = () => {};
  const ctx2d = new Proxy({}, { get: (_, k) => (k === "createRadialGradient" || k === "createLinearGradient")
    ? () => ({ addColorStop: nada }) : nada, set: () => true });
  const canvas = { dataset: { transparente: "1" }, clientWidth: 300, clientHeight: 200, width: 0, height: 0,
    getContext: () => ctx2d };
  const quadros = [];
  let agora = 0, camadas = 0;
  const janela = {
    document: { getElementById: () => canvas, createElement: () => (camadas++, { ...canvas }), addEventListener: nada,
                hidden: false },
    addEventListener: (tipo, f) => { if (tipo === "resize") janela.redimensionou = f; },
    devicePixelRatio: 1, innerWidth: 300, innerHeight: 200,
    performance: { now: () => agora },
    requestAnimationFrame: (f) => (quadros.push(f), quadros.length),
    setTimeout: (f) => (quadros.push(() => f()), 1), clearTimeout: nada, Math,
  };
  janela.window = janela;
  vm.runInNewContext(readFileSync(new URL("../../web/rosto.js", import.meta.url), "utf8"), janela);
  const rodar = (segundos) => {                       // avança o relógio e roda os quadros agendados
    for (let i = 0; i < segundos * 60; i++) {
      agora += 1000 / 60;
      const f = quadros.shift();
      if (f) f(agora);
    }
  };
  return { Rosto: janela.Rosto, rodar, janela, canvas, pendentes: () => quadros.length, camadas: () => camadas };
}

const LILAS = [203, 178, 248];
const perto = (cor, alvo) => cor.every((v, i) => Math.abs(v - alvo[i]) < 6);

test("o brilho volta ao lilás depois de alerta e de ouvir, e a cor volta depois de ficar sem internet", () => {
  const { Rosto, rodar } = carregarRosto();
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
});

test("cabelo, pele e joias são desenhados uma vez só (não a cada quadro)", () => {
  const { Rosto, rodar, canvas, camadas, janela } = carregarRosto();
  Rosto.modo("falando");
  Rosto.voz(0.8);
  rodar(1);
  const feitas = camadas();
  assert.ok(feitas > 0, "prepara as camadas");
  rodar(3);
  Rosto.modo("pensando"); Rosto.emocao("feliz"); Rosto.gesto("acenar");
  rodar(2);
  assert.equal(camadas(), feitas, "nenhuma camada refeita enquanto o tamanho não muda");
  canvas.clientWidth = 128; canvas.clientHeight = 104;              // mudou de tamanho: refaz, no tamanho novo
  janela.redimensionou();
  rodar(1);
  assert.ok(camadas() > feitas, "refaz as camadas no tamanho novo");
});

test("o rosto anima e para de desenhar quando fica escondido", () => {
  const { Rosto, rodar, janela, pendentes } = carregarRosto();
  Rosto.modo("falando");
  Rosto.voz(0.8);
  rodar(1);
  assert.ok(Rosto.estado.atual.abertura > 0.5 && pendentes() > 0, "falando: continua desenhando");
  janela.document.hidden = true;
  rodar(1);
  assert.equal(pendentes(), 0, "escondido: nenhum quadro agendado");
});
