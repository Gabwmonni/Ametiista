"""Cérebro híbrido da Ametista.

Ordem de decisão:
  1. Roteador local (instantâneo, offline): hora, data, timers, clima, música, volume, janelas, rotinas...
  2. Claude na nuvem, em streaming: ela começa a falar a primeira frase enquanto ainda pensa no resto.
     - modelo do dia a dia (rápido) para quase tudo;
     - modelo forte para pedidos difíceis (explicações, análises, a tela). O rápido também pode pedir ajuda.
  3. Ollama local (também em streaming), se a nuvem falhar ou não houver internet.
"""
import json
import re
import unicodedata
from datetime import datetime

import httpx

from . import acoes, config, estado, eventos, ferramentas, memoria, personalidade
from .estado import Cancelado

EMOCOES = personalidade.EMOCOES
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
NUMEROS = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
    "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "quinze": 15, "vinte": 20, "trinta": 30,
    "quarenta": 40, "quarenta e cinco": 45, "cinquenta": 50, "sessenta": 60, "noventa": 90,
}
IGNORAR = "[ignorar]"


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w\s:.,]", " ", t).strip()


def resposta(texto: str, origem: str, emocao: str = "neutra", **extra) -> dict:
    return {"texto": texto, "origem": origem, "emocao": emocao, **extra}


# =====================================================================
# 1. Roteador local
# =====================================================================
def _numero(trecho: str) -> float | None:
    trecho = trecho.strip().replace(",", ".")
    try:
        return float(trecho)
    except ValueError:
        return NUMEROS.get(trecho)


_RE_TIMER = re.compile(
    r"(?:timer|temporizador|cronometro|contagem|me (?:avisa|avise|chama|lembra)|avisa me|daqui a)"
    r".*?(\d+(?:[.,]\d+)?|quarenta e cinco|" + "|".join(sorted(NUMEROS, key=len, reverse=True)) + r")\s*"
    r"(segundos?|minutos?|min|horas?|h)\b"
)
NEGADO = "Desculpe, isso eu só faço para quem tem permissão."


def _ferramenta(ferramenta_: str, emocao: str = "feliz", sondagem_: bool = False, **args) -> dict:
    """Executa uma ferramenta pelo mesmo caminho da IA (permissão, confirmação, registro, desfazer).
    sondagem_: tentativa local que, se falhar, passa o pedido para a nuvem (a falha não vai para o histórico)."""
    r = ferramentas.executar(ferramenta_, args, sondagem=sondagem_)
    texto = ferramentas.falavel(r) if isinstance(r, str) else "Feito."
    if texto.startswith("NEGADO"):
        return resposta(NEGADO, "local", "neutra")
    if texto.startswith("PRECISA CONFIRMAR"):
        p = acoes.pendente()
        return resposta(p["pergunta"] if p else "Confirma?", "local", "pensativa", aguardando=True)
    if texto.startswith(("Erro", "Não consegui")):
        return resposta(texto, "local", "triste")
    return resposta(texto, "local", emocao)


def roteador_local(texto: str, sem_nome: bool = False) -> dict | None:
    t = normalizar(texto)
    t = re.sub(r"[.,!?]+$", "", t).strip()

    if sem_nome:  # conversa sem o nome: só comandos curtos e inequívocos
        r = _rota_pc_musica(t, texto, apenas_controles=True)
        return r

    # Hora e data
    if re.search(r"\b(que horas|qual a hora|horas sao|me diz a hora)\b", t):
        agora = datetime.now()
        return resposta(f"São {agora:%H:%M}.", "local")
    if re.search(r"\b(que dia e hoje|qual a data|data de hoje)\b", t):
        h = datetime.now()
        return resposta(f"Hoje é {DIAS[h.weekday()]}, {h.day} de {MESES[h.month - 1]} de {h.year}.", "local")

    # Desfazer e repetir
    if re.match(r"^(desfaz|desfazer|desfaca|desfaz isso|desfaz o que (voce|vc) fez|volta como estava|"
                r"desfaz a ultima( coisa| acao)?)$", t):
        r = acoes.desfazer_ultima()
        return resposta(r, "local", "feliz" if not r.startswith(("Não", "Essa")) else "pensativa")
    if re.match(r"^((faz|faca|abre|toca|repete) (isso )?de novo|de novo|repete|mais uma vez)$", t):
        item = acoes.ultima_repetivel()
        if item:
            return _ferramenta(item["ferramenta"], **item["args"])

    # Janelas
    m = re.match(r"^(fecha|feche|minimiza|minimize|maximiza|maximize|restaura)\s+(essa|esta|a)\s+janela$", t)
    if m:
        acao = {"fech": "fechar", "mini": "minimizar", "maxi": "maximizar", "rest": "restaurar"}[m.group(1)[:4]]
        return _ferramenta("pc_janela", emocao="neutra", acao=acao)

    # Modo privado e não perturbe
    if re.match(r"^(liga|ativa|entra( no)?|modo) (o )?modo privado$|^modo privado( ligado)?$", t):
        return _ferramenta("modo_privado", emocao="neutra", ligar=True)
    m = re.match(r"^(nao perturbe|modo nao perturbe|nao me perturbe)( por (\d+|uma|duas|tres) ?(horas?|h|minutos?|min))?$", t)
    if m:
        qtd = _numero(m.group(3)) if m.group(3) else 1
        minutos = int(qtd * 60 if (m.group(4) or "h").startswith("h") else qtd)
        return _ferramenta("nao_perturbe", emocao="neutra", minutos=minutos)
    if re.match(r"^(desliga|desativa|tira|sai do) (o )?(modo )?nao perturbe$", t):
        return _ferramenta("nao_perturbe", emocao="feliz", minutos=0)

    # Diagnóstico
    if re.search(r"\b(faz|faca|fazer|roda|rode) (um )?(auto ?)?diagnostico\b|^diagnostico$", t):
        return _ferramenta("diagnostico", emocao="pensativa")

    # Conversa nova
    if re.match(r"^(esquece|apaga) (essa|a|nossa) conversa$|^(nova conversa|muda de assunto)$", t):
        memoria.limpar_historico()
        return resposta("Pronto, começamos do zero.", "local", "feliz")

    # Rotinas ("bom dia", "modo filme", "vou dormir"...)
    from . import rotinas

    rotina = rotinas.achar_por_frase(t)
    if rotina:
        return _ferramenta("rotina_executar", emocao="feliz", nome=rotina)
    rotina = rotinas.achar_desfazer(t)  # "acabou o filme" desfaz o "modo filme"
    if rotina:
        item = next((a for a in acoes.listar(60) if a["ferramenta"] == "rotina_executar" and a["ok"]
                     and a["args"].get("nome", "").lower() == rotina.lower() and not a["desfeito"]), None)
        if not item:
            return resposta(f"O {rotina} não estava ligado.", "local", "neutra")
        r = acoes.desfazer(item["id"])
        ok = not r.startswith(("Não", "Essa"))
        return resposta(f"Pronto, desliguei o {rotina}." if ok else r, "local", "feliz" if ok else "pensativa")

    # Meia hora
    if re.search(r"\b(timer|temporizador|me avisa|daqui a)\b.*\bmeia hora\b", t):
        return _ferramenta("criar_timer", minutos=30, descricao="Timer de meia hora")

    # Timers
    m = _RE_TIMER.search(t)
    if m and not re.search(r"\b(as|para as|amanha)\b\s*\d", t):
        valor = _numero(m.group(1))
        if valor:
            unidade = m.group(2)
            minutos = valor / 60 if unidade.startswith("s") else valor * 60 if unidade.startswith("h") else valor
            descricao = re.sub(r"\b(me (avisa|avise|chama|lembra|lembre)|avisa me|daqui a|em)\b", " ", texto,
                               flags=re.I)
            descricao = re.sub(r"\b(de |para |pra )?\S+\s+(segundos?|minutos?|min|horas?|h)\b", " ", descricao,
                               flags=re.I)
            descricao = re.sub(r"^\s*(de|para|pra)\s+", "", re.sub(r"\s+", " ", descricao)).strip(" ,.?!")
            if re.match(r"^(timer|temporizador|cron[oô]metro|contagem)", descricao, re.I) or len(descricao) < 3:
                descricao = "Timer"
            return _ferramenta("criar_timer", minutos=minutos, descricao=descricao)

    # Clima simples
    if re.search(r"\b(como (esta|ta) o tempo|previsao do tempo|vai chover|temperatura (agora|hoje|la fora))\b", t):
        try:
            linhas = ferramentas.clima(1).split("\n")
            return resposta(" ".join(linhas[:2]), "local")
        except Exception:
            return None  # deixa a nuvem tentar

    r = _rota_pc_musica(t, texto)
    if r:
        return r

    # Luzes / tomadas simples: "acende a luz da sala", "desliga o ventilador"
    m = re.match(r"^(liga|ligar|acende|acender|desliga|desligar|apaga|apagar)\s+(?:a |o |as |os )?(.+)$", t)
    if m and ferramentas.casa_configurada() and not re.search(r"\b(pc|computador|tela|som|musica)\b", m.group(2)):
        ligar = m.group(1).startswith(("liga", "acend"))
        alvo = re.sub(r"^(luz|luzes|lampada)\s+(da|do|de)\s+", "", m.group(2)).strip()
        try:
            achado = _achar_dispositivo(alvo)
        except Exception:
            achado = None
        if achado:
            r = _ferramenta("casa_controlar", entity_id=achado[0], acao="ligar" if ligar else "desligar")
            if r["emocao"] == "feliz":
                r["texto"] = f"{'Ligado' if ligar else 'Desligado'}: {achado[1]}."
            return r
    return None


def _rota_pc_musica(t: str, original: str, apenas_controles: bool = False) -> dict | None:
    from . import spotify

    tem_spotify = spotify.conectado()
    controles = [
        (r"^(pausa|pause|pausar|para a musica|para de tocar|pausa a musica)$", "pausar", "tocar_pausar"),
        (r"^(continua|continuar|despausa|volta a tocar|continua a musica|play|solta a musica)$",
         "continuar", "tocar_pausar"),
        (r"^(proxima|proxima musica|pula|pula essa|pula a musica|passa a musica|avanca a musica)$",
         "proxima", "proxima"),
        (r"^(volta a musica|musica anterior|anterior|volta uma musica)$", "anterior", "anterior"),
    ]
    for padrao, acao_sp, acao_pc in controles:
        if re.match(padrao, t):
            if tem_spotify:
                return _ferramenta("spotify_controle", acao=acao_sp)
            return _ferramenta("pc_midia", acao=acao_pc)

    m = re.match(r"^(aumenta|sobe|aumentar) o (volume|som)( um pouco| bastante| muito)?$", t)
    if m:
        return _ferramenta("pc_volume", acao="aumentar",
                           valor=20 if (m.group(3) or "").strip() in ("bastante", "muito") else 10)
    m = re.match(r"^(abaixa|diminui|baixa|diminuir|abaixar) o (volume|som)( um pouco| bastante| muito)?$", t)
    if m:
        return _ferramenta("pc_volume", acao="diminuir",
                           valor=20 if (m.group(3) or "").strip() in ("bastante", "muito") else 10)
    m = re.match(r"^(coloca |poe |deixa )?(o )?volume (em|no|para|pra|a)? ?(\d{1,3})( por cento|%)?$", t)
    if m:
        return _ferramenta("pc_volume", acao="definir", valor=int(m.group(4)))
    if re.match(r"^(muta|mutar|silencia|tira o som)( o pc| o som| tudo)?$", t):
        return _ferramenta("pc_volume", emocao="neutra", acao="mudo")
    if re.match(r"^(desmuta|volta o som|liga o som)$", t):
        return _ferramenta("pc_volume", acao="som")
    if apenas_controles:
        return None

    if tem_spotify:
        if re.match(r"^(que musica e essa|qual musica (e essa|ta tocando|esta tocando)|o que (ta|esta) tocando)$", t):
            return _ferramenta("spotify_tocando", emocao="neutra")
        if re.match(r"^(curte|curtir|salva) (essa|a) musica$", t):
            return _ferramenta("spotify_curtir")

    m = re.match(r"^(abre|abrir|abra|inicia|executa)\s+(.+)$", t)
    if m and len(m.group(2).split()) <= 5 and not re.search(r"\b(de novo|arquivo|planilha|pasta do|documento)\b", t):
        orig = re.sub(r"[.,!?]+$", "", original.strip())
        r = _ferramenta("pc_abrir", emocao="neutra", sondagem_=True, alvo=re.sub(r"^\S+\s+", "", orig, count=1))
        if not r["texto"].startswith("Não achei"):
            return r
        return None  # a nuvem tenta achar (arquivo, site, nome mal transcrito)

    if re.match(r"^(bloqueia|trava|bloquear)( o pc| o computador| a tela)?$", t):
        return _ferramenta("pc_sistema", emocao="neutra", acao="bloquear")
    if re.match(r"^(minimiza tudo|mostra a area de trabalho|limpa a tela)$", t):
        return _ferramenta("pc_sistema", emocao="neutra", acao="minimizar_tudo")
    if re.match(r"^cancela (o )?desligamento$", t):
        return _ferramenta("pc_sistema", emocao="neutra", acao="cancelar_desligamento")

    m = re.match(r"^(toca|tocar|coloca|bota|poe|reproduz)\s+(.+)$", t)
    if m and tem_spotify:
        orig = re.sub(r"[.,!?]+$", "", original.strip())
        r = _ferramenta("spotify_tocar", busca=re.sub(r"^\S+\s+", "", orig, count=1))
        if "Não encontrei" in r["texto"]:
            return None  # a nuvem tenta entender melhor (ex.: nome mal transcrito)
        return r
    return None


def _achar_dispositivo(alvo: str) -> tuple[str, str] | None:
    candidatos = []
    for linha in ferramentas.casa_listar().split("\n"):
        partes = [p.strip() for p in linha.split("|")]
        if len(partes) < 2:
            continue
        eid, nome = partes[0], partes[1]
        if normalizar(alvo) in normalizar(nome) or normalizar(alvo).replace(" ", "_") in eid:
            candidatos.append((eid, nome))
    return candidatos[0] if len(candidatos) == 1 else None


# =====================================================================
# 2. Escolha do modelo
# =====================================================================
_DIFICIL = re.compile(
    r"\b(explica|explique|explicar|analisa|analise|analisar|compara|compare|comparar|planeja|planeje|planejamento|"
    r"estrategia|resume|resuma|resumo|por que|porque|como funciona|codigo|programa em|script|formula|calcula|"
    r"calcule|escreve um|escreva um|escreve uma|escreva uma|redige|redija|revisa|revise|corrige|corrija|traduz|"
    r"traduza|detalhad\w*|pensa bem|pense bem|com calma|passo a passo|me ajuda a decidir|o que voce acha|"
    r"diferenca entre|vale a pena|recomenda|sugere um plano|orcamento|dimensiona)\b")
_TELA = re.compile(r"\b(minha tela|na tela|essa tela|esse erro|essa mensagem|isso aqui na|onde (eu )?clico|"
                   r"nessa janela|nessa pagina|esse site|o que (e|eh) isso|me mostra onde)\b")


def modelo_para(texto: str) -> tuple[str, str]:
    """(modelo, tipo) com tipo "rapido" ou "forte"."""
    rapido, forte = config.CLAUDE_MODELO, config.CLAUDE_MODELO_FORTE
    if not config.MODELO_AUTOMATICO or not forte or forte == rapido:
        return rapido, "rapido"
    t = normalizar(texto)
    if len(t) > 170 or _DIFICIL.search(t) or _TELA.search(t):
        return forte, "forte"
    return rapido, "rapido"


def _e_modelo_novo(modelo: str) -> bool:
    return modelo.startswith(("claude-opus-5", "claude-sonnet-5", "claude-fable", "claude-mythos"))


def _usa_fallbacks(modelo: str) -> bool:
    return modelo.startswith(("claude-opus-5", "claude-fable"))


def ferramenta_busca_web(modelo: str) -> dict:
    tipo = "web_search_20260209" if modelo.startswith(("claude-opus-5", "claude-sonnet-5")) else "web_search_20250305"
    return {"type": tipo, "name": "web_search", "max_uses": 3,
            "user_location": {"type": "approximate", "country": "BR", "city": config.CIDADE,
                              "timezone": "America/Sao_Paulo"}}


# =====================================================================
# 3. Prompt
# =====================================================================
CAPACIDADES = """# O que você consegue fazer
Você mora no PC de {dono} (Windows), como uma camada por cima da tela, e controla o computador com as
ferramentas: volume e mídia, abrir e fechar programas, sites, pastas e arquivos, pesquisar, janelas (fechar,
minimizar), mouse e teclado, ver a tela, área de transferência, digitar, Spotify, Steam, agenda, casa
inteligente, lembretes e rotinas.

- Ações: execute direto e confirme em poucas palavras ("Pronto!", "Tocando Coldplay."). Nunca diga que fez algo
  sem ter usado a ferramenta e recebido um resultado de sucesso. Se a ferramenta falhar, diga o que houve.
- Confirmação: se uma ferramenta responder "PRECISA CONFIRMAR", faça a pergunta em uma frase curta e pare. O
  sistema executa sozinho quando a pessoa disser "sim". Não chame a ferramenta de novo.
- Pedidos incompletos ("abre de novo", "não esse, o outro", "desfaz", "mais alto"): use a lista das últimas ações
  no contexto para entender a que se referem. Para desfazer use desfazer_acao.
- Tela: para perguntas sobre o que está na tela ("que erro é esse?", "onde clico?") use pc_ver_tela. Para mostrar
  onde clicar use pc_apontar com as coordenadas da imagem. Para clicar ou teclar use pc_clicar e pc_teclas.
- Tarefas grandes, com vários passos no computador (organizar pastas, preencher um formulário, pesquisar e montar
  uma planilha): use agente_iniciar. Você acompanha o andamento na tela e a pessoa pode cancelar.
- Arquivos: para abrir um arquivo pelo nome, use arquivos_buscar e depois arquivo_abrir com o caminho.

# Memória
- lembrar_fato: coisas duradouras sobre {dono} (preferências, pessoas, rotina) quando ele contar ou pedir.
- caderno_guardar / caderno_buscar: o banco pessoal de projetos, equipamentos, arquivos, pessoas e lugares
  (ex.: "a obra de Jundiaí fica na rua X", "meu notebook é um Dell de 16 GB").
- memoria_buscar: conversas passadas ("o que eu te pedi ontem?", "o que falamos sobre o orçamento?").
- Se a pessoa pedir para não guardar algo, não use lembrar_fato nem caderno_guardar para isso.

# Lembretes
- criar_timer (daqui a X minutos), criar_lembrete (data e hora), lembrete_recorrente (todo dia, toda segunda,
  todo mês), lembrete_condicao ("quando eu chegar", "quando eu ligar o PC", "quando eu abrir o AutoCAD",
  "na próxima vez que eu falar com você") e aniversario_adicionar.

# Rotinas e modos
- rotina_executar para "bom dia", "vou dormir", "modo filme" etc.; rotina_criar quando pedirem uma rotina nova.
- nao_perturbe e modo_privado quando pedirem silêncio ou privacidade.

{extras}"""


def _prompt_estavel(tipo_modelo: str) -> str:
    """Parte do prompt que quase nunca muda (fica no cache da API: mais rápido e mais barato)."""
    from . import agenda, spotify, steam

    extras = []
    if steam.disponivel():
        extras.append(steam.INSTRUCOES)
    if agenda.configurada():
        extras.append(agenda.INSTRUCOES)
    if spotify.configurado():
        extras.append("Spotify Premium: use as ferramentas spotify_* para música. Corrija nomes mal transcritos.")
    extras.append("Voz das pessoas: você reconhece quem fala pela voz. O dono pode cadastrar vozes "
                  "(pessoas_cadastrar), listar, remover e mudar o nível delas.")
    if tipo_modelo == "rapido":
        extras.append("Se o pedido for difícil demais para responder bem em poucas frases (uma análise, uma "
                      "explicação longa, um cálculo complicado), chame chamar_modelo_forte antes de responder.")
    base = personalidade.sistema_base(expressiva=_voz_expressiva())
    return base + "\n\n" + CAPACIDADES.format(dono=config.DONO, extras="\n\n".join(extras))


def _voz_expressiva() -> bool:
    from . import voz

    return voz.expressiva()


def _contexto_falante(falante) -> str:
    if falante is None or falante.nivel == "dono":
        return f"Quem está falando agora: {config.DONO} (o dono, pode tudo)."
    quem = falante.nome or "uma pessoa que você não conhece"
    return (f"Quem está falando agora: {quem} (nível {falante.nivel}), NÃO é {config.DONO}. Seja simpática, "
            f"trate pelo nome, mas não revele nada pessoal de {config.DONO} (agenda, memórias, tela, arquivos). "
            "Se pedirem algo que suas ferramentas não permitem, explique com gentileza que só o dono pode.")


def _prompt_contexto(falante=None, sem_nome: bool = False, tipo_modelo: str = "rapido",
                     origem: str = "pc", troca_privada: bool = False) -> str:
    from . import agente, foco, pc

    agora = datetime.now()
    eh_dono = falante is None or falante.nivel == "dono"
    linhas = ["# Contexto de agora",
              f"- Agora: {DIAS[agora.weekday()]}, {agora:%d/%m/%Y %H:%M}. Cidade: {config.CIDADE}.",
              f"- {_contexto_falante(falante)}",
              f"- Casa inteligente: {'Home Assistant conectado' if ferramentas.casa_configurada() else 'não configurada'}."]
    if origem == "celular":
        linhas.append(f"- O pedido veio do app do celular de {config.DONO} (ele pode estar longe do PC).")
    if eh_dono:
        janela = pc.janela_ativa_texto()
        if janela:
            linhas.append(f"- {janela}")
        fatos = memoria.fatos()
        linhas.append(f"- O que você sabe sobre {config.DONO}:\n" +
                      ("\n".join(f"  - {f}" for f in fatos[-60:]) if fatos else "  (nada ainda)"))
        ultimas = acoes.resumo_para_contexto()
        if ultimas:
            linhas.append("- Suas últimas ações (da mais antiga para a mais nova):\n" + ultimas)
        tarefas = agente.resumo_ativas()
        if tarefas:
            linhas.append(f"- Tarefas em andamento no modo agente: {tarefas}")
        sessao = foco.resumo_contexto()
        if sessao:
            linhas.append(f"- {sessao}")
    if estado.privado():
        linhas.append("- MODO PRIVADO ligado: nada desta conversa é guardado. Não use lembrar_fato nem caderno_guardar.")
    elif troca_privada:
        linhas.append("- A pessoa pediu para NÃO guardar esta conversa: não use lembrar_fato nem caderno_guardar.")
    if estado.offline:
        linhas.append("- Aviso: a internet parece instável agora.")
    if sem_nome:
        linhas.append(f"- Esta fala foi captada durante a conversa, SEM a pessoa dizer o seu nome. Se ela não for "
                      f"claramente dirigida a você (a pessoa falando com outra pessoa, ao telefone, a TV, uma música), "
                      f"responda apenas {IGNORAR} e nada mais.")
    if tipo_modelo == "forte" and origem == "pc":
        linhas.append("- Latency-sensitive; begin your visible answer immediately. Mesmo em assuntos difíceis, "
                      "a resposta é falada: seja clara e objetiva, sem se estender.")
    return "\n".join(linhas)


# =====================================================================
# 4. Claude (streaming com ferramentas)
# =====================================================================
_cliente = None


def _claude():
    global _cliente
    if _cliente is None:
        import anthropic

        _cliente = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=2, timeout=60)
    return _cliente


def reiniciar_cliente() -> None:
    """Depois de trocar a chave no painel."""
    global _cliente
    _cliente = None


class _TrocarModelo(Exception):
    pass


_STATUS = {
    "web_search": "pesquisando na web…", "pc_ver_tela": "olhando a tela…", "spotify_tocar": "procurando no Spotify…",
    "agenda_listar": "vendo a agenda…", "arquivos_buscar": "procurando o arquivo…", "memoria_buscar": "lembrando…",
    "steam_buscar_jogo": "procurando na Steam…", "clima": "vendo o clima…", "noticias": "lendo as notícias…",
    "agente_iniciar": "começando a tarefa…", "diagnostico": "fazendo o diagnóstico…",
    "arquivo_ler": "lendo o arquivo…", "pasta_listar": "olhando a pasta…", "pc_processos": "vendo os programas…",
    "limpeza_analisar": "medindo os temporários…", "limpeza_executar": "limpando…",
    "arquivo_enviar_celular": "mandando para o celular…", "conversa_exportar": "montando o bloco de notas…",
    "foco_relatorio": "vendo seus estudos…", "foco_parar": "fechando a sessão…",
}


def _status(nome: str) -> None:
    eventos.publicar({"tipo": "status", "texto": _STATUS.get(nome, "trabalhando nisso…")})


def _eco(conteudo: list) -> list:
    """Conteúdo do assistente para mandar de volta na próxima rodada.

    Se um modelo de reserva assumiu no meio (bloco "fallback"), o que veio antes dele volta só como texto."""
    tipos = [getattr(b, "type", None) for b in conteudo]
    if "fallback" not in tipos:
        return conteudo
    corte = len(tipos) - 1 - tipos[::-1].index("fallback")
    antes = [b for b in conteudo[:corte] if getattr(b, "type", None) == "text"]
    return antes + list(conteudo[corte + 1:])


def _texto_de(conteudo: list) -> str:
    return "".join(getattr(b, "text", "") for b in conteudo if getattr(b, "type", None) == "text")


def _rodada(cliente, params: dict, modelo: str, saida, ficha):
    """Uma chamada em streaming. Manda o texto para a fala conforme chega; devolve a mensagem final."""
    if _usa_fallbacks(modelo):
        gerenciador = cliente.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                                                   **params)
    else:
        gerenciador = cliente.messages.stream(**params)
    with gerenciador as stream:
        for ev in stream:
            if ficha is not None and ficha.cancelado:
                raise Cancelado()
            tipo = getattr(ev, "type", None)
            if tipo == "text":
                saida.texto(ev.text)
            elif tipo == "content_block_start":
                bloco = getattr(ev, "content_block", None)
                if getattr(bloco, "type", None) in ("tool_use", "server_tool_use"):
                    _status(getattr(bloco, "name", ""))
        return stream.get_final_message()


def perguntar_claude(texto: str, falante=None, saida=None, ficha=None, sem_nome: bool = False,
                     origem: str = "pc", modelo: str | None = None, tipo_modelo: str = "rapido",
                     troca_privada: bool = False) -> str:
    """Conversa com o Claude usando ferramentas. Devolve o texto completo (o que já foi para a fala)."""
    cliente = _claude()
    modelo = modelo or config.CLAUDE_MODELO
    mensagens = memoria.historico() + [{"role": "user", "content": texto}]
    ferramentas_api = ferramentas.definicoes_permitidas(falante, forte=tipo_modelo == "forte") + \
        [ferramenta_busca_web(modelo)]
    sistema = [{"type": "text", "text": _prompt_estavel(tipo_modelo), "cache_control": {"type": "ephemeral"}},
               {"type": "text", "text": _prompt_contexto(falante, sem_nome, tipo_modelo, origem, troca_privada)}]
    completo = []
    for _ in range(10):  # limite de rodadas de ferramentas
        params = {"model": modelo, "max_tokens": 16000 if _e_modelo_novo(modelo) else 2048, "system": sistema,
                  "tools": ferramentas_api, "messages": mensagens}
        if _e_modelo_novo(modelo):
            params["output_config"] = {"effort": "medium" if tipo_modelo == "forte" else "low"}
        r = _rodada(cliente, params, modelo, saida, ficha)
        completo.append(_texto_de(r.content))
        if r.stop_reason == "refusal":
            recusa = " [triste] Desculpe, com isso eu não posso ajudar."
            if saida is not None:
                saida.texto(recusa)
            return " ".join(completo) + recusa
        if r.stop_reason == "pause_turn":  # busca na web longa: continua
            if saida is not None and completo[-1].strip():
                saida.texto("\n")
            mensagens.append({"role": "assistant", "content": _eco(r.content)})
            continue
        usos = [b for b in r.content if getattr(b, "type", None) == "tool_use"]
        if r.stop_reason != "tool_use" or not usos:  # fim normal (ou max_tokens: não roda ferramenta cortada)
            return " ".join(c.strip() for c in completo if c.strip())
        if any(b.name == "chamar_modelo_forte" for b in usos) and tipo_modelo == "rapido":
            raise _TrocarModelo()
        if saida is not None and completo[-1].strip():
            saida.texto("\n")  # fecha a frase: ela fala o "deixa eu ver" enquanto a ferramenta trabalha
        resultados = []
        for b in usos:
            if ficha is not None and ficha.cancelado:
                raise Cancelado()
            args = b.input if isinstance(b.input, dict) else {}
            conteudo = ferramentas.executar(b.name, args)
            resultados.append({"type": "tool_result", "tool_use_id": b.id, "content": conteudo})
        mensagens.append({"role": "assistant", "content": _eco(r.content)})
        mensagens.append({"role": "user", "content": resultados})
    if "".join(completo).strip():
        return " ".join(c.strip() for c in completo if c.strip())
    enrolei = "[pensativa] Me enrolei um pouco aqui. Pode repetir de outro jeito?"
    if saida is not None:
        saida.texto(enrolei)
    return enrolei


# =====================================================================
# 5. Local (Ollama)
# =====================================================================
def ollama_disponivel() -> bool:
    try:
        return httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=1.5).status_code == 200
    except Exception:
        return False


def perguntar_ollama(texto: str, falante=None, saida=None, ficha=None, sem_nome: bool = False,
                     origem: str = "pc", troca_privada: bool = False) -> str:
    sistema = personalidade.sistema_base() + "\n\n" + _prompt_contexto(falante, sem_nome, "rapido", origem,
                                                                        troca_privada) + \
        "\n- Você está sem internet agora, usando o cérebro local: não tem ferramentas, só conversa."
    mensagens = [{"role": "system", "content": sistema}] + memoria.historico() + [{"role": "user", "content": texto}]
    partes = []
    with httpx.stream("POST", f"{config.OLLAMA_URL}/api/chat", timeout=90,
                      json={"model": config.OLLAMA_MODELO, "messages": mensagens, "stream": True}) as r:
        r.raise_for_status()
        for linha in r.iter_lines():
            if ficha is not None and ficha.cancelado:
                raise Cancelado()
            if not linha.strip():
                continue
            try:
                dado = json.loads(linha)
            except ValueError:
                continue
            pedaco = (dado.get("message") or {}).get("content", "")
            if pedaco:
                partes.append(pedaco)
                if saida is not None:
                    saida.texto(pedaco)
            if dado.get("done"):
                break
    return "".join(partes).strip()


# =====================================================================
# Ponto de entrada
# =====================================================================
def separar_emocao(texto: str) -> tuple[str, str]:
    m = re.match(r"^\s*\[(\w+)\]\s*", texto)
    emocao = "neutra"
    if m and m.group(1).lower() in EMOCOES:
        emocao = m.group(1).lower()
        texto = texto[m.end():]
    texto = re.sub(r"\[(?:%s)\]" % "|".join(EMOCOES), "", texto)  # etiquetas soltas no meio
    texto = re.sub(r"[*#_`]+", "", texto).strip()  # restos de markdown
    return texto, emocao


class _SaidaComFiltro:
    """Segura o começo da resposta até saber se é [ignorar] (conversa sem o nome)."""

    def __init__(self, saida, filtrar: bool):
        self.saida = saida
        self.filtrar = filtrar
        self.buffer = ""
        self.liberado = not filtrar
        self.ignorado = False

    def texto(self, delta: str) -> None:
        if self.ignorado:
            return
        if self.liberado:
            if self.saida is not None:
                self.saida.texto(delta)
            return
        self.buffer += delta
        limpo = self.buffer.lstrip().lower()
        if limpo.startswith(IGNORAR):
            self.ignorado = True
        elif len(limpo) >= len(IGNORAR) or (limpo and not IGNORAR.startswith(limpo[:len(IGNORAR)])):
            self.liberado = True
            if self.saida is not None:
                self.saida.texto(self.buffer)


def _motivo_falha(e: Exception) -> str:
    """Frase curta, para falar em voz alta, explicando por que o Claude não respondeu."""
    import anthropic

    detalhe = str(getattr(e, "message", "") or e).lower()
    if "credit balance" in detalhe or "billing" in detalhe:
        return "Os créditos da conta da Anthropic acabaram. Dá para recarregar no console da Anthropic."
    if isinstance(e, anthropic.RateLimitError):
        return "Bati no limite de pedidos da conta do Claude. Tente de novo em um minuto."
    if isinstance(e, (anthropic.InternalServerError, anthropic.OverloadedError)) or \
            getattr(e, "status_code", 0) in (500, 502, 503, 529):
        return "Os servidores do Claude estão sobrecarregados agora. Tente de novo daqui a pouco."
    if isinstance(e, anthropic.NotFoundError):
        return "O modelo do Claude configurado não foi encontrado. Confira o nome do modelo no painel."
    if isinstance(e, anthropic.PermissionDeniedError):
        return "A chave da Anthropic não tem permissão para esse modelo. Confira no painel."
    return "O Claude deu um erro agora e não consegui responder. Tente de novo; se continuar, rode o diagnóstico."


def pensar(texto: str, falante=None, saida=None, ficha=None, sem_nome: bool = False, origem: str = "pc",
           troca_privada: bool = False) -> dict:
    """Responde um pedido. O texto vai sendo entregue a `saida` (o Locutor) enquanto é gerado."""
    texto = texto.strip()
    if not texto:
        return resposta("Não ouvi nada.", "local")

    rapida = roteador_local(texto, sem_nome=sem_nome)
    if rapida:
        if saida is not None:
            saida.emocao(rapida["emocao"])
            saida.texto(rapida["texto"])
        return rapida

    filtro = _SaidaComFiltro(saida, filtrar=sem_nome)
    bruto, origem_resp, modelo_usado, falha = None, None, None, None
    if config.ANTHROPIC_API_KEY:
        import anthropic

        modelo, tipo = modelo_para(texto)
        for _ in range(2):
            try:
                bruto = perguntar_claude(texto, falante, filtro, ficha, sem_nome, origem, modelo, tipo, troca_privada)
                origem_resp, modelo_usado = "nuvem", modelo
                estado.definir_offline(False)
                break
            except _TrocarModelo:
                modelo, tipo = config.CLAUDE_MODELO_FORTE, "forte"
                eventos.publicar({"tipo": "status", "texto": "pensando melhor…"})
                continue
            except Cancelado:
                raise
            except anthropic.AuthenticationError:
                msg = "A chave da API da Anthropic foi recusada. Confira no painel de configurações."
                if saida is not None:
                    saida.emocao("triste")
                    saida.texto(msg)
                return resposta(msg, "erro", "triste")
            except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
                print(f"[cerebro] sem conexão com o Claude: {e}")
                estado.definir_offline(True)
                break
            except Exception as e:
                print(f"[cerebro] Claude falhou: {e!r}")
                falha = _motivo_falha(e)
                break
    if bruto is None and ollama_disponivel():
        try:
            bruto, origem_resp = perguntar_ollama(texto, falante, filtro, ficha, sem_nome, origem,
                                                  troca_privada), "local-ia"
        except Cancelado:
            raise
        except Exception as e:
            print(f"[cerebro] Ollama falhou: {e}")
    if bruto is None:
        if estado.offline:
            msg = ("Estou sem internet e sem o cérebro local agora. Consigo fazer o básico: hora, timers, música e "
                   "volume.")
        elif falha:
            msg = falha
        elif not config.ANTHROPIC_API_KEY:
            msg = "Estou sem cérebro na nuvem e sem modelo local agora. Coloque a chave da API no painel ou abra o Ollama."
        else:
            msg = "Não consegui pensar numa resposta agora. Tente de novo."
        if filtro.liberado:
            msg = "… Desculpa, perdi o fio no meio da resposta. " + msg
        if saida is not None:
            saida.emocao("triste")
            saida.texto(msg)
        return resposta(msg, "erro", "triste")
    if filtro.ignorado or bruto.strip().lower().startswith(IGNORAR):
        return resposta("", origem_resp, "neutra", ignorado=True)
    if not filtro.liberado and filtro.buffer and saida is not None:
        saida.texto(filtro.buffer)  # resposta curtinha que ficou presa no filtro
    falado, emocao = separar_emocao(bruto)
    return resposta(falado, origem_resp, emocao, modelo=modelo_usado)
