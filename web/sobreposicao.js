// Sobreposição da Ametista: aparece por cima de tudo quando chamada, fala e some sozinha.
// Quem escuta o microfone é o Python (ouvido.py); aqui só mostramos o estado e tocamos a voz.
(() => {
  const $ = (id) => document.getElementById(id);
  const painel = $("painel"), statusEl = $("status"), origemEl = $("origem");
  const pedidoEl = $("pedido"), respostaEl = $("resposta"), entrada = $("entrada");
  const noNavegador = !new URLSearchParams(location.search).has("sobreposicao");
  if (noNavegador) document.body.classList.add("navegador");

  let ws, audioCtx = null, fonteAtual = null, falando = false;
  let timerEsconder = null;

  // ---------------------------------------------------------------- visual
  const NOMES = { ouvindo: "ouvindo…", pensando: "pensando…", falando: "Ametista", ocioso: "Ametista" };
  function modo(m) {
    Rosto.modo(m === "ocioso" ? "ocioso" : m);
    painel.classList.remove("ouvindo", "pensando", "falando");
    if (m !== "ocioso") painel.classList.add(m);
    statusEl.textContent = NOMES[m] || m;
  }

  function mostrar() {
    clearTimeout(timerEsconder);
    painel.classList.add("visivel");
  }

  function esconder(depois = 0) {
    clearTimeout(timerEsconder);
    timerEsconder = setTimeout(() => {
      if (falando || document.activeElement === entrada && entrada.value) return;
      if (noNavegador) return modo("ocioso");  // no navegador (teste) o painel fica sempre visível
      painel.classList.remove("visivel");
      modo("ocioso");
      setTimeout(() => enviar({ tipo: "esconder" }), 380);  // a janela some depois da animação
    }, depois);
  }

  function nivel(v) { painel.style.setProperty("--nivel", Math.min(1, v).toFixed(3)); }

  // ---------------------------------------------------------------- conexão
  function conectar() {
    ws = window.__ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onmessage = (ev) => receber(JSON.parse(ev.data));
    ws.onclose = () => setTimeout(conectar, 1500);
  }
  const enviar = (msg) => ws && ws.readyState === 1 && ws.send(JSON.stringify(msg));

  async function receber(m) {
    switch (m.tipo) {
      case "acordou":
        mostrar(); calar();
        pedidoEl.textContent = ""; respostaEl.textContent = ""; respostaEl.classList.remove("aviso");
        origemEl.textContent = "";
        Rosto.emocao("feliz"); modo("ouvindo");
        if (m.manual) setTimeout(() => entrada.focus(), 50);
        break;
      case "ouvindo":
        mostrar(); Rosto.emocao("neutra"); modo("ouvindo");
        break;
      case "mic":
        Rosto.mic(m.nivel); nivel(m.nivel);
        break;
      case "transcricao":
        mostrar(); pedidoEl.textContent = (m.quem ? m.quem + ": " : "") + m.texto;
        break;
      case "cadastro":  // cadastro de voz: mostra a frase para a pessoa ler
        mostrar(); calar();
        Rosto.emocao("feliz"); modo("ouvindo");
        statusEl.textContent = `aprendendo a voz de ${m.nome} · ${m.passo} de ${m.total}`;
        pedidoEl.textContent = "Leia em voz alta, com calma:";
        respostaEl.classList.remove("aviso");
        respostaEl.textContent = "“" + m.frase + "”";
        break;
      case "pensando":
        mostrar(); Rosto.emocao("pensativa"); modo("pensando"); nivel(0);
        respostaEl.textContent = ""; respostaEl.classList.remove("aviso");
        break;
      case "resposta":
      case "alerta":
        mostrar();
        if (m.tipo === "alerta") { pedidoEl.textContent = "⏰ aviso"; await tocarAlarme(); }
        Rosto.emocao(m.emocao || "neutra");
        respostaEl.classList.remove("aviso");
        respostaEl.textContent = m.texto;
        origemEl.textContent = { local: "⚡ local", nuvem: "☁ nuvem", "local-ia": "🖥 IA local", erro: "⚠" }[m.origem] || "";
        await falar(m.texto, m.audio);
        enviar({ tipo: "fala_terminou" });
        modo("ocioso");
        esconder(9000);  // se o ouvido não pedir seguimento, some sozinha
        break;
      case "ocioso":
        modo("ocioso"); nivel(0);
        esconder(respostaEl.textContent ? 3500 : 600);
        break;
      case "aviso":
        mostrar(); respostaEl.textContent = m.texto; respostaEl.classList.add("aviso");
        esconder(5000);
        break;
    }
  }

  // ---------------------------------------------------------------- fala
  function garantirAudio() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") audioCtx.resume();
    return audioCtx;
  }

  async function falar(texto, audioB64) {
    falando = true;
    modo("falando");
    try {
      if (audioB64) await tocarMp3(audioB64);
      else await falarNavegador(texto);
    } catch (e) {
      console.warn("áudio falhou, usando voz do sistema", e);
      await falarNavegador(texto);
    }
    falando = false;
    Rosto.voz(0); nivel(0);
    Rosto.emocao("neutra");
  }

  async function tocarMp3(b64) {
    const ctx = garantirAudio();
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const buffer = await ctx.decodeAudioData(bytes.buffer);
    const fonte = ctx.createBufferSource(), analisador = ctx.createAnalyser();
    analisador.fftSize = 512;
    fonte.buffer = buffer;
    fonte.connect(analisador).connect(ctx.destination);
    const dados = new Uint8Array(analisador.fftSize);
    fonteAtual = fonte;
    return new Promise((ok) => {
      let ativo = true;
      const medir = () => {
        if (!ativo) return;
        analisador.getByteTimeDomainData(dados);
        let soma = 0;
        for (const v of dados) soma += ((v - 128) / 128) ** 2;
        const v = Math.min(1, Math.sqrt(soma / dados.length) * 4.5);
        Rosto.voz(v); nivel(v * 0.7);
        requestAnimationFrame(medir);
      };
      fonte.onended = () => { ativo = false; fonteAtual = null; ok(); };
      fonte.start();
      medir();
    });
  }

  function falarNavegador(texto) {
    return new Promise((ok) => {
      if (!("speechSynthesis" in window)) return setTimeout(ok, 1500);
      const u = new SpeechSynthesisUtterance(texto);
      u.lang = "pt-BR";
      const voz = speechSynthesis.getVoices().find((v) => v.lang.startsWith("pt"));
      if (voz) u.voice = voz;
      let ativo = true;
      const boca = () => { if (!ativo) return; Rosto.voz(0.25 + Math.random() * 0.6); setTimeout(boca, 90); };
      u.onend = u.onerror = () => { ativo = false; ok(); };
      speechSynthesis.speak(u);
      boca();
      setTimeout(() => { if (ativo) { ativo = false; ok(); } }, 4000 + texto.length * 90);  // segurança
    });
  }

  function calar() {
    if (fonteAtual) try { fonteAtual.stop(); } catch {}
    if ("speechSynthesis" in window) speechSynthesis.cancel();
  }

  function tocarAlarme() {
    const ctx = garantirAudio();
    [880, 1175, 1568, 1175, 1568].forEach((f, i) => {
      const o = ctx.createOscillator(), g = ctx.createGain(), t0 = ctx.currentTime + i * 0.16;
      o.frequency.value = f;
      g.gain.setValueAtTime(0, t0);
      g.gain.linearRampToValueAtTime(0.22, t0 + 0.02);
      g.gain.exponentialRampToValueAtTime(0.001, t0 + 0.45);
      o.connect(g).connect(ctx.destination);
      o.start(t0); o.stop(t0 + 0.5);
    });
    return new Promise((ok) => setTimeout(ok, 1000));
  }

  // ---------------------------------------------------------------- interação
  $("formulario").onsubmit = (e) => {
    e.preventDefault();
    const t = entrada.value.trim();
    if (!t) return;
    garantirAudio();
    entrada.value = "";
    enviar({ tipo: "texto", texto: t });
  };
  $("btnMic").onclick = () => { garantirAudio(); calar(); enviar({ tipo: "chamar" }); };
  $("rosto").onclick = () => { if (falando) calar(); };

  addEventListener("keydown", (e) => {
    garantirAudio();
    if (e.key === "Escape") {
      calar();
      enviar({ tipo: "cancelar_escuta" });
      falando = false;
      esconder(0);
    }
  });
  addEventListener("pointerdown", garantirAudio, { once: true });

  // No navegador (teste), mostra o painel logo de cara
  if (noNavegador) {
    mostrar();
    respostaEl.textContent = 'Diga "Ametista" ou digite abaixo.';
  }
  modo("ocioso");
  conectar();
})();
