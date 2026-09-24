"""Tudo o que a Ametista FAZ passa por aqui.

1. Permissão: quem pediu pode usar essa ferramenta? (dono, família, visitante)
2. Risco da ação:
     livre      -> faz na hora (abrir programa, volume, música...)
     confirmar  -> pergunta antes (fechar programa, cancelar compromisso, instalar jogo reiniciando a Steam)
     critica    -> pergunta antes, só o dono, nunca sozinha numa rotina automática (desligar o PC...)
   A confirmação é resolvida AQUI, pelo sistema, com a resposta falada do usuário ("sim", "pode").
   A IA não consegue pular essa etapa: mesmo que ela peça de novo, a ação fica esperando o "sim".
3. Registro legível: o quê, quando, quem pediu, por quê (o pedido), resultado e como desfazer.
"""
import json
import re
import threading
import time
import unicodedata
from datetime import datetime

from . import eventos

LIVRE, CONFIRMAR, CRITICA = "livre", "confirmar", "critica"
# resultados de ferramenta que significam "não deu certo"
FALHAS = ("NEGADO", "Erro", "PRECISA CONFIRMAR", "PULADO", "Não consegui", "Não achei", "Não encontrei",
          "Ação desconhecida", "Ferramenta desconhecida")
VALIDADE_CONFIRMACAO = 90          # segundos para responder "sim"
VALIDADE_CRITICA = 45

_trava = threading.RLock()
_pendente: dict | None = None
_tabela_pronta = False


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower())
    return re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


# ====================================================================== risco
def _risco_pc_sistema(a: dict) -> str:
    return CRITICA if a.get("acao") in ("desligar", "reiniciar", "suspender") else LIVRE


def _risco_steam(a: dict) -> str:
    from . import steam

    try:
        precisa = steam.precisa_reiniciar_para(a.get("unidade", ""), int(a.get("appid", 0)))
    except Exception:
        precisa = False
    return CONFIRMAR if precisa else LIVRE


def _risco_arquivo(a: dict) -> str:
    from .arquivos import EXECUTAVEIS

    caminho = str(a.get("caminho", "")).lower()
    return CONFIRMAR if any(caminho.endswith(e) for e in EXECUTAVEIS) else LIVRE


def _risco_casa(a: dict) -> str:
    dominio = str(a.get("entity_id", "")).split(".", 1)[0]
    return CRITICA if dominio in ("lock", "alarm_control_panel") else LIVRE


def _risco_teclado(a: dict) -> str:
    """Digitar/apertar teclas num terminal ou na caixa Executar roda comandos: pede confirmação."""
    from . import controle

    if a.get("teclas") and controle.atalho_de_comando(a["teclas"]):
        return CONFIRMAR
    return CONFIRMAR if controle.janela_de_comando() else LIVRE


RISCO = {
    "pc_sistema": _risco_pc_sistema,
    "pc_digitar": _risco_teclado,
    "pc_teclas": _risco_teclado,
    "pc_fechar": CONFIRMAR,
    "steam_instalar": _risco_steam,
    "arquivo_abrir": _risco_arquivo,
    "casa_controlar": _risco_casa,
    "agenda_cancelar": CONFIRMAR,
    "pessoas_remover": CONFIRMAR,
    "pessoas_nivel": CONFIRMAR,
    "rotina_apagar": CONFIRMAR,
    "caderno_apagar": CONFIRMAR,
    "memoria_apagar_conversas": CRITICA,
}
# parâmetro que a função recebe quando a pessoa confirmou (a IA não vê esses parâmetros)
ARG_CONFIRMACAO = {"pc_sistema": "confirmado", "steam_instalar": "confirmado_reiniciar"}


def risco(nome: str, args: dict) -> str:
    r = RISCO.get(nome, LIVRE)
    return r(args) if callable(r) else r


def pergunta_padrao(nome: str, args: dict) -> str:
    """Pergunta usada quando não há IA no meio (rotinas, comandos locais)."""
    if nome == "pc_sistema":
        verbo = {"desligar": "desligar", "reiniciar": "reiniciar", "suspender": "suspender"}.get(args.get("acao"), "")
        return f"Posso {verbo} o PC?"
    if nome == "pc_fechar":
        return f"Posso fechar o {args.get('programa', 'programa')}? Se tiver algo sem salvar, pode perder."
    if nome == "steam_instalar":
        return "Para instalar nessa unidade, a Steam precisa reiniciar e fechar o que estiver aberto nela. Posso?"
    if nome == "agenda_cancelar":
        return "Posso cancelar esse compromisso?"
    if nome == "arquivo_abrir":
        return "Esse arquivo é um programa. Quer mesmo que eu abra?"
    if nome in ("pc_digitar", "pc_teclas"):
        from . import controle

        if nome == "pc_teclas" and controle.atalho_de_comando(args.get("teclas", "")):
            return f"O atalho {args.get('teclas')} abre um lugar onde dá para rodar comandos no PC. Posso?"
        lugar = controle.janela_de_comando() or "terminal"
        if nome == "pc_digitar":
            texto = str(args.get("texto", "")).strip()
            texto = texto if len(texto) <= 60 else texto[:57] + "…"
            return f"A janela da frente é um {lugar}: o que eu digitar vira comando. Posso digitar “{texto}”?"
        return f"A janela da frente é um {lugar}. Posso apertar {args.get('teclas')}?"
    return f"Posso fazer isso ({descrever(nome, args)})?"


# ====================================================================== descrição legível
def descrever(nome: str, a: dict) -> str:
    g = a.get
    d = {
        "pc_volume": lambda: {"mudo": "Mutou o som do PC", "som": "Voltou o som do PC"}.get(
            g("acao"), f"Volume do PC: {g('acao')} {g('valor', '')}".strip()),
        "pc_midia": lambda: {"tocar_pausar": "Pausou/continuou a mídia", "proxima": "Pulou para a próxima",
                             "anterior": "Voltou para a anterior", "parar": "Parou a mídia"}.get(g("acao"), "Mídia"),
        "pc_abrir": lambda: f"Abriu {g('alvo')}",
        "pc_fechar": lambda: f"Fechou {g('programa')}",
        "pc_pesquisar": lambda: f"Pesquisou \"{g('consulta')}\" no {g('onde', 'google')}",
        "pc_sistema": lambda: {"bloquear": "Bloqueou o PC", "minimizar_tudo": "Minimizou as janelas",
                               "desligar": "Desligou o PC", "reiniciar": "Reiniciou o PC",
                               "suspender": "Suspendeu o PC",
                               "cancelar_desligamento": "Cancelou o desligamento"}.get(g("acao"), "Sistema"),
        "pc_ver_tela": lambda: "Olhou a tela",
        "pc_digitar": lambda: f"Digitou um texto ({len(str(g('texto', '')))} letras)",
        "pc_teclas": lambda: f"Apertou {g('teclas')}",
        "pc_clicar": lambda: f"Clicou em ({g('x')}, {g('y')})",
        "pc_janela": lambda: f"Janela: {g('acao')} {g('alvo', '') or 'a janela da frente'}".strip(),
        "pc_apontar": lambda: f"Mostrou onde clicar: {g('rotulo', '')}".strip(),
        "pc_area_transferencia": lambda: "Leu a área de transferência" if g("acao") == "ler"
        else "Copiou um texto",
        "criar_timer": lambda: f"Criou timer de {g('minutos')} min: {g('descricao', 'Timer')}",
        "criar_lembrete": lambda: f"Criou lembrete: {g('texto')}",
        "lembrete_recorrente": lambda: f"Criou lembrete recorrente: {g('texto')}",
        "lembrete_condicao": lambda: f"Criou lembrete ({g('condicao')}): {g('texto')}",
        "aniversario_adicionar": lambda: f"Anotou o aniversário de {g('nome')}",
        "cancelar_lembrete": lambda: "Cancelou um lembrete",
        "lembrar_fato": lambda: f"Guardou na memória: {g('fato')}",
        "esquecer_fato": lambda: f"Esqueceu: {g('trecho')}",
        "caderno_guardar": lambda: f"Anotou no caderno: {g('nome')}",
        "caderno_apagar": lambda: f"Apagou do caderno: {g('nome')}",
        "agenda_criar": lambda: f"Marcou na agenda: {g('titulo')}",
        "agenda_alterar": lambda: "Alterou um compromisso",
        "agenda_cancelar": lambda: "Cancelou um compromisso",
        "casa_controlar": lambda: f"Casa: {g('acao')} {g('entity_id')}",
        "spotify_tocar": lambda: f"Tocou {g('busca')} no Spotify",
        "spotify_controle": lambda: f"Spotify: {g('acao')}",
        "spotify_volume": lambda: f"Volume do Spotify em {g('percentual')}%",
        "steam_instalar": lambda: f"Instalou o jogo {g('appid')} em {g('unidade')}",
        "rotina_executar": lambda: f"Rotina: {g('nome')}",
        "agente_iniciar": lambda: f"Tarefa: {g('objetivo')}",
        "nao_perturbe": lambda: f"Não perturbe por {g('minutos')} min" if g("minutos") else "Desligou o não perturbe",
        "arquivo_abrir": lambda: f"Abriu o arquivo {str(g('caminho', '')).replace(chr(92), '/').rsplit('/', 1)[-1]}",
    }.get(nome)
    try:
        return d() if d else f"{nome} {json.dumps(a, ensure_ascii=False)[:80]}"
    except Exception:
        return nome


# ====================================================================== desfazer
def _id_lembrete(resultado: str) -> str | None:
    m = re.search(r"\(id ([0-9a-f]{8})\)", resultado or "")
    return m.group(1) if m else None


def _preparar_desfazer(nome: str, a: dict) -> dict | None:
    """Guarda o estado de antes, para poder desfazer depois."""
    try:
        if nome == "pc_volume":
            from . import pc

            v = pc.volume_atual()
            return {"volume": v} if v is not None else None
        if nome == "spotify_volume":
            from . import spotify

            atual = spotify.cliente().current_playback() or {}
            v = (atual.get("device") or {}).get("volume_percent")
            return {"volume": v} if v is not None else None
        if nome == "casa_controlar":
            from . import ferramentas

            return ferramentas.casa_estado(a["entity_id"])
        if nome in ("agenda_alterar", "agenda_cancelar"):
            from . import agenda

            return {"evento": agenda.obter(a["id"])}
        if nome == "cancelar_lembrete":
            from . import memoria

            item = memoria.obter_lembrete(a.get("id", ""))
            return {"item": item} if item else None
        if nome == "caderno_guardar":
            from . import memoria

            iguais = [i for i in memoria.caderno_listar() if i["nome"].lower() == str(a.get("nome", "")).lower()]
            return {"antes": iguais[0] if iguais else None}
        if nome == "nao_perturbe":
            from . import estado

            return {"ate": estado.nao_perturbe_ate()}
        if nome == "pc_janela":
            from . import controle

            return {"janela": controle.janela_alvo(a.get("alvo", ""))}
    except Exception as e:
        print(f"[acoes] não consegui preparar o desfazer de {nome}: {e}")
    return None


def _executar_desfazer(item: dict) -> str:
    nome, a = item["ferramenta"], item["args"]
    ctx = item.get("antes") or {}
    res = item.get("resultado") or ""
    if nome == "pc_volume" and ctx.get("volume") is not None:
        from . import pc

        return pc.volume("definir", int(ctx["volume"]))
    if nome == "spotify_volume" and ctx.get("volume") is not None:
        from . import spotify

        return spotify.volume(int(ctx["volume"]))
    if nome in ("criar_timer", "criar_lembrete", "lembrete_recorrente", "lembrete_condicao",
                "aniversario_adicionar"):
        from . import memoria

        i = _id_lembrete(res)
        return "Lembrete desfeito." if i and memoria.remover_lembrete(i) else "Esse lembrete já não existe."
    if nome == "cancelar_lembrete" and ctx.get("item"):
        from . import memoria

        l = ctx["item"]
        quando = datetime.fromisoformat(l["quando"]) if l.get("quando") else None
        memoria.criar_lembrete(l["texto"], quando, l["tipo"], l.get("recorrencia"), l.get("condicao"), l.get("grupo"))
        return "Lembrete de volta."
    if nome == "lembrar_fato":
        from . import memoria

        memoria.esquecer_fato_exato(a.get("fato", ""))
        return "Esqueci isso."
    if nome == "caderno_guardar":
        from . import memoria

        antes = ctx.get("antes")
        if antes:
            memoria.caderno_guardar(antes["nome"], antes["detalhes"], antes["categoria"])
            return "O caderno voltou como estava."
        memoria.caderno_apagar(a.get("nome", ""))
        return "Tirei do caderno."
    if nome == "agenda_criar":
        from . import agenda

        m = re.search(r"\[((?:g|m):[^\]]+)\]", res)
        return agenda.cancelar(m.group(1)) if m else "Não achei o compromisso criado."
    if nome == "agenda_alterar" and ctx.get("evento"):
        from . import agenda

        e = ctx["evento"]
        return agenda.alterar(a["id"], titulo=e["titulo"], inicio=e["inicio"], fim=e["fim"], local=e.get("local"))
    if nome == "agenda_cancelar" and ctx.get("evento"):
        from . import agenda

        e = ctx["evento"]
        return agenda.criar(e["titulo"], e["inicio"], fim=e["fim"], local=e.get("local") or "",
                            agenda=e.get("agenda", ""), dia_inteiro=e.get("dia_inteiro", False))
    if nome == "casa_controlar" and ctx.get("estado") in ("on", "off"):
        from . import ferramentas

        return ferramentas.casa_controlar(a["entity_id"], "ligar" if ctx["estado"] == "on" else "desligar",
                                          brilho=ctx.get("brilho"))
    if nome == "spotify_controle":
        from . import spotify

        inverso = {"pausar": "continuar", "continuar": "pausar", "proxima": "anterior",
                   "aleatorio_ligar": "aleatorio_desligar", "aleatorio_desligar": "aleatorio_ligar"}.get(a.get("acao"))
        if inverso:
            return spotify.controle(inverso)
    if nome == "pc_midia":
        from . import pc

        inverso = {"tocar_pausar": "tocar_pausar", "proxima": "anterior"}.get(a.get("acao"))
        if inverso:
            return pc.midia(inverso)
    if nome == "nao_perturbe":
        from . import estado

        ate = ctx.get("ate")
        estado.definir_nao_perturbe(datetime.fromisoformat(ate) if ate else None)
        return "Não perturbe como estava antes."
    if nome == "pc_janela" and ctx.get("janela") and a.get("acao") in ("minimizar", "maximizar"):
        from . import controle

        return controle.janela_acao("restaurar", hwnd=ctx["janela"])
    if nome == "pc_sistema" and a.get("acao") in ("desligar", "reiniciar"):
        from . import pc

        return pc.sistema("cancelar_desligamento")
    if nome == "rotina_executar":
        filhos = [f for f in listar(200) if f.get("grupo") == item.get("grupo_proprio")]
        saidas = [desfazer(f["id"]) for f in filhos if f.get("desfazivel") and not f.get("desfeito")]
        return "Desfiz a rotina." if saidas else "Essa rotina não tem nada para desfazer."
    raise RuntimeError("Essa ação não dá para desfazer.")


DESFAZIVEIS = {"pc_volume", "spotify_volume", "criar_timer", "criar_lembrete", "lembrete_recorrente",
               "lembrete_condicao", "aniversario_adicionar", "cancelar_lembrete", "lembrar_fato",
               "caderno_guardar", "agenda_criar", "agenda_alterar", "agenda_cancelar", "casa_controlar",
               "spotify_controle", "pc_midia", "nao_perturbe", "pc_janela", "rotina_executar", "pc_sistema"}


def _desfazivel(nome: str, a: dict, antes: dict | None, ok: bool) -> bool:
    if not ok or nome not in DESFAZIVEIS:
        return False
    if nome == "pc_sistema":
        return a.get("acao") in ("desligar", "reiniciar")
    if nome in ("pc_volume", "spotify_volume", "agenda_alterar", "agenda_cancelar", "cancelar_lembrete"):
        return bool(antes)
    if nome == "casa_controlar":
        return bool(antes) and antes.get("estado") in ("on", "off")
    if nome == "spotify_controle":
        return a.get("acao") in ("pausar", "continuar", "proxima", "aleatorio_ligar", "aleatorio_desligar")
    if nome == "pc_midia":
        return a.get("acao") in ("tocar_pausar", "proxima")
    if nome == "pc_janela":
        return bool(antes and antes.get("janela")) and a.get("acao") in ("minimizar", "maximizar")
    return True


# ====================================================================== registro
def _tabela():
    global _tabela_pronta
    from . import memoria

    con = memoria.db()
    if not _tabela_pronta:
        with memoria._trava:
            con.execute("""CREATE TABLE IF NOT EXISTS acoes(id INTEGER PRIMARY KEY, quando TEXT, quem TEXT,
                origem TEXT, ferramenta TEXT, args TEXT, descricao TEXT, motivo TEXT, resultado TEXT, ok INTEGER,
                antes TEXT, desfazivel INTEGER, desfeito INTEGER DEFAULT 0, grupo TEXT, grupo_proprio TEXT,
                troca INTEGER)""")
            con.commit()
        _tabela_pronta = True
    return con


def _linha(r) -> dict:
    d = dict(r)
    d["args"] = json.loads(d["args"] or "{}")
    d["antes"] = json.loads(d["antes"]) if d.get("antes") else None
    d["ok"], d["desfazivel"], d["desfeito"] = bool(d["ok"]), bool(d["desfazivel"]), bool(d["desfeito"])
    return d


def _args_para_log(a: dict) -> dict:
    saida = {}
    for k, v in a.items():
        if isinstance(v, str) and len(v) > 200:
            v = v[:200] + "…"
        saida[k] = v
    return saida


def registrar(nome: str, a: dict, resultado, ok: bool, antes: dict | None, *, quem: str = "", origem: str = "pc",
              motivo: str = "", grupo: str | None = None, grupo_proprio: str | None = None,
              troca: int | None = None) -> dict:
    from . import estado, memoria

    texto = resultado if isinstance(resultado, str) else (
        next((b.get("text", "") for b in resultado if isinstance(b, dict) and b.get("type") == "text"), "")
        if isinstance(resultado, list) else str(resultado))
    item = {"quando": datetime.now().isoformat(timespec="seconds"), "quem": quem, "origem": origem,
            "ferramenta": nome, "args": _args_para_log(a), "descricao": descrever(nome, a),
            "motivo": "" if estado.privado() else (motivo or "")[:300], "resultado": (texto or "")[:400], "ok": ok,
            "antes": antes, "desfazivel": _desfazivel(nome, a, antes, ok), "desfeito": False, "grupo": grupo,
            "grupo_proprio": grupo_proprio, "troca": troca}
    con = _tabela()
    with memoria._trava:
        cur = con.execute(
            "INSERT INTO acoes(quando, quem, origem, ferramenta, args, descricao, motivo, resultado, ok, antes, "
            "desfazivel, grupo, grupo_proprio, troca) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (item["quando"], quem, origem, nome, json.dumps(item["args"], ensure_ascii=False), item["descricao"],
             item["motivo"], item["resultado"], int(ok), json.dumps(antes, ensure_ascii=False, default=str)
             if antes else None, int(item["desfazivel"]), grupo, grupo_proprio, troca))
        con.execute("DELETE FROM acoes WHERE id <= (SELECT MAX(id) FROM acoes) - 5000")
        con.commit()
        item["id"] = cur.lastrowid
    eventos.publicar({"tipo": "acao", "acao": _publico(item)})
    return item


def _publico(item: dict) -> dict:
    return {k: item.get(k) for k in ("id", "quando", "quem", "origem", "descricao", "motivo", "resultado", "ok",
                                     "desfazivel", "desfeito", "ferramenta")}


def listar(limite: int = 50, somente_publico: bool = False) -> list[dict]:
    from . import memoria

    con = _tabela()
    with memoria._trava:
        linhas = con.execute("SELECT * FROM acoes ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
    itens = [_linha(r) for r in linhas]
    return [_publico(i) for i in itens] if somente_publico else itens


def obter(id_: int) -> dict | None:
    from . import memoria

    con = _tabela()
    with memoria._trava:
        r = con.execute("SELECT * FROM acoes WHERE id=?", (id_,)).fetchone()
    return _linha(r) if r else None


def desfazer(id_: int) -> str:
    from . import memoria

    item = obter(int(id_))
    if not item:
        return "Não achei essa ação."
    if item["desfeito"]:
        return "Essa ação já foi desfeita."
    if not item["desfazivel"]:
        return "Essa ação não dá para desfazer."
    try:
        texto = _executar_desfazer(item)
    except Exception as e:
        return f"Não consegui desfazer: {e}"
    con = _tabela()
    with memoria._trava:
        con.execute("UPDATE acoes SET desfeito=1 WHERE id=?", (item["id"],))
        con.commit()
    item["desfeito"] = True
    eventos.publicar({"tipo": "acao", "acao": _publico(item)})
    return texto


def desfazer_ultima() -> str:
    for item in listar(30):
        if item["grupo"]:  # parte de uma rotina: desfaz a rotina inteira
            continue
        if item["desfazivel"] and not item["desfeito"]:
            return desfazer(item["id"])
    return "Não achei nenhuma ação recente que dê para desfazer."


def ultima_repetivel() -> dict | None:
    for item in listar(15):
        if item["ok"] and item["ferramenta"] in ("pc_abrir", "spotify_tocar", "pc_pesquisar", "arquivo_abrir",
                                                  "rotina_executar", "casa_controlar", "pc_volume"):
            return item
    return None


def resumo_para_contexto(n: int = 8, minutos: int = 45) -> str:
    """As últimas ações, para entender "abre de novo", "não esse, o outro", "desfaz"."""
    agora = time.time()
    linhas = []
    for item in listar(n):
        quando = datetime.fromisoformat(item["quando"])
        if agora - quando.timestamp() > minutos * 60:
            break
        estado_txt = "ok" if item["ok"] else "falhou"
        if item["desfeito"]:
            estado_txt = "desfeita"
        linhas.append(f"- {quando:%H:%M} {item['descricao']} [{item['ferramenta']} "
                      f"{json.dumps(item['args'], ensure_ascii=False)[:120]}] -> {estado_txt}: "
                      f"{(item['resultado'] or '')[:90]}")
    return "\n".join(reversed(linhas))


# ====================================================================== execução
def executar(nome: str, args: dict, funcao, *, falante=None, origem: str = "pc", motivo: str = "",
             troca: int | None = None, confirmado: bool = False, grupo: str | None = None,
             automatico: bool = False, registrar_falha: bool = True):
    """Executa uma ferramenta passando por permissão, risco, registro e desfazer.

    automatico: pedido sem ninguém acompanhando (rotina agendada) -> ações críticas são puladas.
    registrar_falha=False: tentativa que, se falhar, segue por outro caminho (não suja o histórico)."""
    from . import identidade

    falante = falante or identidade.falante_atual.get()
    args = {k: v for k, v in (args or {}).items() if k != ARG_CONFIRMACAO.get(nome)}
    if not identidade.permitido(nome, falante):
        return f"NEGADO: {falante.nome or 'essa pessoa'} ({falante.nivel}) não tem permissão para isso."
    nivel = risco(nome, args)
    if nivel == CRITICA and falante.nivel != "dono":
        return "NEGADO: só o dono pode fazer isso."
    if nivel != LIVRE and not confirmado:
        if automatico and nivel == CRITICA:
            return "PULADO: ação crítica não roda sozinha numa rotina automática."
        criar_pendente(nome, args, funcao, nivel=nivel, falante=falante, origem=origem, motivo=motivo, troca=troca,
                       grupo=grupo)
        return (f"PRECISA CONFIRMAR ({nivel}): {pergunta_padrao(nome, args)} Pergunte isso ao usuário em uma frase "
                "curta e pare. Não chame a ferramenta de novo: o sistema executa sozinho quando ele disser sim.")
    chamada = dict(args)
    if confirmado and nome in ARG_CONFIRMACAO:
        chamada[ARG_CONFIRMACAO[nome]] = True
    antes = _preparar_desfazer(nome, args)
    grupo_proprio = f"r{int(time.time() * 1000)}" if nome == "rotina_executar" else None
    if grupo_proprio:
        chamada["_grupo"] = grupo_proprio
    ok = True
    try:
        resultado = funcao(**chamada)
    except TypeError as e:
        ok, resultado = False, f"Erro nos parâmetros de {nome}: {e}"
    except Exception as e:
        ok, resultado = False, f"Erro ao executar {nome}: {e}"
    if isinstance(resultado, str) and resultado.startswith(FALHAS):
        ok = False
    if nome not in ("pc_ver_tela", "listar_lembretes", "memoria_buscar", "caderno_buscar", "arquivos_buscar",
                    "pc_status", "clima", "noticias", "agenda_listar", "spotify_tocando", "pessoas_listar",
                    "steam_buscar_jogo", "steam_unidades", "steam_status", "rotina_listar", "casa_listar",
                    "spotify_aparelhos", "acoes_listar", "diagnostico", "tarefas_listar", "caderno_listar") \
            and (ok or registrar_falha):
        registrar(nome, args, resultado, ok, antes, quem=getattr(falante, "nome", "") or "",
                  origem=origem, motivo=motivo, grupo=grupo, grupo_proprio=grupo_proprio, troca=troca)
    return resultado


# ====================================================================== confirmações
_SIM = re.compile(r"^(sim|s|pode|podes|claro|confirmo|confirma|confirmado|isso|exato|manda|manda ver|faz|faca|"
                  r"vai|ok|okay|beleza|blz|com certeza|positivo|autorizo|autorizado|quero|por favor|certo|"
                  r"tudo bem|ta bom|pode sim|sim pode|pode ir|bora|yes)\b")
_NAO = re.compile(r"^(nao|n|negativo|cancela|cancelar|deixa|deixa pra la|esquece|nem|melhor nao|para|pare|"
                  r"nada|no|nope|agora nao|espera)\b")


def classificar_resposta(texto: str) -> str | None:
    t = _norm(texto)
    t = re.sub(r"^(ametista|ametista,)\s+", "", t)
    if not t:
        return None
    if _NAO.match(t) or re.search(r"\bnao (pode|quero|faz|faca)\b", t):
        return "nao"
    if _SIM.match(t) and len(t.split()) <= 8:
        return "sim"
    return None


def criar_pendente(nome: str, args: dict, funcao, *, nivel: str, falante=None, origem: str = "pc",
                   motivo: str = "", troca: int | None = None, grupo: str | None = None,
                   pergunta: str | None = None) -> dict:
    global _pendente
    with _trava:
        _pendente = {"tipo": "ferramenta", "nome": nome, "args": args, "funcao": funcao, "nivel": nivel,
                     "falante": falante, "origem": origem, "motivo": motivo, "troca": troca, "grupo": grupo,
                     "criado": time.time(), "pergunta": pergunta or pergunta_padrao(nome, args)}
        p = _pendente
    eventos.publicar({"tipo": "aguardando", "pergunta": p["pergunta"]})
    return p


def pendente() -> dict | None:
    global _pendente
    with _trava:
        p = _pendente
        if not p:
            return None
        validade = VALIDADE_CRITICA if p.get("nivel") == CRITICA else VALIDADE_CONFIRMACAO
        if time.time() - p["criado"] > validade:
            _pendente = None
            if p["tipo"] == "agente":
                p["resposta"] = "nao"
                p["evento"].set()
            eventos.publicar({"tipo": "aguardando_fim"})
            return None
        return p


def cancelar_pendente() -> None:
    global _pendente
    with _trava:
        p, _pendente = _pendente, None
    if p:
        if p["tipo"] == "agente":
            p["resposta"] = "nao"
            p["evento"].set()
        eventos.publicar({"tipo": "aguardando_fim"})


def resolver_pendente(texto: str, falante=None) -> tuple[bool, str | None]:
    """Chamado com cada fala nova. Devolve (tratado, resposta para falar)."""
    global _pendente
    p = pendente()
    if not p:
        return False, None
    resposta = classificar_resposta(texto)
    if resposta is None:
        if p["tipo"] == "agente":  # o agente espera sim ou não; outra fala segue normalmente
            return False, None
        cancelar_pendente()
        return False, None
    dono_do_pedido = p.get("falante")
    if falante is not None and dono_do_pedido is not None and falante.nivel != "dono" \
            and falante.nome != getattr(dono_do_pedido, "nome", None):
        return True, "Essa confirmação é de outra pessoa."
    with _trava:
        _pendente = None
    eventos.publicar({"tipo": "aguardando_fim"})
    if p["tipo"] == "agente":
        p["resposta"] = resposta
        p["evento"].set()
        return True, "Combinado, vou continuar." if resposta == "sim" else "Tudo bem, não vou fazer isso."
    if resposta == "nao":
        return True, "Tudo bem, não fiz."
    resultado = executar(p["nome"], p["args"], p["funcao"], falante=p.get("falante"), origem=p["origem"],
                         motivo=p["motivo"], troca=p["troca"], confirmado=True, grupo=p.get("grupo"))
    return True, resultado if isinstance(resultado, str) else "Feito."


def pedir_confirmacao_agente(pergunta: str, esperar: float = 120, ficha=None) -> bool:
    """O modo agente pede um "sim" antes de uma ação sem volta (enviar, comprar, apagar...)."""
    global _pendente
    ev = threading.Event()
    with _trava:
        _pendente = {"tipo": "agente", "pergunta": pergunta, "evento": ev, "criado": time.time(),
                     "nivel": CONFIRMAR, "resposta": None, "falante": None}
        p = _pendente
    eventos.publicar({"tipo": "aguardando", "pergunta": pergunta})
    fim = time.time() + esperar
    while time.time() < fim:
        if ev.wait(0.5):
            break
        if ficha is not None and ficha.cancelado:
            break
    with _trava:
        if _pendente is p:
            _pendente = None
    eventos.publicar({"tipo": "aguardando_fim"})
    return p.get("resposta") == "sim"
