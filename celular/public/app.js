// Ametista no celular: status do PC, conversa por texto e voz, tela do PC e avisos.
(() => {
  const $ = (id) => document.getElementById(id);
  const CHAVE_TOKEN = "ametista_token";
  const CHAVE_VOZ = "ametista_voz";
  const MAX_MENSAGENS = 120;        // a conversa na tela não cresce para sempre (memória do celular)
  const PAUSAR_APOS_MS = 20_000;    // app em segundo plano há 20 s: desconecta (bateria e dados)
  let token = lerToken();
  let vozLigada = lerVoz();
  let pausado = false, timerPausa = null, ultimaMensagem = Date.now(), iniciado = false;
  let ws = null, estado = null, audioCtx = null, fonteAtual = null;
  let aguardando = new Map();   // id do pedido -> elemento "digitando…"
  let reconectar = 1000;

  if ("serviceWorker" in navigator) {
    const jaTinha = !!navigator.serviceWorker.controller;   // chegou versão nova do app: recarrega uma vez para usá-la
    navigator.serviceWorker.addEventListener("controllerchange", () => { if (jaTinha) location.reload(); });
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }

  function lerToken() { try { return localStorage.getItem(CHAVE_TOKEN); } catch { return null; } }
  function lerVoz() { try { return localStorage.getItem(CHAVE_VOZ) !== "0"; } catch { return true; } }
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
    ws.onmessage = (ev) => { ultimaMensagem = Date.now(); receber(JSON.parse(ev.data)); };
    ws.onclose = (ev) => {
      if (ev.code === 4001) { sair("Este celular foi desconectado pelo PC. Pareie de novo."); return; }
      if (pausado) return;              // fechamos de propósito (app em segundo plano)
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
    const info = e.info || {};
    $("btnPrivado").setAttribute("aria-pressed", !!info.privado);
    if (e.online && info.privado) { pil.classList.add("privado"); }
    if (e.online) {
      if (!info.privado) pil.classList.add("ligado");
      pil.textContent = info.privado ? "modo privado" : "PC ligado";
      est.textContent = e.desde ? `Ligado desde ${dia(e.desde)} às ${hora(e.desde)}` : "PC ligado";
      const i = e.info || {};
      const partes = [];
      if (e.desde) partes.push("ligado " + tempoRelativo(e.desde));
      if (i.cpu != null) partes.push(`CPU ${i.cpu}%`);
      if (i.ram != null) partes.push(`memória ${i.ram}%`);
      if (i.tocando) partes.push(`♫ ${i.tocando}`);
      if (i.janela) partes.push(`🪟 ${i.janela}`);
      if (i.tarefa) partes.push(`⚙️ ${i.tarefa}`);
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
    const conversa = $("conversa");
    conversa.appendChild(div);
    while (conversa.childElementCount > MAX_MENSAGENS) conversa.firstElementChild.remove();
    conversa.scrollTop = conversa.scrollHeight;
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
        executarAcaoPendente();
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
        $("confirmar").classList.toggle("oculta", !m.aguardando);
        if (m.aguardando) Rosto.modo("aguardando");
        if (m.audio && vozLigada) tocar(m.audio, m.mime);
        break;
      }
      case "tarefa":
        pintarTarefa(m.tarefa);
        break;
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
      case "arquivo":
        receberArquivo(m);
        break;
    }
  }

  // ---------------------------------------------------------------- arquivos que o PC manda
  const recebendo = new Map();   // id -> pedaços que já chegaram
  const urlsArquivos = [];
  const tamanhoLegivel = (n) => n >= 1048576 ? `${(n / 1048576).toFixed(1).replace(".", ",")} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;
  function receberArquivo(m) {
    let r = recebendo.get(m.id);
    if (!r) {
      r = { partes: new Array(m.total), chegaram: 0, bolha: adicionar("ela", "📎 Recebendo " + m.nome + "…") };
      recebendo.set(m.id, r);
    }
    if (r.partes[m.parte] === undefined) { r.partes[m.parte] = m.dados; r.chegaram++; }
    r.bolha.firstChild.textContent = `📎 Recebendo ${m.nome}… ${Math.round(100 * r.chegaram / m.total)}%`;
    if (r.chegaram < m.total) return;
    recebendo.delete(m.id);
    const blob = new Blob(r.partes.map((b64) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))),
                          { type: m.mime || "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    urlsArquivos.push(url);
    while (urlsArquivos.length > 12) URL.revokeObjectURL(urlsArquivos.shift());
    r.bolha.textContent = `📎 ${m.nome} (${tamanhoLegivel(blob.size)})`;
    if ((m.mime || "").startsWith("image/")) {
      const img = document.createElement("img"); img.src = url; img.alt = m.nome; r.bolha.appendChild(img);
    }
    const acoes = document.createElement("div"); acoes.className = "arquivo-acoes";
    const abrir = document.createElement("a"); abrir.href = url; abrir.target = "_blank"; abrir.rel = "noopener";
    abrir.textContent = "Abrir";
    const baixar = document.createElement("a"); baixar.href = url; baixar.download = m.nome; baixar.textContent = "Baixar";
    acoes.append(abrir, baixar); r.bolha.appendChild(acoes);
    $("conversa").scrollTop = $("conversa").scrollHeight;
    enviar({ tipo: "arquivo_recebido", arquivo: m.id });
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

  // ---------------------------------------------------------------- tarefas do modo agente
  let tarefaAtual = null;
  const ESTADOS = { planejando: "planejando…", executando: "em andamento", aguardando: "esperando você",
                    concluida: "concluída ✅", cancelada: "cancelada", erro: "com problema" };
  function pintarTarefa(t) {
    if (!t) return;
    tarefaAtual = t;
    const ativa = ["planejando", "executando", "aguardando"].includes(t.estado);
    $("cartaoTarefa").classList.remove("oculta");
    $("tarefaTitulo").textContent = t.objetivo;
    $("tarefaBarra").style.width = (t.progresso || 0) + "%";
    const atual = (t.passos || []).find((p) => p.estado === "fazendo");
    $("tarefaPasso").textContent = ativa ? `${ESTADOS[t.estado]}${atual ? " · " + atual.texto : ""}` : (t.resumo || ESTADOS[t.estado]);
    $("btnCancelarTarefa").classList.toggle("oculta", !ativa);
    if (!ativa) setTimeout(() => { if (tarefaAtual === t) $("cartaoTarefa").classList.add("oculta"); }, 60_000);
  }
  $("btnCancelarTarefa").onclick = () => tarefaAtual && enviar({ tipo: "cancelar_tarefa", tarefa: tarefaAtual.id });

  function pararTudo() {
    if (!estado || !estado.online) { adicionar("aviso", "O PC está desligado."); return; }
    const id = "x" + Date.now();
    aguardando.set(id, digitando());
    enviar({ tipo: "parar_tudo", id });
    if (navigator.vibrate) navigator.vibrate(60);
  }

  // Voz das respostas: desligada, o PC nem gera o áudio (economiza dados e bateria)
  function pintarVoz() {
    const b = $("btnVoz");
    b.textContent = vozLigada ? "🔊" : "🔇";
    b.setAttribute("aria-pressed", vozLigada);
    b.title = vozLigada ? "Respostas com voz (toque para só texto)" : "Só texto (toque para ouvir as respostas)";
  }
  $("btnVoz").onclick = () => {
    vozLigada = !vozLigada;
    try { localStorage.setItem(CHAVE_VOZ, vozLigada ? "1" : "0"); } catch {}
    if (!vozLigada && fonteAtual) try { fonteAtual.stop(); } catch {}
    pintarVoz();
  };
  pintarVoz();

  $("btnPrivado").onclick = () => {
    if (!estado || !estado.online) return adicionar("aviso", "O PC está desligado.");
    const ligado = $("btnPrivado").getAttribute("aria-pressed") === "true";
    enviar({ tipo: "privado", valor: !ligado });
    adicionar("aviso", ligado ? "Modo privado desligado no PC." : "Modo privado ligado no PC: microfone, memória e iniciativa desligados.");
  };
  $("confirmar").onclick = (e) => {
    const b = e.target.closest("button"); if (!b) return;
    $("confirmar").classList.add("oculta");
    pedir(b.dataset.resposta);
  };

  // ---------------------------------------------------------------- avisos com o app fechado (Web Push)
  const ehIOS = /iPhone|iPad|iPod/.test(navigator.userAgent);
  const instalado = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

  function bannerAvisos(texto, botao = true) {
    $("bannerAvisos").classList.remove("oculta");
    $("bannerTexto").textContent = texto;
    $("btnAvisos").classList.toggle("oculta", !botao);
  }

  async function prepararAvisos() {
    if (!("serviceWorker" in navigator)) return;
    if (!("PushManager" in window) || !("Notification" in window)) {
      if (ehIOS && !instalado) bannerAvisos("No iPhone: toque em Compartilhar → Adicionar à Tela de Início para receber avisos com o app fechado.", false);
      return;
    }
    if (Notification.permission === "denied") return;
    const reg = await navigator.serviceWorker.ready;
    const atual = await reg.pushManager.getSubscription();
    if (atual && Notification.permission === "granted") { inscreverNoPC(atual).catch(() => {}); return; }
    bannerAvisos("Receba os avisos da Ametista mesmo com o app fechado.");
  }

  async function inscreverNoPC(inscricao) {
    const r = await fetch("/api/push/inscrever", { method: "POST", headers: { authorization: "Bearer " + token, "content-type": "application/json" },
      body: JSON.stringify({ inscricao: inscricao.toJSON() }) });
    if (!r.ok) throw new Error("não consegui registrar os avisos");
  }

  $("btnAvisos").onclick = async () => {
    try {
      const perm = await Notification.requestPermission();
      if (perm !== "granted") { bannerAvisos("Sem permissão para avisos. Dá para liberar nas configurações do navegador.", false); return; }
      const { chave } = await (await fetch("/api/push/chave", { headers: { authorization: "Bearer " + token } })).json();
      const reg = await navigator.serviceWorker.ready;
      const inscricao = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: deB64(chave) });
      await inscreverNoPC(inscricao);
      $("bannerAvisos").classList.add("oculta");
      adicionar("aviso", "Avisos ativados: lembretes e alertas chegam mesmo com o app fechado.");
      fetch("/api/push/testar", { method: "POST", headers: { authorization: "Bearer " + token } }).catch(() => {});
    } catch (e) {
      bannerAvisos("Não deu para ativar os avisos: " + e.message, true);
    }
  };

  function deB64(t) {
    const s = atob(t.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((t.length + 3) % 4));
    return Uint8Array.from(s, (c) => c.charCodeAt(0));
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
    if (!enviar({ tipo: "pedido", id, texto, voz: vozLigada })) adicionar("aviso", "Sem conexão, tentando de novo…");
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
    if (b.dataset.pedido === "__tela") pedirTela();
    else if (b.dataset.pedido === "__parar") pararTudo();
    else pedir(b.dataset.pedido);
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
    enviar({ tipo: "pedido", id, audio: b64, mime: blob.type, voz: vozLigada });
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
  // atalhos do ícone do app (segurar o ícone): ?acao=falar | tela | parar
  let acaoPendente = new URLSearchParams(location.search).get("acao");
  function executarAcaoPendente() {
    if (!acaoPendente || !estado || !estado.online) return;
    const a = acaoPendente; acaoPendente = null;
    history.replaceState(null, "", "/");
    if (a === "tela") pedirTela();
    else if (a === "parar") pararTudo();
    else if (a === "falar") $("entrada").focus();
  }

  function iniciar() {
    mostrarTela("principal");
    pintarEstado(null);
    conectar();
    if (iniciado) return;
    iniciado = true;
    prepararAvisos().catch(() => {});
    // Com o app aberto o PC manda o status sozinho a cada 30 s. Se ficar mais de 70 s sem notícia
    // (PC caiu sem avisar), pergunta. Em segundo plano não faz nada.
    setInterval(() => {
      if (!document.hidden && !pausado && Date.now() - ultimaMensagem > 70_000) enviar({ tipo: "estado" });
    }, 30_000);
    // Em segundo plano por 20 s: desconecta (o PC para de mandar status). Os avisos continuam chegando
    // por notificação. Ao voltar, reconecta na hora.
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        clearTimeout(timerPausa);
        timerPausa = setTimeout(() => {
          if (document.hidden && ws && ws.readyState <= 1) { pausado = true; ws.close(1000, "segundo plano"); }
        }, PAUSAR_APOS_MS);
      } else {
        clearTimeout(timerPausa);
        if (pausado || !ws || ws.readyState > 1) { pausado = false; conectar(); }
        else enviar({ tipo: "estado" });
      }
    });
  }

  const doLink = new URLSearchParams(location.hash.slice(1)).get("parear");
  if (doLink) { mostrarTela("parear"); $("codigo").value = doLink; parear(doLink); }
  else if (token) iniciar();
  else mostrarTela("parear");
})();
