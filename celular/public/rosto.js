// Rosto da Ametista: olhos e boca desenhados em canvas, com emoções, estados, cabeça e sincronia labial.
//
// Leve de propósito: só redesenha o necessário (30 quadros/s falando ou em movimento, 10 parada, 8 dormindo)
// e para de vez quando a janela ou o app estão escondidos.
//
// Estados (Rosto.modo):  dormindo | ocioso | ouvindo | pensando | falando |
//                        executando | alerta | offline | aguardando | privado
// Gestos (Rosto.gesto):  acenar (sim com a cabeça) | negar | inclinar
(() => {
  const canvas = document.getElementById("rosto");
  const ctx = canvas.getContext("2d");
  // Camada separada para os olhos: as pálpebras "apagam" pixels (sem manchas pretas sobre o brilho)
  const camada = document.createElement("canvas");
  const cc = camada.getContext("2d");
  const principal = ctx;
  // data-transparente="1": sem fundo nem partículas (para a sobreposição por cima do Windows)
  const TRANSPARENTE = canvas.dataset.transparente === "1";
  const FUNDO = "#07050c";
  const PALETAS = {
    normal: { olho: [199, 155, 255], olho2: [138, 77, 255], halo: [160, 100, 255] },
    alerta: { olho: [255, 190, 120], olho2: [255, 104, 90], halo: [255, 130, 90] },
    offline: { olho: [150, 144, 166], olho2: [96, 90, 112], halo: [120, 115, 135] },
    privado: { olho: [150, 120, 200], olho2: [90, 60, 150], halo: [110, 80, 170] },
  };

  // Formato alvo de cada emoção
  const EMOCOES = {
    neutra:    { abertura: 1.00, tampa: 0.00, incl: 0.00, sorriso: 0.00, boca: 0.25, escala: 1.00 },
    feliz:     { abertura: 1.00, tampa: 0.00, incl: 0.00, sorriso: 0.62, boca: 0.75, escala: 1.02 },
    pensativa: { abertura: 0.80, tampa: 0.18, incl: 0.00, sorriso: 0.00, boca: 0.05, escala: 0.98 },
    surpresa:  { abertura: 1.15, tampa: 0.00, incl: 0.00, sorriso: 0.00, boca: -0.1, escala: 1.12 },
    triste:    { abertura: 0.85, tampa: 0.22, incl: -0.22, sorriso: 0.00, boca: -0.55, escala: 0.96 },
    brava:     { abertura: 0.90, tampa: 0.25, incl: 0.28, sorriso: 0.00, boca: -0.35, escala: 1.00 },
  };
  // Estados que mandam no formato, por cima da emoção
  const FORMA_MODO = {
    dormindo:   { abertura: 0.07, tampa: 0.00, incl: 0.00, sorriso: 0.00, boca: 0.10, escala: 1.00 },
    executando: { abertura: 0.72, tampa: 0.14, incl: 0.06, sorriso: 0.00, boca: 0.08, escala: 0.98 },
    alerta:     { abertura: 1.18, tampa: 0.00, incl: 0.00, sorriso: 0.00, boca: -0.1, escala: 1.10 },
    offline:    { abertura: 0.55, tampa: 0.20, incl: -0.12, sorriso: 0.00, boca: -0.15, escala: 0.96 },
    privado:    { abertura: 0.16, tampa: 0.00, incl: 0.00, sorriso: 0.30, boca: 0.15, escala: 0.98 },
  };

  const estado = {
    modo: "dormindo",
    emocao: "neutra",
    voz: 0,                    // 0..1 volume da fala (boca)
    mic: 0,                    // 0..1 volume do microfone (halo)
    atual: { ...FORMA_MODO.dormindo },
    // cópia de verdade (as cores mudam aos poucos; com cópia rasa a paleta original era alterada junto e o
    // rosto não voltava mais ao lilás depois de um alerta, do modo privado ou de ficar sem internet)
    cor: { olho: [...PALETAS.normal.olho], olho2: [...PALETAS.normal.olho2], halo: [...PALETAS.normal.halo] },
    olhar: { x: 0, y: 0 }, alvoOlhar: { x: 0, y: 0 },
    piscar: 0, proxPiscada: 2, proxOlhar: 1,
    cabeca: { rot: 0, dx: 0, dy: 0 },
    gesto: null, gestoT: 0,
  };

  let W = 0, H = 0, dpr = 1;
  function redimensionar() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = canvas.clientWidth || innerWidth; H = canvas.clientHeight || innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    camada.width = W * dpr; camada.height = H * dpr;
  }
  addEventListener("resize", redimensionar);
  if (window.ResizeObserver) new ResizeObserver(redimensionar).observe(canvas);
  redimensionar();

  // Partículas (pequenos cristais flutuando)
  const cristais = Array.from({ length: 28 }, () => ({
    x: Math.random(), y: Math.random(), r: 1 + Math.random() * 2.5,
    v: 0.004 + Math.random() * 0.01, fase: Math.random() * 6.28,
  }));

  const lerp = (a, b, t) => a + (b - a) * t;
  const rgb = (c, a = 1) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;

  function retanguloArredondado(x, y, w, h, r, c = ctx) {
    r = Math.max(0, Math.min(r, w / 2, h / 2));
    c.beginPath();
    c.moveTo(x + r, y);
    c.arcTo(x + w, y, x + w, y + h, r);
    c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r);
    c.arcTo(x, y, x + w, y, r);
    c.closePath();
  }

  function desenharOlho(cx, cy, w, h, lado, p) {
    // lado: -1 olho esquerdo, +1 olho direito (o lado interno aponta para o nariz)
    let abertura = p.abertura;
    if (estado.modo === "aguardando" && lado > 0) abertura *= 1.08;   // uma "sobrancelha" levantada
    const hAberto = Math.max(h * abertura * (1 - estado.piscar), h * 0.05);
    const x = cx - w / 2, y = cy - hAberto / 2;

    // Brilho difuso atrás do olho
    const raio = w * (TRANSPARENTE ? 0.85 : 1.3);
    const halo = principal.createRadialGradient(cx, cy, 0, cx, cy, raio);
    const forcaHalo = estado.modo === "alerta" ? 0.42 : estado.modo === "offline" ? 0.12 : 0.28;
    halo.addColorStop(0, rgb(estado.cor.halo, forcaHalo));
    halo.addColorStop(1, rgb(estado.cor.halo, 0));
    principal.fillStyle = halo;
    principal.beginPath();
    principal.arc(cx, cy, raio, 0, 6.29);
    principal.fill();

    const c = cc;
    c.save();
    retanguloArredondado(x, y, w, hAberto, Math.min(w, hAberto) * 0.42, c);
    const grad = c.createLinearGradient(0, y, 0, y + hAberto);
    grad.addColorStop(0, rgb(estado.cor.olho));
    grad.addColorStop(1, rgb(estado.cor.olho2));
    c.fillStyle = grad;
    c.fill();

    if (hAberto > h * 0.3) {  // reflexo
      c.fillStyle = "rgba(255,255,255,0.55)";
      c.beginPath();
      c.ellipse(cx + w * 0.2, y + hAberto * 0.25, w * 0.09, w * 0.07, 0, 0, 6.29);
      c.fill();
    }

    c.globalCompositeOperation = "destination-out";
    c.fillStyle = "#000";
    // Pálpebra de cima, inclinada (brava: lado interno baixo; triste: lado interno alto)
    if (p.tampa > 0.01 || Math.abs(p.incl) > 0.01) {
      const base = y + hAberto * p.tampa;
      const dx = p.incl * hAberto;
      const yInterno = base + dx, yExterno = base - dx;
      const xInterno = lado < 0 ? x + w : x, xExterno = lado < 0 ? x : x + w;
      c.beginPath();
      c.moveTo(xExterno - 2, y - 2);
      c.lineTo(xInterno + 2 * -lado, y - 2);
      c.lineTo(xInterno + 2 * -lado, yInterno);
      c.lineTo(xExterno - 2 * -lado, yExterno);
      c.closePath();
      c.fill();
    }
    // Pálpebra de baixo em arco (olhos sorridentes ^^)
    if (p.sorriso > 0.01) {
      c.beginPath();
      c.ellipse(cx, y + hAberto * 1.08, w * 0.95, hAberto * p.sorriso, 0, 0, 6.29);
      c.fill();
    }
    c.restore();
  }

  function desenharBoca(cx, cy, S, p, t) {
    const larg = S * 0.11;
    ctx.strokeStyle = rgb(estado.cor.olho);
    ctx.fillStyle = rgb(estado.cor.olho);
    ctx.lineCap = "round";
    const traco = Math.max(3, S * 0.012);
    ctx.lineWidth = traco;
    const m = estado.modo;
    // brilho: o mesmo traço, largo e translúcido, por baixo (bem mais barato que sombra desfocada)
    const comBrilho = (desenhar) => {
      ctx.save();
      ctx.globalAlpha = 0.28;
      ctx.strokeStyle = ctx.fillStyle = rgb(estado.cor.halo);
      ctx.lineWidth = traco * 3.2;
      desenhar(true);
      ctx.restore();
      desenhar(false);
    };

    if (m === "falando") {
      const abre = S * 0.012 + estado.voz * S * 0.075;
      comBrilho((brilho) => {
        const f = brilho ? traco * 1.1 : 0;
        retanguloArredondado(cx - larg / 2 - f, cy - abre / 2 - f, larg + 2 * f, abre + 2 * f, (Math.min(abre, larg) + 2 * f) / 2);
        ctx.fill();
      });
    } else if (m === "pensando") {
      for (let i = 0; i < 3; i++) {
        const a = Math.sin(t * 5 - i * 0.8) * 0.5 + 0.5;
        ctx.globalAlpha = 0.35 + a * 0.65;
        ctx.beginPath();
        ctx.arc(cx - S * 0.04 + i * S * 0.04, cy - a * S * 0.012, S * 0.009, 0, 6.29);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    } else if (m === "executando") {  // boca concentrada, uma linha que ondula de leve
      ctx.beginPath();
      for (let i = 0; i <= 10; i++) {
        const xx = cx - larg / 2 + (larg * i) / 10;
        const yy = cy + Math.sin(t * 6 + i * 0.9) * S * 0.004;
        i ? ctx.lineTo(xx, yy) : ctx.moveTo(xx, yy);
      }
      ctx.stroke();
    } else if (m === "alerta" || (m !== "dormindo" && estado.emocao === "surpresa")) {
      comBrilho(() => {
        ctx.beginPath();
        ctx.ellipse(cx, cy, S * 0.022, S * 0.03, 0, 0, 6.29);
        ctx.stroke();
      });
    } else if (m === "aguardando") {  // boquinha de lado, esperando resposta
      comBrilho(() => {
        ctx.beginPath();
        ctx.moveTo(cx - larg * 0.3, cy + S * 0.004);
        ctx.quadraticCurveTo(cx + larg * 0.1, cy + S * 0.012, cx + larg * 0.35, cy - S * 0.006);
        ctx.stroke();
      });
    } else {
      const curva = p.boca * S * 0.05;
      comBrilho(() => {
        ctx.beginPath();
        ctx.moveTo(cx - larg / 2, cy);
        ctx.quadraticCurveTo(cx, cy + curva, cx + larg / 2, cy);
        ctx.stroke();
      });
    }
  }

  function desenharExtras(cx, cy, S, sep, w, t) {
    const m = estado.modo;
    ctx.fillStyle = rgb(estado.cor.olho, 0.75);
    ctx.strokeStyle = rgb(estado.cor.olho, 0.75);
    if (m === "dormindo") {
      ctx.font = `${Math.round(S * 0.035)}px system-ui`;
      for (let i = 0; i < 3; i++) {
        const f = (t * 0.35 + i / 3) % 1;
        ctx.globalAlpha = Math.sin(f * Math.PI);
        ctx.fillText("z", cx + sep + w * 0.6 + f * S * 0.08, cy - f * S * 0.16);
      }
      ctx.globalAlpha = 1;
    } else if (m === "executando") {  // arco girando: "trabalhando nisso"
      const r = S * 0.07;
      const x0 = cx + sep + w * 0.9, y0 = cy - S * 0.15;
      ctx.lineWidth = Math.max(2, S * 0.008);
      ctx.beginPath();
      ctx.arc(x0, y0, r * 0.5, t * 4, t * 4 + 4.2);
      ctx.stroke();
    } else if (m === "aguardando") {
      ctx.font = `bold ${Math.round(S * 0.06)}px system-ui`;
      ctx.globalAlpha = 0.6 + Math.sin(t * 3) * 0.3;
      ctx.fillText("?", cx + sep + w * 0.75, cy - S * 0.13 + Math.sin(t * 2) * S * 0.01);
      ctx.globalAlpha = 1;
    } else if (m === "offline") {  // nuvem cortada
      const x0 = cx + sep + w * 0.85, y0 = cy - S * 0.15, r = S * 0.022;
      ctx.lineWidth = Math.max(2, S * 0.006);
      ctx.beginPath();
      ctx.arc(x0 - r, y0, r, Math.PI * 0.5, Math.PI * 1.5);
      ctx.arc(x0, y0 - r * 0.7, r * 1.2, Math.PI, 0);
      ctx.arc(x0 + r * 1.1, y0, r, Math.PI * 1.5, Math.PI * 0.5);
      ctx.closePath();
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x0 - r * 2, y0 + r * 1.5); ctx.lineTo(x0 + r * 2, y0 - r * 2);
      ctx.stroke();
    } else if (m === "privado") {  // cadeado
      const x0 = cx + sep + w * 0.8, y0 = cy - S * 0.13, s = S * 0.022;
      ctx.lineWidth = Math.max(2, S * 0.006);
      retanguloArredondado(x0 - s, y0, s * 2, s * 1.6, s * 0.3);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(x0, y0, s * 0.7, Math.PI, 0);
      ctx.stroke();
    }
  }

  function atualizarCabeca(dt, t) {
    const m = estado.modo;
    let rot = Math.sin(t * 0.55) * 0.018, dx = 0, dy = 0;       // balanço leve
    if (m === "pensando") rot = 0.07 + Math.sin(t * 0.8) * 0.01;
    else if (m === "aguardando") rot = -0.12;
    else if (m === "ouvindo") dy = -1.5;
    else if (m === "executando") rot = Math.sin(t * 1.6) * 0.03;
    else if (m === "offline" || m === "dormindo") rot = 0.03, dy = 2;
    if (estado.gesto) {
      const g = estado.gesto, f = (t - estado.gestoT) / 0.9;
      if (f >= 1) estado.gesto = null;
      else {
        const env = Math.sin(f * Math.PI);
        if (g === "acenar") dy += Math.sin(f * Math.PI * 4) * 6 * env;
        else if (g === "negar") dx += Math.sin(f * Math.PI * 5) * 7 * env;
        else if (g === "inclinar") rot += 0.16 * env;
      }
    }
    const k = 1 - Math.pow(0.002, dt);
    estado.cabeca.rot = lerp(estado.cabeca.rot, rot, k);
    estado.cabeca.dx = estado.gesto ? dx : lerp(estado.cabeca.dx, dx, k);
    estado.cabeca.dy = estado.gesto ? dy : lerp(estado.cabeca.dy, dy, k);
  }

  // ---------------------------------------------------------------- quadros por segundo (economia)
  const QPS = { falando: 30, ouvindo: 30, alerta: 30, pensando: 20, executando: 20, aguardando: 20,
                ocioso: 10, offline: 10, dormindo: 8, privado: 8 };
  const QPS_MOVIMENTO = 30;
  let ultimo = performance.now(), ultimoDesenho = 0, turboAte = 0, espera = null, pedido = 0;

  function movimento(segundos) {  // piscada, olhar, troca de emoção: fica suave por um instante
    turboAte = Math.max(turboAte, performance.now() + segundos * 1000);
    acordar();
  }
  function agendar() {
    if (espera !== null || pedido || document.hidden) return;
    const qps = performance.now() < turboAte ? QPS_MOVIMENTO : (QPS[estado.modo] || 10);
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

    // Interpola a forma rumo ao alvo (estado > emoção) e a cor rumo à paleta do estado
    const alvo = FORMA_MODO[m] || EMOCOES[estado.emocao] || EMOCOES.neutra;
    const k = 1 - Math.pow(0.001, dt);
    for (const c in alvo) estado.atual[c] = lerp(estado.atual[c], alvo[c], k);
    const p = estado.atual;
    const pal = PALETAS[m === "alerta" ? "alerta" : m === "offline" ? "offline" : m === "privado" ? "privado" : "normal"];
    for (const c of ["olho", "olho2", "halo"]) for (let i = 0; i < 3; i++)
      estado.cor[c][i] = lerp(estado.cor[c][i], pal[c][i], 1 - Math.pow(0.02, dt));

    // Piscadas
    estado.proxPiscada -= dt;
    if (estado.proxPiscada <= 0 && m !== "dormindo" && m !== "privado") {
      estado.piscar = 1;
      estado.proxPiscada = 2.5 + Math.random() * 4;
      movimento(0.25);
    }
    estado.piscar = Math.max(0, estado.piscar - dt * 7);

    // Para onde olhar
    estado.proxOlhar -= dt;
    if (m === "pensando") estado.alvoOlhar = { x: 0.5, y: -0.55 };
    else if (m === "ouvindo" || m === "aguardando" || m === "alerta") estado.alvoOlhar = { x: 0, y: 0 };
    else if (m === "executando") estado.alvoOlhar = { x: Math.sin(t * 1.3) * 0.7, y: 0.25 };
    else if (estado.proxOlhar <= 0 && m !== "dormindo" && m !== "privado") {   // de olhos fechados não olha em volta
      estado.alvoOlhar = Math.random() < 0.45 ? { x: 0, y: 0 }
        : { x: (Math.random() - 0.5) * 1.2, y: (Math.random() - 0.5) * 0.6 };
      estado.proxOlhar = 1.2 + Math.random() * 3;
      movimento(0.45);
    }
    estado.olhar.x = lerp(estado.olhar.x, estado.alvoOlhar.x, 1 - Math.pow(0.0005, dt));
    estado.olhar.y = lerp(estado.olhar.y, estado.alvoOlhar.y, 1 - Math.pow(0.0005, dt));
    atualizarCabeca(dt, t);

    // Fundo
    const S = Math.min(W, H * 1.35) * (TRANSPARENTE ? 1.45 : 1);
    const cx = W / 2, cy = H * (TRANSPARENTE ? 0.4 : 0.44);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (TRANSPARENTE) ctx.clearRect(0, 0, W, H);
    else {
      ctx.fillStyle = FUNDO; ctx.fillRect(0, 0, W, H);
      const bg = ctx.createRadialGradient(cx, cy, 0, cx, cy, S * 0.8);
      bg.addColorStop(0, rgb(estado.cor.halo, 0.12));
      bg.addColorStop(1, rgb(estado.cor.halo, 0));
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, W, H);
      for (const c of cristais) {
        c.y -= c.v * dt;
        if (c.y < -0.02) { c.y = 1.02; c.x = Math.random(); }
        ctx.fillStyle = rgb(estado.cor.olho, 0.15 + 0.2 * Math.sin(t + c.fase) ** 2);
        ctx.save();
        ctx.translate(c.x * W + Math.sin(t * 0.5 + c.fase) * 10, c.y * H);
        ctx.rotate(Math.PI / 4);
        ctx.fillRect(-c.r, -c.r, c.r * 2, c.r * 2);
        ctx.restore();
      }
      if (m === "ouvindo") {  // halo de escuta que reage ao microfone
        const r = S * (0.42 + estado.mic * 0.08 + Math.sin(t * 3) * 0.008);
        ctx.strokeStyle = rgb(estado.cor.olho, 0.25 + estado.mic * 0.6);
        ctx.lineWidth = 2 + estado.mic * 6;
        ctx.beginPath();
        ctx.ellipse(cx, cy + S * 0.03, r, r * 0.78, 0, 0, 6.29);
        ctx.stroke();
      }
    }
    if (m === "alerta") {  // pulso de alerta
      const a = (Math.sin(t * 6) * 0.5 + 0.5) * 0.25;
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, S * 0.55);
      g.addColorStop(0, rgb(estado.cor.halo, a));
      g.addColorStop(1, rgb(estado.cor.halo, 0));
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);
    }

    // Respiração, cabeça e olhar
    const resp = m === "dormindo" || m === "privado" ? Math.sin(t * 1.2) * S * 0.01 : Math.sin(t * 1.6) * S * 0.004;
    const fala = m === "falando" ? estado.voz * S * 0.006 : 0;
    const ox = estado.olhar.x * S * 0.05, oy = estado.olhar.y * S * 0.04 + resp - fala;
    const esc = p.escala;
    const w = S * 0.15 * esc, h = S * 0.21 * esc, sep = S * 0.17;
    const cab = estado.cabeca;

    const girar = (c) => {
      c.setTransform(dpr, 0, 0, dpr, 0, 0);
      c.translate(cx + cab.dx, cy + cab.dy + S * 0.05);
      c.rotate(cab.rot);
      c.translate(-cx, -(cy + S * 0.05));
    };
    // só a região dos olhos (com folga para cabeça, olhar e escala) passa pela camada separada
    const folga = S * 0.12;
    const rx = Math.max(0, Math.floor((cx - sep - w - folga) * dpr));
    const ry = Math.max(0, Math.floor((cy - h * 0.8 - folga) * dpr));
    const rw = Math.min(camada.width - rx, Math.ceil((2 * (sep + w + folga)) * dpr));
    const rh = Math.min(camada.height - ry, Math.ceil((h * 1.6 + 2 * folga) * dpr));
    cc.setTransform(1, 0, 0, 1, 0, 0);
    cc.clearRect(rx, ry, rw, rh);
    girar(cc);
    girar(ctx);
    desenharOlho(cx - sep + ox, cy + oy, w, h, -1, p);
    desenharOlho(cx + sep + ox, cy + oy, w, h, 1, p);
    if (rw > 0 && rh > 0) {
      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.drawImage(camada, rx, ry, rw, rh, rx, ry, rw, rh);
      ctx.restore();
    }
    girar(ctx);
    desenharBoca(cx + ox * 0.6, cy + h * 0.5 + S * 0.1 + oy * 0.5, S, p, t);
    desenharExtras(cx, cy + oy, S, sep, w, t);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    agendar();
  }
  agendar();

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
})();
