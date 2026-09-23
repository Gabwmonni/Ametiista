// Ametista no celular: status do PC, conversa por texto e voz, tela do PC e avisos.
(() => {
  const $ = (id) => document.getElementById(id);
  const CHAVE_TOKEN = "ametista_token";
  let token = lerToken();
  let ws = null, estado = null, audioCtx = null, fonteAtual = null;
  let aguardando = new Map();   // id do pedido -> elemento "digitando…"
  let reconectar = 1000;

  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});

  function lerToken() { try { return localStorage.getItem(CHAVE_TOKEN); } catch { return null; } }
  function salvarToken(t) { try { t ? localStorage.setItem(CHAVE_TOKEN, t) : localStorage.removeItem(CHAVE_TOKEN); } catch {} }

  // ---------------------------------------------------------------- pareamento
  function mostrarTela(qual) {
    $("telaParear").classList.toggle("oculta", qual !== "parear");
    $("telaPrincipal").classList.toggle("oculta", qual !== "principal");
  }

  async function parear(codigo) {
    $("erroParear").textContent = "";
    try {
      const r = await fetch("/api/parear", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ codigo, nome: nomeAparelho() }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.erro || "Não deu certo.");
      token = d.token; salvarToken(token);
      history.replaceState(null, "", "/");
      iniciar();
    } catch (e) {
      $("erroParear").textContent = e.message;
    }
  }

  function nomeAparelho() {
    const ua = navigator.userAgent;
    if (/iPhone/.test(ua)) return "iPhone";
    if (/Android/.test(ua)) return (ua.match(/Android[^;]*;\s*([^;)]+)/) || [, "Android"])[1].trim().slice(0, 30);
    return "Celular";
  }

  $("formParear").onsubmit = (e) => { e.preventDefault(); parear($("codigo").value); };

  // ---------------------------------------------------------------- conexão
  function conectar() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/api/ws?papel=celular&token=${encodeURIComponent(token)}`);
    ws.onopen = () => { reconectar = 1000; };
    ws.onmessage = (ev) => receber(JSON.parse(ev.data));
    ws.onclose = (ev) => {
      if (ev.code === 4001) { sair("Este celular foi desconectado pelo PC. Pareie de novo."); return; }
      pintarEstado(null);
      setTimeout(async () => {
        // token ainda vale? (401 = foi revogado)
        const r = await fetch("/api/estado", { headers: { authorization: "Bearer " + token } }).catch(() => null);
        if (r && r.status === 401) return sair("Pareamento expirou. Pareie de novo.");
        conectar();
      }, reconectar);
      reconectar = Math.min(reconectar * 2, 20000);
    };
  }

  function sair(motivo) {
    token = null; salvarToken(null);
    mostrarTela("parear");
    $("erroParear").textContent = motivo || "";
  }

  const enviar = (msg) => ws && ws.readyState === 1 && (ws.send(JSON.stringify(msg)), true);

  // ---------------------------------------------------------------- status do PC
  function tempoRelativo(ms) {
    const s = Math.round((Date.now() - ms) / 1000);
    if (s < 60) return "agora há pouco";
    const m = Math.round(s / 60);
    if (m < 60) return `há ${m} min`;
    const h = Math.floor(m / 60);
    if (h < 24) return `há ${h} h${m % 60 ? " " + (m % 60) + " min" : ""}`;
    return `há ${Math.floor(h / 24)} dia(s)`;
  }
  const hora = (ms) => new Date(ms).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  const dia = (ms) => {
    const d = new Date(ms), hoje = new Date();
    const ontem = new Date(); ontem.setDate(hoje.getDate() - 1);
    if (d.toDateString() === hoje.toDateString()) return "hoje";
    if (d.toDateString() === ontem.toDateString()) return "ontem";
    return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  };

  function pintarEstado(e) {
    const pil = $("pilula"), est = $("estadoPc"), det = $("detalhePc");
    pil.className = "pilula";
    if (!e) { pil.textContent = "sem conexão"; est.textContent = "Conectando…"; det.textContent = ""; Rosto.modo("dormindo"); return; }
    if (e.online) {
      pil.classList.add("ligado"); pil.textContent = "PC ligado";
      est.textContent = e.desde ? `Ligado desde ${dia(e.desde)} às ${hora(e.desde)}` : "PC ligado";
      const i = e.info || {};
      const partes = [];
      if (e.desde) partes.push("ligado " + tempoRelativo(e.desde));
      if (i.cpu != null) partes.push(`CPU ${i.cpu}%`);
      if (i.ram != null) partes.push(`memória ${i.ram}%`);
      if (i.tocando) partes.push(`♫ ${i.tocando}`);
      if (i.janela) partes.push(`🪟 ${i.janela}`);
      det.textContent = partes.join(" · ");
      if (Rosto.estado.modo === "dormindo") { Rosto.modo("ocioso"); Rosto.emocao("feliz"); }
    } else {
      pil.classList.add("desligado"); pil.textContent = "PC desligado";
      est.textContent = "PC desligado ou sem internet";
      det.textContent = e.ultimo ? `Visto por último ${dia(e.ultimo)} às ${hora(e.ultimo)} (${tempoRelativo(e.ultimo)})` : "";
      Rosto.modo("dormindo");
    }
  }

  // ---------------------------------------------------------------- conversa
  function adicionar(classe, texto, extra) {
    const div = document.createElement("div");
    div.className = "msg " + classe;
    if (texto) div.appendChild(document.createTextNode(texto));
    if (extra) div.appendChild(extra);
    $("conversa").appendChild(div);
    $("conversa").scrollTop = $("conversa").scrollHeight;
    return div;
  }

  function digitando() {
    const s = document.createElement("span");
    s.className = "digitando"; s.innerHTML = "<i></i><i></i><i></i>";
    return adicionar("ela", "", s);
  }

  let notificacoesVistas = new Set();
  async function receber(m) {
    switch (m.tipo) {
      case "estado":
        estado = m; pintarEstado(m);
        for (const n of m.notificacoes || []) mostrarNotificacao(n, true);
        break;
      case "transcricao": {
        const bolha = aguardando.get(m.id);
        const minha = document.querySelector(`[data-pedido-id="${m.id}"]`);
        if (minha) minha.firstChild.textContent = "🎤 " + m.texto;
        break;
      }
      case "resposta": {
        const bolha = aguardando.get(m.id);
        if (bolha) { bolha.textContent = m.texto; aguardando.delete(m.id); } else adicionar("ela", m.texto);
        Rosto.emocao(m.emocao || "neutra");
        if (m.audio) tocar(m.audio, m.mime);
        break;
      }
      case "tela": {
        const bolha = aguardando.get(m.id);
        if (bolha) { bolha.remove(); aguardando.delete(m.id); }
        const src = "data:image/jpeg;base64," + m.imagem;
        $("imgTela").src = src;
        $("modalTela").classList.remove("oculta");
        if (m.janela) adicionar("aviso", "🖥️ " + m.janela);
        break;
      }
      case "erro": {
        const bolha = aguardando.get(m.id);
        if (bolha) { bolha.textContent = "⚠️ " + m.texto; aguardando.delete(m.id); } else adicionar("aviso", "⚠️ " + m.texto);
        Rosto.emocao("triste");
        break;
      }
      case "notificacao":
        mostrarNotificacao(m, false);
        break;
    }
  }

  function mostrarNotificacao(n, antiga) {
    const chave = n.quando + n.texto;
    if (notificacoesVistas.has(chave)) return;
    notificacoesVistas.add(chave);
    if (antiga && Date.now() - n.quando > 6 * 3600_000) return;  // mostra só as das últimas 6 h
    const q = document.createElement("span");
    q.className = "quando"; q.textContent = `${dia(n.quando)} às ${hora(n.quando)}`;
    adicionar("notif", `🔔 ${n.titulo ? n.titulo + ": " : ""}${n.texto}`, q);
    if (!antiga && navigator.vibrate) navigator.vibrate(120);
  }

  let contador = 0;
  function pedir(texto) {
    texto = texto.trim();
    if (!texto) return;
    if (!estado || !estado.online) { adicionar("aviso", "O PC está desligado ou sem internet agora."); return; }
    const id = "p" + Date.now() + (contador++);
    adicionar("eu", texto).dataset.pedidoId = id;
    aguardando.set(id, digitando());
    Rosto.emocao("pensativa");
    if (!enviar({ tipo: "pedido", id, texto })) adicionar("aviso", "Sem conexão, tentando de novo…");
  }

  function pedirTela() {
    if (!estado || !estado.online) { adicionar("aviso", "O PC está desligado."); return; }
    const id = "t" + Date.now();
    aguardando.set(id, digitando());
    enviar({ tipo: "tela", id });
  }

  $("formPedido").onsubmit = (e) => { e.preventDefault(); garantirAudio(); pedir($("entrada").value); $("entrada").value = ""; };
  $("atalhos").onclick = (e) => {
    const b = e.target.closest("button"); if (!b) return;
    garantirAudio();
    b.dataset.pedido === "__tela" ? pedirTela() : pedir(b.dataset.pedido);
  };
  $("btnFecharTela").onclick = () => $("modalTela").classList.add("oculta");
  $("btnAtualizarTela").onclick = () => { $("modalTela").classList.add("oculta"); pedirTela(); };

  // ---------------------------------------------------------------- voz: gravar (segure o botão)
  let gravador = null, pedacos = [], inicioGravacao = 0;
  const btnMic = $("btnMic");

  async function comecarGravar(e) {
    e.preventDefault();
    garantirAudio();
    if (gravador) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const tipos = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus", "audio/webm"];
      const mime = tipos.find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || "";
      gravador = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      pedacos = [];
      gravador.ondataavailable = (ev) => ev.data.size && pedacos.push(ev.data);
      gravador.onstop = () => { stream.getTracks().forEach((t) => t.stop()); enviarAudio(gravador.mimeType); gravador = null; };
      gravador.start();
      inicioGravacao = Date.now();
      btnMic.classList.add("gravando");
      Rosto.modo("ouvindo");
      if (navigator.vibrate) navigator.vibrate(30);
    } catch (err) {
      adicionar("aviso", "Não consegui usar o microfone: " + err.message);
    }
  }

  function pararGravar(e) {
    e && e.preventDefault();
    if (!gravador) return;
    btnMic.classList.remove("gravando");
    Rosto.modo(estado && estado.online ? "ocioso" : "dormindo");
    if (Date.now() - inicioGravacao < 500) { pedacos = []; gravador.onstop = () => { gravador.stream.getTracks().forEach((t) => t.stop()); gravador = null; }; }
    gravador.stop();
  }

  async function enviarAudio(mime) {
    if (!pedacos.length) return;
    const blob = new Blob(pedacos, { type: mime || "audio/webm" });
    if (!estado || !estado.online) { adicionar("aviso", "O PC está desligado."); return; }
    const b64 = await new Promise((ok) => { const r = new FileReader(); r.onload = () => ok(r.result.split(",")[1]); r.readAsDataURL(blob); });
    const id = "a" + Date.now();
    adicionar("eu", "🎤 …").dataset.pedidoId = id;
    aguardando.set(id, digitando());
    Rosto.emocao("pensativa");
    enviar({ tipo: "pedido", id, audio: b64, mime: blob.type });
  }

  btnMic.addEventListener("pointerdown", comecarGravar);
  btnMic.addEventListener("pointerup", pararGravar);
  btnMic.addEventListener("pointerleave", pararGravar);
  btnMic.addEventListener("pointercancel", pararGravar);
  btnMic.addEventListener("contextmenu", (e) => e.preventDefault());

  // ---------------------------------------------------------------- voz: tocar a resposta
  function garantirAudio() {
    if (!audioCtx) { try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch {} }
    if (audioCtx && audioCtx.state === "suspended") audioCtx.resume();
  }

  async function tocar(b64, mime) {
    garantirAudio();
    if (!audioCtx) return;
    try {
      if (fonteAtual) try { fonteAtual.stop(); } catch {}
      const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      const buffer = await audioCtx.decodeAudioData(bytes.buffer);
      const fonte = audioCtx.createBufferSource(), an = audioCtx.createAnalyser();
      an.fftSize = 512; fonte.buffer = buffer;
      fonte.connect(an).connect(audioCtx.destination);
      const dados = new Uint8Array(an.fftSize);
      fonteAtual = fonte;
      Rosto.modo("falando");
      let ativo = true;
      const medir = () => {
        if (!ativo) return;
        an.getByteTimeDomainData(dados);
        let s = 0; for (const v of dados) s += ((v - 128) / 128) ** 2;
        Rosto.voz(Math.min(1, Math.sqrt(s / dados.length) * 4.5));
        requestAnimationFrame(medir);
      };
      fonte.onended = () => { ativo = false; fonteAtual = null; Rosto.voz(0); Rosto.modo("ocioso"); Rosto.emocao("neutra"); };
      fonte.start(); medir();
    } catch (e) { console.warn("não consegui tocar o áudio", e); }
  }

  // ---------------------------------------------------------------- início
  function iniciar() {
    mostrarTela("principal");
    pintarEstado(null);
    conectar();
    // confere o estado de tempos em tempos (detecta PC que caiu sem avisar)
    setInterval(() => enviar({ tipo: "estado" }), 30_000);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) enviar({ tipo: "estado" }); });
  }

  const doLink = new URLSearchParams(location.hash.slice(1)).get("parear");
  if (doLink) { mostrarTela("parear"); $("codigo").value = doLink; parear(doLink); }
  else if (token) iniciar();
  else mostrarTela("parear");
})();
