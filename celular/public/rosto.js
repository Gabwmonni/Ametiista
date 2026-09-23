// Rosto da Ametista: olhos e boca desenhados em canvas, com emoções e sincronia labial.
(() => {
  const canvas = document.getElementById("rosto");
  const ctx = canvas.getContext("2d");
  // Camada separada para os olhos: as pálpebras "apagam" pixels (sem manchas pretas sobre o brilho)
  const camada = document.createElement("canvas");
  const cc = camada.getContext("2d");
  const principal = ctx;
  // data-transparente="1": sem fundo nem partículas (para a sobreposição por cima do Windows)
  const TRANSPARENTE = canvas.dataset.transparente === "1";
  const COR = { fundo: "#07050c", olho: "#c79bff", olho2: "#8a4dff", brilho: "#f3e8ff" };

  // Formato alvo de cada emoção
  const EMOCOES = {
    neutra:    { abertura: 1.00, tampa: 0.00, incl: 0.00, sorriso: 0.00, boca: 0.25, escala: 1.00 },
    feliz:     { abertura: 1.00, tampa: 0.00, incl: 0.00, sorriso: 0.62, boca: 0.75, escala: 1.02 },
    pensativa: { abertura: 0.80, tampa: 0.18, incl: 0.00, sorriso: 0.00, boca: 0.05, escala: 0.98 },
    surpresa:  { abertura: 1.15, tampa: 0.00, incl: 0.00, sorriso: 0.00, boca: -0.1, escala: 1.12 },
    triste:    { abertura: 0.85, tampa: 0.22, incl: -0.22, sorriso: 0.00, boca: -0.55, escala: 0.96 },
    brava:     { abertura: 0.90, tampa: 0.25, incl: 0.28, sorriso: 0.00, boca: -0.35, escala: 1.00 },
    dormindo:  { abertura: 0.07, tampa: 0.00, incl: 0.00, sorriso: 0.00, boca: 0.10, escala: 1.00 },
  };

  const estado = {
    modo: "dormindo",          // dormindo | ocioso | ouvindo | pensando | falando
    emocao: "neutra",
    voz: 0,                    // 0..1 volume da fala (boca)
    mic: 0,                    // 0..1 volume do microfone (halo)
    atual: { ...EMOCOES.dormindo },
    olhar: { x: 0, y: 0 }, alvoOlhar: { x: 0, y: 0 },
    piscar: 0, proxPiscada: 2, proxOlhar: 1,
  };

  let W = 0, H = 0, dpr = 1;
  function redimensionar() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = canvas.clientWidth || innerWidth; H = canvas.clientHeight || innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    camada.width = W * dpr; camada.height = H * dpr;
    cc.setTransform(dpr, 0, 0, dpr, 0, 0);
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

  function retanguloArredondado(x, y, w, h, r, c = ctx) {
    r = Math.max(0, Math.min(r, w / 2, h / 2));
    const ctx = c;
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function desenharOlho(cx, cy, w, h, lado, p) {
    // lado: -1 olho esquerdo, +1 olho direito (o lado interno aponta para o nariz)
    const hAberto = Math.max(h * p.abertura * (1 - estado.piscar), h * 0.05);
    const x = cx - w / 2, y = cy - hAberto / 2;

    // Brilho difuso atrás do olho
    const raio = w * (TRANSPARENTE ? 0.85 : 1.3);  // no painel pequeno, halo menor (sem "caixa" visível)
    const halo = principal.createRadialGradient(cx, cy, 0, cx, cy, raio);
    halo.addColorStop(0, "rgba(160,100,255,0.28)");
    halo.addColorStop(1, "rgba(160,100,255,0)");
    principal.fillStyle = halo;
    principal.beginPath();
    principal.arc(cx, cy, raio, 0, 6.29);
    principal.fill();

    const ctx = cc;
    ctx.save();
    retanguloArredondado(x, y, w, hAberto, Math.min(w, hAberto) * 0.42, ctx);
    const grad = ctx.createLinearGradient(0, y, 0, y + hAberto);
    grad.addColorStop(0, COR.olho);
    grad.addColorStop(1, COR.olho2);
    ctx.fillStyle = grad;
    ctx.fill();

    // Reflexo
    if (hAberto > h * 0.3) {
      ctx.fillStyle = "rgba(255,255,255,0.55)";
      ctx.beginPath();
      ctx.ellipse(cx + w * 0.2, y + hAberto * 0.25, w * 0.09, w * 0.07, 0, 0, 6.29);
      ctx.fill();
    }

    ctx.globalCompositeOperation = "destination-out";
    ctx.fillStyle = "#000";
    // Pálpebra de cima, inclinada (brava: lado interno baixo; triste: lado interno alto)
    if (p.tampa > 0.01 || Math.abs(p.incl) > 0.01) {
      const base = y + hAberto * p.tampa;
      const dx = p.incl * hAberto;
      const yInterno = base + dx, yExterno = base - dx;
      const xInterno = lado < 0 ? x + w : x, xExterno = lado < 0 ? x : x + w;
      ctx.beginPath();
      ctx.moveTo(xExterno - 2, y - 2);
      ctx.lineTo(xInterno + 2 * -lado, y - 2);
      ctx.lineTo(xInterno + 2 * -lado, yInterno);
      ctx.lineTo(xExterno - 2 * -lado, yExterno);
      ctx.closePath();
      ctx.fill();
    }
    // Pálpebra de baixo em arco (olhos sorridentes ^^)
    if (p.sorriso > 0.01) {
      ctx.beginPath();
      ctx.ellipse(cx, y + hAberto * 1.08, w * 0.95, hAberto * p.sorriso, 0, 0, 6.29);
      ctx.fill();
    }
    ctx.restore();
  }

  function desenharBoca(cx, cy, S, p, t) {
    const larg = S * 0.11;
    ctx.strokeStyle = COR.olho;
    ctx.fillStyle = COR.olho;
    ctx.lineCap = "round";
    ctx.lineWidth = Math.max(3, S * 0.012);
    ctx.shadowColor = "rgba(160,100,255,0.8)";
    ctx.shadowBlur = 14;

    if (estado.modo === "falando") {
      const abre = S * 0.012 + estado.voz * S * 0.075;
      retanguloArredondado(cx - larg / 2, cy - abre / 2, larg, abre, Math.min(abre, larg) / 2);
      ctx.fill();
    } else if (estado.modo === "pensando") {
      for (let i = 0; i < 3; i++) {
        const a = Math.sin(t * 5 - i * 0.8) * 0.5 + 0.5;
        ctx.globalAlpha = 0.35 + a * 0.65;
        ctx.beginPath();
        ctx.arc(cx - S * 0.04 + i * S * 0.04, cy - a * S * 0.012, S * 0.009, 0, 6.29);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    } else if (estado.emocao === "surpresa") {
      ctx.beginPath();
      ctx.ellipse(cx, cy, S * 0.022, S * 0.03, 0, 0, 6.29);
      ctx.stroke();
    } else {
      const curva = p.boca * S * 0.05;
      ctx.beginPath();
      ctx.moveTo(cx - larg / 2, cy);
      ctx.quadraticCurveTo(cx, cy + curva, cx + larg / 2, cy);
      ctx.stroke();
    }
    ctx.shadowBlur = 0;
  }

  let ultimo = performance.now();
  function quadro(agora) {
    const dt = Math.min((agora - ultimo) / 1000, 0.05);
    ultimo = agora;
    const t = agora / 1000;

    // Interpola a forma rumo à emoção alvo
    const alvo = estado.modo === "dormindo" ? EMOCOES.dormindo : (EMOCOES[estado.emocao] || EMOCOES.neutra);
    for (const k in alvo) estado.atual[k] = lerp(estado.atual[k], alvo[k], 1 - Math.pow(0.001, dt));
    const p = estado.atual;

    // Piscadas
    estado.proxPiscada -= dt;
    if (estado.proxPiscada <= 0 && estado.modo !== "dormindo") {
      estado.piscar = 1;
      estado.proxPiscada = 2.5 + Math.random() * 4;
    }
    estado.piscar = Math.max(0, estado.piscar - dt * 7);

    // Para onde olhar
    estado.proxOlhar -= dt;
    if (estado.modo === "pensando") estado.alvoOlhar = { x: 0.5, y: -0.55 };
    else if (estado.modo === "ouvindo") estado.alvoOlhar = { x: 0, y: 0 };
    else if (estado.proxOlhar <= 0) {
      estado.alvoOlhar = Math.random() < 0.45 ? { x: 0, y: 0 }
        : { x: (Math.random() - 0.5) * 1.2, y: (Math.random() - 0.5) * 0.6 };
      estado.proxOlhar = 1.2 + Math.random() * 3;
    }
    estado.olhar.x = lerp(estado.olhar.x, estado.alvoOlhar.x, 1 - Math.pow(0.0005, dt));
    estado.olhar.y = lerp(estado.olhar.y, estado.alvoOlhar.y, 1 - Math.pow(0.0005, dt));

    // Fundo
    const S = Math.min(W, H * 1.35) * (TRANSPARENTE ? 1.45 : 1);
    const cx = W / 2, cy = H * (TRANSPARENTE ? 0.4 : 0.44);
    if (TRANSPARENTE) ctx.clearRect(0, 0, W, H);
    else { ctx.fillStyle = COR.fundo; ctx.fillRect(0, 0, W, H); }
    const bg = ctx.createRadialGradient(cx, cy, 0, cx, cy, S * 0.8);
    bg.addColorStop(0, "rgba(90,40,160,0.18)");
    bg.addColorStop(1, "rgba(90,40,160,0)");
    ctx.fillStyle = bg;
    if (!TRANSPARENTE) ctx.fillRect(0, 0, W, H);

    for (const c of TRANSPARENTE ? [] : cristais) {
      c.y -= c.v * dt;
      if (c.y < -0.02) { c.y = 1.02; c.x = Math.random(); }
      ctx.fillStyle = `rgba(183,125,255,${0.15 + 0.2 * Math.sin(t + c.fase) ** 2})`;
      ctx.save();
      ctx.translate(c.x * W + Math.sin(t * 0.5 + c.fase) * 10, c.y * H);
      ctx.rotate(Math.PI / 4);
      ctx.fillRect(-c.r, -c.r, c.r * 2, c.r * 2);
      ctx.restore();
    }

    // Halo de escuta que reage ao microfone
    if (estado.modo === "ouvindo" && !TRANSPARENTE) {
      const r = S * (0.42 + estado.mic * 0.08 + Math.sin(t * 3) * 0.008);
      ctx.strokeStyle = `rgba(183,125,255,${0.25 + estado.mic * 0.6})`;
      ctx.lineWidth = 2 + estado.mic * 6;
      ctx.beginPath();
      ctx.ellipse(cx, cy + S * 0.03, r, r * 0.78, 0, 0, 6.29);
      ctx.stroke();
    }

    // Respiração e balanço leves
    const resp = estado.modo === "dormindo" ? Math.sin(t * 1.2) * S * 0.01 : Math.sin(t * 1.6) * S * 0.004;
    const fala = estado.modo === "falando" ? estado.voz * S * 0.006 : 0;
    const ox = estado.olhar.x * S * 0.05, oy = estado.olhar.y * S * 0.04 + resp - fala;

    const esc = p.escala;
    const w = S * 0.15 * esc, h = S * 0.21 * esc, sep = S * 0.17;
    cc.clearRect(0, 0, W, H);
    desenharOlho(cx - sep + ox, cy + oy, w, h, -1, p);
    desenharOlho(cx + sep + ox, cy + oy, w, h, 1, p);
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(camada, 0, 0);
    ctx.restore();
    desenharBoca(cx + ox * 0.6, cy + h * 0.5 + S * 0.1 + oy * 0.5, S, p, t);

    // Zzz quando dormindo
    if (estado.modo === "dormindo") {
      ctx.fillStyle = "rgba(183,125,255,0.6)";
      ctx.font = `${Math.round(S * 0.035)}px system-ui`;
      for (let i = 0; i < 3; i++) {
        const f = (t * 0.35 + i / 3) % 1;
        ctx.globalAlpha = Math.sin(f * Math.PI);
        ctx.fillText("z", cx + sep + w * 0.6 + f * S * 0.08, cy - f * S * 0.16);
      }
      ctx.globalAlpha = 1;
    }

    requestAnimationFrame(quadro);
  }
  requestAnimationFrame(quadro);

  window.Rosto = {
    modo(m) { estado.modo = m; },
    emocao(e) { estado.emocao = EMOCOES[e] ? e : "neutra"; },
    voz(v) { estado.voz = v; },
    mic(v) { estado.mic = v; },
    get estado() { return estado; },
  };
})();
