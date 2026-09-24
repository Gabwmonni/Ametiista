// Sobreposição da Ametista: aparece por cima de tudo quando chamada, fala e some sozinha.
// Quem escuta o microfone é o Python (ouvido.py); aqui mostramos o estado, tocamos a voz (em trechos,
// na ordem em que chegam) e mostramos conversa, tarefas, avisos e o histórico de ações.
(() => {
  const $ = (id) => document.getElementById(id);
  const painel = $("painel"), statusEl = $("status"), origemEl = $("origem");
  const pedidoEl = $("pedido"), respostaEl = $("resposta"), entrada = $("entrada");
  const TOKEN = document.body.dataset.token;
  const noNavegador = !new URLSearchParams(location.search).has("sobreposicao");
  if (noNavegador) document.body.classList.add("navegador");

  let ws, audioCtx = null, fonteAtual = null, falando = false;
  let timerEsconder = null, modoTela = "compacto", tarefaNaTela = false;
  let base = { privado: false, offline: false };   // estado de fundo do rosto
  let pendente = null;                             // pergunta aguardando sim/não
  const listas = { conversa: [], tarefas: new Map(), avisos: [], historico: [] };
  let avisosNaoLidos = 0;

  // ---------------------------------------------------------------- visual
  const NOMES = { ouvindo: "ouvindo…", pensando: "pensando…", falando: "Ametista", ocioso: "Ametista",
                  executando: "trabalhando numa tarefa…", alerta: "aviso", aguardando: "esperando sua resposta",
                  offline: "sem internet", privado: "modo privado" };
  const MODOS = ["ouvindo", "pensando", "falando", "executando", "alerta", "offline", "privado", "aguardando"];

  function modo(m, texto) {
    if (m === "ocioso") {  // sem nada acontecendo: mostra o estado de fundo
      m = pendente ? "aguardando" : base.privado ? "privado" : base.offline ? "offline"
        : tarefaAtiva() ? "executando" : "ocioso";
    }
    Rosto.modo(m);
    painel.classList.remove(...MODOS);
    if (m !== "ocioso") painel.classList.add(m);
    statusEl.textContent = texto || (m === "aguardando" && pendente ? pendente : NOMES[m] || m);
  }

  function mostrar() {
    clearTimeout(timerEsconder);
    painel.classList.add("visivel");
  }

  function esconder(depois = 0) {
    clearTimeout(timerEsconder);
    timerEsconder = setTimeout(() => {
      if (falando || pendente || modoTela === "expandido" || tarefaNaTela) return;
      if (document.activeElement === entrada && entrada.value) return;
      if (noNavegador) return modo("ocioso");  // no navegador (teste) o painel fica sempre visível
      painel.classList.remove("visivel");
      modo("ocioso");
      setTimeout(() => enviar({ tipo: "esconder" }), 380);  // a janela some depois da animação
    }, depois);
  }

  function tamanho(novo) {
    modoTela = novo;
    painel.dataset.modo = novo;
    $("btnExpandir").setAttribute("aria-expanded", novo === "expandido");
    enviar({ tipo: "tamanho", modo: novo });
    if (novo === "expandido") { mostrar(); avisosNaoLidos = 0; pintarContadores(); rolarConversa(); }
  }

  function nivel(v) { painel.style.setProperty("--nivel", Math.min(1, v).toFixed(3)); }

  // ---------------------------------------------------------------- conexão
  function conectar() {
    ws = window.__ws = new WebSocket(`ws://${location.host}/ws?token=${encodeURIComponent(TOKEN)}`);
    ws.onmessage = (ev) => receber(JSON.parse(ev.data));
    ws.onclose = () => setTimeout(conectar, 1500);
  }
  const enviar = (msg) => ws && ws.readyState === 1 && ws.send(JSON.stringify(msg));

  // ---------------------------------------------------------------- fala em trechos
  // Cada resposta tem um id; os trechos chegam numerados e são tocados em ordem.
  let fala = null;   // {id, trechos: Map, proximo, total, fim, cancelada}
  let tocandoFila = false;

  function novaFala(id) {
    fala = { id, trechos: new Map(), proximo: 0, total: null, fim: false, cancelada: false, texto: "" };
    respostaEl.textContent = ""; respostaEl.classList.remove("aviso");
    return fala;
  }

  async function tocarFila() {
    if (tocandoFila || !fala) return;
    tocandoFila = true;
    const f = fala;
    while (!f.cancelada && f.trechos.has(f.proximo)) {
      const t = f.trechos.get(f.proximo);
      f.trechos.delete(f.proximo);
      f.proximo++;
      if (t.emocao) Rosto.emocao(t.emocao);
      f.texto = (f.texto + " " + t.texto).trim();
      respostaEl.textContent = f.texto;
      respostaEl.scrollTop = respostaEl.scrollHeight;
      await falar(t.texto, t.audio);
    }
    tocandoFila = false;
    if (!f.cancelada && f.fim && f.proximo >= f.total) terminarFala(f);
  }

  function terminarFala(f) {
    if (f !== fala) return;
    fala = null;
    setFalando(false);
    Rosto.voz(0); nivel(0);
    enviar({ tipo: "fala_terminou", id: f.id });
    if (f.emocaoFinal === "feliz") Rosto.gesto("acenar");
    Rosto.emocao("neutra");
    adicionarConversa("assistant", f.texto);
    modo("ocioso");
    esconder(pendente ? 30000 : 9000);  // se o ouvido não pedir seguimento, some sozinha
  }

  function cancelarFala() {
    if (fala) { fala.cancelada = true; const f = fala; fala = null; if (f.texto) adicionarConversa("assistant", f.texto + " …"); }
    calarAudio();
    setFalando(false);
    Rosto.voz(0); nivel(0);
  }

  function setFalando(v) {
    if (falando !== v) enviar({ tipo: "falando", valor: v });
    falando = v;
  }

  // ---------------------------------------------------------------- mensagens do servidor
  async function receber(m) {
    switch (m.tipo) {
      case "inicial":
        base.privado = !!m.privado; base.offline = !!m.offline;
        pintarPrivado();
        listas.conversa = (m.conversa || []).map((c) => ({ papel: c.papel, texto: c.texto }));
        listas.tarefas = new Map((m.tarefas || []).map((t) => [t.id, t]));
        listas.avisos = m.avisos || [];
        listas.historico = m.acoes || [];
        pendente = m.pendente || null;
        renderTudo();
        modo("ocioso");
        break;
      case "estado":
        base.privado = !!m.privado; base.offline = !!m.offline;
        pintarPrivado();
        if (!falando) modo("ocioso");
        break;
      case "acordou":
        mostrar(); cancelarFala();
        pedidoEl.textContent = ""; respostaEl.textContent = ""; respostaEl.classList.remove("aviso");
        origemEl.textContent = "";
        Rosto.emocao("feliz"); modo("ouvindo");
        if (m.manual) setTimeout(() => entrada.focus(), 50);
        break;
      case "ouvindo":
        mostrar(); Rosto.emocao("neutra"); modo("ouvindo");
        break;
      case "conversa":  // conversa contínua: continua atenta, mas sai da frente
        esconder(1500);
        break;
      case "mic":
        Rosto.mic(m.nivel); nivel(m.nivel);
        break;
      case "transcricao":
        mostrar(); pedidoEl.textContent = (m.quem ? m.quem + ": " : "") + m.texto;
        adicionarConversa("user", (m.quem ? m.quem + ": " : "") + m.texto);
        break;
      case "cadastro":  // cadastro de voz: mostra a frase para a pessoa ler
        mostrar(); cancelarFala();
        Rosto.emocao("feliz"); modo("ouvindo", `aprendendo a voz de ${m.nome} · ${m.passo} de ${m.total}`);
        pedidoEl.textContent = "Leia em voz alta, com calma:";
        respostaEl.classList.remove("aviso");
        respostaEl.textContent = "“" + m.frase + "”";
        break;
      case "pensando":
        mostrar(); Rosto.emocao("pensativa"); modo("pensando"); nivel(0);
        respostaEl.textContent = ""; respostaEl.classList.remove("aviso");
        break;
      case "status":
        if (!falando) { mostrar(); modo("pensando", m.texto); }
        break;
      case "fala_inicio":
        mostrar();
        novaFala(m.id);
        Rosto.emocao(m.emocao || "neutra");
        origemEl.textContent = { local: "⚡ local", nuvem: "☁ nuvem", "local-ia": "🖥 IA local", erro: "⚠" }[m.origem] || "";
        break;
      case "fala_trecho":
        if (!fala || fala.id !== m.id) { if (fala && fala.cancelada) return; novaFala(m.id); }
        fala.trechos.set(m.seq, m);
        tocarFila();
        break;
      case "fala_fim":
        if (fala && fala.id === m.id) {
          fala.fim = true; fala.total = m.total; fala.emocaoFinal = m.emocao;
          if (!tocandoFila && fala.proximo >= fala.total) terminarFala(fala);
        }
        break;
      case "calar":
        cancelarFala();
        modo("ocioso");
        break;
      case "alerta":
        mostrar(); cancelarFala();
        pedidoEl.textContent = m.proativo ? "💡 " + (m.titulo || "") : "⏰ aviso";
        modo(m.proativo ? "falando" : "alerta");
        Rosto.emocao(m.emocao || "surpresa");
        respostaEl.classList.remove("aviso");
        respostaEl.textContent = m.texto;
        if (m.tom) await tocarAlarme();
        await falar(m.texto, m.audio);
        setFalando(false);
        enviar({ tipo: "fala_terminou", id: m.id });
        modo("ocioso");
        esconder(9000);
        break;
      case "aviso":
        mostrar(); respostaEl.textContent = m.texto; respostaEl.classList.add("aviso");
        esconder(5000);
        break;
      case "aguardando":
        pendente = m.pergunta || "Confirma?";
        $("confirmar").classList.remove("oculta");
        mostrar();
        if (!falando) modo("aguardando");
        break;
      case "aguardando_fim":
        pendente = null;
        $("confirmar").classList.add("oculta");
        if (!falando) modo("ocioso");
        break;
      case "tarefa":
        listas.tarefas.set(m.tarefa.id, m.tarefa);
        renderTarefas();
        pintarTarefa(m.tarefa);
        break;
      case "agente_tela":
        tarefaNaTela = !!m.ativo;
        if (tarefaNaTela) { mostrar(); tamanho("tarefa"); modo("executando"); }
        else { tamanho("compacto"); modo("ocioso"); esconder(6000); }
        break;
      case "acao":
        listas.historico = [m.acao, ...listas.historico.filter((a) => a.id !== m.acao.id)].slice(0, 200);
        renderHistorico();
        break;
      case "aviso_novo":
        listas.avisos = [m.aviso, ...listas.avisos].slice(0, 100);
        if (modoTela !== "expandido") avisosNaoLidos++;
        renderAvisos();
        break;
      case "parou_tudo":
        pendente = null; $("confirmar").classList.add("oculta");
        break;
      case "ocioso":
        modo("ocioso"); nivel(0);
        esconder(respostaEl.textContent ? 3500 : 600);
        break;
    }
  }

  // ---------------------------------------------------------------- áudio
  function garantirAudio() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") audioCtx.resume();
    return audioCtx;
  }

  async function falar(texto, audioB64) {
    setFalando(true);
    if (Rosto.estado.modo !== "alerta") modo("falando");
    try {
      if (audioB64) await tocarAudio(audioB64);
      else await falarNavegador(texto);
    } catch (e) {
      console.warn("áudio falhou, usando voz do sistema", e);
      await falarNavegador(texto);
    }
    Rosto.voz(0); nivel(0);
  }

  async function tocarAudio(b64) {
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
      fonte.onended = () => { ativo = false; if (fonteAtual === fonte) fonteAtual = null; ok(); };
      fonte.start();
      medir();
    });
  }

  let resolverNavegador = null;
  function falarNavegador(texto) {
    return new Promise((ok) => {
      if (!("speechSynthesis" in window) || !texto) return setTimeout(ok, 300);
      const u = new SpeechSynthesisUtterance(texto);
      u.lang = "pt-BR";
      const voz = speechSynthesis.getVoices().find((v) => v.lang.startsWith("pt"));
      if (voz) u.voice = voz;
      let ativo = true;
      const fim = () => { if (ativo) { ativo = false; resolverNavegador = null; ok(); } };
      resolverNavegador = fim;
      const boca = () => { if (!ativo) return; Rosto.voz(0.25 + Math.random() * 0.6); setTimeout(boca, 90); };
      u.onend = u.onerror = fim;
      speechSynthesis.speak(u);
      boca();
      setTimeout(fim, 4000 + texto.length * 90);  // segurança
    });
  }

  function calarAudio() {
    if (fonteAtual) { try { fonteAtual.stop(); } catch {} fonteAtual = null; }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    if (resolverNavegador) resolverNavegador();
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

  // ---------------------------------------------------------------- listas (área expandida)
  const hora = (iso) => { try { return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }); } catch { return ""; } };
  const el = (tag, classe, texto) => { const e = document.createElement(tag); if (classe) e.className = classe; if (texto != null) e.textContent = texto; return e; };
  const tarefaAtiva = () => [...listas.tarefas.values()].some((t) => ["planejando", "executando", "aguardando"].includes(t.estado));

  function adicionarConversa(papel, texto) {
    if (!texto) return;
    listas.conversa.push({ papel, texto });
    listas.conversa = listas.conversa.slice(-80);
    renderConversa();
  }

  function rolarConversa() { const l = $("abaConversa"); l.scrollTop = l.scrollHeight; }

  function renderConversa() {
    const l = $("abaConversa");
    l.replaceChildren();
    if (!listas.conversa.length) l.append(el("div", "vazio", "Nenhuma conversa ainda. Diga \"Ametista\" ou digite abaixo."));
    for (const c of listas.conversa) l.append(el("div", "msg " + (c.papel === "user" ? "user" : "assistant"), c.texto));
    rolarConversa();
  }

  const ESTADO_TAREFA = { planejando: "planejando", executando: "em andamento", aguardando: "esperando você",
                          concluida: "concluída", cancelada: "cancelada", erro: "com problema" };
  function renderTarefas() {
    const l = $("abaTarefas");
    l.replaceChildren();
    const itens = [...listas.tarefas.values()].sort((a, b) => (b.criada || "").localeCompare(a.criada || ""));
    if (!itens.length) l.append(el("div", "vazio", "Nenhuma tarefa. Peça algo grande, como \"organiza minha pasta de Downloads\"."));
    for (const t of itens) {
      const item = el("div", "item");
      const corpo = el("div", "corpo");
      corpo.append(el("div", "titulo", t.objetivo), el("div", "detalhe", `${ESTADO_TAREFA[t.estado] || t.estado} · ${t.progresso || 0}%`));
      if (t.passos && t.passos.length) {
        const ul = el("ul", "passos");
        t.passos.forEach((p) => ul.append(el("li", p.estado, p.texto)));
        corpo.append(ul);
      }
      if (t.resumo) corpo.append(el("div", "detalhe", t.resumo));
      item.append(el("span", "quando", hora(t.criada)), corpo);
      if (["planejando", "executando", "aguardando"].includes(t.estado)) {
        const b = el("button", "", "Cancelar");
        b.onclick = () => enviar({ tipo: "cancelar_tarefa", id: t.id });
        item.append(b);
      }
      l.append(item);
    }
    pintarContadores();
  }

  function pintarTarefa(t) {
    const ativa = ["planejando", "executando", "aguardando"].includes(t.estado);
    $("tarefaTitulo").textContent = t.objetivo;
    $("tarefaBarra").style.width = (t.progresso || 0) + "%";
    const atual = (t.passos || []).find((p) => p.estado === "fazendo");
    $("tarefaPasso").textContent = ativa ? (atual ? atual.texto : ESTADO_TAREFA[t.estado]) + " · diga \"para tudo\" para cancelar"
      : t.resumo || ESTADO_TAREFA[t.estado];
    if (!falando) modo("ocioso");
  }

  function renderAvisos() {
    const l = $("abaAvisos");
    l.replaceChildren();
    if (!listas.avisos.length) l.append(el("div", "vazio", "Nenhum aviso."));
    for (const a of listas.avisos) {
      const item = el("div", "item");
      const corpo = el("div", "corpo");
      corpo.append(el("div", "titulo", a.titulo && a.titulo !== "Ametista" ? a.titulo : (a.tipo === "proativo" ? "Sugestão" : "Aviso")),
                   el("div", "detalhe", a.texto));
      item.append(el("span", "quando", hora(a.quando)), corpo);
      l.append(item);
    }
    pintarContadores();
  }

  function renderHistorico() {
    const l = $("abaHistorico");
    l.replaceChildren();
    if (!listas.historico.length) l.append(el("div", "vazio", "Nenhuma ação ainda. Tudo o que eu fizer aparece aqui, com como desfazer."));
    for (const a of listas.historico) {
      const item = el("div", "item" + (a.ok ? "" : " falhou") + (a.desfeito ? " desfeito" : ""));
      const corpo = el("div", "corpo");
      corpo.append(el("div", "titulo", a.descricao));
      const det = [a.quem ? `pedido por ${a.quem}` : "", a.motivo ? `“${a.motivo}”` : "", a.resultado].filter(Boolean).join(" · ");
      if (det) corpo.append(el("div", "detalhe", det));
      item.append(el("span", "quando", hora(a.quando)), corpo);
      if (a.desfazivel && !a.desfeito) {
        const b = el("button", "", "Desfazer");
        b.onclick = () => { b.disabled = true; enviar({ tipo: "desfazer", id: a.id }); };
        item.append(b);
      }
      l.append(item);
    }
  }

  function pintarContadores() {
    const ativas = [...listas.tarefas.values()].filter((t) => ["planejando", "executando", "aguardando"].includes(t.estado)).length;
    $("nTarefas").textContent = ativas ? ativas : "";
    $("nAvisos").textContent = avisosNaoLidos ? avisosNaoLidos : "";
  }

  function renderTudo() { renderConversa(); renderTarefas(); renderAvisos(); renderHistorico(); }

  function pintarPrivado() {
    $("btnPrivado").setAttribute("aria-pressed", base.privado);
    entrada.placeholder = base.privado ? "Modo privado: microfone desligado. Digite aqui…" : "Pergunte ou peça algo…";
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
  $("btnMic").onclick = () => { garantirAudio(); cancelarFala(); enviar({ tipo: "chamar" }); };
  $("btnParar").onclick = () => { cancelarFala(); enviar({ tipo: "parar_tudo" }); };
  $("btnPrivado").onclick = () => enviar({ tipo: "privado", valor: !base.privado });
  $("btnExpandir").onclick = () => tamanho(modoTela === "expandido" ? "compacto" : "expandido");
  $("btnPainel").onclick = () => noNavegador ? window.open("/painel", "_blank") : enviar({ tipo: "abrir_painel" });
  $("btnSim").onclick = () => enviar({ tipo: "responder", resposta: "sim" });
  $("btnNao").onclick = () => enviar({ tipo: "responder", resposta: "nao" });
  $("rosto").onclick = () => { if (falando) { cancelarFala(); enviar({ tipo: "cancelar_escuta" }); } };
  document.querySelectorAll(".abas [data-aba]").forEach((b) => b.onclick = () => {
    document.querySelectorAll(".abas [data-aba]").forEach((x) => x.classList.toggle("ativa", x === b));
    for (const aba of ["conversa", "tarefas", "avisos", "historico"])
      $("aba" + aba[0].toUpperCase() + aba.slice(1)).classList.toggle("oculta", aba !== b.dataset.aba);
    if (b.dataset.aba === "avisos") { avisosNaoLidos = 0; pintarContadores(); }
    if (b.dataset.aba === "conversa") rolarConversa();
  });

  addEventListener("keydown", (e) => {
    garantirAudio();
    if (e.key === "Escape") {
      if (modoTela === "expandido") return tamanho("compacto");
      const idFala = fala && fala.id;
      cancelarFala();
      enviar({ tipo: "cancelar_escuta" });
      if (idFala) enviar({ tipo: "fala_terminou", id: idFala });
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
  renderTudo();
  conectar();
})();
