// Ametista, o rosto de reserva (quando o computador não tem WebGL, o rosto.js carrega este): a ilustração
// completa da ficha de personagem (ametista-retrato.webp), viva:
// respira, pisca de verdade (a pálpebra, com a maquiagem e os cílios dela, desce sobre o olho), a boca abre e
// fecha com a voz e sorri, os cristais do cabelo, dos brincos e do monóculo cintilam, e um brilho iridescente
// passa de vez em quando. Tem emoções (luz e cor), estados (ouvindo, pensando, dormindo...) e gestos de cabeça.
//
// Estados (Rosto.modo):  dormindo | ocioso | ouvindo | pensando | falando |
//                        executando | alerta | offline | aguardando | privado
// Emoções (Rosto.emocao): neutra | feliz | pensativa | surpresa | triste | brava
// Gestos (Rosto.gesto):  acenar (sim com a cabeça) | negar | inclinar
//
// Leve de propósito: a ilustração é redimensionada uma vez para o tamanho da tela; a cada quadro ela é copiada
// e só as pálpebras, a boca e os brilhos mexem por cima. 24 quadros/s falando, 30 só no instante de uma
// piscada, 8 parada ou dormindo, e nada quando a janela ou o app estão escondidos.
(() => {
  const canvas = document.getElementById("rosto");
  const ctx = canvas.getContext("2d");
  const TRANSPARENTE = canvas.dataset.transparente === "1";
  const script = document.currentScript;
  const ARQUIVO = canvas.dataset.imagem ||
    (script && script.src ? script.src.replace(/[^/]*$/, "ametista-retrato.webp") : "ametista-retrato.webp");

  // ---------------------------------------------------------------- a ilustração (medidas no original, 486 x 738)
  const ORIG = { w: 486, h: 738 };
  // Olhos, cada um no seu próprio eixo (centro e inclinação): os cantos, o meio da linha dos cílios de cima e o
  // meio da pálpebra de baixo. Fechado, a pálpebra de cima vai até logo acima da de baixo.
  const OLHOS = [
    { x: 316, y: 241, ang: -0.43, e: [-44, 10], d: [38, 1.7], cima: [-3, -12.5], baixo: [-3, 18] },   // sem monóculo
    { x: 168, y: 315, ang: -0.24, e: [-40, 8], d: [45, 0], cima: [2.5, -11.5], baixo: [2.5, 19] },     // atrás do monóculo
  ];
  // Boca, no eixo que liga os dois cantos: a linha onde começa o lábio de baixo sobe no meio (os dentes de cima
  // aparecem entre os lábios) e desce nos cantos.
  const BOCA = { x: 301, y: 398, ang: -0.454, meia: 45, abre: 8.5, sorri: 2.6 };
  const labio = (x) => -1.3 + 6 * Math.pow(Math.min(1.3, Math.abs(x) / BOCA.meia), 2.6);
  // cristais que cintilam (cabelo, brincos, monóculo, gotas penduradas, anel)
  const CRISTAIS = [[38, 238], [18, 286], [432, 60], [456, 96], [444, 372], [452, 430], [120, 268], [228, 282],
                    [118, 430], [92, 478], [132, 520], [212, 604], [398, 170], [60, 180], [470, 520]];
  // enquadramentos: o rosto em molduras quase quadradas, a ilustração inteira em molduras altas
  const ROSTO = { x: 36, y: 40, w: 440, h: 540 };
  const TUDO = { x: 0, y: 0, w: 486, h: 738 };
  const SOBRA = 1.06;                       // a ilustração é um pouco maior que a moldura: a cabeça mexe sem mostrar a borda

  const EMOCOES = {        // luz por cima da ilustração: cor, força, brilho, saturação, "pulinho", sorriso
    neutra:    { cor: [255, 255, 255], forca: 0.00, luz: 1.00, sat: 1.00, zoom: 1.00, sorriso: 0 },
    feliz:     { cor: [255, 190, 230], forca: 0.16, luz: 1.04, sat: 1.00, zoom: 1.01, sorriso: 1 },
    pensativa: { cor: [190, 200, 255], forca: 0.12, luz: 0.98, sat: 0.95, zoom: 1.00, sorriso: 0 },
    surpresa:  { cor: [255, 255, 255], forca: 0.14, luz: 1.06, sat: 1.00, zoom: 1.03, sorriso: 0 },
    triste:    { cor: [150, 170, 230], forca: 0.20, luz: 0.90, sat: 0.75, zoom: 1.00, sorriso: 0 },
    brava:     { cor: [255, 120, 130], forca: 0.18, luz: 0.97, sat: 1.00, zoom: 1.00, sorriso: 0 },
  };
  const HALO = { normal: [203, 178, 248], alerta: [255, 176, 120], ouvindo: [179, 206, 251], feliz: [252, 201, 242] };

  const estado = {
    modo: "dormindo",
    emocao: "neutra",
    voz: 0, mic: 0,
    boca: 0,                        // abertura da boca suavizada (0..1)
    fechar: 1,                      // 0 = olhos abertos, 1 = fechados (dormindo)
    piscar: 0, proxPiscada: 2,
    efeito: { ...EMOCOES.neutra, cor: [...EMOCOES.neutra.cor] },
    brilho: [...HALO.normal],
    cinza: 0,
    cabeca: { rot: 0, dx: 0, dy: 0 },
    gesto: null, gestoT: 0,
    reflexo: -1, proxReflexo: 4,    // o brilho iridescente que atravessa a ilustração
    forcado: null,                  // testes: {piscar, boca} fixos
  };

  // ---------------------------------------------------------------- imagem
  const img = new Image();
  let pronta = false;
  img.onload = () => { pronta = true; base = null; acordar(); };
  img.src = ARQUIVO;

  // ---------------------------------------------------------------- tamanho
  let W = 0, H = 0, dpr = 1, base = null;
  function redimensionar() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = canvas.clientWidth || innerWidth; H = canvas.clientHeight || innerHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    base = null;
    if (typeof acordar === "function") acordar();
  }
  addEventListener("resize", redimensionar);
  if (window.ResizeObserver) new ResizeObserver(redimensionar).observe(canvas);

  const lerp = (a, b, t) => a + (b - a) * t;
  const rgba = (c, a = 1) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;

  // Onde a ilustração fica: "cobre" a moldura, centrada no rosto (ou nela toda, se a moldura for alta)
  function preparar() {
    const m = Math.max(4, Math.round(Math.min(W, H) * 0.045));              // margem para o brilho em volta
    const q = { x: m, y: m, w: W - 2 * m, h: H - 2 * m, r: Math.min(W, H) * 0.16 };
    const alvo = q.h / q.w > 1.35 ? TUDO : ROSTO;
    const esc = Math.max(q.w / alvo.w, q.h / alvo.h) * SOBRA;
    let ox = q.x + q.w / 2 - (alvo.x + alvo.w / 2) * esc, oy = q.y + q.h / 2 - (alvo.y + alvo.h / 2) * esc;
    // nunca deixa a borda da ilustração aparecer dentro da moldura
    ox = Math.min(q.x, Math.max(q.x + q.w - ORIG.w * esc, ox));
    oy = Math.min(q.y, Math.max(q.y + q.h - ORIG.h * esc, oy));
    // a ilustração já no tamanho da tela (redimensionar a foto a cada quadro custaria mais)
    const c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(ORIG.w * esc * dpr)); c.height = Math.max(1, Math.round(ORIG.h * esc * dpr));
    const g = c.getContext("2d");
    g.imageSmoothingQuality = "high";
    g.drawImage(img, 0, 0, c.width, c.height);
    // quantas fatias a boca usa ao abrir: mais em telas grandes, poucas no ícone
    const fatias = Math.max(8, Math.min(32, Math.round(BOCA.meia * 2.6 * esc * dpr / 4)));
    base = { c, esc, ox, oy, q, fatias, chave: `${W}x${H}x${dpr}` };
  }

  // a própria ilustração, desenhada no sistema de medidas em que se está (original)
  const ilustracao = () => ctx.drawImage(base.c, 0, 0, ORIG.w, ORIG.h);

  // ---------------------------------------------------------------- partes que mexem (em medidas do original)
  // Curva de Bézier quadrática que passa pelos cantos e por "meio" no ponto do meio
  const controle = (e, d, meio) => [2 * meio[0] - (e[0] + d[0]) / 2, 2 * meio[1] - (e[1] + d[1]) / 2];

  // A pálpebra de cima desce: a faixa de pele e maquiagem acima dos cílios é esticada até a beira nova, então
  // os cílios descem junto e a textura continua a dela.
  function palpebra(o, fecha) {
    if (fecha <= 0.02) return;
    const { e, d } = o;
    const fim = [o.baixo[0], o.baixo[1] - 1.5];                              // onde a pálpebra encosta, fechada
    const meio = [lerp(o.cima[0], fim[0], fecha), lerp(o.cima[1], fim[1], fecha)];
    const cAberta = controle(e, d, [o.cima[0], o.cima[1] - 3.5]);            // um pouco acima: cobre os cílios de cima
    const cAgora = controle(e, d, meio);
    const pivo = o.cima[1] - 22;                                              // a faixa de cima (sombra) vai até aqui
    const estica = (meio[1] - pivo) / (o.cima[1] - pivo);
    ctx.save();
    ctx.translate(o.x, o.y); ctx.rotate(o.ang);
    ctx.beginPath();
    ctx.moveTo(e[0] - 1, e[1]); ctx.quadraticCurveTo(cAberta[0], cAberta[1], d[0] + 1, d[1]);
    ctx.quadraticCurveTo(cAgora[0], cAgora[1], e[0] - 1, e[1]);
    ctx.closePath();
    ctx.save(); ctx.clip();
    ctx.translate(0, pivo); ctx.scale(1, estica); ctx.translate(0, -pivo);   // estica a faixa para baixo
    ctx.rotate(-o.ang); ctx.translate(-o.x, -o.y);
    ilustracao();
    ctx.restore();
    // a beira: uma linha de cílios firme, e os cílios virados para baixo quando fecha de vez
    ctx.strokeStyle = `rgba(48,26,56,${Math.min(0.85, fecha * 2)})`; ctx.lineWidth = 2.2; ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(e[0], e[1]); ctx.quadraticCurveTo(cAgora[0], cAgora[1], d[0], d[1]); ctx.stroke();
    if (fecha > 0.8) {
      ctx.globalAlpha = (fecha - 0.8) * 5; ctx.lineWidth = 1.3;
      for (let i = 1; i < 7; i++) {
        const t = i / 7, u = 1 - t;
        const x = u * u * e[0] + 2 * u * t * cAgora[0] + t * t * d[0];
        const y = u * u * e[1] + 2 * u * t * cAgora[1] + t * t * d[1];
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + (t - 0.5) * 5, y + 4.5); ctx.stroke();
      }
    }
    ctx.restore();
  }

  // A boca: o lábio de baixo (e o queixo logo abaixo) descem mostrando o escuro da boca; sorrindo, os cantos
  // sobem. Feito em fatias verticais inclinadas, cada uma com o seu deslocamento, para a curva sair lisa.
  function boca(abre, sorriso) {
    if (abre <= 0.02 && sorriso <= 0.02) return;
    const M = BOCA.meia, ext = M * 1.3, n = base.fatias, larg = (2 * ext) / n;
    const sobe = (x) => {
      const u = Math.abs(x) / M;
      return -sorriso * BOCA.sorri * (u <= 1 ? u * u : Math.max(0, 1 - (u - 1) / 0.3));
    };
    const desce = (x) => abre * BOCA.abre * Math.pow(Math.max(0, 1 - (x / M) ** 2), 0.7);
    const xs = Array.from({ length: n + 1 }, (_, i) => -ext + i * larg);
    ctx.save();
    ctx.translate(BOCA.x, BOCA.y); ctx.rotate(BOCA.ang);
    const fatia = (x0, x1, y0a, y0b, y1a, y1b, s0, s1) => {      // de (x0..x1) entre y0 e y1, deslocada s0..s1
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(x0 - 0.35, y0a + s0); ctx.lineTo(x1 + 0.35, y0b + s1);
      ctx.lineTo(x1 + 0.35, y1b + s1); ctx.lineTo(x0 - 0.35, y1a + s0);
      ctx.closePath(); ctx.clip();
      const incl = (s1 - s0) / (x1 - x0);
      ctx.transform(1, incl, 0, 1, 0, s0 - incl * x0);
      ctx.rotate(-BOCA.ang); ctx.translate(-BOCA.x, -BOCA.y);
      ilustracao();
      ctx.restore();
    };
    // o lábio de cima (só quando sorri)
    if (sorriso > 0.02) {
      for (let i = 0; i < n; i++) {
        const x0 = xs[i], x1 = xs[i + 1];
        fatia(x0, x1, -24, -24, labio(x0), labio(x1), sobe(x0), sobe(x1));
      }
    }
    // o escuro da boca, entre os dentes de cima e o lábio de baixo
    if (abre > 0.02) {
      const g = ctx.createLinearGradient(0, -2, 0, BOCA.abre + 2);
      g.addColorStop(0, "#2a0c1c"); g.addColorStop(0.55, "#4a1830"); g.addColorStop(1, "#7a3050");
      ctx.fillStyle = g;
      const dentro = Array.from({ length: 25 }, (_, i) => -M + (2 * M * i) / 24);   // de canto a canto
      const folga = (x) => Math.min(0.5, desce(x) * 0.15);
      ctx.beginPath();
      dentro.forEach((x, i) => (i ? ctx.lineTo : ctx.moveTo).call(ctx, x, labio(x) + sobe(x) - folga(x)));
      for (let i = dentro.length - 1; i >= 0; i--) {
        const x = dentro[i];
        ctx.lineTo(x, labio(x) + sobe(x) + desce(x) + folga(x));
      }
      ctx.closePath(); ctx.fill();
    }
    // o lábio de baixo e o queixo
    for (let i = 0; i < n; i++) {
      const x0 = xs[i], x1 = xs[i + 1];
      const s0 = sobe(x0) + desce(x0), s1 = sobe(x1) + desce(x1);
      if (Math.abs(s0) < 0.05 && Math.abs(s1) < 0.05) continue;
      fatia(x0, x1, labio(x0), labio(x1), 38, 38, s0, s1);
    }
    ctx.restore();
  }

  function estrela(x, y, r, a) {
    ctx.save(); ctx.translate(x, y); ctx.globalAlpha = a;
    const g = ctx.createRadialGradient(0, 0, 0, 0, 0, r);
    g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.4, "rgba(214,200,255,0.8)"); g.addColorStop(1, "rgba(214,200,255,0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.moveTo(0, -r); ctx.quadraticCurveTo(r * 0.12, -r * 0.12, r, 0); ctx.quadraticCurveTo(r * 0.12, r * 0.12, 0, r);
    ctx.quadraticCurveTo(-r * 0.12, r * 0.12, -r, 0); ctx.quadraticCurveTo(-r * 0.12, -r * 0.12, 0, -r);
    ctx.fill(); ctx.restore();
  }

  function cintilar(t) {
    const intenso = estado.modo === "pensando" || estado.modo === "executando" ? 1.6 : 1;
    CRISTAIS.forEach(([x, y], i) => {
      const f = Math.sin(t * (0.9 + (i % 5) * 0.23) + i * 1.7);
      if (f > 0.55) estrela(x, y, 9 + f * 7 * intenso, (f - 0.55) * 2.2);
    });
  }

  function reflexo() {                        // uma faixa de luz iridescente atravessando, de vez em quando
    const f = estado.reflexo;
    if (f < 0 || f > 1) return;
    const x = -200 + f * (ORIG.w + 400);
    const g = ctx.createLinearGradient(x - 120, 0, x + 120, 120);
    g.addColorStop(0, "rgba(255,255,255,0)"); g.addColorStop(0.42, "rgba(252,201,242,0.20)");
    g.addColorStop(0.5, "rgba(255,255,255,0.32)"); g.addColorStop(0.58, "rgba(179,206,251,0.20)"); g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.fillStyle = g; ctx.fillRect(0, 0, ORIG.w, ORIG.h); ctx.restore();
  }

  // Cor e luz da emoção e do estado, por cima de tudo (misturas simples: bem mais leves que filtros)
  function tingir(olhosFechados) {
    const ef = estado.efeito;
    const luz = ef.luz * (olhosFechados ? 0.88 : 1) * (1 - estado.cinza * 0.2);
    const sat = Math.min(1, ef.sat * (1 - estado.cinza));
    ctx.save();
    if (sat < 0.99) { ctx.globalCompositeOperation = "saturation"; ctx.fillStyle = `rgba(128,128,128,${1 - sat})`; ctx.fillRect(0, 0, ORIG.w, ORIG.h); }
    if (luz < 0.995) { ctx.globalCompositeOperation = "multiply"; const v = Math.round(255 * luz); ctx.fillStyle = `rgb(${v},${v},${v})`; ctx.fillRect(0, 0, ORIG.w, ORIG.h); }
    else if (luz > 1.005) { ctx.globalCompositeOperation = "screen"; ctx.fillStyle = `rgba(255,255,255,${(luz - 1) * 1.6})`; ctx.fillRect(0, 0, ORIG.w, ORIG.h); }
    if (ef.forca > 0.01) { ctx.globalCompositeOperation = "soft-light"; ctx.fillStyle = rgba(ef.cor, ef.forca * 2.2); ctx.fillRect(0, 0, ORIG.w, ORIG.h); }
    ctx.restore();
  }

  // ---------------------------------------------------------------- moldura, brilho e selo do estado (em pixels da tela)
  function moldura(q) {
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(q.x, q.y, q.w, q.h, q.r);
    else ctx.rect(q.x, q.y, q.w, q.h);
  }
  function halo(q, t) {
    const m = estado.modo;
    let forca = 0.35, extra = 0;
    if (m === "ouvindo") { forca = 0.55 + estado.mic * 0.45; extra = estado.mic * 6 + Math.sin(t * 3) * 1.5; }
    else if (m === "alerta") forca = 0.5 + (Math.sin(t * 6) * 0.5 + 0.5) * 0.4;
    else if (m === "falando") forca = 0.45 + estado.boca * 0.3;
    else if (m === "dormindo" || m === "offline" || m === "privado") forca = 0.15;
    ctx.save();
    ctx.shadowColor = rgba(estado.brilho, forca); ctx.shadowBlur = (8 + extra) * dpr;
    moldura(q); ctx.fillStyle = rgba(estado.brilho, 0.9); ctx.fill();
    ctx.restore();
  }
  function borda(q, t) {                      // aro iridescente girando devagar
    const a = t * 0.6;
    let g;
    if (ctx.createConicGradient) {
      g = ctx.createConicGradient(a, q.x + q.w / 2, q.y + q.h / 2);
      [["#cbb2f8", 0], ["#b3cefb", 0.25], ["#fcc9f2", 0.5], ["#e6c7a2", 0.75], ["#cbb2f8", 1]].forEach(([c, p]) => g.addColorStop(p, c));
    } else {
      g = ctx.createLinearGradient(q.x, q.y, q.x + q.w, q.y + q.h);
      g.addColorStop(0, "#cbb2f8"); g.addColorStop(0.5, "#fcc9f2"); g.addColorStop(1, "#b3cefb");
    }
    ctx.strokeStyle = g; ctx.lineWidth = Math.max(1.5, Math.min(W, H) * 0.018);
    moldura(q); ctx.stroke();
  }

  const COM_ICONE = ["dormindo", "pensando", "executando", "aguardando", "privado", "offline"];
  function selo(q, t) {
    const m = estado.modo;
    if (!COM_ICONE.includes(m)) return;
    const r = Math.max(9, Math.min(W, H) * 0.12);
    ctx.save();
    ctx.translate(q.x + q.w - r * 0.75, q.y + r * 0.75);
    ctx.fillStyle = "rgba(22,14,38,0.78)"; ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "rgba(203,178,248,0.6)"; ctx.lineWidth = Math.max(1, r * 0.08); ctx.stroke();
    ctx.fillStyle = "#e0d2fb"; ctx.strokeStyle = "#e0d2fb"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    const s = r / 46;
    ctx.scale(s, s);
    if (m === "dormindo") {
      ctx.font = "bold 30px system-ui";
      for (let i = 0; i < 3; i++) { const f = (t * 0.3 + i / 3) % 1; ctx.globalAlpha = Math.sin(f * Math.PI); ctx.fillText("z", -12 + f * 24, 20 - f * 40); }
    } else if (m === "pensando") {
      for (let i = 0; i < 3; i++) {
        const a = t * 2 + i * 2.1;
        ctx.globalAlpha = 0.95; ctx.beginPath(); ctx.arc(Math.cos(a) * 22, Math.sin(a) * 9, 7 + Math.sin(t * 4 + i) * 2.5, 0, Math.PI * 2); ctx.fill();
      }
    } else if (m === "executando") {
      ctx.lineWidth = 6; ctx.lineCap = "round"; ctx.beginPath(); ctx.arc(0, 0, 26, t * 3, t * 3 + 4); ctx.stroke();
    } else if (m === "aguardando") {
      ctx.font = "bold 56px system-ui"; ctx.globalAlpha = 0.7 + Math.sin(t * 3) * 0.3; ctx.fillText("?", 0, 4);
    } else if (m === "privado") {
      ctx.lineWidth = 6; ctx.beginPath(); ctx.arc(0, -8, 13, Math.PI, 0); ctx.stroke(); ctx.fillRect(-20, -8, 40, 30);
    } else if (m === "offline") {
      ctx.lineWidth = 5; ctx.lineCap = "round";
      ctx.beginPath(); ctx.arc(-12, 4, 12, Math.PI * 0.5, Math.PI * 1.5); ctx.arc(0, -6, 14, Math.PI, 0); ctx.arc(13, 4, 12, Math.PI * 1.5, Math.PI * 0.5); ctx.closePath(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(-26, 24); ctx.lineTo(26, -24); ctx.stroke();
    }
    ctx.restore();
  }

  // ---------------------------------------------------------------- cabeça: respira, inclina, acena, nega
  function atualizarCabeca(dt, t) {
    const m = estado.modo;
    let rot = 0, dx = 0, dy = 0;
    if (m === "pensando") rot = 0.02;
    else if (m === "aguardando") rot = -0.02;
    else if (m === "ouvindo") dy = -3;
    else if (m === "dormindo" || m === "offline") dy = 4;
    if (estado.gesto) {
      const f = (t - estado.gestoT) / 0.9;
      if (f >= 1) estado.gesto = null;
      else {
        const env = Math.sin(f * Math.PI);
        if (estado.gesto === "acenar") dy += Math.sin(f * Math.PI * 4) * 8 * env;
        else if (estado.gesto === "negar") dx += Math.sin(f * Math.PI * 5) * 9 * env;
        else if (estado.gesto === "inclinar") rot += 0.035 * env;
      }
    }
    const k = 1 - Math.pow(0.002, dt);
    estado.cabeca.rot = lerp(estado.cabeca.rot, rot, k);
    estado.cabeca.dx = estado.gesto ? dx : lerp(estado.cabeca.dx, dx, k);
    estado.cabeca.dy = estado.gesto ? dy : lerp(estado.cabeca.dy, dy, k);
  }

  // ---------------------------------------------------------------- quadros por segundo (economia)
  const QPS = { falando: 24, ouvindo: 30, alerta: 30, pensando: 20, executando: 20, aguardando: 16,
                ocioso: 8, offline: 8, dormindo: 8, privado: 8 };
  let ultimo = performance.now(), ultimoDesenho = 0, turboAte = 0, espera = null, pedido = 0;
  function movimento(segundos) { turboAte = Math.max(turboAte, performance.now() + segundos * 1000); acordar(); }
  function agendar() {
    if (espera !== null || pedido || document.hidden) return;
    const agora = performance.now();
    const qps = Math.max(QPS[estado.modo] || 10, agora < turboAte ? 30 : 0);
    const falta = 1000 / qps - (agora - ultimoDesenho);
    if (falta <= 8) pedido = requestAnimationFrame(quadro);
    else espera = setTimeout(() => { espera = null; pedido = requestAnimationFrame(quadro); }, falta);
  }
  function acordar() {
    if (espera !== null) { clearTimeout(espera); espera = null; }
    agendar();
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { ultimo = performance.now(); acordar(); } });

  function quadro(agora) {
    pedido = 0;
    ultimoDesenho = performance.now();
    const dt = Math.min((agora - ultimo) / 1000, 0.25);
    ultimo = agora;
    const t = agora / 1000;
    const m = estado.modo;

    // emoção e estado rumo ao alvo
    const alvo = EMOCOES[estado.emocao] || EMOCOES.neutra;
    const k = 1 - Math.pow(0.001, dt);
    for (const c of ["forca", "luz", "sat", "zoom", "sorriso"]) estado.efeito[c] = lerp(estado.efeito[c], alvo[c], k);
    for (let i = 0; i < 3; i++) estado.efeito.cor[i] = lerp(estado.efeito.cor[i], alvo.cor[i], k);
    const corAlvo = m === "alerta" ? HALO.alerta : m === "ouvindo" ? HALO.ouvindo : estado.emocao === "feliz" ? HALO.feliz : HALO.normal;
    for (let i = 0; i < 3; i++) estado.brilho[i] = lerp(estado.brilho[i], corAlvo[i], 1 - Math.pow(0.02, dt));
    estado.cinza = lerp(estado.cinza, m === "offline" ? 0.8 : 0, 1 - Math.pow(0.02, dt));
    const olhosFechados = m === "dormindo" || m === "privado";
    estado.fechar = lerp(estado.fechar, olhosFechados ? 1 : m === "offline" ? 0.45 : 0, 1 - Math.pow(0.01, dt));
    const abreAlvo = m === "falando" ? Math.min(1, estado.voz * 1.15) : m === "alerta" || estado.emocao === "surpresa" ? 0.3 : 0;
    estado.boca = lerp(estado.boca, abreAlvo, 1 - Math.pow(0.0005, dt));

    // piscadas e o reflexo que passa
    estado.proxPiscada -= dt;
    if (estado.proxPiscada <= 0 && estado.fechar < 0.3) {
      estado.piscar = 1; estado.proxPiscada = 2.5 + Math.random() * 4; movimento(0.3);
    }
    estado.piscar = Math.max(0, estado.piscar - dt * 6.5);
    estado.proxReflexo -= dt;
    if (estado.proxReflexo <= 0 && !olhosFechados && m !== "offline") {
      estado.reflexo = 0; estado.proxReflexo = 7 + Math.random() * 8; movimento(1.2);
    }
    if (estado.reflexo >= 0) estado.reflexo = estado.reflexo + dt / 1.1 > 1 ? -1 : estado.reflexo + dt / 1.1;
    atualizarCabeca(dt, t);

    if (!pronta || !(W > 4 && H > 4)) { agendar(); return; }
    if (!base || base.chave !== `${W}x${H}x${dpr}`) preparar();

    const f = estado.forcado;
    const piscada = Math.sin(Math.min(1, estado.piscar) * Math.PI);            // desce e sobe
    const fecha = f && f.piscar != null ? f.piscar : Math.max(estado.fechar, piscada);
    const abre = f && f.boca != null ? f.boca : estado.boca;
    const sorriso = f && f.sorriso != null ? f.sorriso : estado.efeito.sorriso;

    // ---- desenho
    const b = base, q = b.q;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (!TRANSPARENTE) { ctx.fillStyle = "#0b0712"; ctx.fillRect(0, 0, W, H); }
    halo(q, t);
    ctx.save();
    moldura(q); ctx.clip();
    // respiração + cabeça: tudo em volta do centro da moldura (sempre para fora: a borda nunca aparece)
    const resp = 1 + (Math.sin(t * 1.5) + 1) * 0.004 + (estado.efeito.zoom - 1);
    const cx = q.x + q.w / 2, cy = q.y + q.h / 2;
    ctx.translate(cx + estado.cabeca.dx * b.esc, cy + (estado.cabeca.dy + Math.sin(t * 1.5) * 1.2) * b.esc);
    ctx.rotate(estado.cabeca.rot); ctx.scale(resp, resp); ctx.translate(-cx, -cy);
    ctx.translate(b.ox, b.oy); ctx.scale(b.esc, b.esc);                         // agora em medidas do original
    ilustracao();
    OLHOS.forEach((o) => palpebra(o, fecha));
    boca(abre, sorriso);
    tingir(olhosFechados);
    if (!olhosFechados && m !== "offline") { cintilar(t); reflexo(); }
    ctx.restore();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    borda(q, t);
    selo(q, t);
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
    forcar(f) { estado.forcado = f; acordar(); },          // para os testes: {piscar, boca, sorriso} de 0 a 1
    get estado() { return estado; },
  };
  redimensionar();
  agendar();
})();
