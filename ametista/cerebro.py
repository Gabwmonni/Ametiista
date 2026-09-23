"""Cérebro híbrido da Ametista.

Ordem de decisão:
  1. Roteador local (instantâneo, offline): hora, data, timers, clima, luzes simples.
  2. Claude na nuvem, com ferramentas e busca na web.
  3. Ollama local, se a nuvem falhar ou não houver chave.
"""
import re
import unicodedata
from datetime import datetime

import httpx

from . import config, ferramentas, memoria, spotify

EMOCOES = ("neutra", "feliz", "pensativa", "surpresa", "triste", "brava")
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
NUMEROS = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
    "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "quinze": 15, "vinte": 20, "trinta": 30,
    "quarenta": 40, "quarenta e cinco": 45, "cinquenta": 50, "sessenta": 60, "noventa": 90,
}


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w\s:.,]", " ", t).strip()


def resposta(texto: str, origem: str, emocao: str = "neutra") -> dict:
    return {"texto": texto, "origem": origem, "emocao": emocao}


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


def roteador_local(texto: str) -> dict | None:
    t = normalizar(texto)

    # Hora
    if re.search(r"\b(que horas|qual a hora|horas sao|me diz a hora)\b", t):
        agora = datetime.now()
        return resposta(f"São {agora:%H:%M}.", "local")

    # Data
    if re.search(r"\b(que dia e hoje|qual a data|data de hoje|que dia e amanha)\b", t):
        h = datetime.now()
        return resposta(f"Hoje é {DIAS[h.weekday()]}, {h.day} de {MESES[h.month - 1]} de {h.year}.", "local")

    # Meia hora
    if re.search(r"\b(timer|temporizador|me avisa|daqui a)\b.*\bmeia hora\b", t) and _pode("criar_timer"):
        return resposta(ferramentas.criar_timer(30, "Timer de meia hora"), "local", "feliz")

    # Timers
    m = _RE_TIMER.search(t)
    if m and not re.search(r"\b(as|para as|amanha)\b\s*\d", t) and _pode("criar_timer"):
        valor = _numero(m.group(1))
        if valor:
            unidade = m.group(2)
            minutos = valor / 60 if unidade.startswith("s") else valor * 60 if unidade.startswith("h") else valor
            # "me lembra de tirar o bolo daqui a 10 minutos" -> guarda o pedido como descrição
            descricao = re.sub(r"\b(me (avisa|avise|chama|lembra|lembre)|avisa me|daqui a|em)\b", " ", texto,
                               flags=re.I)
            descricao = re.sub(r"\b(de |para |pra )?\S+\s+(segundos?|minutos?|min|horas?|h)\b", " ", descricao,
                               flags=re.I)
            descricao = re.sub(r"^\s*(de|para|pra)\s+", "", re.sub(r"\s+", " ", descricao)).strip(" ,.?!")
            if re.match(r"^(timer|temporizador|cron[oô]metro|contagem)", descricao, re.I) or len(descricao) < 3:
                descricao = "Timer"
            return resposta(ferramentas.criar_timer(minutos, descricao), "local", "feliz")

    # Clima simples
    if re.search(r"\b(como (esta|ta) o tempo|previsao do tempo|vai chover|temperatura (agora|hoje|la fora))\b", t):
        try:
            linhas = ferramentas.clima(1).split("\n")
            return resposta(" ".join(linhas[:2]), "local")
        except Exception:
            return None  # deixa a nuvem tentar

    # Música, volume e programas
    r = _rota_pc_musica(t, texto)
    if r:
        return r

    # Luzes / tomadas simples: "acende a luz da sala", "desliga o ventilador"
    m = re.match(r"^(liga|ligar|acende|acender|desliga|desligar|apaga|apagar)\s+(?:a |o |as |os )?(.+)$", t)
    if m and ferramentas.casa_configurada() and _pode("casa_controlar"):
        ligar = m.group(1).startswith(("liga", "acend"))
        alvo = m.group(2)
        alvo = re.sub(r"^(luz|luzes|lampada)\s+(da|do|de)\s+", "", alvo).strip()
        try:
            achado = _achar_dispositivo(alvo)
        except Exception:
            achado = None
        if achado:
            ferramentas.casa_controlar(achado[0], "ligar" if ligar else "desligar")
            return resposta(f"{'Ligado' if ligar else 'Desligado'}: {achado[1]}.", "local", "feliz")

    return None


def _pode(ferramenta: str) -> bool:
    from .identidade import permitido

    return permitido(ferramenta)


NEGADO = "Desculpe, isso eu só faço para quem tem permissão."


def _executar_local(funcao, *args, emocao="feliz", ferramenta: str = "") -> dict:
    if ferramenta and not _pode(ferramenta):
        return resposta(NEGADO, "local", "neutra")
    try:
        return resposta(funcao(*args), "local", emocao)
    except Exception as e:
        return resposta(str(e) if isinstance(e, RuntimeError) else f"Não consegui: {e}", "local", "triste")


def _rota_pc_musica(t: str, original: str) -> dict | None:
    from . import pc, spotify

    tem_spotify = spotify.conectado()
    t = re.sub(r"[.,!?]+$", "", t).strip()

    # --- controles de música (Spotify se conectado, senão teclas de mídia)
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
                return _executar_local(spotify.controle, acao_sp, ferramenta="spotify_controle")
            return _executar_local(pc.midia, acao_pc, ferramenta="pc_midia")

    if tem_spotify:
        if re.match(r"^(que musica e essa|qual musica (e essa|ta tocando|esta tocando)|o que (ta|esta) tocando)$", t):
            return _executar_local(spotify.tocando, emocao="neutra", ferramenta="spotify_tocando")
        if re.match(r"^(curte|curtir|salva) (essa|a) musica$", t):
            return _executar_local(spotify.curtir, ferramenta="spotify_curtir")

    # --- volume do PC
    m = re.match(r"^(aumenta|sobe|aumentar) o (volume|som)( um pouco| bastante| muito)?$", t)
    if m:
        return _executar_local(pc.volume, "aumentar", 20 if (m.group(3) or "").strip() in ("bastante", "muito") else 10, ferramenta="pc_volume")
    m = re.match(r"^(abaixa|diminui|baixa|diminuir|abaixar) o (volume|som)( um pouco| bastante| muito)?$", t)
    if m:
        return _executar_local(pc.volume, "diminuir", 20 if (m.group(3) or "").strip() in ("bastante", "muito") else 10, ferramenta="pc_volume")
    m = re.match(r"^(coloca |poe |deixa )?(o )?volume (em|no|para|pra|a)? ?(\d{1,3})( por cento|%)?$", t)
    if m:
        return _executar_local(pc.volume, "definir", int(m.group(4)), ferramenta="pc_volume")
    if re.match(r"^(muta|mutar|silencia|tira o som)( o pc| o som| tudo)?$", t):
        return _executar_local(pc.volume, "mudo", ferramenta="pc_volume")
    if re.match(r"^(desmuta|volta o som|liga o som)$", t):
        return _executar_local(pc.volume, "som", ferramenta="pc_volume")

    # --- abrir programas/sites
    m = re.match(r"^(abre|abrir|abra|inicia|executa)\s+(.+)$", t)
    if m and len(m.group(2).split()) <= 5:
        orig = re.sub(r"[.,!?]+$", "", original.strip())
        return _executar_local(pc.abrir, re.sub(r"^\S+\s+", "", orig, count=1), emocao="neutra",
                               ferramenta="pc_abrir")

    # --- sistema
    if re.match(r"^(bloqueia|trava|bloquear)( o pc| o computador| a tela)?$", t):
        return _executar_local(pc.sistema, "bloquear", emocao="neutra", ferramenta="pc_sistema")
    if re.match(r"^(minimiza tudo|mostra a area de trabalho|limpa a tela)$", t):
        return _executar_local(pc.sistema, "minimizar_tudo", emocao="neutra", ferramenta="pc_sistema")
    if re.match(r"^cancela (o )?desligamento$", t):
        return _executar_local(pc.sistema, "cancelar_desligamento", emocao="neutra", ferramenta="pc_sistema")
    # --- tocar no Spotify (por último: "coloca o volume em 50" não é música)
    m = re.match(r"^(toca|tocar|coloca|bota|poe|reproduz)\s+(.+)$", t)
    if m and tem_spotify:
        if not _pode("spotify_tocar"):
            return resposta(NEGADO, "local", "neutra")
        orig = re.sub(r"[.,!?]+$", "", original.strip())  # mantém acentos e maiúsculas
        busca = re.sub(r"^\S+\s+", "", orig, count=1)
        try:
            return resposta(spotify.tocar(busca), "local", "feliz")
        except RuntimeError as e:
            if "Não encontrei" in str(e):
                return None  # a nuvem tenta entender melhor (ex.: nome mal transcrito)
            return resposta(str(e), "local", "triste")
        except Exception as e:
            return resposta(f"O Spotify deu erro: {e}", "local", "triste")
    return None


def _achar_dispositivo(alvo: str) -> tuple[str, str] | None:
    linhas = ferramentas.casa_listar().split("\n")
    candidatos = []
    for linha in linhas:
        partes = [p.strip() for p in linha.split("|")]
        if len(partes) < 2:
            continue
        eid, nome = partes[0], partes[1]
        if normalizar(alvo) in normalizar(nome) or normalizar(alvo).replace(" ", "_") in eid:
            candidatos.append((eid, nome))
    # Só age sozinho se não houver ambiguidade
    return candidatos[0] if len(candidatos) == 1 else None


# =====================================================================
# 2. Nuvem (Claude)
# =====================================================================
def _contexto_falante(falante) -> str:
    if falante is None or falante.nivel == "dono":
        return f"Quem está falando agora: {config.DONO} (o dono, pode tudo)."
    quem = falante.nome or "uma pessoa que você não conhece"
    return (f"Quem está falando agora: {quem} (nível {falante.nivel}), NÃO é {config.DONO}. Seja simpática, "
            f"trate pelo nome, mas não revele nada pessoal do {config.DONO} (agenda, memórias, tela). "
            "Se pedirem algo que suas ferramentas não permitem, explique com gentileza que só o dono pode.")


def _prompt_sistema(falante=None) -> str:
    from . import agenda, pc, steam

    agora = datetime.now()
    eh_dono = falante is None or falante.nivel == "dono"
    fatos = memoria.fatos() if eh_dono else []
    lista_fatos = "\n".join(f"- {f}" for f in fatos) if fatos else "(nada ainda)"
    janela = pc.janela_ativa_texto() if eh_dono else ""
    casa = "Há um Home Assistant conectado." if ferramentas.casa_configurada() else \
        "A automação residencial ainda não foi configurada."
    return f"""Você é {config.NOME}, uma assistente de voz caseira, criada por {config.DONO} (o projeto Ametista).
Você tem um rosto animado numa tela e fala em voz alta.

Personalidade: calorosa, esperta, bem-humorada na medida certa, direta. Fala português do Brasil natural.

Regras de fala (MUITO importante, tudo vira áudio):
- Respostas curtas: 1 a 3 frases, a menos que peçam detalhes.
- Nada de markdown, listas, emojis, asteriscos ou links. Escreva como se fala.
- Números e horários de forma falada natural (ex.: "às três e meia").
- Comece SEMPRE com uma etiqueta de emoção para o rosto: [neutra], [feliz], [pensativa], [surpresa], [triste] ou [brava].

Contexto:
- Agora: {DIAS[agora.weekday()]}, {agora:%d/%m/%Y %H:%M}. Cidade: {config.CIDADE}.
- {casa}
- {_contexto_falante(falante)}
- {janela or "Janela em foco no PC: (desconhecida)"}
- O que você sabe sobre {config.DONO}:
{lista_fatos}

Você mora no PC de {config.DONO} (Windows), como uma camada por cima da tela, e controla o computador:
volume, teclas de mídia, abrir e fechar programas, sites e pastas, pesquisar, bloquear, ver a tela (print),
área de transferência, digitar texto{", e o Spotify Premium dele" if spotify.configurado() else ""}.
Quando ele perguntar sobre algo que está na tela ("que erro é esse?", "resume isso"), use pc_ver_tela.
Antes de desligar, reiniciar, suspender ou fechar programas com trabalho aberto, pergunte e espere o "sim".
Depois de uma ação simples, confirme em poucas palavras ("Pronto!", "Tocando Coldplay.").

{steam.INSTRUCOES if steam.disponivel() else ""}
{agenda.INSTRUCOES if agenda.configurada() else ""}
Voz das pessoas: você reconhece quem fala pela voz. O dono pode cadastrar vozes (pessoas_cadastrar),
listar, remover e mudar o nível delas.

Use as ferramentas quando precisar (clima, notícias, lembretes, timers, memória, casa, busca na web).
Quando {config.DONO} contar algo duradouro sobre si ou pedir para lembrar, use lembrar_fato."""


_cliente = None


def _claude():
    global _cliente
    if _cliente is None:
        import anthropic
        _cliente = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _cliente


def perguntar_claude(texto: str, falante=None) -> str:
    cliente = _claude()
    mensagens = memoria.historico() + [{"role": "user", "content": texto}]
    ferramentas_api = ferramentas.definicoes_permitidas() + [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 3,
         "user_location": {"type": "approximate", "country": "BR", "city": config.CIDADE,
                           "timezone": "America/Sao_Paulo"}}
    ]
    sistema = _prompt_sistema(falante)
    for _ in range(8):  # limite de rodadas de ferramentas
        r = cliente.messages.create(
            model=config.CLAUDE_MODELO, max_tokens=900, system=sistema,
            tools=ferramentas_api, messages=mensagens,
        )
        mensagens.append({"role": "assistant", "content": r.content})
        if r.stop_reason == "tool_use":
            resultados = [
                {"type": "tool_result", "tool_use_id": b.id, "content": ferramentas.executar(b.name, b.input)}
                for b in r.content if b.type == "tool_use"
            ]
            mensagens.append({"role": "user", "content": resultados})
            continue
        if r.stop_reason == "pause_turn":  # busca na web longa: continua
            continue
        return "".join(b.text for b in r.content if b.type == "text").strip()
    return "[pensativa] Me enrolei um pouco aqui. Pode repetir de outro jeito?"


# =====================================================================
# 3. Local (Ollama)
# =====================================================================
def ollama_disponivel() -> bool:
    try:
        return httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=1.5).status_code == 200
    except Exception:
        return False


def perguntar_ollama(texto: str, falante=None) -> str:
    mensagens = [{"role": "system", "content": _prompt_sistema(falante)}] + memoria.historico() + \
                [{"role": "user", "content": texto}]
    r = httpx.post(f"{config.OLLAMA_URL}/api/chat", timeout=90,
                   json={"model": config.OLLAMA_MODELO, "messages": mensagens, "stream": False})
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


# =====================================================================
# Ponto de entrada
# =====================================================================
def _separar_emocao(texto: str) -> tuple[str, str]:
    m = re.match(r"^\s*\[(\w+)\]\s*", texto)
    emocao = "neutra"
    if m and m.group(1).lower() in EMOCOES:
        emocao = m.group(1).lower()
        texto = texto[m.end():]
    texto = re.sub(r"\[(?:%s)\]" % "|".join(EMOCOES), "", texto)  # etiquetas soltas no meio
    texto = re.sub(r"[*#_`]+", "", texto).strip()  # restos de markdown
    return texto, emocao


def pensar(texto: str, falante=None) -> dict:
    texto = texto.strip()
    if not texto:
        return resposta("Não ouvi nada.", "local")

    rapida = roteador_local(texto)
    if rapida:
        memoria.adicionar_historico("user", texto)
        memoria.adicionar_historico("assistant", rapida["texto"])
        return rapida

    bruto, origem = None, None
    if config.ANTHROPIC_API_KEY:
        try:
            bruto, origem = perguntar_claude(texto, falante), "nuvem"
        except Exception as e:
            print(f"[cerebro] Claude falhou: {e}")
    if bruto is None and ollama_disponivel():
        try:
            bruto, origem = perguntar_ollama(texto, falante), "local-ia"
        except Exception as e:
            print(f"[cerebro] Ollama falhou: {e}")
    if bruto is None:
        return resposta("Estou sem cérebro na nuvem e sem modelo local agora. "
                        "Confira a chave da API ou se o Ollama está aberto.", "erro", "triste")

    falado, emocao = _separar_emocao(bruto)
    memoria.adicionar_historico("user", texto)
    memoria.adicionar_historico("assistant", falado)
    return resposta(falado, origem, emocao)
