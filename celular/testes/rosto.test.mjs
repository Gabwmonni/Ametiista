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
  let agora = 0;
  const janela = {
    document: { getElementById: () => canvas, createElement: () => ({ ...canvas }), addEventListener: nada, hidden: false },
    addEventListener: nada, devicePixelRatio: 1, innerWidth: 300, innerHeight: 200,
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
  return { Rosto: janela.Rosto, rodar, janela, pendentes: () => quadros.length };
}

const LILAS = [199, 155, 255];
const perto = (cor, alvo) => cor.every((v, i) => Math.abs(v - alvo[i]) < 6);

test("o rosto volta ao lilás depois de alerta, modo privado e sem internet", () => {
  const { Rosto, rodar } = carregarRosto();
  Rosto.modo("ocioso");
  rodar(2);
  assert.ok(perto(Rosto.estado.cor.olho, LILAS), "começa lilás");
  for (const estado of ["alerta", "privado", "offline"]) {
    Rosto.modo(estado);
    rodar(3);
    assert.ok(!perto(Rosto.estado.cor.olho, LILAS), `${estado} muda a cor`);
    Rosto.modo("ocioso");
    rodar(3);
    assert.ok(perto(Rosto.estado.cor.olho, LILAS), `depois de ${estado} volta ao lilás: ${Rosto.estado.cor.olho}`);
  }
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
