// Ametista: o rosto dela, desenhado em canvas. Só o essencial da ficha de personagem, flutuando: os olhos de
// cristal (íris azul em estrela, sombra rosa), o monóculo de cristal sobre o olho direito dela, a boca e os
// detalhes em metal líquido iridescente (sobrancelhas, renda com gotas de cristal sob os olhos, arabesco,
// corrente do monóculo). Pisca, olha em volta, flutua, fala (a boca segue a voz), tem emoções, estados e
// gestos de cabeça. Ela de corpo inteiro é a ilustração da ficha (ametista.webp).
//
// Estados (Rosto.modo):  dormindo | ocioso | ouvindo | pensando | falando |
//                        executando | alerta | offline | aguardando | privado
// Emoções (Rosto.emocao): neutra | feliz | pensativa | surpresa | triste | brava
// Gestos (Rosto.gesto):  acenar (sim com a cabeça) | negar | inclinar
//
// Leve de propósito: o que não mexe (renda, gotas, monóculo, brilho dos olhos) é desenhado uma vez em imagens
// prontas; a cada quadro só se redesenha o que mexe (olhos, sobrancelhas, boca). 24 quadros/s falando, 30 só no
// instante de uma piscada, 8 parada ou dormindo, e nada quando a janela ou o app estão escondidos.
(() => {
  const canvas = document.getElementById("rosto");
  const ctxTela = canvas.getContext("2d");
  let ctx = ctxTela;                     // troca para a imagem que está sendo preparada (veja prepararCamadas)
  const TRANSPARENTE = canvas.dataset.transparente === "1";

  // ---------------------------------------------------------------- paleta (medida na ficha)
  const COR = {
    esclera: ["#ffffff", "#f6f2ff", "#ddd4f4"],
    iris: ["#f4f8ff", "#b3cefb", "#7d8ff0", "#4049a8", "#262a6e"], anelIris: "252,201,242", pupila: "#1c1a4c",
    cilios: "#2a1f38", sombraOlho: "252,190,236", brilhoOlho: "203,178,248",
    labio: ["#f6bdd6", "#e39abb", "#c77399"], labioLinha: "#9c4f7a", boca: "#4a1d3c",
    // metal líquido iridescente: ouro rosé que passa por rosa, lilás e azul-cristal
    metal: ["#fff1de", "#e6c7a2", "#fcc9f2", "#cbb2f8", "#b3cefb", "#f3dcc0"], metalBorda: "rgba(52,34,74,0.55)",
    cristal: ["#ffffff", "#fcc9f2", "#cbb2f8", "#b3cefb"],
    halo: [203, 178, 248], haloAlerta: [255, 176, 120], haloOuvindo: [179, 206, 251],
  };

  // Formato alvo de cada emoção (tudo em números: o rosto passa de um para outro suavemente)
  const EMOCOES = {
    neutra:    { abertura: 1.00, sorriso: 0.10, sobrY: 0,  sobrAng: 0.00, boca: 0.25, bocaAb: 0.00, assim: 0 },
    feliz:     { abertura: 0.90, sorriso: 0.50, sobrY: 4,  sobrAng: -0.1, boca: 1.00, bocaAb: 0.00, assim: 0 },
    pensativa: { abertura: 0.88, sorriso: 0.06, sobrY: 6,  sobrAng: 0.10, boca: 0.05, bocaAb: 0.00, assim: 1 },
    surpresa:  { abertura: 1.14, sorriso: 0.00, sobrY: 18, sobrAng: 0.00, boca: 0.00, bocaAb: 0.42, assim: 0 },
    triste:    { abertura: 0.84, sorriso: 0.04, sobrY: 6,  sobrAng: -0.8, boca: -0.60, bocaAb: 0.00, assim: 0 },
    brava:     { abertura: 0.78, sorriso: 0.12, sobrY: -8, sobrAng: 0.80, boca: -0.15, bocaAb: 0.00, assim: 0 },
  };
  // Estados que mandam no formato, por cima da emoção
  const FORMA_MODO = {
    dormindo:   { abertura: 0.00, sorriso: 0.00, sobrY: 0,  sobrAng: 0.0, boca: 0.30, bocaAb: 0.00, assim: 0 },
    privado:    { abertura: 0.00, sorriso: 0.00, sobrY: 2,  sobrAng: 0.0, boca: 0.60, bocaAb: 0.00, assim: 0 },
    offline:    { abertura: 0.55, sorriso: 0.05, sobrY: 0,  sobrAng: -0.3, boca: -0.10, bocaAb: 0.00, assim: 0 },
    alerta:     { abertura: 1.14, sorriso: 0.00, sobrY: 16, sobrAng: 0.0, boca: 0.00, bocaAb: 0.40, assim: 0 },
    executando: { abertura: 0.86, sorriso: 0.10, sobrY: -2, sobrAng: 0.35, boca: 0.10, bocaAb: 0.00, assim: 0 },
    aguardando: { abertura: 1.02, sorriso: 0.10, sobrY: 10, sobrAng: 0.0, boca: 0.35, bocaAb: 0.00, assim: 1 },
  };

  const estado = {
    modo: "dormindo",
    emocao: "neutra",
    voz: 0,                    // 0..1 volume da fala (boca)
    mic: 0,                    // 0..1 volume do microfone (brilho de escuta)
    atual: { ...FORMA_MODO.dormindo },
    brilho: [...COR.halo],     // cor do brilho de fundo (muda com o estado)
    cinza: 0,                  // 0..1 (sem internet: sem cor)
    olhar: { x: 0, y: 0 }, alvoOlhar: { x: 0, y: 0 },
    piscar: 0, proxPiscada: 2, proxOlhar: 1,
    cabeca: { rot: 0, dx: 0, dy: 0 },
    gesto: null, gestoT: 0,
    boca: 0,                   // abertura da boca suavizada
  };

  let W = 0, H = 0, dpr = 1;
  function redimensionar() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = canvas.clientWidth || innerWidth; H = canvas.clientHeight || innerHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    if (typeof acordar === "function") acordar();
  }
  addEventListener("resize", redimensionar);
  if (window.ResizeObserver) new ResizeObserver(redimensionar).observe(canvas);

  const lerp = (a, b, t) => a + (b - a) * t;
  const rgba = (c, a = 1) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;
  const bez = (a, b, c, d, u) => {
    const v = 1 - u;
    return v * v * v * a + 3 * v * v * u * b + 3 * v * u * u * c + u * u * u * d;
  };
  // enquadramento, em unidades do modelo: de perto (barra do PC, celular) ou com mais respiro (tamanhos grandes)
  const PERTO = { x0: -235, x1: 235, y0: -135, y1: 245 };
  const GRANDE = { x0: -260, x1: 260, y0: -165, y1: 270 };

  // ---------------------------------------------------------------- metal líquido e cristais
  // Degradê iridescente ao longo de uma peça (de x0,y0 a x1,y1)
  function iridescente(x0, y0, x1, y1) {
    const g = ctx.createLinearGradient(x0, y0, x1, y1), c = COR.metal;
    for (let i = 0; i < c.length; i++) g.addColorStop(i / (c.length - 1), c[i]);
    return g;
  }
  // Risca um caminho como metal líquido: borda escura, corpo iridescente e um fio de luz por cima
  function metal(caminho, larg, x0, y0, x1, y1) {
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    caminho(); ctx.strokeStyle = COR.metalBorda; ctx.lineWidth = larg + 1.8; ctx.stroke();
    caminho(); ctx.strokeStyle = iridescente(x0, y0, x1, y1); ctx.lineWidth = larg; ctx.stroke();
    ctx.save(); ctx.translate(-larg * 0.15, -larg * 0.28);
    caminho(); ctx.strokeStyle = "rgba(255,255,255,0.78)"; ctx.lineWidth = Math.max(0.8, larg * 0.3); ctx.stroke();
    ctx.restore();
  }
  // Uma conta de metal (esfera pequena com brilho)
  function conta(x, y, r) {
    ctx.fillStyle = COR.metalBorda; ctx.beginPath(); ctx.arc(x, y, r + 0.9, 0, Math.PI * 2); ctx.fill();
    const g = ctx.createRadialGradient(x - r * 0.4, y - r * 0.4, 0, x, y, r);
    g.addColorStop(0, "#ffffff"); g.addColorStop(0.45, COR.metal[2]); g.addColorStop(1, COR.metal[1]);
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
  }
  function gradCristal(x, y, h) {
    const g = ctx.createLinearGradient(x - h * 0.5, y - h, x + h * 0.5, y + h);
    g.addColorStop(0, COR.cristal[0]); g.addColorStop(0.35, COR.cristal[1]); g.addColorStop(0.65, COR.cristal[2]); g.addColorStop(1, COR.cristal[3]);
    return g;
  }
  // Gota de cristal lapidada, pendurada no ponto (x, y - h)
  function cristalGota(x, y, w, h, t = 0) {
    ctx.fillStyle = gradCristal(x, y, h);
    ctx.beginPath(); ctx.moveTo(x, y - h); ctx.lineTo(x + w, y - h * 0.1); ctx.lineTo(x, y + h * 0.75); ctx.lineTo(x - w, y - h * 0.1); ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.9)"; ctx.lineWidth = 1.4; ctx.stroke();
    ctx.strokeStyle = "rgba(120,110,170,0.45)"; ctx.lineWidth = 1;         // facetas
    ctx.beginPath(); ctx.moveTo(x, y - h); ctx.lineTo(x, y + h * 0.75);
    ctx.moveTo(x - w, y - h * 0.1); ctx.lineTo(x + w * 0.35, y + h * 0.1); ctx.lineTo(x + w, y - h * 0.1); ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255,0.7)";
    ctx.beginPath(); ctx.moveTo(x - w * 0.55, y - h * 0.15); ctx.lineTo(x - w * 0.1, y - h * 0.7); ctx.lineTo(x - w * 0.05, y - h * 0.15); ctx.fill();
    faisca(x, y, w, h, t);
  }
  function estrela(x, y, r, cor) {
    ctx.fillStyle = cor;
    ctx.beginPath();
    ctx.moveTo(x, y - r); ctx.quadraticCurveTo(x, y, x + r, y); ctx.quadraticCurveTo(x, y, x, y + r);
    ctx.quadraticCurveTo(x, y, x - r, y); ctx.quadraticCurveTo(x, y, x, y - r);
    ctx.fill();
  }
  // O brilho que pisca num cristal. Se a peça está indo para uma imagem pronta, só anota: o brilho é desenhado
  // a cada quadro por cima dela.
  let anotando = null;
  function faisca(x, y, w, h, t) {
    if (anotando) { anotando.push([x, y, w, h, t]); return; }
    const pisca = (Math.sin(t * 2.2 + x * 0.7) + 1) / 2;
    if (pisca > 0.72) estrela(x - w * 0.3, y - h * 0.45, 9 * (pisca - 0.68) * 3, "rgba(255,255,255,0.95)");
  }

  // ---------------------------------------------------------------- os olhos
  const OLHO = { dentro: 30, fora: 166, meio: 22, irisX: 98, irisY: 16 };
  function formaDoOlho(s, p, aberto) {
    const sobe = p.sorriso * 24;                       // pálpebra de baixo sobe no sorriso
    const ab = (y) => OLHO.meio + (y - OLHO.meio) * Math.min(aberto, 1.2);
    const ix = s * OLHO.dentro, ox = s * OLHO.fora;
    return {
      aberto, ix, ox,
      cima: [[ix, ab(28)], [s * 50, ab(-22)], [s * 124, ab(-42)], [ox, ab(-6)]],
      baixo: [[ox, ab(-6)], [s * 150, ab(48) - sobe], [s * 70, ab(58) - sobe], [ix, ab(28)]],
    };
  }

  // O brilho lilás atrás de cada olho e a sombra rosa da pálpebra, com um pó cintilante (imagem pronta)
  function luzDosOlhos() {
    for (const s of [-1, 1]) {
      let g = ctx.createRadialGradient(s * 98, 14, 20, s * 98, 14, 150);
      g.addColorStop(0, `rgba(${COR.brilhoOlho},0.22)`); g.addColorStop(1, `rgba(${COR.brilhoOlho},0)`);
      ctx.fillStyle = g; ctx.fillRect(s * 98 - 150, -136, 300, 300);
      g = ctx.createRadialGradient(s * 118, -16, 6, s * 110, -8, 92);
      g.addColorStop(0, `rgba(${COR.sombraOlho},0.62)`); g.addColorStop(0.5, `rgba(${COR.sombraOlho},0.3)`);
      g.addColorStop(1, `rgba(${COR.sombraOlho},0)`);
      ctx.fillStyle = g; ctx.beginPath(); ctx.ellipse(s * 110, -8, 96, 50, s * -0.14, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "rgba(255,255,255,0.75)";                       // pó cintilante na sombra
      for (const [x, y, r] of [[70, -40, 1.6], [96, -50, 1.2], [128, -46, 1.8], [150, -30, 1.3], [112, -34, 1], [84, -30, 1.1]]) {
        ctx.beginPath(); ctx.arc(s * x, y, r, 0, Math.PI * 2); ctx.fill();
      }
    }
  }

  // A íris de cristal: azul em estrela, anel rosa, pupila com estrela e brilhos (imagem pronta em volta de 0,0)
  const IRIS = 44;
  function iris() {
    const r = 41;
    const gi = ctx.createRadialGradient(0, -5, 2, 0, 0, r);
    gi.addColorStop(0, COR.iris[0]); gi.addColorStop(0.28, COR.iris[1]); gi.addColorStop(0.62, COR.iris[2]);
    gi.addColorStop(0.9, COR.iris[3]); gi.addColorStop(1, COR.iris[4]);
    ctx.fillStyle = gi; ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); ctx.fill();
    ctx.lineCap = "round";
    for (let i = 0; i < 28; i++) {                                     // raios em estrela
      const a = (i / 28) * Math.PI * 2 + 0.1, longo = i % 2 === 0;
      const r0 = longo ? 12 : 16, r1 = longo ? 37 : 28;
      ctx.strokeStyle = i % 4 === 1 ? `rgba(${COR.anelIris},0.55)` : "rgba(255,255,255,0.5)";
      ctx.lineWidth = longo ? 1.8 : 1.2;
      ctx.beginPath(); ctx.moveTo(Math.cos(a) * r0, Math.sin(a) * r0); ctx.lineTo(Math.cos(a) * r1, Math.sin(a) * r1); ctx.stroke();
    }
    ctx.strokeStyle = "rgba(30,28,90,0.8)"; ctx.lineWidth = 2.5;        // aro da íris
    ctx.beginPath(); ctx.arc(0, 0, r - 1, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = `rgba(${COR.anelIris},0.75)`; ctx.lineWidth = 2.2; // anel rosa em volta da pupila
    ctx.beginPath(); ctx.arc(0, 0, 15, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = COR.pupila; ctx.beginPath(); ctx.arc(0, 0, 11, 0, Math.PI * 2); ctx.fill();
    estrela(0, 0, 13, "rgba(255,255,255,0.95)");                       // a estrela no centro
    ctx.fillStyle = "rgba(255,255,255,0.95)";
    ctx.beginPath(); ctx.ellipse(-15, -15, 9, 6.5, -0.6, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(16, 14, 4, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,0.6)";                           // cintilâncias de cristal
    for (const [a, d, rr] of [[0.6, 30, 1.8], [2.2, 27, 1.4], [3.6, 32, 1.6], [5.1, 29, 1.3]]) {
      ctx.beginPath(); ctx.arc(Math.cos(a) * d, Math.sin(a) * d, rr, 0, Math.PI * 2); ctx.fill();
    }
  }

  // Um olho amendoado. s = -1 (esquerda da tela) ou 1. p = formato atual.
  function olho(s, p) {
    const { aberto, ix, ox, cima, baixo } = formaDoOlho(s, p, Math.max(0, p.abertura * (1 - estado.piscar)));
    const forma = (c, b) => {
      ctx.beginPath(); ctx.moveTo(...c[0]);
      ctx.bezierCurveTo(...c[1], ...c[2], ...c[3]);
      ctx.bezierCurveTo(...b[1], ...b[2], ...b[3]);
      ctx.closePath();
    };
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    // pálpebras de porcelana: aparecem quando o olho fecha ou semicerra (piscada, dormindo, brava)
    if (aberto < 0.99) {
      const lid = formaDoOlho(s, p, 1);
      const gp = ctx.createLinearGradient(0, -30, 0, 60);
      gp.addColorStop(0, "rgba(244,176,224,0.55)"); gp.addColorStop(0.6, "rgba(226,200,240,0.4)"); gp.addColorStop(1, "rgba(200,180,235,0.3)");
      forma(lid.cima, lid.baixo); ctx.fillStyle = gp; ctx.fill();
    }
    // dobra da pálpebra (some com o olho fechado)
    ctx.strokeStyle = `rgba(230,170,215,${0.6 * Math.min(aberto, 1)})`; ctx.lineWidth = 2.2;
    ctx.beginPath(); ctx.moveTo(s * 48, cima[0][1] - 40 * Math.min(aberto, 1));
    ctx.bezierCurveTo(s * 82, -54, s * 132, -62, s * 160, -30); ctx.stroke();

    if (aberto > 0.06) {
      ctx.save();
      forma(cima, baixo);
      const ge = ctx.createRadialGradient(s * 98, 16, 10, s * 98, 16, 80);
      ge.addColorStop(0, COR.esclera[0]); ge.addColorStop(0.6, COR.esclera[1]); ge.addColorStop(1, COR.esclera[2]);
      ctx.fillStyle = ge; ctx.fill(); ctx.clip();
      const cx = s * OLHO.irisX + estado.olhar.x * 18, cy = OLHO.irisY + estado.olhar.y * 10;
      ctx.drawImage(camadas.iris.c, cx - IRIS, cy - IRIS, IRIS * 2, IRIS * 2);
      // sombra da pálpebra sobre o olho
      const sp = ctx.createLinearGradient(0, cima[2][1] - 4, 0, cima[2][1] + 36);
      sp.addColorStop(0, "rgba(80,50,130,0.5)"); sp.addColorStop(1, "rgba(80,50,130,0)");
      ctx.fillStyle = sp; ctx.fillRect(Math.min(ix, ox), cima[2][1] - 12, Math.abs(ox - ix), 60);
      ctx.restore();
      // linha de baixo, rosada, e o brilho do canto de dentro
      ctx.strokeStyle = "rgba(236,160,205,0.9)"; ctx.lineWidth = 2.6;
      ctx.beginPath(); ctx.moveTo(...baixo[0]); ctx.bezierCurveTo(...baixo[1], ...baixo[2], s * 50, baixo[3][1] + 3); ctx.stroke();
      ctx.fillStyle = "rgba(255,255,255,0.85)";
      ctx.beginPath(); ctx.arc(s * 40, baixo[3][1] + 2, 2.6, 0, Math.PI * 2); ctx.fill();
    }
    // cílios de cima: fina no canto de dentro, grossa para fora, com um "gatinho" e cílios longos
    ctx.strokeStyle = COR.cilios;
    if (aberto > 0.06) {
      ctx.lineWidth = 4;
      ctx.beginPath(); ctx.moveTo(...cima[0]); ctx.bezierCurveTo(...cima[1], ...cima[2], ...cima[3]); ctx.stroke();
      ctx.lineWidth = 8.5;
      ctx.beginPath(); ctx.moveTo(lerp(ix, s * 70, 0.9), lerp(cima[0][1], cima[1][1], 0.9) - 2);
      ctx.bezierCurveTo(s * 100, cima[2][1] - 4, s * 140, cima[2][1] + 2, ox, cima[3][1]);
      ctx.lineTo(ox + s * 18, cima[3][1] - 13);          // o "gatinho" no canto de fora
      ctx.stroke();
      ctx.lineWidth = 2.8;
      ctx.beginPath();
      for (const [f, comp, abre] of [[0.42, 12, 0.1], [0.58, 16, 0.2], [0.72, 19, 0.35], [0.85, 22, 0.5], [0.97, 24, 0.7]]) {
        const x = lerp(s * 70, ox, f), y = lerp(cima[2][1], cima[3][1], f) - 3;
        ctx.moveTo(x, y); ctx.quadraticCurveTo(x + s * comp * abre * 0.5, y - comp * 0.8, x + s * comp * abre * 1.6, y - comp);
      }
      ctx.stroke();
    } else {                                             // fechado: um arco sereno com os cílios para baixo
      ctx.lineWidth = 6;
      ctx.beginPath(); ctx.moveTo(ix, OLHO.meio + 8); ctx.bezierCurveTo(s * 66, OLHO.meio + 30, s * 132, OLHO.meio + 30, ox, OLHO.meio + 2); ctx.stroke();
      ctx.lineWidth = 2.8;
      ctx.beginPath();
      for (const f of [0.5, 0.66, 0.8, 0.93]) {
        const x = lerp(s * 66, ox, f), y = OLHO.meio + 27 - f * 20;
        ctx.moveTo(x, y); ctx.quadraticCurveTo(x + s * 4, y + 9, x + s * 11, y + 14);
      }
      ctx.stroke();
    }
  }

  // Renda de metal líquido sob os olhos: uma rede fina, arcos, contas e gotas de cristal penduradas (mais longas
  // no olho sem o monóculo, como lágrimas de cristal). Imagem pronta.
  function renda(s) {
    const A = [[48, 76], [84, 96], [132, 92], [168, 56]];              // acompanha a pálpebra de baixo
    const B = [[62, 98], [92, 118], [132, 114], [160, 86]];            // a borda de baixo da rede
    const pa = (u) => [s * bez(A[0][0], A[1][0], A[2][0], A[3][0], u), bez(A[0][1], A[1][1], A[2][1], A[3][1], u)];
    const pb = (u) => [s * bez(B[0][0], B[1][0], B[2][0], B[3][0], u), bez(B[0][1], B[1][1], B[2][1], B[3][1], u)];
    // a rede (como na ficha): linhas cruzadas entre as duas bordas
    ctx.strokeStyle = "rgba(236,205,190,0.5)"; ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i <= 8; i++) {
      const [ax, ay] = pa(0.08 + i * 0.1), [bx, by] = pb(Math.min(1, 0.08 + (i + 1) * 0.1)), [cx, cy] = pb(Math.max(0, 0.08 + (i - 1) * 0.1));
      ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.moveTo(ax, ay); ctx.lineTo(cx, cy);
    }
    ctx.stroke();
    metal(() => { ctx.beginPath(); ctx.moveTo(s * A[0][0], A[0][1]); ctx.bezierCurveTo(s * A[1][0], A[1][1], s * A[2][0], A[2][1], s * A[3][0], A[3][1]); },
      2.4, s * 48, 40, s * 168, 110);
    const us = [0.12, 0.3, 0.48, 0.66, 0.84, 1];
    metal(() => {                                                      // arcos da borda de baixo
      ctx.beginPath();
      for (let i = 0; i < us.length - 1; i++) {
        const [ax, ay] = pb(us[i]), [bx, by] = pb(us[i + 1]);
        ctx.moveTo(ax, ay); ctx.quadraticCurveTo((ax + bx) / 2, (ay + by) / 2 + 12, bx, by);
      }
    }, 1.8, s * 60, 80, s * 160, 130);
    for (const u of us) conta(...pb(u), 2.2);
    const gotas = s > 0 ? [[0.3, 20, 0.8], [0.48, 38, 1.05], [0.66, 26, 0.9], [0.84, 12, 0.7]] : [[0.48, 12, 0.7], [0.66, 18, 0.75]];
    for (const [u, comp, tam] of gotas) {
      const [x, y] = pb(u);
      metal(() => { ctx.beginPath(); ctx.moveTo(x, y + 2); ctx.lineTo(x, y + comp); }, 1.4, x, y, x, y + comp);
      cristalGota(x, y + comp + 12 * tam, 7 * tam, 13 * tam, u * 9 + s);
    }
  }

  // Arabesco de metal líquido nascendo da ponta do "gatinho" do olho sem monóculo: uma volta para cima,
  // outra para baixo, contas e uma gota de cristal
  function arabesco() {
    metal(() => {
      ctx.beginPath(); ctx.moveTo(186, -20);
      ctx.bezierCurveTo(206, -30, 214, -52, 200, -62);
      ctx.bezierCurveTo(190, -68, 180, -58, 188, -52);
    }, 2.2, 186, -68, 214, -20);
    metal(() => {
      ctx.beginPath(); ctx.moveTo(186, -20);
      ctx.bezierCurveTo(218, -12, 226, 30, 208, 52);
      ctx.bezierCurveTo(198, 64, 180, 58, 184, 46);
      ctx.bezierCurveTo(188, 38, 200, 42, 197, 50);
    }, 2.6, 180, -20, 226, 64);
    metal(() => { ctx.beginPath(); ctx.moveTo(212, 2); ctx.quadraticCurveTo(232, -2, 236, -22); }, 1.6, 212, -22, 236, 2);
    conta(236, -24, 2.8); conta(214, -40, 2); conta(221, 18, 2);
    metal(() => { ctx.beginPath(); ctx.moveTo(208, 56); ctx.lineTo(209, 84); }, 1.4, 208, 56, 209, 84);
    cristalGota(209, 100, 8, 16, 4);
  }

  // Monóculo de cristal sobre o olho direito dela (o da esquerda na tela): lente iridescente, aro de metal
  // líquido com contas, uma flor de filigrana, a corrente e gotas penduradas. Imagem pronta.
  const LENTE = { x: -98, y: 18, r: 80 };
  function monoculo() {
    const { x: cx, y: cy, r } = LENTE;
    ctx.save();
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.clip();
    const gl = ctx.createRadialGradient(cx - 20, cy - 25, 10, cx, cy, r);
    gl.addColorStop(0, "rgba(255,255,255,0.12)"); gl.addColorStop(0.7, "rgba(214,196,255,0.1)"); gl.addColorStop(1, "rgba(252,201,242,0.28)");
    ctx.fillStyle = gl; ctx.fillRect(cx - r, cy - r, r * 2, r * 2);
    // borda de arco-íris por dentro (reflexos multicoloridos do cristal)
    const arco = (ctx.createConicGradient && ctx.createConicGradient(0.6, cx, cy)) || ctx.createLinearGradient(cx - r, cy - r, cx + r, cy + r);
    ["rgba(252,201,242,.7)", "rgba(203,178,248,.55)", "rgba(179,206,251,.7)", "rgba(190,240,230,.45)", "rgba(255,226,180,.55)", "rgba(252,201,242,.7)"]
      .forEach((c, i, l) => arco.addColorStop(i / (l.length - 1), c));
    ctx.strokeStyle = arco; ctx.lineWidth = 11;
    ctx.beginPath(); ctx.arc(cx, cy, r - 4, 0, Math.PI * 2); ctx.stroke();
    // reflexos na lente
    ctx.fillStyle = "rgba(255,255,255,0.24)";
    ctx.beginPath(); ctx.moveTo(cx - r - 8, cy - r); ctx.lineTo(cx - r + 34, cy - r); ctx.lineTo(cx - 42, cy + r); ctx.lineTo(cx - 84, cy + r); ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,0.14)";
    ctx.beginPath(); ctx.moveTo(cx - 18, cy - r); ctx.lineTo(cx - 4, cy - r); ctx.lineTo(cx + 42, cy + r); ctx.lineTo(cx + 28, cy + r); ctx.fill();
    ctx.restore();
    // aro de metal líquido (as cores giram em volta)
    const ga = (ctx.createConicGradient && ctx.createConicGradient(-0.8, cx, cy)) || ctx.createLinearGradient(cx - r, cy - r, cx + r, cy + r);
    COR.metal.concat(COR.metal[0]).forEach((c, i, l) => ga.addColorStop(i / (l.length - 1), c));
    ctx.strokeStyle = COR.metalBorda; ctx.lineWidth = 8.5;
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = ga; ctx.lineWidth = 6.5;
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = "rgba(255,255,255,0.85)"; ctx.lineWidth = 1.8;
    ctx.beginPath(); ctx.arc(cx, cy, r - 1.5, Math.PI * 1.02, Math.PI * 1.5); ctx.stroke();
    ctx.beginPath(); ctx.arc(cx, cy, r + 1.5, Math.PI * 0.1, Math.PI * 0.3); ctx.stroke();
    for (let i = 0; i < 20; i++) {                                     // contas miúdas em volta
      const a = (i / 20) * Math.PI * 2 + 0.08;
      conta(cx + Math.cos(a) * (r + 7), cy + Math.sin(a) * (r + 7), 1.7);
    }
    // flor de filigrana com um cristal, no lado de fora do aro
    const fx = cx - r - 12, fy = cy - 2;
    for (const a of [-1.0, 0, 1.0]) {
      metal(() => { ctx.beginPath(); ctx.ellipse(fx + Math.cos(Math.PI + a) * 10, fy + Math.sin(Math.PI + a) * 10, 10, 5.5, a, 0, Math.PI * 2); },
        1.6, fx - 20, fy - 12, fx, fy + 12);
    }
    cristalGota(fx, fy + 4, 5.5, 10, 5);
    // corrente de contas descendo em curva, com uma gota de cristal na ponta
    for (let i = 1; i < 16; i++) {
      const u = i / 16;
      const x = bez(fx - 4, fx - 36, fx - 28, fx - 14, u), y = bez(fy + 10, fy + 60, fy + 120, fy + 150, u);
      conta(x, y, i % 3 ? 1.6 : 2.4);
    }
    cristalGota(fx - 14, fy + 170, 8, 17, 6);
    // gotas de cristal penduradas embaixo do aro
    for (const [a, comp, tam] of [[0.58, 14, 0.75], [0.68, 30, 0.95], [0.78, 18, 0.8]]) {
      const x = cx + Math.cos(a * Math.PI) * (r + 4), y = cy + Math.sin(a * Math.PI) * (r + 4);
      metal(() => { ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y + comp); }, 1.4, x, y, x, y + comp);
      cristalGota(x, y + comp + 13 * tam, 7 * tam, 13 * tam, a * 7);
    }
  }

  // ---------------------------------------------------------------- o que mexe a cada quadro
  // Sobrancelhas de metal líquido: finas, arqueadas, mais cheias perto do nariz
  function sobrancelhas(p) {
    for (const s of [-1, 1]) {
      const extra = p.assim && s > 0 ? 10 : 0;           // uma sobrancelha levantada (dúvida)
      const y = -80 - p.sobrY - extra;
      const dentro = y + p.sobrAng * 20, fora = y + 8 - p.sobrAng * 6, topo = Math.min(dentro, fora) - 20;
      const forma = () => {
        ctx.beginPath(); ctx.moveTo(s * 42, dentro + 4);
        ctx.quadraticCurveTo(s * 98, topo, s * 158, fora + 4);
        ctx.quadraticCurveTo(s * 100, topo + 10, s * 46, dentro + 12);
        ctx.closePath();
      };
      forma(); ctx.strokeStyle = COR.metalBorda; ctx.lineWidth = 1.6; ctx.lineJoin = "round"; ctx.stroke();
      ctx.fillStyle = iridescente(s * 42, topo, s * 158, fora + 12); ctx.fill();
      ctx.strokeStyle = "rgba(255,255,255,0.8)"; ctx.lineWidth = 1.3;
      ctx.beginPath(); ctx.moveTo(s * 52, dentro + 5); ctx.quadraticCurveTo(s * 98, topo + 2, s * 146, fora + 3); ctx.stroke();
    }
  }

  // Um brilho rosa suave embaixo da renda (imagem pronta)
  function rubor() {
    for (const s of [-1, 1]) {
      const g = ctx.createRadialGradient(s * 116, 108, 4, s * 116, 108, 60);
      g.addColorStop(0, "rgba(252,170,215,0.1)"); g.addColorStop(1, "rgba(252,170,215,0)");
      ctx.fillStyle = g; ctx.fillRect(s * 116 - 60, 48, 120, 120);
    }
  }

  function boca(p) {
    const c = p.boca, o = estado.boca;
    const y = 196, larg = 34;
    const canto = y - c * 8, meio = y + c * 6;
    const gl = ctx.createLinearGradient(0, meio - 14, 0, meio + 22);
    gl.addColorStop(0, COR.labio[2]); gl.addColorStop(0.45, COR.labio[1]); gl.addColorStop(1, COR.labio[0]);
    if (o < 0.05) {
      // lábio de baixo, cheio, com brilho molhado
      ctx.fillStyle = gl;
      ctx.beginPath(); ctx.moveTo(-larg * 0.8, canto + 1);
      ctx.bezierCurveTo(-20, meio + 22, 20, meio + 22, larg * 0.8, canto + 1);
      ctx.quadraticCurveTo(0, meio + 4, -larg * 0.8, canto + 1); ctx.fill();
      ctx.fillStyle = "rgba(255,255,255,0.65)"; ctx.beginPath(); ctx.ellipse(-5, meio + 12, 8, 2.8, -0.1, 0, Math.PI * 2); ctx.fill();
      // lábio de cima com arco do cupido
      ctx.fillStyle = COR.labio[2];
      ctx.beginPath(); ctx.moveTo(-larg, canto);
      ctx.quadraticCurveTo(-15, meio - 13, -5, meio - 8); ctx.quadraticCurveTo(0, meio - 5, 5, meio - 8);
      ctx.quadraticCurveTo(15, meio - 13, larg, canto); ctx.quadraticCurveTo(0, meio + 4, -larg, canto); ctx.fill();
      ctx.fillStyle = "rgba(255,255,255,0.35)"; ctx.beginPath(); ctx.ellipse(-12, meio - 7, 6, 1.8, -0.3, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = COR.labioLinha; ctx.lineWidth = 2.4; ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(-larg, canto); ctx.quadraticCurveTo(0, meio + 5, larg, canto); ctx.stroke();
      return;
    }
    const redondo = p.bocaAb > 0.3 && estado.modo !== "falando";                // surpresa: um "o"
    const lx = redondo ? 18 : larg * (0.92 - o * 0.22), topo = meio - 5 - o * 4, fundo = meio + 6 + o * 26;
    ctx.fillStyle = COR.boca;
    ctx.beginPath(); ctx.moveTo(-lx, canto);
    ctx.bezierCurveTo(-lx * 0.6, topo, lx * 0.6, topo, lx, canto);
    ctx.bezierCurveTo(lx * 0.7, fundo, -lx * 0.7, fundo, -lx, canto);
    ctx.fill();
    ctx.save(); ctx.clip();
    ctx.fillStyle = "rgba(255,255,255,0.92)"; ctx.fillRect(-lx, topo - 2, lx * 2, 4 + o * 4);   // dentes
    ctx.fillStyle = "#e07f9f"; ctx.beginPath(); ctx.ellipse(0, fundo - 3, lx * 0.6, 7 + o * 5, 0, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
    ctx.lineCap = "round";
    ctx.lineWidth = 5.5; ctx.strokeStyle = COR.labio[2];
    ctx.beginPath(); ctx.moveTo(-lx, canto); ctx.bezierCurveTo(-lx * 0.6, topo, lx * 0.6, topo, lx, canto); ctx.stroke();
    ctx.strokeStyle = COR.labio[1]; ctx.lineWidth = 7;
    ctx.beginPath(); ctx.moveTo(lx, canto); ctx.bezierCurveTo(lx * 0.7, fundo, -lx * 0.7, fundo, -lx, canto); ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255,0.55)";
    ctx.beginPath(); ctx.ellipse(-4, canto * 0.25 + fundo * 0.75 + 1, 6, 2, 0, 0, Math.PI * 2); ctx.fill();
  }

  // ---------------------------------------------------------------- efeitos de estado
  function brilhoDeFundo(t, perto) {
    const m = estado.modo, r0 = perto ? 170 : 270;       // some antes da borda do quadro
    let forca = TRANSPARENTE ? 0.2 : 0.28, raio = r0;
    if (m === "ouvindo") { forca = 0.38 + estado.mic * 0.45; raio = r0 + estado.mic * 20 + Math.sin(t * 3) * 4; }
    else if (m === "alerta") forca = 0.35 + (Math.sin(t * 6) * 0.5 + 0.5) * 0.3;
    else if (m === "dormindo" || m === "offline") forca = 0.1;
    const g = ctx.createRadialGradient(0, 55, 30, 0, 55, raio);
    g.addColorStop(0, rgba(estado.brilho, forca)); g.addColorStop(1, rgba(estado.brilho, 0));
    ctx.fillStyle = g;
    ctx.fillRect(-raio, 55 - raio, raio * 2, raio * 2);
  }

  // Ícone do estado, no canto (parado, não gira com o rosto), num selo escuro
  const COM_ICONE = ["dormindo", "pensando", "executando", "aguardando", "privado", "offline"];
  function extras(t) {
    const m = estado.modo;
    if (!COM_ICONE.includes(m)) return;
    ctx.save();
    ctx.translate(196, -100); ctx.scale(0.78, 0.78);
    ctx.fillStyle = "rgba(22,14,38,0.7)"; ctx.beginPath(); ctx.arc(0, 0, 46, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "rgba(203,178,248,0.55)"; ctx.lineWidth = 2.5; ctx.stroke();
    ctx.fillStyle = "#d5c4f7"; ctx.lineCap = "round"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    if (m === "dormindo") {                                 // "z" subindo devagar
      ctx.font = "bold 34px system-ui";
      for (let i = 0; i < 3; i++) {
        const f = (t * 0.3 + i / 3) % 1;
        ctx.globalAlpha = Math.sin(f * Math.PI);
        ctx.fillText("z", -14 + f * 28, 24 - f * 48);
      }
    } else if (m === "pensando") {                          // três brilhos girando
      for (let i = 0; i < 3; i++) {
        const a = t * 2 + i * 2.1;
        estrela(Math.cos(a) * 24, Math.sin(a) * 10, 11 + Math.sin(t * 4 + i) * 4, "rgba(214,194,252,0.95)");
      }
    } else if (m === "executando") {                        // um cristal girando: "trabalhando nisso"
      ctx.save(); ctx.rotate(t * 2.4); cristalGota(0, 0, 11, 20, t); ctx.restore();
      ctx.lineWidth = 4; ctx.strokeStyle = "rgba(203,178,248,0.85)";
      ctx.beginPath(); ctx.arc(0, 0, 34, t * 3, t * 3 + 4); ctx.stroke();
    } else if (m === "aguardando") {
      ctx.font = "bold 62px system-ui"; ctx.globalAlpha = 0.65 + Math.sin(t * 3) * 0.3;
      ctx.fillText("?", 0, 4 + Math.sin(t * 2) * 5);
    } else if (m === "privado") {                           // cadeado de cristal
      ctx.lineWidth = 6; ctx.strokeStyle = COR.metal[1];
      ctx.beginPath(); ctx.arc(0, -8, 15, Math.PI, 0); ctx.stroke();
      ctx.fillStyle = gradCristal(0, 12, 22); ctx.fillRect(-23, -8, 46, 36);
    } else if (m === "offline") {                           // nuvem riscada
      const r = 14;
      ctx.lineWidth = 4.5; ctx.strokeStyle = "rgba(190,180,210,0.95)";
      ctx.beginPath();
      ctx.arc(-r, 4, r, Math.PI * 0.5, Math.PI * 1.5); ctx.arc(0, 4 - r * 0.7, r * 1.2, Math.PI, 0);
      ctx.arc(r * 1.1, 4, r, Math.PI * 1.5, Math.PI * 0.5); ctx.closePath(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(-r * 2, 4 + r * 1.6); ctx.lineTo(r * 2, 4 - r * 2); ctx.stroke();
    }
    ctx.restore();
  }

  // O rosto flutua devagar (sem girar: girar custa mais), inclina pensando ou esperando, acena e nega
  function atualizarCabeca(dt, t) {
    const m = estado.modo;
    let rot = 0, dx = Math.sin(t * 0.55) * 3, dy = 0;
    if (m === "pensando") rot = 0.07;
    else if (m === "aguardando") rot = -0.08;
    else if (m === "ouvindo") dy = -4;
    else if (m === "executando") dx = Math.sin(t * 1.6) * 6;
    else if (m === "offline" || m === "dormindo") dy = 8;
    if (estado.gesto) {
      const g = estado.gesto, f = (t - estado.gestoT) / 0.9;
      if (f >= 1) estado.gesto = null;
      else {
        const env = Math.sin(f * Math.PI);
        if (g === "acenar") dy += Math.sin(f * Math.PI * 4) * 14 * env;
        else if (g === "negar") dx += Math.sin(f * Math.PI * 5) * 16 * env;
        else if (g === "inclinar") rot += 0.15 * env;
      }
    }
    const k = 1 - Math.pow(0.002, dt);
    estado.cabeca.rot = lerp(estado.cabeca.rot, rot, k);
    estado.cabeca.dx = estado.gesto ? dx : lerp(estado.cabeca.dx, dx, k);
    estado.cabeca.dy = estado.gesto ? dy : lerp(estado.cabeca.dy, dy, k);
  }

  // ---------------------------------------------------------------- imagens prontas (economia)
  let camadas = null;
  function prepararCamadas(esc, chave) {
    const k = esc * dpr;
    // uma imagem que cobre o retângulo (x0,y0)-(x1,y1) do modelo, na resolução da tela
    const nova = (desenhar, x0, y0, x1, y1) => {
      const c = document.createElement("canvas");
      c.width = Math.ceil((x1 - x0) * k); c.height = Math.ceil((y1 - y0) * k);
      const brilhos = [];
      ctx = c.getContext("2d"); anotando = brilhos;
      try {
        ctx.setTransform(k, 0, 0, k, -x0 * k, -y0 * k);
        desenhar();
      } finally { ctx = ctxTela; anotando = null; }
      return { c, brilhos, x0, y0, w: c.width / k, h: c.height / k };
    };
    camadas = { chave,
      fundo: nova(() => { luzDosOlhos(); rubor(); renda(-1); renda(1); arabesco(); }, -250, -140, 250, 175),
      monoculo: nova(monoculo, -236, -76, -10, 200),
      iris: nova(iris, -IRIS, -IRIS, IRIS, IRIS) };
  }
  function colar(camada, t) {
    ctx.drawImage(camada.c, camada.x0, camada.y0, camada.w, camada.h);
    for (const [x, y, w, h, t0] of camada.brilhos) faisca(x, y, w, h, t + t0);
  }

  // ---------------------------------------------------------------- quadros por segundo (economia)
  const QPS = { falando: 24, ouvindo: 30, alerta: 30, pensando: 20, executando: 20, aguardando: 20,
                ocioso: 8, offline: 8, dormindo: 8, privado: 8 };
  let ultimo = performance.now(), ultimoDesenho = 0, turboAte = 0, suaveAte = 0, espera = null, pedido = 0;

  // piscada, troca de emoção, gesto: 30 quadros/s por um instante; o olhar passeando: 20 bastam
  function movimento(segundos, rapido = true) {
    const ate = performance.now() + segundos * 1000;
    if (rapido) turboAte = Math.max(turboAte, ate); else suaveAte = Math.max(suaveAte, ate);
    acordar();
  }
  function agendar() {
    if (espera !== null || pedido || document.hidden) return;
    const agora = performance.now();
    const qps = Math.max(QPS[estado.modo] || 10, agora < turboAte ? 30 : 0, agora < suaveAte ? 20 : 0);
    const falta = 1000 / qps - (agora - ultimoDesenho);
    if (falta <= 8) pedido = requestAnimationFrame(quadro);
    else espera = setTimeout(() => { espera = null; pedido = requestAnimationFrame(quadro); }, falta);
  }
  function acordar() {  // algo mudou: não espera o próximo quadro lento
    if (espera !== null) { clearTimeout(espera); espera = null; }
    agendar();
  }
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) { ultimo = performance.now(); acordar(); }
  });

  function quadro(agora) {
    pedido = 0;
    ultimoDesenho = performance.now();   // o relógio de agora (o do quadro pode estar um quadro atrás)
    const dt = Math.min((agora - ultimo) / 1000, 0.25);
    ultimo = agora;
    const t = agora / 1000;
    const m = estado.modo;

    // formato rumo ao alvo (estado > emoção), cor do brilho rumo à do estado
    const alvo = FORMA_MODO[m] || EMOCOES[estado.emocao] || EMOCOES.neutra;
    const k = 1 - Math.pow(0.001, dt);
    for (const c in alvo) estado.atual[c] = lerp(estado.atual[c], alvo[c], k);
    const p = estado.atual;
    const corAlvo = m === "alerta" ? COR.haloAlerta : m === "ouvindo" ? COR.haloOuvindo : COR.halo;
    for (let i = 0; i < 3; i++) estado.brilho[i] = lerp(estado.brilho[i], corAlvo[i], 1 - Math.pow(0.02, dt));
    estado.cinza = lerp(estado.cinza, m === "offline" ? 0.75 : 0, 1 - Math.pow(0.02, dt));
    const abreAlvo = m === "falando" ? Math.min(1, estado.voz * 1.1) : p.bocaAb;
    estado.boca = lerp(estado.boca, abreAlvo, 1 - Math.pow(0.0005, dt));

    // piscadas e olhar
    estado.proxPiscada -= dt;
    if (estado.proxPiscada <= 0 && p.abertura > 0.3) {
      estado.piscar = 1;
      estado.proxPiscada = 2.5 + Math.random() * 4;
      movimento(0.25);
    }
    estado.piscar = Math.max(0, estado.piscar - dt * 7);
    estado.proxOlhar -= dt;
    if (m === "pensando") estado.alvoOlhar = { x: 0.55, y: -0.6 };
    else if (m === "ouvindo" || m === "aguardando" || m === "alerta" || m === "falando") estado.alvoOlhar = { x: 0, y: 0 };
    else if (m === "executando") estado.alvoOlhar = { x: Math.sin(t * 1.3) * 0.6, y: 0.35 };
    else if (estado.emocao === "triste" && !FORMA_MODO[m]) estado.alvoOlhar = { x: -0.2, y: 0.5 };
    else if (estado.proxOlhar <= 0 && p.abertura > 0.3) {
      estado.alvoOlhar = Math.random() < 0.45 ? { x: 0, y: 0 }
        : { x: (Math.random() - 0.5) * 1.2, y: (Math.random() - 0.5) * 0.6 };
      estado.proxOlhar = 1.2 + Math.random() * 3;
      movimento(0.45, false);
    }
    estado.olhar.x = lerp(estado.olhar.x, estado.alvoOlhar.x, 1 - Math.pow(0.0005, dt));
    estado.olhar.y = lerp(estado.olhar.y, estado.alvoOlhar.y, 1 - Math.pow(0.0005, dt));
    atualizarCabeca(dt, t);

    // enquadramento
    const f = W < 260 || H < 220 ? PERTO : GRANDE;
    const esc = Math.min(W / (f.x1 - f.x0), H / (f.y1 - f.y0));
    const ox = W / 2 - ((f.x0 + f.x1) / 2) * esc, oy = H / 2 - ((f.y0 + f.y1) / 2) * esc;
    if (!(esc > 0)) { agendar(); return; }             // ainda sem tamanho na tela
    const chave = `${W}x${H}x${dpr}`;
    if (!camadas || camadas.chave !== chave) prepararCamadas(esc, chave);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!TRANSPARENTE) {
      const g = ctx.createRadialGradient(W * dpr / 2, H * dpr * 0.45, 0, W * dpr / 2, H * dpr * 0.45, Math.max(W, H) * dpr * 0.8);
      g.addColorStop(0, "#241838"); g.addColorStop(1, "#0b0712");
      ctx.fillStyle = g; ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
    const base = () => ctx.setTransform(esc * dpr, 0, 0, esc * dpr, ox * dpr, oy * dpr);
    const flutua = m === "dormindo" || m === "privado" ? Math.sin(t * 1.2) * 5 : Math.sin(t * 1.6) * 3;
    const semCor = estado.cinza > 0.02 && "filter" in ctx;
    if (semCor) ctx.filter = `saturate(${1 - estado.cinza}) brightness(${1 - estado.cinza * 0.25})`;

    // de perto o brilho de fundo só aparece quando diz algo (ouvindo, alerta)
    if (f !== PERTO || m === "ouvindo" || m === "alerta") { base(); brilhoDeFundo(t, f === PERTO); }
    const cab = estado.cabeca;
    base();                                            // o rosto gira em volta do centro dele
    ctx.translate(cab.dx, cab.dy + flutua);
    if (Math.abs(cab.rot) > 0.001) { ctx.translate(0, 70); ctx.rotate(cab.rot); ctx.translate(0, -70); }
    colar(camadas.fundo, t);                          // brilho dos olhos, renda, arabesco
    olho(-1, p); olho(1, p);
    sobrancelhas(p); boca(p);
    colar(camadas.monoculo, t);
    if (semCor) ctx.filter = "none";
    base(); extras(t);
    ctx.setTransform(1, 0, 0, 1, 0, 0);

    agendar();
  }

  window.Rosto = {
    modo(m) { if (m !== estado.modo) { estado.modo = m; movimento(0.8); } },
    emocao(e) {
      const nova = EMOCOES[e] ? e : "neutra";
      if (nova !== estado.emocao) { estado.emocao = nova; movimento(0.8); }
    },
    voz(v) { estado.voz = v; },
    mic(v) { estado.mic = v; },
    gesto(g) { estado.gesto = g; estado.gestoT = performance.now() / 1000; movimento(1); },
    get estado() { return estado; },
  };
  redimensionar();
  agendar();
})();
