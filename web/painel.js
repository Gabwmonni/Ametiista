// Painel de configuração da Ametista: tudo o que antes era no .env, mais personalidade, rotinas,
// memória, histórico de ações e diagnóstico.
(() => {
  const $ = (id) => document.getElementById(id);
  const TOKEN = document.body.dataset.token;
  const conteudo = $("conteudo");
  let config = null;            // {secoes, campos}
  let alterados = {};           // chave -> valor novo
  let secaoAtual = null;

  // ---------------------------------------------------------------- utilidades
  async function api(caminho, corpo, metodo) {
    const r = await fetch(caminho, {
      method: metodo || (corpo !== undefined ? "POST" : "GET"),
      headers: { "X-Ametista-Token": TOKEN, "Content-Type": "application/json" },
      body: corpo !== undefined ? JSON.stringify(corpo) : undefined,
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || d.erro || `erro ${r.status}`);
    return d;
  }

  function el(tag, attrs = {}, ...filhos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") e.className = v;
      else if (k === "texto") e.textContent = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (k in e && k !== "list") e[k] = v;
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (const f of filhos.flat()) if (f != null) e.append(f instanceof Node ? f : document.createTextNode(f));
    return e;
  }

  let timerToast;
  function toast(texto, erro = false, acao = null) {
    const t = $("toast");
    t.replaceChildren(texto);
    if (acao) t.append(" ", el("button", { class: "link", texto: acao.rotulo, onclick: acao.fn }));
    t.classList.toggle("erro", erro);
    t.classList.add("visivel");
    t.style.pointerEvents = acao ? "auto" : "none";
    clearTimeout(timerToast);
    timerToast = setTimeout(() => t.classList.remove("visivel"), acao ? 12000 : 4000);
  }

  async function tentar(fn, sucesso) {
    try { const r = await fn(); if (sucesso) toast(typeof sucesso === "function" ? sucesso(r) : sucesso); return r; }
    catch (e) { toast(e.message, true); }
  }

  function tocar(audio, mime) {
    if (!audio) return toast("Não consegui gerar a voz.", true);
    new Audio(`data:${mime || "audio/mpeg"};base64,${audio}`).play().catch(() => {});
  }

  // ---------------------------------------------------------------- menu
  const PAGINAS_EXTRAS = [
    { grupo: "Ela", itens: [["Personalidade", paginaPersonalidade], ["Rotinas", paginaRotinas]] },
    { grupo: "Dados", itens: [["Memória e lembretes", paginaMemoria], ["Histórico", paginaHistorico]] },
    { grupo: "Ajuda", itens: [["Diagnóstico", paginaDiagnostico], ["Registro (log)", paginaLog]] },
  ];

  function montarMenu() {
    const menu = $("menu");
    menu.replaceChildren(el("div", { class: "grupo", texto: "Configurações" }));
    for (const s of config.secoes) menu.append(el("button", { texto: s, "data-secao": s, onclick: () => abrir(s) }));
    for (const g of PAGINAS_EXTRAS) {
      menu.append(el("div", { class: "grupo", texto: g.grupo }));
      for (const [nome] of g.itens) menu.append(el("button", { texto: nome, "data-secao": nome, onclick: () => abrir(nome) }));
    }
  }

  function abrir(secao) {
    secaoAtual = secao;
    document.querySelectorAll(".menu button").forEach((b) => b.classList.toggle("ativa", b.dataset.secao === secao));
    history.replaceState(null, "", "#" + encodeURIComponent(secao));
    conteudo.replaceChildren();
    const extra = PAGINAS_EXTRAS.flatMap((g) => g.itens).find(([n]) => n === secao);
    if (extra) extra[1]();
    else paginaConfig(secao);
    conteudo.focus();
    scrollTo(0, 0);
  }

  // ---------------------------------------------------------------- páginas de configuração
  const DESCRICOES = {
    "Geral": "Nomes, cidade e atalhos.",
    "Cérebro": "A inteligência dela: Claude na nuvem ou o Ollama no próprio PC, com as mesmas ferramentas.",
    "Voz": "Como ela fala. Toque em \"Ouvir\" para testar.",
    "Ouvido": "Microfone, palavra de ativação, conversa contínua e interrupção por voz.",
    "Pessoas": "Quem pode falar com ela e o que cada pessoa pode fazer.",
    "Proatividade": "Quando ela pode puxar assunto sozinha.",
    "Foco": "Sessões de estudo: ela percebe quando você troca o estudo por distração e chama você de volta.",
    "Memória": "O que ela guarda e como procura.",
    "Agenda": "Google Agenda, Outlook e avisos.",
    "Contas": "Spotify e Steam.",
    "Casa": "Home Assistant: luzes, tomadas, ar-condicionado.",
    "Celular": "O app do celular e o pareamento.",
    "Avançado": "Só mexa se souber o que está fazendo.",
  };

  function valorAtual(c) { return c.chave in alterados ? alterados[c.chave] : c.valor; }

  function marcar(chave, valor) {
    const c = config.campos.find((x) => x.chave === chave);
    if (c && String(c.valor) === String(valor) && c.tipo !== "segredo") delete alterados[chave];
    else alterados[chave] = String(valor);
    const n = Object.keys(alterados).length;
    $("rodape").hidden = n === 0;
    $("rodapeTexto").textContent = n === 1 ? "1 alteração não salva." : `${n} alterações não salvas.`;
  }

  function controleDe(c) {
    const v = valorAtual(c);
    const aoMudar = (e) => marcar(c.chave, e.target.type === "checkbox" ? (e.target.checked ? "1" : "0") : e.target.value);
    switch (c.tipo) {
      case "bool": {
        return el("label", { class: "interruptor" },
          el("input", { type: "checkbox", id: "c_" + c.chave, checked: ["1", "true", "sim"].includes(String(v).toLowerCase()), onchange: aoMudar }),
          el("span"));
      }
      case "opcao": {
        const s = el("select", { id: "c_" + c.chave, onchange: aoMudar });
        const vals = c.opcoes.map((o) => o.valor);
        for (const o of c.opcoes) s.append(el("option", { value: o.valor, texto: o.rotulo, selected: String(v) === o.valor }));
        if (v && !vals.includes(String(v))) s.append(el("option", { value: v, texto: `${v} (personalizado)`, selected: true }));
        return s;
      }
      case "segredo": {
        const wrap = el("div", { class: "controle" });
        wrap.append(el("input", { type: "password", id: "c_" + c.chave, autocomplete: "off",
          placeholder: c.definido ? `definida (${c.dica}) — digite para trocar` : "não definida", oninput: aoMudar }));
        if (c.definido) wrap.append(el("button", { class: "link", texto: "apagar", onclick: async () => {
          if (!confirm("Apagar este segredo?")) return;
          await tentar(() => api("/api/config/apagar-segredo", { chave: c.chave }), "Apagado.");
          await recarregarConfig();
        } }));
        return wrap;
      }
      case "microfone": {
        const s = el("select", { id: "c_" + c.chave, onchange: aoMudar });
        s.append(el("option", { value: "", texto: "Padrão do Windows", selected: !v }));
        api("/api/microfones").then((d) => {
          for (const m of d.microfones) s.append(el("option", { value: m.id, texto: m.nome + (m.padrao ? " (padrão)" : ""), selected: String(v) === m.id }));
        }).catch(() => {});
        return s;
      }
      case "voz_edge": {
        const wrap = el("div", { class: "controle" });
        const s = el("select", { id: "c_" + c.chave, onchange: aoMudar });
        s.append(el("option", { value: v, texto: v, selected: true }));
        api("/api/vozes").then((d) => {
          s.replaceChildren();
          for (const x of d.vozes) s.append(el("option", { value: x.id, texto: `${x.nome} (${x.genero === "Female" ? "feminina" : "masculina"}, ${x.id.slice(0, 5)})`, selected: x.id === v }));
          if (!d.vozes.some((x) => x.id === v)) s.append(el("option", { value: v, texto: v, selected: true }));
        }).catch(() => {});
        wrap.append(s, el("button", { class: "secundario", texto: "Ouvir", onclick: testarVoz }));
        return wrap;
      }
      case "intervalo": {
        const [a, b] = String(v || "22:00-07:00").split("-");
        const wrap = el("div", { class: "controle" });
        const ia = el("input", { type: "time", value: a || "22:00" }), ib = el("input", { type: "time", value: b || "07:00" });
        const mudou = () => marcar(c.chave, `${ia.value}-${ib.value}`);
        ia.onchange = ib.onchange = mudou;
        wrap.append("das", ia, "às", ib);
        return wrap;
      }
      case "numero":
        return el("input", { type: "text", inputMode: "decimal", id: "c_" + c.chave, value: v, oninput: aoMudar });
      default:
        return el("input", { type: "text", id: "c_" + c.chave, value: v, oninput: aoMudar, spellcheck: false });
    }
  }

  function campo(c) {
    const rot = el("label", { for: "c_" + c.chave }, c.rotulo, c.reiniciar ? el("span", { class: "reiniciar", texto: "reinício" }) : null,
      c.ajuda ? el("div", { class: "ajuda", texto: c.ajuda }) : null);
    return el("div", { class: "campo" }, el("div", {}, rot), el("div", { class: "controle" }, controleDe(c)));
  }

  function paginaConfig(secao) {
    const campos = config.campos.filter((c) => c.secao === secao);
    conteudo.append(el("h1", { texto: secao }), el("p", { class: "sub", texto: DESCRICOES[secao] || "" }));
    const cartao = el("div", { class: "cartao" });
    for (const c of campos) {
      cartao.append(campo(c));
      if (c.chave === "CIDADE") cartao.append(buscaCidade());
    }
    conteudo.append(cartao);
    const extra = { "Cérebro": extraCerebro, "Voz": extraVoz, "Pessoas": extraPessoas, "Memória": extraMemoria, "Foco": extraFoco,
                    "Contas": extraContas, "Agenda": extraContas, "Celular": extraCelular }[secao];
    if (extra) extra();
  }

  function buscaCidade() {
    const resultados = el("div", { class: "lista-cidades" });
    const q = el("input", { type: "text", placeholder: "Digite a cidade para achar latitude e longitude" });
    const buscar = async () => {
      const d = await tentar(() => api("/api/cidade?q=" + encodeURIComponent(q.value)));
      resultados.replaceChildren();
      for (const c of (d && d.cidades) || []) resultados.append(el("button", { texto: `${c.nome} — ${c.regiao}`, onclick: () => {
        marcar("CIDADE", c.nome); marcar("LATITUDE", c.latitude); marcar("LONGITUDE", c.longitude);
        for (const [k, v] of [["CIDADE", c.nome], ["LATITUDE", c.latitude], ["LONGITUDE", c.longitude]]) { const i = $("c_" + k); if (i) i.value = v; }
        resultados.replaceChildren();
      } }));
    };
    q.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); buscar(); } };
    return el("div", { class: "campo" }, el("div", { class: "ajuda", texto: "Achar a cidade automaticamente" }),
      el("div", { class: "controle" }, q, el("button", { class: "secundario", texto: "Buscar", onclick: buscar }), resultados));
  }

  // Ouve a combinação escolhida na tela (voz pronta, velocidade e tom), mesmo antes de salvar
  async function testarVoz() {
    const valor = (chave) => { const e = document.getElementById("c_" + chave); return e ? e.value : undefined; };
    const provedor = valor("VOZ_PROVEDOR");
    if (provedor && provedor !== "edge" && Object.keys(alterados).some((k) => k.startsWith("ELEVENLABS") || k === "VOZ_PROVEDOR"))
      toast("Salve antes para ouvir a voz clonada.");
    const corpo = provedor === "edge" || !provedor
      ? { provedor: "edge", voz: valor("AMETISTA_VOZ"), velocidade: valor("VOZ_VELOCIDADE"), tom: valor("VOZ_TOM") } : {};
    const d = await tentar(() => api("/api/testar-voz", corpo));
    if (d && d.audio) tocar(d.audio, d.mime);
    else if (d) toast("Não consegui gerar a voz agora (sem internet?).", true);
  }

  function extraCerebro() {
    conteudo.append(el("h2", { texto: "Testar" }), el("div", { class: "cartao" }, el("div", { class: "linha" },
      el("div", { class: "cresce" }, "Confere a chave e os modelos escolhidos.", el("div", { class: "detalhe", texto: "Não gasta créditos." })),
      el("button", { class: "secundario", texto: "Testar conexão", onclick: async (e) => {
        e.target.disabled = true;
        const d = await tentar(() => api("/api/testar-claude", {}));
        e.target.disabled = false;
        if (d) toast(`${d.situacao === "ok" ? "✅" : "⚠️"} ${d.detalhe}`, d.situacao !== "ok");
      } }))));
  }

  function extraVoz() {
    conteudo.append(el("div", { class: "cartao" }, el("div", { class: "linha" },
      el("div", { class: "cresce" }, "Ouvir como ela fica com o que está escolhido acima (antes de salvar)."),
      el("button", { class: "secundario", texto: "Ouvir", onclick: testarVoz }))));
    const cartao = el("div", { class: "cartao" });
    conteudo.append(el("h2", { texto: "Voz clonada no PC" }), cartao);
    api("/api/voz-local").then((d) => {
      let selo, texto;
      if (!d.instalado) {
        selo = el("span", { class: "selo", texto: "não instalada" });
        texto = "Coloque os áudios da voz em voz\\amostras e dê dois cliques em clonar_voz.bat (opção 1). Ele instala tudo na primeira vez.";
      } else if (!d.referencias) {
        selo = el("span", { class: "selo erro", texto: "sem amostras" });
        texto = "Instalada, mas sem a voz: coloque os áudios em voz\\amostras e rode o clonar_voz.bat.";
      } else {
        const onde = d.dispositivo === "cuda" || d.cuda ? `na placa de vídeo${d.gpu ? " (" + d.gpu + ")" : ""}` : "no processador";
        selo = el("span", { class: "selo " + (d.erro ? "erro" : "ok"), texto: d.erro ? "com erro" : d.pronto ? "pronta" : d.rodando ? "carregando" : "instalada" });
        texto = d.erro ? `${d.erro} (veja dados/voz_local.log)` :
          `${d.referencias} trechos de referência, rodando ${onde}.` + (d.escolhida ? "" : " Para usar, escolha \"Voz clonada no próprio PC\" acima e salve.");
      }
      cartao.append(el("div", { class: "linha" }, selo, el("div", { class: "cresce detalhe", texto })));
    }).catch(() => {});
  }

  function extraFoco() {
    const cartao = el("div", { class: "cartao" });
    conteudo.append(el("h2", { texto: "Sessão e relatório" }), cartao);
    const materia = el("input", { type: "text", placeholder: "Matéria (opcional)" });
    const desenhar = async () => {
      const d = await tentar(() => api("/api/foco"));
      if (!d) return;
      cartao.replaceChildren();
      if (d.sessao) {
        cartao.append(el("div", { class: "linha" }, el("span", { class: "selo ok", texto: "estudando" }), el("div", { class: "cresce", texto: d.sessao + "." }),
          el("button", { class: "secundario", texto: "Encerrar", onclick: async () => { await tentar(() => api("/api/foco", { acao: "parar" }), (r) => r.resultado); desenhar(); } })));
      } else {
        cartao.append(el("div", { class: "linha" }, el("div", { class: "cresce" }, materia),
          el("button", { class: "primario", texto: "Estudar 50 min", onclick: async () => {
            await tentar(() => api("/api/foco", { acao: "iniciar", minutos: 50, materia: materia.value }), (r) => r.resultado); desenhar();
          } })));
      }
      cartao.append(el("div", { class: "linha detalhe", texto: d.relatorio }));
    };
    desenhar();
  }

  async function extraPessoas() {
    const cartao = el("div", { class: "cartao" });
    conteudo.append(el("h2", { texto: "Vozes cadastradas" }), cartao);
    const desenhar = async () => {
      const d = await tentar(() => api("/api/pessoas"));
      if (!d) return;
      cartao.replaceChildren();
      if (!d.disponivel) cartao.append(el("div", { class: "linha" }, el("span", { class: "selo erro", texto: "modelo de voz não instalado" }), "Rode o instalar.bat."));
      if (!d.pessoas.length) cartao.append(el("div", { class: "linha detalhe", texto: "Ninguém cadastrado: ela atende qualquer voz." }));
      for (const p of d.pessoas) {
        const nivel = el("select", { onchange: (e) => tentar(() => api("/api/pessoas/nivel", { nome: p.nome, nivel: e.target.value }), "Nível alterado.") });
        for (const [v, r] of [["dono", "Dono (tudo)"], ["familia", "Família"], ["visitante", "Visitante"]]) nivel.append(el("option", { value: v, texto: r, selected: p.nivel === v }));
        cartao.append(el("div", { class: "linha" }, el("div", { class: "cresce" }, el("b", { texto: p.nome }), el("div", { class: "detalhe", texto: `${p.amostras} amostras de voz` })),
          nivel, el("button", { class: "perigo", texto: "Remover", onclick: async () => {
            if (!confirm(`Remover a voz de ${p.nome}?`)) return;
            await tentar(() => api("/api/pessoas/remover", { nome: p.nome }), "Removido."); desenhar();
          } })));
      }
      const nome = el("input", { type: "text", placeholder: "Nome da pessoa" });
      const nivelNovo = el("select");
      for (const [v, r] of [["familia", "Família"], ["visitante", "Visitante"], ["dono", "Dono"]]) nivelNovo.append(el("option", { value: v, texto: r }));
      cartao.append(el("div", { class: "linha" }, el("div", { class: "cresce" }, nome), nivelNovo,
        el("button", { class: "primario", texto: "Cadastrar voz", onclick: async () => {
          if (!nome.value.trim()) return toast("Digite o nome.", true);
          await tentar(() => api("/api/pessoas/cadastrar", { nome: nome.value.trim(), nivel: nivelNovo.value }),
            "Olhe para a Ametista: ela vai mostrar 7 frases para a pessoa ler em voz alta.");
        } })));
    };
    desenhar();
  }

  function extraMemoria() {
    conteudo.append(el("h2", { texto: "Apagar" }), el("div", { class: "cartao" }, el("div", { class: "linha" },
      el("div", { class: "cresce" }, "Apagar todo o histórico de conversas.", el("div", { class: "detalhe", texto: "Os fatos, o caderno e os lembretes continuam." })),
      el("button", { class: "perigo", texto: "Apagar conversas", onclick: async () => {
        if (!confirm("Apagar TODO o histórico de conversas? Não dá para desfazer.")) return;
        await tentar(() => api("/api/conversas/apagar", {}), (r) => `Apaguei ${r.apagadas} falas.`);
      } }))));
  }

  async function extraContas() {
    const cartao = el("div", { class: "cartao" });
    conteudo.append(el("h2", { texto: "Conectar" }), cartao);
    const d = await tentar(() => api("/api/contas"));
    if (!d) return;
    const linha = (nome, info, qual, dica) => cartao.append(el("div", { class: "linha" },
      el("div", { class: "cresce" }, el("b", { texto: nome }), el("div", { class: "detalhe", texto: dica })),
      el("span", { class: "selo " + (info.conectado ? "ok" : info.configurado ? "aviso" : ""), texto: info.conectado ? "conectado" : info.configurado ? "falta autorizar" : "não configurado" }),
      el("button", { class: "secundario", texto: "Conectar", disabled: !info.configurado, onclick: async () => {
        const r = await tentar(() => api("/api/contas/" + qual, {}));
        if (r && r.url) window.open(r.url, "_blank");
        else if (r) toast(r.mensagem);
      } })));
    if (secaoAtual === "Contas") linha("Spotify", d.spotify, "spotify", "Coloque o Client ID acima, salve e clique em Conectar.");
    if (secaoAtual === "Agenda") {
      linha("Google Agenda", d.google, "google", "Precisa do arquivo dados\\google_credenciais.json (veja o LEIA-ME).");
      linha("Outlook", d.outlook, "outlook", "Coloque o ID do app do Outlook acima e salve.");
    }
  }

  async function extraCelular() {
    const cartao = el("div", { class: "cartao" });
    conteudo.append(el("h2", { texto: "Parear" }), cartao);
    const d = await tentar(() => api("/api/contas"));
    const qr = el("div", { class: "qr" });
    cartao.append(el("div", { class: "linha" },
      el("div", { class: "cresce" }, el("b", { texto: "App do celular" }), el("div", { class: "detalhe",
        texto: d && d.celular.configurado ? (d.celular.conectado ? "PC conectado ao serviço do celular." : "Publicado, mas o PC não está conectado agora.")
          : "Ainda não publicado: rode o publicar_celular.bat." })),
      el("button", { class: "primario", texto: "Parear celular", disabled: !(d && d.celular.conectado), onclick: async () => {
        const r = await tentar(() => api("/api/celular/parear", {}));
        if (!r) return;
        qr.replaceChildren(el("img", { src: r.qr, alt: "QR code para parear" }),
          el("div", {}, el("div", { class: "codigo", texto: r.codigo.slice(0, 4) + " " + r.codigo.slice(4) }),
            el("p", { class: "detalhe", texto: "Aponte a câmera do celular para o QR code ou abra o app e digite o código. Vale por 10 minutos e só uma vez." })));
      } }),
      el("button", { class: "perigo", texto: "Desconectar todos", disabled: !(d && d.celular.configurado), onclick: async () => {
        if (!confirm("Desconectar todos os celulares pareados?")) return;
        await tentar(() => api("/api/celular/revogar", {}), "Celulares desconectados.");
      } })), qr);
  }

  // ---------------------------------------------------------------- personalidade
  async function paginaPersonalidade() {
    conteudo.append(el("h1", { texto: "Personalidade" }),
      el("p", { class: "sub", texto: "O documento de identidade dela. Todo cérebro (nuvem e local) lê este texto antes de responder. A mudança vale na próxima pergunta." }),
      el("div", { class: "retrato" },
        el("img", { src: "/static/ametista.jpg", alt: "A Ametista, da ficha de personagem", width: 190, height: 289 }),
        el("div", {},
          el("h2", { texto: "Como ela é" }),
          el("p", { texto: "Cabelo branco-prateado com reflexos iridescentes, preso num coque meio bagunçado; olhos azul-cristal com um brilho de estrela; um monóculo de cristal sobre o olho direito; filigranas de metal líquido com gotas de cristal sob os olhos e brincos longos de cristal." }),
          el("p", { class: "detalhe", texto: "No rosto animado (barra do PC e celular) ficam só os olhos de cristal, o monóculo, a boca e os detalhes em metal líquido iridescente." }))));
    const d = await tentar(() => api("/api/identidade"));
    const area = el("textarea", { value: (d && d.texto) || "", spellcheck: true });
    conteudo.append(area, el("div", { class: "linha" }, el("span", { class: "cresce detalhe", texto: "Linhas que começam com > são notas para você e não vão para a IA." }),
      el("button", { class: "primario", texto: "Salvar personalidade", onclick: () => tentar(() => api("/api/identidade", { texto: area.value }), "Personalidade salva.") })));
  }

  // ---------------------------------------------------------------- rotinas
  const TIPOS_PASSO = [
    ["falar", "Falar uma frase"], ["resumo", "Resumo do dia"], ["noticias", "Manchetes"], ["amanha", "Agenda de amanhã"],
    ["pausar_musica", "Pausar a música"], ["luzes", "Luzes"], ["nao_perturbe_min", "Não perturbe (minutos)"],
    ["nao_perturbe_ate", "Não perturbe até"], ["esperar", "Esperar (segundos)"], ["ferramenta", "Ação da Ametista"],
  ];
  const DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];

  async function paginaRotinas() {
    conteudo.append(el("h1", { texto: "Rotinas" }),
      el("p", { class: "sub", texto: "Vários passos com uma frase. Também dá para criar por voz: \"Ametista, cria uma rotina modo jogo que abre a Steam e coloca o volume em 40\"." }));
    const d = await tentar(() => api("/api/rotinas"));
    if (!d) return;
    let rotinas = d.rotinas;
    const lista = el("div");
    const desenhar = () => { lista.replaceChildren(...rotinas.map((r, i) => cartaoRotina(r, i, rotinas, desenhar))); };
    desenhar();
    conteudo.append(lista, el("div", { class: "linha" },
      el("button", { class: "secundario", texto: "+ Nova rotina", onclick: () => { rotinas.push({ nome: "nova rotina", frases: [], passos: [{ falar: "Pronto!" }], horario: null, dias: null, ativa: true }); desenhar(); } }),
      el("span", { class: "cresce" }),
      el("button", { class: "primario", texto: "Salvar rotinas", onclick: () => tentar(() => api("/api/rotinas", { rotinas }), "Rotinas salvas.") })));
  }

  function cartaoRotina(r, i, rotinas, redesenhar) {
    const c = el("div", { class: "rotina" });
    c.append(el("div", { class: "rotina-topo" },
      el("input", { type: "text", class: "nome", value: r.nome, oninput: (e) => r.nome = e.target.value }),
      el("label", { class: "interruptor", title: "Ativa" }, el("input", { type: "checkbox", checked: r.ativa !== false, onchange: (e) => r.ativa = e.target.checked }), el("span")),
      el("span", { class: "cresce" }),
      el("button", { class: "secundario", texto: "Executar agora", onclick: () => tentar(() => api("/api/rotinas/executar", { nome: r.nome }), "Executando…") }),
      el("button", { class: "perigo", texto: "Apagar", onclick: () => { if (confirm(`Apagar a rotina ${r.nome}?`)) { rotinas.splice(i, 1); redesenhar(); } } })));
    const dias = el("div", { class: "dias" });
    DIAS.forEach((nome, idx) => dias.append(el("label", {}, el("input", { type: "checkbox", checked: (r.dias || []).includes(idx), onchange: (e) => {
      const s = new Set(r.dias || []); e.target.checked ? s.add(idx) : s.delete(idx); r.dias = [...s].sort(); if (!r.dias.length) r.dias = null;
    } }), nome)));
    c.append(el("div", { class: "grade" },
      el("label", {}, "Frases que disparam (separadas por vírgula)", el("input", { type: "text", value: (r.frases || []).join(", "), oninput: (e) => r.frases = e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })),
      el("label", {}, "Rodar sozinha às (opcional)", el("input", { type: "time", value: r.horario || "", onchange: (e) => r.horario = e.target.value || null })),
      el("label", {}, "Nos dias (vazio = todos)", dias)));
    const passos = el("div");
    const desenharPassos = () => {
      passos.replaceChildren(...r.passos.map((p, j) => linhaPasso(p, j, r, desenharPassos)));
      passos.append(el("button", { class: "link", texto: "+ adicionar passo", onclick: () => { r.passos.push({ falar: "" }); desenharPassos(); } }));
    };
    desenharPassos();
    c.append(passos);
    return c;
  }

  function linhaPasso(p, j, r, redesenhar) {
    const tipo = Object.keys(p).find((k) => k !== "args") || "falar";
    const sel = el("select", { onchange: (e) => {
      const novo = e.target.value;
      const padrao = { falar: "", resumo: true, noticias: 3, amanha: true, pausar_musica: true, luzes: "desligar",
                       nao_perturbe_min: 60, nao_perturbe_ate: "07:00", esperar: 5, ferramenta: "pc_volume" }[novo];
      r.passos[j] = novo === "ferramenta" ? { ferramenta: padrao, args: {} } : { [novo]: padrao };
      redesenhar();
    } });
    for (const [v, rot] of TIPOS_PASSO) sel.append(el("option", { value: v, texto: rot, selected: v === tipo }));
    const valor = el("div", { class: "valor" });
    if (tipo === "falar") valor.append(el("input", { type: "text", value: p.falar, placeholder: "O que ela fala ({dono} vira seu nome)", oninput: (e) => p.falar = e.target.value }));
    else if (["noticias", "nao_perturbe_min", "esperar"].includes(tipo)) valor.append(el("input", { type: "number", value: p[tipo], oninput: (e) => p[tipo] = Number(e.target.value) }));
    else if (tipo === "nao_perturbe_ate") valor.append(el("input", { type: "time", value: p[tipo], onchange: (e) => p[tipo] = e.target.value }));
    else if (tipo === "luzes") {
      const s = el("select", { onchange: (e) => p.luzes = e.target.value });
      for (const v of ["desligar", "ligar"]) s.append(el("option", { value: v, texto: v === "ligar" ? "acender todas" : "apagar todas", selected: p.luzes === v }));
      valor.append(s);
    } else if (tipo === "ferramenta") {
      valor.append(el("input", { type: "text", value: p.ferramenta, placeholder: "ex.: pc_volume", oninput: (e) => p.ferramenta = e.target.value }),
        el("input", { type: "text", value: JSON.stringify(p.args || {}), placeholder: '{"acao": "definir", "valor": 20}', oninput: (e) => {
          try { p.args = JSON.parse(e.target.value || "{}"); e.target.style.borderColor = ""; } catch { e.target.style.borderColor = "var(--vermelho)"; }
        } }));
    } else valor.append(el("span", { class: "detalhe", texto: "sem opções" }));
    return el("div", { class: "passo" }, el("span", { class: "num", texto: j + 1 }), sel, valor,
      el("button", { class: "x", title: "Remover passo", texto: "×", onclick: () => { r.passos.splice(j, 1); redesenhar(); } }));
  }

  // ---------------------------------------------------------------- memória e lembretes
  async function paginaMemoria() {
    conteudo.append(el("h1", { texto: "Memória e lembretes" }), el("p", { class: "sub", texto: "Tudo fica só neste PC (pasta dados)." }));
    const d = await tentar(() => api("/api/memoria"));
    if (!d) return;
    const recarregar = () => abrir("Memória e lembretes");
    const fatos = el("div", { class: "cartao" });
    if (!d.fatos.length) fatos.append(el("div", { class: "linha detalhe", texto: "Nada ainda. Diga \"Ametista, lembra que…\"." }));
    for (const f of d.fatos) fatos.append(el("div", { class: "linha" }, el("span", { class: "cresce", texto: f }),
      el("button", { class: "link", texto: "esquecer", onclick: async () => { await tentar(() => api("/api/memoria/esquecer-fato", { texto: f })); recarregar(); } })));
    const caderno = el("div", { class: "cartao" });
    if (!d.caderno.length) caderno.append(el("div", { class: "linha detalhe", texto: "Vazio. Diga \"Ametista, anota no caderno que a obra de Jundiaí…\"." }));
    for (const c of d.caderno) caderno.append(el("div", { class: "linha" },
      el("div", { class: "cresce" }, el("b", { texto: c.nome }), " ", el("span", { class: "selo", texto: c.categoria }), el("div", { class: "detalhe", texto: c.detalhes })),
      el("button", { class: "link", texto: "apagar", onclick: async () => { if (confirm(`Apagar ${c.nome}?`)) { await tentar(() => api("/api/memoria/caderno-apagar", { nome: c.nome })); recarregar(); } } })));
    const lembretes = el("div", { class: "cartao" });
    const visiveis = d.lembretes.filter((l) => l.tipo !== "aniversario_vespera");
    if (!visiveis.length) lembretes.append(el("div", { class: "linha detalhe", texto: "Nenhum lembrete pendente." }));
    for (const l of visiveis) {
      const quando = l.quando ? new Date(l.quando).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : (l.condicao || "");
      const rep = l.recorrencia && l.tipo !== "aniversario" ? ` · repete (${l.recorrencia.tipo})` : "";
      lembretes.append(el("div", { class: "linha" },
        el("div", { class: "cresce" }, el("b", { texto: l.texto }), el("div", { class: "detalhe", texto: `${l.tipo} · ${quando}${rep}` })),
        el("button", { class: "link", texto: "cancelar", onclick: async () => { await tentar(() => api("/api/memoria/lembrete-cancelar", { id: l.id })); recarregar(); } })));
    }
    conteudo.append(el("h2", { texto: "O que ela sabe sobre você" }), fatos, el("h2", { texto: "Caderno pessoal" }), caderno,
      el("h2", { texto: "Lembretes, alarmes e aniversários" }), lembretes);
  }

  // ---------------------------------------------------------------- histórico
  async function paginaHistorico() {
    conteudo.append(el("h1", { texto: "Histórico" }), el("p", { class: "sub", texto: "O que ela fez (com desfazer) e o que vocês conversaram." }));
    const acoes = el("div", { class: "cartao" });
    const d = await tentar(() => api("/api/acoes?limite=150"));
    for (const a of (d && d.acoes) || []) {
      const quando = new Date(a.quando).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
      acoes.append(el("div", { class: "linha" },
        el("div", { class: "cresce" }, el("b", { texto: a.descricao, style: a.desfeito ? "text-decoration: line-through" : "" }),
          el("div", { class: "detalhe", texto: [quando, a.quem && `por ${a.quem}`, a.origem, a.motivo && `“${a.motivo}”`, a.resultado].filter(Boolean).join(" · ") })),
        el("span", { class: "selo " + (a.ok ? "ok" : "erro"), texto: a.desfeito ? "desfeita" : a.ok ? "ok" : "falhou" }),
        a.desfazivel && !a.desfeito ? el("button", { class: "secundario", texto: "Desfazer", onclick: async () => {
          const r = await tentar(() => api("/api/acoes/desfazer", { id: a.id })); if (r) toast(r.resultado); abrir("Histórico");
        } }) : null));
    }
    if (!acoes.childNodes.length) acoes.append(el("div", { class: "linha detalhe", texto: "Nenhuma ação registrada." }));
    const dia = el("input", { type: "date", value: new Date().toISOString().slice(0, 10) });
    const conversas = el("div", { class: "cartao" });
    const carregarDia = async () => {
      const r = await tentar(() => api("/api/conversas?dia=" + dia.value));
      conversas.replaceChildren();
      for (const c of (r && r.conversas) || []) conversas.append(el("div", { class: "linha" },
        el("span", { class: "detalhe", texto: c.quando.slice(11, 16) }),
        el("div", { class: "cresce" }, el("b", { texto: c.papel === "user" ? (c.quem || "Você") : "Ametista" }), " ", c.texto)));
      if (!conversas.childNodes.length) conversas.append(el("div", { class: "linha detalhe", texto: "Nenhuma conversa guardada nesse dia." }));
    };
    dia.onchange = carregarDia;
    conteudo.append(el("h2", { texto: "Ações" }), acoes, el("h2", {}, "Conversas de ", dia), conversas);
    carregarDia();
  }

  // ---------------------------------------------------------------- diagnóstico e log
  async function paginaDiagnostico() {
    conteudo.append(el("h1", { texto: "Diagnóstico" }), el("p", { class: "sub", texto: "Confere cada peça da Ametista. Também dá para pedir por voz: \"Ametista, faça um diagnóstico\"." }));
    const cartao = el("div", { class: "cartao diag" }, el("div", { class: "linha detalhe", texto: "Clique em Rodar diagnóstico." }));
    const botao = el("button", { class: "primario", texto: "Rodar diagnóstico", onclick: async () => {
      botao.disabled = true; botao.textContent = "Conferindo…";
      const d = await tentar(() => api("/api/diagnostico", {}));
      botao.disabled = false; botao.textContent = "Rodar de novo";
      if (!d) return;
      cartao.replaceChildren(el("div", { class: "linha" }, el("b", { class: "cresce", texto: d.resumo })));
      for (const i of d.itens) cartao.append(el("div", { class: "linha" },
        el("span", { class: "selo " + i.situacao, texto: { ok: "ok", aviso: "atenção", erro: "problema" }[i.situacao] }),
        el("div", { class: "cresce" }, el("b", { texto: i.item }), el("div", { class: "detalhe", texto: i.detalhe }))));
    } });
    conteudo.append(el("div", { class: "linha" }, botao), cartao);
  }

  async function paginaLog() {
    conteudo.append(el("h1", { texto: "Registro (log)" }), el("p", { class: "sub", texto: "As últimas mensagens do programa (dados\\ametista.log)." }));
    const d = await tentar(() => api("/api/log"));
    conteudo.append(el("div", { class: "log", texto: ((d && d.linhas) || []).join("\n") || "Vazio." }),
      el("div", { class: "linha" }, el("button", { class: "secundario", texto: "Atualizar", onclick: () => abrir("Registro (log)") })));
  }

  // ---------------------------------------------------------------- topo e rodapé
  async function recarregarConfig() {
    config = await api("/api/config");
    alterados = {};
    $("rodape").hidden = true;
  }

  $("btnSalvar").onclick = async () => {
    const valores = { ...alterados };
    const r = await tentar(() => api("/api/config", { valores }));
    if (!r) return;
    await recarregarConfig();
    abrir(secaoAtual);
    if (r.reiniciar && r.reiniciar.length) toast("Salvo. Algumas mudanças só valem depois de reiniciar a Ametista.", false,
      { rotulo: "Reiniciar agora", fn: () => tentar(() => api("/api/reiniciar", {}), "Reiniciando…") });
    else toast("Salvo.");
  };
  $("btnDescartar").onclick = () => { alterados = {}; $("rodape").hidden = true; abrir(secaoAtual); };
  addEventListener("beforeunload", (e) => { if (Object.keys(alterados).length) { e.preventDefault(); e.returnValue = ""; } });

  async function pintarEstado() {
    const d = await api("/api/estado").catch(() => null);
    if (!d) return;
    $("titulo").textContent = d.nome;
    $("versao").textContent = "v" + d.versao;
    $("chipPrivado").setAttribute("aria-pressed", !!d.privado);
    $("chipSilencio").setAttribute("aria-pressed", !!d.nao_perturbe);
    $("chipSilencio").textContent = d.nao_perturbe ? `🌙 Não perturbe até ${d.nao_perturbe.slice(11, 16)}` : "🌙 Não perturbe";
  }
  $("chipPrivado").onclick = async () => {
    const ligar = $("chipPrivado").getAttribute("aria-pressed") !== "true";
    await tentar(() => api("/api/privado", { valor: ligar }), ligar ? "Modo privado ligado." : "Modo privado desligado.");
    pintarEstado();
  };
  $("chipSilencio").onclick = async () => {
    const ligar = $("chipSilencio").getAttribute("aria-pressed") !== "true";
    await tentar(() => api("/api/nao-perturbe", { minutos: ligar ? 60 : 0 }), (r) => r.resultado);
    pintarEstado();
  };
  $("btnParar").onclick = () => tentar(() => api("/api/parar-tudo", {}), "Parei tudo.");

  (async () => {
    try { await recarregarConfig(); }
    catch (e) { conteudo.replaceChildren(el("h1", { texto: "Não consegui falar com a Ametista" }), el("p", { class: "sub", texto: e.message })); return; }
    montarMenu();
    pintarEstado();
    setInterval(pintarEstado, 15000);
    const inicial = decodeURIComponent(location.hash.slice(1));
    abrir([...config.secoes, ...PAGINAS_EXTRAS.flatMap((g) => g.itens.map(([n]) => n))].includes(inicial) ? inicial : config.secoes[0]);
  })();
})();
