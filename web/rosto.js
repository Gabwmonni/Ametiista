// Ametista: o rosto dela (modelo simplificado da ficha de personagem), desenhado em canvas.
// Cabelo prata com reflexos iridescentes preso num coque meio bagunçado, olhos azul-cristal com íris em
// estrela, monóculo de cristal sobre o olho direito dela, filigrana de metal líquido com gotas de cristal
// sob os olhos, brincos longos e a estrela de cristal no coque. Pisca, olha em volta, respira, fala (a boca
// segue a voz), tem emoções, estados e gestos de cabeça.
//
// Estados (Rosto.modo):  dormindo | ocioso | ouvindo | pensando | falando |
//                        executando | alerta | offline | aguardando | privado
// Emoções (Rosto.emocao): neutra | feliz | pensativa | surpresa | triste | brava
// Gestos (Rosto.gesto):  acenar (sim com a cabeça) | negar | inclinar
//
// Leve de propósito: cabelo, pele e joias são desenhados uma vez numa imagem pronta, e a cada quadro só se
// redesenha o que mexe (olhos, boca, brilhos); 24 quadros/s falando, 30 só no instante de uma piscada, 8 parada
// ou dormindo, e nada quando a janela ou o app estão escondidos. Em tamanho pequeno (barra do PC, celular) mostra
// o rosto de perto, com as bordas esfumadas; em tamanho grande, o busto.
(() => {
  const canvas = document.getElementById("rosto");
  const ctxTela = canvas.getContext("2d");
  let ctx = ctxTela;                     // troca para a camada que está sendo preparada (veja prepararCamadas)
  const TRANSPARENTE = canvas.dataset.transparente === "1";

  // ---------------------------------------------------------------- paleta (medida na ficha)
  const COR = {
    pele: "#fbf3f7", pele2: "#f1e1eb", peleSombra: "rgba(205,168,200,0.38)", blush: "246,160,200",
    labioCima: "#d98aab", labioBaixo: "#eaa3c0", boca: "#6b2c52",
    cabelo: ["#ffffff", "#f1ebf9", "#ddd1f2", "#c7cbf6"], cabeloLinha: "rgba(160,138,205,0.5)",
    cabeloSombra: "rgba(170,150,215,0.45)",
    esclera: "#fdfbff", iris: ["#f6f9ff", "#bdcbfb", "#8f9df1", "#5561c2"], pupila: "#2b2c6c",
    cilios: "#2f2438", sombraOlho: "244,178,222", sobrancelha: "#b9a5d3",
    metal: "#e6c7a2", metalEsc: "#b48a64", metalClaro: "#fff3e2", cristal: ["#ffffff", "#fcc9f2", "#cbb2f8", "#b3cefb"],
    halo: [203, 178, 248], haloAlerta: [255, 176, 120], haloOuvindo: [179, 206, 251],
  };

  // Formato alvo de cada emoção (tudo em números: o rosto passa de um para outro suavemente)
  const EMOCOES = {
    neutra:    { abertura: 1.00, sorriso: 0.10, sobrY: 0,  sobrAng: 0.00, boca: 0.25, bocaAb: 0.00, blush: 0.55, assim: 0 },
    feliz:     { abertura: 0.90, sorriso: 0.50, sobrY: 4,  sobrAng: -0.1, boca: 1.00, bocaAb: 0.08, blush: 1.00, assim: 0 },
    pensativa: { abertura: 0.88, sorriso: 0.06, sobrY: 6,  sobrAng: 0.10, boca: 0.05, bocaAb: 0.00, blush: 0.45, assim: 1 },
    surpresa:  { abertura: 1.14, sorriso: 0.00, sobrY: 18, sobrAng: 0.00, boca: 0.00, bocaAb: 0.42, blush: 0.60, assim: 0 },
    triste:    { abertura: 0.84, sorriso: 0.04, sobrY: 6,  sobrAng: -0.8, boca: -0.60, bocaAb: 0.00, blush: 0.35, assim: 0 },
    brava:     { abertura: 0.78, sorriso: 0.12, sobrY: -8, sobrAng: 0.80, boca: -0.15, bocaAb: 0.00, blush: 0.40, assim: 0 },
  };
  // Estados que mandam no formato, por cima da emoção
  const FORMA_MODO = {
    dormindo:   { abertura: 0.00, sorriso: 0.00, sobrY: 0,  sobrAng: 0.0, boca: 0.30, bocaAb: 0.00, blush: 0.40, assim: 0 },
    privado:    { abertura: 0.00, sorriso: 0.00, sobrY: 2,  sobrAng: 0.0, boca: 0.60, bocaAb: 0.00, blush: 0.60, assim: 0 },
    offline:    { abertura: 0.55, sorriso: 0.05, sobrY: 0,  sobrAng: -0.3, boca: -0.10, bocaAb: 0.00, blush: 0.20, assim: 0 },
    alerta:     { abertura: 1.14, sorriso: 0.00, sobrY: 16, sobrAng: 0.0, boca: 0.00, bocaAb: 0.40, blush: 0.60, assim: 0 },
    executando: { abertura: 0.86, sorriso: 0.10, sobrY: -2, sobrAng: 0.35, boca: 0.10, bocaAb: 0.00, blush: 0.45, assim: 0 },
    aguardando: { abertura: 1.02, sorriso: 0.10, sobrY: 10, sobrAng: 0.0, boca: 0.35, bocaAb: 0.00, blush: 0.60, assim: 1 },
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
  // enquadramento: de perto (tamanhos pequenos) ou busto (tamanhos grandes), em unidades do modelo
  const PERTO = { x0: -250, x1: 250, y0: -290, y1: 258 };
  const BUSTO = { x0: -430, x1: 430, y0: -610, y1: 560 };

  // desenha um caminho a partir de uma lista: ["M", x, y], ["C", ...6], ["Q", ...4], ["L", x, y]
  function caminho(cmds, espelho = 1) {
    ctx.beginPath();
    for (const [c, ...v] of cmds) {
      const p = v.map((n, i) => (i % 2 === 0 ? n * espelho : n));
      if (c === "M") ctx.moveTo(...p); else if (c === "L") ctx.lineTo(...p);
      else if (c === "C") ctx.bezierCurveTo(...p); else if (c === "Q") ctx.quadraticCurveTo(...p);
    }
    ctx.closePath();
  }
  function gradCabelo(y0, y1, fundo = 0) {
    const g = ctx.createLinearGradient(0, y0, 0, y1);
    g.addColorStop(0, COR.cabelo[fundo]); g.addColorStop(0.35, COR.cabelo[1 + fundo]);
    g.addColorStop(0.8, COR.cabelo[2]); g.addColorStop(1, COR.cabelo[3]);
    return g;
  }
  const bez = (a, b, c, d, u) => {
    const v = 1 - u;
    return v * v * v * a + 3 * v * v * u * b + 3 * v * u * u * c + u * u * u * d;
  };
  // Uma mecha: larga na raiz (x0,y0), afinando até a ponta (x1,y1); b1 e b2 curvam o meio para um lado.
  // Preenche com o estilo atual; com contorno, marca as bordas (sem riscar a raiz).
  function mecha(x0, y0, x1, y1, larg, b1 = 0, b2 = b1, contorno = true) {
    const dx = x1 - x0, dy = y1 - y0, L = Math.hypot(dx, dy) || 1;
    const nx = -dy / L, ny = dx / L, h = larg / 2;
    const c1x = x0 + dx * 0.33 + nx * b1, c1y = y0 + dy * 0.33 + ny * b1;
    const c2x = x0 + dx * 0.66 + nx * b2, c2y = y0 + dy * 0.66 + ny * b2;
    ctx.beginPath();
    ctx.moveTo(x0 - nx * h, y0 - ny * h);
    ctx.bezierCurveTo(c1x - nx * h * 0.8, c1y - ny * h * 0.8, c2x - nx * h * 0.35, c2y - ny * h * 0.35, x1, y1);
    ctx.bezierCurveTo(c2x + nx * h * 0.35, c2y + ny * h * 0.35, c1x + nx * h * 0.8, c1y + ny * h * 0.8, x0 + nx * h, y0 + ny * h);
    ctx.fill();
    if (contorno) ctx.stroke();
  }
  // ---------------------------------------------------------------- partes do corpo
  function cabeloAtras(t) {
    // fios soltos que escaparam do coque, caindo atrás até os ombros
    ctx.fillStyle = gradCabelo(-60, 420, 1);
    ctx.strokeStyle = COR.cabeloLinha; ctx.lineWidth = 1.6;
    for (const s of [-1, 1]) {
      ctx.save(); ctx.scale(s, 1);
      mecha(200, -60, 236, 372, 50, -20, 18);
      mecha(174, 10, 146, 336, 30, 14, -14);
      ctx.restore();
    }
    // volume da cabeça por trás (o cabelo está preso: vai só até a altura das orelhas)
    ctx.fillStyle = gradCabelo(-420, 150, 1);
    caminho([["M", -228, 40], ["C", -254, -250, -120, -418, 10, -416], ["C", 150, -414, 264, -250, 228, 40],
      ["C", 216, 100, 198, 126, 170, 136], ["L", -170, 136], ["C", -198, 126, -216, 100, -228, 40]]);
    ctx.fill();
    // o coque meio bagunçado: voltas de cabelo presas no alto da cabeça
    for (const [x, y, rx, ry, a, fundo] of [[-58, -468, 94, 62, -0.35, 1], [86, -474, 100, 68, 0.4, 1], [16, -530, 84, 50, 0.05, 0]]) {
      ctx.fillStyle = gradCabelo(y - ry, y + ry + 50, fundo);
      ctx.beginPath(); ctx.ellipse(x, y, rx, ry, a, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = COR.cabeloSombra; ctx.lineWidth = 3; ctx.lineCap = "round";
      ctx.beginPath(); ctx.ellipse(x, y + 10, rx * 0.72, ry * 0.5, a, Math.PI * 1.02, Math.PI * 1.95); ctx.stroke();
      ctx.beginPath(); ctx.ellipse(x, y + 4, rx * 0.4, ry * 0.3, a, Math.PI * 0.9, Math.PI * 2.1); ctx.stroke();
      ctx.strokeStyle = "rgba(255,255,255,0.9)"; ctx.lineWidth = 4;
      ctx.beginPath(); ctx.ellipse(x, y, rx * 0.86, ry * 0.76, a, Math.PI * 1.18, Math.PI * 1.55); ctx.stroke();
    }
    // fios arrepiados escapando do coque
    ctx.strokeStyle = COR.cabelo[2]; ctx.lineWidth = 2.4;
    ctx.beginPath();
    for (const [x0, y0, x1, y1, x2, y2] of [[-128, -478, -178, -500, -196, -540], [170, -500, 214, -520, 226, -556],
      [176, -452, 226, -452, 246, -480], [-30, -570, -70, -596, -104, -592]]) {
      ctx.moveTo(x0, y0); ctx.quadraticCurveTo(x1, y1, x2, y2);
    }
    ctx.stroke();
    estrelaDeCristal(150, -500, 60, t);                     // os ornamentos de cristal do coque
    estrelaDeCristal(-122, -498, 40, t + 2);
    ctx.strokeStyle = COR.metal; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(176, -470); ctx.quadraticCurveTo(214, -420, 212, -366); ctx.stroke();
    cristalGota(212, -348, 9, 18, t + 1);
  }
  function corpo() {
    const g = ctx.createLinearGradient(0, 240, 0, 560);
    g.addColorStop(0, COR.pele2); g.addColorStop(0.4, COR.pele); g.addColorStop(1, COR.pele2);
    ctx.fillStyle = g;
    caminho([["M", -42, 220], ["C", -42, 300, -44, 340, -50, 370], ["C", -150, 394, -300, 430, -338, 560], ["L", 338, 560],
      ["C", 300, 430, 150, 394, 50, 370], ["C", 44, 340, 42, 300, 42, 220]]);
    ctx.fill();
    ctx.fillStyle = COR.peleSombra;                      // sombra do queixo no pescoço
    ctx.beginPath(); ctx.ellipse(0, 262, 50, 30, 0, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "rgba(205,168,200,0.35)"; ctx.lineWidth = 3; ctx.lineCap = "round";   // clavículas
    ctx.beginPath(); ctx.moveTo(-40, 408); ctx.quadraticCurveTo(-100, 398, -150, 410);
    ctx.moveTo(40, 408); ctx.quadraticCurveTo(100, 398, 150, 410); ctx.stroke();
    // tecido lilás com borda de metal, e o colar com uma gota de cristal
    const tg = ctx.createLinearGradient(0, 470, 0, 560);
    tg.addColorStop(0, "#e6dcf6"); tg.addColorStop(1, "#cbbcec");
    ctx.fillStyle = tg;
    caminho([["M", -338, 560], ["C", -250, 500, -120, 488, 0, 505], ["C", 120, 488, 250, 500, 338, 560]]);
    ctx.fill();
    ctx.strokeStyle = COR.metal; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(-290, 530); ctx.bezierCurveTo(-200, 485, -110, 480, 0, 497);
    ctx.bezierCurveTo(110, 480, 200, 485, 290, 530); ctx.stroke();
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(-88, 384); ctx.quadraticCurveTo(0, 452, 88, 384); ctx.stroke();
    cristalGota(0, 456, 12, 24);
  }
  function rostoBase() {
    const g = ctx.createRadialGradient(-30, -30, 40, 0, 40, 320);
    g.addColorStop(0, COR.pele); g.addColorStop(0.7, COR.pele); g.addColorStop(1, COR.pele2);
    ctx.fillStyle = g;
    caminho([["M", -166, -170], ["C", -174, -50, -168, 58, -142, 154], ["C", -110, 236, -50, 290, 0, 298],
      ["C", 50, 290, 110, 236, 142, 154], ["C", 168, 58, 174, -50, 166, -170], ["C", 140, -300, -140, -300, -166, -170]]);
    ctx.fill();
    // sombra do cabelo na testa (só dentro do rosto)
    ctx.save(); ctx.clip();
    const sg = ctx.createLinearGradient(0, -200, 0, -60);
    sg.addColorStop(0, "rgba(190,170,225,0.5)"); sg.addColorStop(1, "rgba(190,170,225,0)");
    ctx.fillStyle = sg; ctx.fillRect(-180, -220, 360, 170);
    ctx.restore();
    // nariz: uma sombra delicada de lado e a pontinha
    ctx.strokeStyle = "rgba(206,160,190,0.28)"; ctx.lineWidth = 5; ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(14, 64); ctx.quadraticCurveTo(20, 100, 14, 122); ctx.stroke();
    ctx.strokeStyle = "rgba(200,150,182,0.6)"; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(-8, 132); ctx.quadraticCurveTo(2, 138, 12, 131); ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255,0.75)"; ctx.beginPath(); ctx.ellipse(-2, 116, 3.5, 6, 0, 0, Math.PI * 2); ctx.fill();
  }
  function bochechas(p) {
    const g = (x) => {
      const r = ctx.createRadialGradient(x, 100, 4, x, 100, 50);
      r.addColorStop(0, `rgba(${COR.blush},${0.34 * p.blush})`); r.addColorStop(1, `rgba(${COR.blush},0)`);
      return r;
    };
    for (const s of [-1, 1]) { ctx.fillStyle = g(s * 112); ctx.beginPath(); ctx.ellipse(s * 112, 100, 56, 30, 0, 0, Math.PI * 2); ctx.fill(); }
  }

  // Sombra rosa-lilás das pálpebras, esfumada até o canto de fora (fica na camada pronta)
  function sombrasDosOlhos() {
    for (const s of [-1, 1]) {
      const sg = ctx.createRadialGradient(s * 122, -14, 6, s * 112, -8, 84);
      sg.addColorStop(0, `rgba(${COR.sombraOlho},0.42)`); sg.addColorStop(0.55, `rgba(${COR.sombraOlho},0.2)`);
      sg.addColorStop(1, `rgba(${COR.sombraOlho},0)`);
      ctx.fillStyle = sg; ctx.beginPath(); ctx.ellipse(s * 110, -8, 86, 40, s * -0.14, 0, Math.PI * 2); ctx.fill();
    }
  }

  // A íris azul-cristal com raios em estrela, a pupila com a estrela e os brilhos (desenhada uma vez, em volta
  // de 0,0; o olho só a posiciona)
  const IRIS = 42;
  function iris() {
    const r = 40;
    const gi = ctx.createRadialGradient(0, -4, 3, 0, 0, r);
    gi.addColorStop(0, COR.iris[0]); gi.addColorStop(0.35, COR.iris[1]); gi.addColorStop(0.75, COR.iris[2]); gi.addColorStop(1, COR.iris[3]);
    ctx.fillStyle = gi; ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.55)"; ctx.lineWidth = 1.8;
    ctx.beginPath();
    for (let i = 0; i < 16; i++) {
      const a = (i / 16) * Math.PI * 2 + 0.2, r0 = i % 2 ? 14 : 11, r1 = i % 2 ? 30 : 37;
      ctx.moveTo(Math.cos(a) * r0, Math.sin(a) * r0);
      ctx.lineTo(Math.cos(a) * r1, Math.sin(a) * r1);
    }
    ctx.stroke();
    ctx.fillStyle = COR.pupila; ctx.beginPath(); ctx.arc(0, 0, 11, 0, Math.PI * 2); ctx.fill();
    estrela(0, 0, 13, "rgba(255,255,255,0.95)");                          // a estrela no centro
    ctx.fillStyle = "rgba(255,255,255,0.95)";
    ctx.beginPath(); ctx.ellipse(-15, -14, 8.5, 6.5, -0.5, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(15, 13, 4, 0, Math.PI * 2); ctx.fill();
  }

  // Um olho amendoado. s = -1 (esquerda da tela) ou 1. p = formato atual.
  function olho(s, p) {
    const aberto = Math.max(0, p.abertura * (1 - estado.piscar));
    const meio = 22;                                   // linha em que as pálpebras se encontram
    const sobe = p.sorriso * 24;                       // pálpebra de baixo sobe no sorriso
    const ab = (y) => meio + (y - meio) * Math.min(aberto, 1.2);
    const ix = s * 30, ox = s * 166;
    const cima = [[ix, ab(30)], [s * 52, ab(-24)], [s * 128, ab(-40)], [ox, ab(-2)]];
    const baixo = [[ox, ab(-2)], [s * 148, ab(52) - sobe], [s * 66, ab(58) - sobe], [ix, ab(30)]];
    const forma = () => {
      ctx.beginPath(); ctx.moveTo(...cima[0]);
      ctx.bezierCurveTo(...cima[1], ...cima[2], ...cima[3]);
      ctx.bezierCurveTo(...baixo[1], ...baixo[2], ...baixo[3]);
      ctx.closePath();
    };
    // dobra da pálpebra (some com o olho fechado)
    ctx.strokeStyle = `rgba(180,140,190,${0.55 * Math.min(aberto, 1)})`; ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.moveTo(s * 46, cima[0][1] - 40 * Math.min(aberto, 1));
    ctx.bezierCurveTo(s * 80, -52, s * 132, -60, s * 160, -26); ctx.stroke();

    if (aberto > 0.06) {
      ctx.save();
      forma(); ctx.fillStyle = COR.esclera; ctx.fill(); ctx.clip();
      // íris azul-cristal com raios em estrela
      const cx = s * 98 + estado.olhar.x * 18, cy = 16 + estado.olhar.y * 10;
      ctx.drawImage(camadas.iris.c, cx - IRIS, cy - IRIS, IRIS * 2, IRIS * 2);
      // sombra da pálpebra sobre o olho
      const sp = ctx.createLinearGradient(0, cima[2][1] - 4, 0, cima[2][1] + 34);
      sp.addColorStop(0, "rgba(110,80,150,0.4)"); sp.addColorStop(1, "rgba(110,80,150,0)");
      ctx.fillStyle = sp; ctx.fillRect(Math.min(ix, ox), cima[2][1] - 12, Math.abs(ox - ix), 60);
      ctx.restore();
      // linha de baixo, rosada, com cílios finos
      ctx.strokeStyle = "rgba(214,140,180,0.8)"; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(...baixo[0]); ctx.bezierCurveTo(...baixo[1], ...baixo[2], s * 52, baixo[3][1] + 4); ctx.stroke();
    }
    // linha dos cílios de cima: fina no canto de dentro, grossa para fora, com um "gatinho" e cílios longos
    ctx.strokeStyle = COR.cilios; ctx.lineCap = "round"; ctx.lineJoin = "round";
    if (aberto > 0.06) {
      ctx.lineWidth = 4;
      ctx.beginPath(); ctx.moveTo(...cima[0]); ctx.bezierCurveTo(...cima[1], ...cima[2], ...cima[3]); ctx.stroke();
      ctx.lineWidth = 8;
      ctx.beginPath(); ctx.moveTo(lerp(ix, s * 70, 0.9), lerp(cima[0][1], cima[1][1], 0.9) - 2);
      ctx.bezierCurveTo(s * 100, cima[2][1] - 4, s * 140, cima[2][1] + 2, ox, cima[3][1]);
      ctx.lineTo(ox + s * 16, cima[3][1] - 12);          // o "gatinho" no canto de fora
      ctx.stroke();
      ctx.lineWidth = 3;
      ctx.beginPath();
      for (const [f, comp, abre] of [[0.62, 16, 0.2], [0.8, 20, 0.35], [0.95, 22, 0.55]]) {
        const x = lerp(s * 70, ox, f), y = lerp(cima[2][1], cima[3][1], f) - 3;
        ctx.moveTo(x, y); ctx.quadraticCurveTo(x + s * comp * abre * 0.5, y - comp * 0.8, x + s * comp * abre * 1.6, y - comp);
      }
      ctx.stroke();
    } else {
      ctx.lineWidth = 6;
      ctx.beginPath(); ctx.moveTo(ix, meio + 8); ctx.bezierCurveTo(s * 66, meio + 30, s * 132, meio + 30, ox, meio + 2); ctx.stroke();
      ctx.lineWidth = 3;
      ctx.beginPath();
      for (const f of [0.6, 0.8, 0.95]) {
        const x = lerp(s * 66, ox, f), y = meio + 26 - f * 20;
        ctx.moveTo(x, y); ctx.quadraticCurveTo(x + s * 4, y + 8, x + s * 10, y + 13);
      }
      ctx.stroke();
    }
  }

  // Filigrana de metal líquido sob os olhos: renda fina em arcos, contas e gotas de cristal penduradas
  // (mais longas no olho sem o monóculo, como lágrimas de cristal)
  function lagrimaDeCristal(s, t) {
    const P = [[50, 74], [84, 92], [130, 88], [164, 54]];            // a linha que acompanha a pálpebra de baixo
    const ponto = (u) => [s * bez(P[0][0], P[1][0], P[2][0], P[3][0], u), bez(P[0][1], P[1][1], P[2][1], P[3][1], u)];
    ctx.strokeStyle = COR.metal; ctx.lineWidth = 1.8; ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(s * P[0][0], P[0][1]);
    ctx.bezierCurveTo(s * P[1][0], P[1][1], s * P[2][0], P[2][1], s * P[3][0], P[3][1]);
    const us = [0.1, 0.27, 0.44, 0.61, 0.78, 0.94];
    const pts = us.map(ponto);
    for (let i = 0; i < pts.length - 1; i++) {                       // arcos da renda
      const [ax, ay] = pts[i], [bx, by] = pts[i + 1];
      ctx.moveTo(ax, ay); ctx.quadraticCurveTo((ax + bx) / 2, (ay + by) / 2 + 13, bx, by);
    }
    ctx.stroke();
    ctx.fillStyle = COR.metalClaro;
    for (const [x, y] of pts) { ctx.beginPath(); ctx.arc(x, y, 2.4, 0, Math.PI * 2); ctx.fill(); }
    const gotas = s > 0 ? [[1, 16, 0.75], [2, 30, 1], [3, 20, 0.85], [4, 10, 0.7]] : [[2, 10, 0.65], [3, 16, 0.7]];
    for (const [i, comp, tam] of gotas) {
      const [x, y] = pts[i];
      ctx.beginPath(); ctx.moveTo(x, y + 2); ctx.lineTo(x, y + comp); ctx.stroke();
      cristalGota(x, y + comp + 12 * tam, 6.5 * tam, 12 * tam, t + i);
    }
  }
  function sobrancelhas(p) {
    ctx.fillStyle = COR.sobrancelha;
    for (const s of [-1, 1]) {
      const extra = p.assim && s > 0 ? 10 : 0;           // uma sobrancelha levantada (dúvida)
      const y = -78 - p.sobrY - extra;
      const dentro = y + p.sobrAng * 20, fora = y + 8 - p.sobrAng * 6, topo = Math.min(dentro, fora) - 20;
      // fina e arqueada: mais cheia perto do nariz, afinando para fora
      ctx.beginPath(); ctx.moveTo(s * 42, dentro + 4);
      ctx.quadraticCurveTo(s * 98, topo, s * 158, fora + 4);
      ctx.quadraticCurveTo(s * 100, topo + 9, s * 46, dentro + 11);
      ctx.closePath(); ctx.fill();
    }
  }
  function boca(p) {
    const c = p.boca, o = estado.boca;
    const y = 196, larg = 32;
    const canto = y - c * 8, meio = y + c * 6;
    if (o < 0.05) {
      // lábio de baixo, cheio e rosado, com brilho
      ctx.fillStyle = COR.labioBaixo;
      ctx.beginPath(); ctx.moveTo(-larg * 0.75, canto + 2);
      ctx.bezierCurveTo(-18, meio + 20, 18, meio + 20, larg * 0.75, canto + 2);
      ctx.quadraticCurveTo(0, meio + 4, -larg * 0.75, canto + 2); ctx.fill();
      ctx.fillStyle = "rgba(255,255,255,0.6)"; ctx.beginPath(); ctx.ellipse(-4, meio + 12, 7, 2.5, 0, 0, Math.PI * 2); ctx.fill();
      // lábio de cima com arco do cupido
      ctx.fillStyle = COR.labioCima;
      ctx.beginPath(); ctx.moveTo(-larg, canto);
      ctx.quadraticCurveTo(-14, meio - 12, -5, meio - 8); ctx.quadraticCurveTo(0, meio - 5, 5, meio - 8);
      ctx.quadraticCurveTo(14, meio - 12, larg, canto); ctx.quadraticCurveTo(0, meio + 4, -larg, canto); ctx.fill();
      ctx.strokeStyle = "rgba(170,90,130,0.75)"; ctx.lineWidth = 2.5; ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(-larg, canto); ctx.quadraticCurveTo(0, meio + 5, larg, canto); ctx.stroke();
      return;
    }
    const redondo = p.bocaAb > 0.3 && estado.modo !== "falando";                // surpresa: um "o"
    const lx = redondo ? 18 : larg - o * 5, topo = meio - 6 - o * 3, fundo = meio + 6 + o * 30;
    ctx.fillStyle = COR.boca;
    ctx.beginPath(); ctx.moveTo(-lx, canto);
    ctx.bezierCurveTo(-lx * 0.6, topo, lx * 0.6, topo, lx, canto);
    ctx.bezierCurveTo(lx * 0.7, fundo, -lx * 0.7, fundo, -lx, canto);
    ctx.fill();
    ctx.save(); ctx.clip();
    ctx.fillStyle = "rgba(255,255,255,0.9)"; ctx.fillRect(-lx, topo - 2, lx * 2, 4 + o * 4);   // dentes
    ctx.fillStyle = "#e07f9f"; ctx.beginPath(); ctx.ellipse(0, fundo - 3, lx * 0.6, 7 + o * 5, 0, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
    ctx.lineWidth = 5; ctx.strokeStyle = COR.labioCima;
    ctx.beginPath(); ctx.moveTo(-lx, canto); ctx.bezierCurveTo(-lx * 0.6, topo, lx * 0.6, topo, lx, canto); ctx.stroke();
    ctx.strokeStyle = COR.labioBaixo; ctx.lineWidth = 6;
    ctx.beginPath(); ctx.moveTo(lx, canto); ctx.bezierCurveTo(lx * 0.7, fundo, -lx * 0.7, fundo, -lx, canto); ctx.stroke();
  }

  function cabeloFrente(t) {
    // mechas longas e onduladas que emolduram o rosto, dos dois lados, balançando de leve
    // (desenhadas antes do topo da cabeça, que esconde as raízes)
    ctx.strokeStyle = COR.cabeloLinha; ctx.lineWidth = 1.8; ctx.lineJoin = "round"; ctx.lineCap = "round";
    ctx.fillStyle = gradCabelo(-240, 340);
    for (const s of [-1, 1]) {
      ctx.save(); ctx.scale(s, 1);
      mecha(176, -290, 238, 334, 50, -44, 30);
      mecha(170, -250, 208, 250, 18, 4, -20);
      mecha(160, -270, 150, 196, 36, -26, 22);
      ctx.restore();
    }
    ctx.fillStyle = gradCabelo(-420, -120);
    // topo da cabeça (a borda de baixo fica escondida pela franja)
    caminho([["M", -214, -120], ["C", -240, -330, -100, -410, 0, -408], ["C", 130, -406, 244, -320, 214, -120],
      ["C", 150, -220, -150, -220, -214, -120]]);
    ctx.fill();
    // franja meio bagunçada: repartida à esquerda e varrida para o lado, com pontas de alturas diferentes
    ctx.fillStyle = gradCabelo(-400, -80, 1);
    mecha(-40, -396, 200, -118, 150, -50, -40);
    mecha(-32, -386, 152, -84, 108, -40, -20);
    ctx.fillStyle = gradCabelo(-400, -80);
    mecha(-44, -386, 82, -100, 88, -30, -10);
    mecha(-56, -382, 14, -122, 66, -16, -4);
    mecha(-78, -392, -208, -128, 118, 36, 22);
    mecha(-70, -388, -130, -100, 80, 20, 8);
    mecha(-62, -386, -62, -146, 50, 6, -4);
    // fios soltos cruzando o rosto (como na ficha)
    ctx.strokeStyle = "rgba(240,234,252,0.95)"; ctx.lineWidth = 2.2;
    ctx.beginPath();
    ctx.moveTo(-20, -340); ctx.bezierCurveTo(40, -240, 20, -120, 64, -40);
    ctx.moveTo(110, -300); ctx.bezierCurveTo(170, -200, 150, -80, 196, 30);
    ctx.moveTo(-110, -330); ctx.bezierCurveTo(-190, -210, -150, -90, -204, 60);
    ctx.stroke();
    // brilho prateado e reflexos iridescentes
    ctx.strokeStyle = "rgba(255,255,255,0.9)"; ctx.lineWidth = 7;
    ctx.beginPath(); ctx.arc(0, -150, 200, Math.PI * 1.24, Math.PI * 1.42); ctx.stroke();
    ctx.lineWidth = 4; ctx.beginPath(); ctx.arc(0, -150, 200, Math.PI * 1.56, Math.PI * 1.7); ctx.stroke();
    ctx.lineWidth = 3;
    ctx.strokeStyle = "rgba(252,190,236,0.8)";
    ctx.beginPath(); ctx.moveTo(-200, -130); ctx.bezierCurveTo(-226, 0, -204, 130, -222, 250); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(40, -372); ctx.bezierCurveTo(110, -340, 160, -270, 180, -190); ctx.stroke();
    ctx.strokeStyle = "rgba(170,200,251,0.85)";
    ctx.beginPath(); ctx.moveTo(204, -110); ctx.bezierCurveTo(226, 10, 210, 140, 224, 260); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(-96, -372); ctx.bezierCurveTo(-150, -330, -180, -270, -190, -200); ctx.stroke();
    estrelaDeCristal(-190, -262, 40, t + 3);                                    // cristal preso na lateral
  }
  // Brincos longos de cristal (o cabelo preso deixa à mostra)
  function brincos(t) {
    for (const s of [-1, 1]) {
      const x = s * 176, y = 104;
      ctx.fillStyle = COR.metal; ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = COR.metal; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + s * 3, y + 40); ctx.moveTo(x + s * 3, y + 70); ctx.lineTo(x + s * 5, y + 96); ctx.stroke();
      cristalGota(x + s * 3, y + 56, 9, 17, t + s);
      cristalGota(x + s * 5, y + 120, 12, 26, t + s + 1);
    }
  }
  // Monóculo de cristal sobre o olho direito dela (o da esquerda na tela)
  const LENTE = { x: -98, y: 18, r: 80 };
  function monoculo(t) {
    const { x: cx, y: cy, r } = LENTE;
    ctx.save();
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.clip();
    const gl = ctx.createLinearGradient(cx - r, cy - r, cx + r, cy + r);
    gl.addColorStop(0, "rgba(252,201,242,0.2)"); gl.addColorStop(0.5, "rgba(236,226,255,0.06)"); gl.addColorStop(1, "rgba(179,206,251,0.22)");
    ctx.fillStyle = gl; ctx.fillRect(cx - r, cy - r, r * 2, r * 2);
    // borda iridescente do cristal, por dentro do aro
    const gi = ctx.createLinearGradient(cx - r, cy - r, cx + r, cy + r);
    gi.addColorStop(0, "rgba(252,201,242,0.6)"); gi.addColorStop(0.5, "rgba(203,178,248,0.4)"); gi.addColorStop(1, "rgba(179,206,251,0.65)");
    ctx.strokeStyle = gi; ctx.lineWidth = 10;
    ctx.beginPath(); ctx.arc(cx, cy, r - 3, 0, Math.PI * 2); ctx.stroke();
    ctx.restore();
    // aro fino de ouro rosé, com contas miúdas
    const ga = ctx.createLinearGradient(cx - r, cy - r, cx + r, cy + r);
    ga.addColorStop(0, COR.metalClaro); ga.addColorStop(0.45, COR.metal); ga.addColorStop(0.8, COR.metalEsc); ga.addColorStop(1, COR.metal);
    ctx.strokeStyle = ga; ctx.lineWidth = 5;
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = "rgba(255,255,255,0.85)"; ctx.lineWidth = 1.6;
    ctx.beginPath(); ctx.arc(cx, cy, r - 1, Math.PI * 1.05, Math.PI * 1.45); ctx.stroke();
    ctx.fillStyle = COR.metalClaro;
    for (let i = 0; i < 16; i++) {
      const a = (i / 16) * Math.PI * 2 + 0.1;
      ctx.beginPath(); ctx.arc(cx + Math.cos(a) * (r + 5), cy + Math.sin(a) * (r + 5), 1.8, 0, Math.PI * 2); ctx.fill();
    }
    // flor de filigrana com um cristal, no lado de fora do aro
    const fx = cx - r - 10, fy = cy - 4;
    ctx.strokeStyle = COR.metal; ctx.lineWidth = 2;
    for (const a of [-0.9, 0, 0.9]) {
      ctx.beginPath(); ctx.ellipse(fx + Math.cos(Math.PI + a) * 9, fy + Math.sin(Math.PI + a) * 9, 9, 5, a, 0, Math.PI * 2); ctx.stroke();
    }
    cristalGota(fx, fy, 5, 9, t + 5);
    // corrente de contas subindo até o cabelo
    ctx.fillStyle = COR.metal;
    for (let i = 1; i < 18; i++) {
      const u = i / 18;
      const x = bez(fx - 6, fx - 50, fx - 56, -206, u), y = bez(fy - 6, fy - 60, fy - 170, -236, u);
      ctx.beginPath(); ctx.arc(x, y, i % 3 ? 1.8 : 2.8, 0, Math.PI * 2); ctx.fill();
    }
    // gotas de cristal penduradas na parte de baixo do aro
    ctx.strokeStyle = COR.metal; ctx.lineWidth = 1.8;
    for (const [a, comp, tam] of [[0.6, 16, 0.75], [0.7, 32, 0.95], [0.8, 20, 0.8]]) {
      const x = cx + Math.cos(a * Math.PI) * (r + 3), y = cy + Math.sin(a * Math.PI) * (r + 3);
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y + comp); ctx.stroke();
      cristalGota(x, y + comp + 13 * tam, 6.5 * tam, 13 * tam, t + a * 7);
    }
  }
  // O reflexo na lente do monóculo
  function reflexoDaLente() {
    const { x: cx, y: cy, r } = LENTE, d = -8;
    ctx.save();
    ctx.beginPath(); ctx.arc(cx, cy, r - 2, 0, Math.PI * 2); ctx.clip();
    ctx.fillStyle = "rgba(255,255,255,0.26)";
    ctx.beginPath(); ctx.moveTo(cx - r + d, cy - r); ctx.lineTo(cx - r + 42 + d, cy - r); ctx.lineTo(cx - 34 + d, cy + r); ctx.lineTo(cx - 76 + d, cy + r); ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,0.16)";
    ctx.beginPath(); ctx.moveTo(cx - 10 + d, cy - r); ctx.lineTo(cx + 4 + d, cy - r); ctx.lineTo(cx + 50 + d, cy + r); ctx.lineTo(cx + 36 + d, cy + r); ctx.fill();
    ctx.restore();
  }

  // ---------------------------------------------------------------- cristais
  function gradCristal(x, y, h) {
    const g = ctx.createLinearGradient(x - h * 0.5, y - h, x + h * 0.5, y + h);
    g.addColorStop(0, COR.cristal[0]); g.addColorStop(0.35, COR.cristal[1]); g.addColorStop(0.65, COR.cristal[2]); g.addColorStop(1, COR.cristal[3]);
    return g;
  }
  function cristalGota(x, y, w, h, t = 0) {
    ctx.fillStyle = gradCristal(x, y, h);
    ctx.beginPath(); ctx.moveTo(x, y - h); ctx.lineTo(x + w, y); ctx.lineTo(x, y + h * 0.7); ctx.lineTo(x - w, y); ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.85)"; ctx.lineWidth = 1.6; ctx.stroke();
    ctx.strokeStyle = "rgba(157,149,186,0.6)"; ctx.beginPath(); ctx.moveTo(x, y - h); ctx.lineTo(x, y + h * 0.7); ctx.stroke();
    faisca(0, x, y, w, h, t);
  }
  function estrelaDeCristal(x, y, tam, t) {   // a flor de cristal: pétalas em losango, iridescentes
    for (let i = 0; i < 8; i++) {
      const L = tam * (i % 2 ? 0.62 : 1);
      ctx.save(); ctx.translate(x, y); ctx.rotate(i * Math.PI / 4);
      ctx.fillStyle = gradCristal(0, -L / 2, L);
      ctx.beginPath(); ctx.moveTo(0, -L); ctx.lineTo(L * 0.2, -L * 0.45); ctx.lineTo(0, 0); ctx.lineTo(-L * 0.2, -L * 0.45); ctx.closePath();
      ctx.fill();
      ctx.strokeStyle = "rgba(255,255,255,0.9)"; ctx.lineWidth = 1.4; ctx.stroke();
      ctx.restore();
    }
    ctx.fillStyle = COR.metalClaro; ctx.beginPath(); ctx.arc(x, y, tam * 0.12, 0, Math.PI * 2); ctx.fill();
    faisca(1, x, y, tam, 0, t);
  }
  // O brilho que pisca num cristal (tipo 0: gota, 1: estrela de cristal). Se a peça está indo para uma camada
  // pronta, só anota: o brilho é desenhado a cada quadro por cima dela.
  let anotando = null;
  function faisca(tipo, x, y, a, b, t) {
    if (anotando) { anotando.push([tipo, x, y, a, b, t]); return; }
    if (tipo === 0) {
      const pisca = (Math.sin(t * 2.2 + x) + 1) / 2;
      if (pisca > 0.75) estrela(x - a * 0.3, y - b * 0.4, 7 * (pisca - 0.7) * 3, "rgba(255,255,255,0.95)");
    } else {
      const pisca = (Math.sin(t * 1.7) + 1) / 2;
      if (pisca > 0.6) estrela(x + a * 0.3, y - a * 0.5, a * 0.35 * (pisca - 0.5) * 2, "rgba(255,255,255,0.95)");
    }
  }
  function estrela(x, y, r, cor) {
    ctx.fillStyle = cor;
    ctx.beginPath();
    ctx.moveTo(x, y - r); ctx.quadraticCurveTo(x, y, x + r, y); ctx.quadraticCurveTo(x, y, x, y + r);
    ctx.quadraticCurveTo(x, y, x - r, y); ctx.quadraticCurveTo(x, y, x, y - r);
    ctx.fill();
  }

  // ---------------------------------------------------------------- efeitos de estado
  function brilhoDeFundo(t) {
    const m = estado.modo;
    let forca = TRANSPARENTE ? 0.22 : 0.3, raio = 360;
    if (m === "ouvindo") { forca = 0.4 + estado.mic * 0.45; raio = 390 + estado.mic * 50 + Math.sin(t * 3) * 6; }
    else if (m === "alerta") forca = 0.35 + (Math.sin(t * 6) * 0.5 + 0.5) * 0.3;
    else if (m === "dormindo" || m === "offline") forca = 0.1;
    const g = ctx.createRadialGradient(0, -20, 60, 0, -20, raio);
    g.addColorStop(0, rgba(estado.brilho, forca)); g.addColorStop(1, rgba(estado.brilho, 0));
    ctx.fillStyle = g;
    ctx.fillRect(-raio, -raio - 20, raio * 2, raio * 2);
  }

  // Ícone do estado, ao lado da cabeça (parado, não gira com ela). De perto (barra do PC, celular) vai num
  // selo escuro, para aparecer mesmo por cima do cabelo claro.
  const COM_ICONE = ["dormindo", "pensando", "executando", "aguardando", "privado", "offline"];
  function extras(t, perto) {
    const m = estado.modo;
    if (!COM_ICONE.includes(m)) return;
    ctx.save();
    if (perto) {
      ctx.translate(226, -148); ctx.scale(1.2, 1.2);
      ctx.fillStyle = "rgba(22,14,38,0.62)"; ctx.beginPath(); ctx.arc(0, 0, 54, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = "rgba(203,178,248,0.55)"; ctx.lineWidth = 2.5; ctx.stroke();
    } else ctx.translate(300, -286);
    ctx.fillStyle = "#c9b6f0"; ctx.lineCap = "round"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    if (m === "dormindo") {                                 // "z" subindo devagar
      ctx.font = "bold 40px system-ui";
      for (let i = 0; i < 3; i++) {
        const f = (t * 0.3 + i / 3) % 1;
        ctx.globalAlpha = Math.sin(f * Math.PI);
        ctx.fillText("z", -18 + f * 36, 30 - f * 60);
      }
    } else if (m === "pensando") {                          // três brilhos girando
      for (let i = 0; i < 3; i++) {
        const a = t * 2 + i * 2.1;
        estrela(Math.cos(a) * 28, Math.sin(a) * 12, 12 + Math.sin(t * 4 + i) * 4, "rgba(214,194,252,0.95)");
      }
    } else if (m === "executando") {                        // um cristal girando: "trabalhando nisso"
      ctx.save(); ctx.rotate(t * 2.4); cristalGota(0, 0, 12, 22, t); ctx.restore();
      ctx.lineWidth = 4; ctx.strokeStyle = "rgba(203,178,248,0.85)";
      ctx.beginPath(); ctx.arc(0, 0, 38, t * 3, t * 3 + 4); ctx.stroke();
    } else if (m === "aguardando") {
      ctx.font = "bold 72px system-ui"; ctx.globalAlpha = 0.65 + Math.sin(t * 3) * 0.3;
      ctx.fillText("?", 0, 4 + Math.sin(t * 2) * 6);
    } else if (m === "privado") {                           // cadeado de cristal
      ctx.lineWidth = 7; ctx.strokeStyle = COR.metal;
      ctx.beginPath(); ctx.arc(0, -8, 17, Math.PI, 0); ctx.stroke();
      ctx.fillStyle = gradCristal(0, 14, 24); ctx.fillRect(-26, -8, 52, 40);
    } else if (m === "offline") {                           // nuvem riscada
      const r = 16;
      ctx.lineWidth = 5; ctx.strokeStyle = "rgba(190,180,210,0.95)";
      ctx.beginPath();
      ctx.arc(-r, 4, r, Math.PI * 0.5, Math.PI * 1.5); ctx.arc(0, 4 - r * 0.7, r * 1.2, Math.PI, 0);
      ctx.arc(r * 1.1, 4, r, Math.PI * 1.5, Math.PI * 0.5); ctx.closePath(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(-r * 2, 4 + r * 1.6); ctx.lineTo(r * 2, 4 - r * 2); ctx.stroke();
    }
    ctx.restore();
  }
  // De perto o cabelo passa das bordas do quadro: em vez de um corte reto, as bordas somem aos poucos
  function esfumarBordas() {
    const w = canvas.width, h = canvas.height;
    const faixa = (x0, y0, x1, y1, forca) => {        // só as faixas da borda (o meio fica intacto)
      const g = ctx.createLinearGradient(x0, y0, x1, y1);
      g.addColorStop(0, `rgba(0,0,0,${forca})`); g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = g;
      ctx.fillRect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0) || w, Math.abs(y1 - y0) || h);
    };
    ctx.globalCompositeOperation = "destination-out";
    faixa(0, 0, 0, h * 0.2, 1); faixa(0, h, 0, h * 0.88, 0.9);
    faixa(0, 0, w * 0.1, 0, 0.9); faixa(w, 0, w * 0.9, 0, 0.9);
    ctx.globalCompositeOperation = "source-over";
  }

  function atualizarCabeca(dt, t) {
    const m = estado.modo;
    let rot = Math.sin(t * 0.55) * 0.02, dx = 0, dy = 0;
    if (m === "pensando") rot = 0.07 + Math.sin(t * 0.8) * 0.01;
    else if (m === "aguardando") rot = -0.1;
    else if (m === "ouvindo") dy = -4;
    else if (m === "executando") rot = Math.sin(t * 1.6) * 0.025;
    else if (m === "offline" || m === "dormindo") { rot = 0.06; dy = 8; }
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

  // ---------------------------------------------------------------- camadas prontas (economia)
  // Cabelo, corpo, pele e joias não mudam de um quadro para outro: são desenhados uma vez em imagens do
  // tamanho da tela e só colados a cada quadro. Redesenha-se só o que se mexe: olhos, boca, bochechas,
  // sobrancelhas, o reflexo da lente e os brilhos dos cristais.
  let camadas = null;
  function prepararCamadas(esc, ox, oy, chave, perto) {
    const k = esc * dpr, m = 130;                  // margem para a cabeça inclinar sem mostrar a borda
    // uma imagem que cobre o retângulo (x0,y0)-(x1,y1) do modelo; por padrão, a tela inteira e a margem
    const nova = (desenhar, x0 = -ox / esc - m, y0 = -oy / esc - m, x1 = (W - ox) / esc + m, y1 = (H - oy) / esc + m) => {
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
    const cabeca = () => {
      rostoBase(); sombrasDosOlhos(); lagrimaDeCristal(-1, 0); lagrimaDeCristal(1, 0);
      cabeloFrente(0); brincos(0);
    };
    camadas = { chave,
      atras: perto ? null : nova(() => cabeloAtras(0)),
      corpo: perto ? null : nova(corpo),
      cabeca: nova(perto ? () => { cabeloAtras(0); corpo(); cabeca(); } : cabeca),
      monoculo: nova(() => { monoculo(0); reflexoDaLente(); }, -262, -262, -8, 170),
      iris: nova(iris, -IRIS, -IRIS, IRIS, IRIS) };
  }
  function colar(camada, t) {
    ctx.drawImage(camada.c, camada.x0, camada.y0, camada.w, camada.h);
    for (const [tipo, x, y, a, b, t0] of camada.brilhos) faisca(tipo, x, y, a, b, t + t0);
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
    const falta = 1000 / qps - (performance.now() - ultimoDesenho);
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
    const f = W < 260 || H < 220 ? PERTO : BUSTO;
    const esc = Math.min(W / (f.x1 - f.x0), H / (f.y1 - f.y0));
    const ox = W / 2 - ((f.x0 + f.x1) / 2) * esc, oy = H / 2 - ((f.y0 + f.y1) / 2) * esc;
    if (!(esc > 0)) { agendar(); return; }             // ainda sem tamanho na tela
    const chave = `${W}x${H}x${dpr}`;
    if (!camadas || camadas.chave !== chave) prepararCamadas(esc, ox, oy, chave, f === PERTO);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!TRANSPARENTE) {
      const g = ctx.createRadialGradient(W * dpr / 2, H * dpr * 0.4, 0, W * dpr / 2, H * dpr * 0.4, Math.max(W, H) * dpr * 0.8);
      g.addColorStop(0, "#241838"); g.addColorStop(1, "#0b0712");
      ctx.fillStyle = g; ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
    const base = (extraY = 0) => ctx.setTransform(esc * dpr, 0, 0, esc * dpr, ox * dpr, (oy + extraY * esc) * dpr);
    const respira = m === "dormindo" || m === "privado" ? Math.sin(t * 1.2) * 6 : Math.sin(t * 1.6) * 3;
    const semCor = estado.cinza > 0.02 && "filter" in ctx;
    if (semCor) ctx.filter = `saturate(${1 - estado.cinza}) brightness(${1 - estado.cinza * 0.25})`;

    // de perto o brilho quase não aparece (o rosto cobre o quadro): só quando diz algo (ouvindo, alerta)
    if (f !== PERTO || m === "ouvindo" || m === "alerta") { base(); brilhoDeFundo(t); }
    const cab = estado.cabeca;
    const girar = () => {  // a cabeça gira em torno do pescoço
      base(respira * 0.6);
      ctx.translate(cab.dx, cab.dy + 250); ctx.rotate(cab.rot); ctx.translate(0, -250);
    };
    if (camadas.corpo) {                             // de longe: cabelo de trás, corpo e cabeça em camadas
      girar(); colar(camadas.atras, t);
      base(respira); colar(camadas.corpo, t);
    }
    girar(); colar(camadas.cabeca, t);
    bochechas(p);
    olho(-1, p); olho(1, p);
    sobrancelhas(p); boca(p);
    colar(camadas.monoculo, t);
    if (semCor) ctx.filter = "none";
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    if (f === PERTO) esfumarBordas();
    base(); extras(t, f === PERTO);
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
