"""Modo agente: tarefas grandes, em etapas, com o andamento visível na tela.

Exemplos: "organiza minha pasta de Downloads por tipo de arquivo", "pesquisa três notebooks até 5 mil reais e
monta uma planilha", "preenche esse formulário com os dados da obra de Jundiaí".

Como funciona:
  - roda em segundo plano com o modelo forte (AGENTE_MODELO), que enxerga a tela e usa mouse e teclado
    (ferramenta de controle do computador do Claude) e também as ferramentas da Ametista;
  - primeiro monta um plano (etapas), depois vai marcando cada etapa na sobreposição e no celular;
  - antes de qualquer coisa sem volta (enviar, comprar, apagar, publicar) ele PARA e pergunta;
  - para na hora com "para tudo", no botão cancelar, ou se você mexer no mouse enquanto ele trabalha.
"""
import base64
import io
import itertools
import threading
import time
from datetime import datetime

from . import acoes, config, estado, eventos, fala
from .estado import Cancelado

MAX_RODADAS = 80
FERRAMENTAS_AGENTE = ["pc_abrir", "pc_pesquisar", "pc_janela", "pc_area_transferencia", "arquivos_buscar",
                      "arquivo_abrir", "arquivo_mostrar_na_pasta", "caderno_buscar", "memoria_buscar",
                      "criar_lembrete", "agenda_listar", "agenda_criar", "clima", "noticias", "spotify_tocar",
                      "pc_status"]
_ids = itertools.count(1)
_tarefas: dict[str, "Tarefa"] = {}
_trava = threading.Lock()


class Parada(Exception):
    pass


class Tarefa:
    def __init__(self, objetivo: str, usar_tela: bool, falante=None):
        self.id = f"t{next(_ids)}"
        self.objetivo = objetivo
        self.usar_tela = usar_tela
        self.falante = falante
        self.criada = datetime.now().isoformat(timespec="seconds")
        self.estado = "planejando"
        self.passos: list[dict] = []
        self.nota = ""
        self.resumo = ""
        self.ficha = estado.nova_ficha(objetivo, "agente")
        self.geo: dict | None = None
        self.ultimo_cursor: tuple[int, int] | None = None
        self.controlando = False

    def dict(self) -> dict:
        feitos = sum(1 for p in self.passos if p["estado"] in ("feito", "pulado"))
        return {"id": self.id, "objetivo": self.objetivo, "estado": self.estado, "passos": self.passos,
                "nota": self.nota, "resumo": self.resumo, "criada": self.criada,
                "progresso": round(100 * feitos / len(self.passos)) if self.passos else 0}

    def publicar(self) -> None:
        eventos.publicar({"tipo": "tarefa", "tarefa": self.dict()})

    def ativa(self) -> bool:
        return self.estado in ("planejando", "executando", "aguardando")


# ====================================================================== controle do computador (toolset)
def _captura(t: Tarefa):
    from . import controle

    img, geo = controle.capturar("principal", config.AGENTE_MODELO)
    t.geo = geo
    return img


def _imagem_b64(img) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def _conferir_mouse(t: Tarefa) -> None:
    """Se a pessoa mexeu no mouse enquanto o agente trabalhava, ele para (segurança)."""
    from . import controle

    if t.ultimo_cursor is None or not controle.WINDOWS:
        return
    x, y = controle.posicao_cursor()
    if abs(x - t.ultimo_cursor[0]) > 40 or abs(y - t.ultimo_cursor[1]) > 40:
        raise Parada("Parei porque você mexeu no mouse. Se quiser, é só pedir de novo.")


def _conferir_comando(t: Tarefa, nome: str, texto: str) -> None:
    """Digitar num terminal (ou abrir o Executar) roda comandos no PC: o agente pede um "sim" antes."""
    from . import controle

    atalho = nome != "type" and controle.atalho_de_comando(texto)
    lugar = controle.janela_de_comando()
    if not atalho and not lugar:
        return
    if atalho:
        pergunta = f"Para continuar a tarefa eu preciso abrir um lugar de comandos ({texto}). Posso?"
    elif nome == "type":
        curto = texto.strip() if len(texto.strip()) <= 60 else texto.strip()[:57] + "…"
        pergunta = f"Vou digitar num {lugar}, e isso roda comandos no PC: “{curto}”. Posso?"
    else:
        pergunta = f"Vou apertar {texto} num {lugar}. Posso?"
    t.estado = "aguardando"
    t.publicar()
    fala.falar(pergunta, "pensativa", origem="agente")
    sim = acoes.pedir_confirmacao_agente(pergunta, 120, t.ficha)
    t.estado = "executando"
    t.publicar()
    t.ficha.conferir()
    if not sim:
        raise RuntimeError("o usuário não autorizou digitar num lugar que roda comandos. Não tente de novo; "
                           "ajuste o plano ou conclua.")
    t.ultimo_cursor = controle.posicao_cursor() if controle.WINDOWS else None


def _acao_computador(t: Tarefa, nome: str, a: dict):
    """Executa uma ação do toolset. Devolve o conteúdo do tool_result."""
    from . import controle

    t.ficha.conferir()
    if nome == "screenshot":
        return [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": _imagem_b64(_captura(t))}}]
    if t.geo is None:
        _captura(t)
    geo = t.geo

    def ponto(chave: str = "coordinate"):
        c = a.get(chave)
        if not c:
            return None
        return controle.para_tela(c[0], c[1], geo)

    if nome == "zoom":
        import math

        from PIL import Image

        x0, y0 = controle.para_tela(a["region"][0], a["region"][1], geo)
        x1, y1 = controle.para_tela(a["region"][2], a["region"][3], geo)
        import mss

        with (getattr(mss, "MSS", None) or mss.mss)() as s:  # mss 10+ renomeou para MSS
            bruto = s.grab({"left": min(x0, x1), "top": min(y0, y1), "width": max(1, abs(x1 - x0)),
                            "height": max(1, abs(y1 - y0))})
            img = Image.frombytes("RGB", bruto.size, bruto.rgb)
        max_lado, max_px = controle.limites(config.AGENTE_MODELO)
        w, h = img.size
        esc = min(1.0, max_lado / max(w, h), math.sqrt(max_px / (w * h)))
        if esc < 1:
            img = img.resize((int(w * esc), int(h * esc)))
        return [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _imagem_b64(img)}}]
    if nome == "cursor_position":
        x, y = controle.posicao_cursor()
        return f"{int((x - geo['x0']) * geo['escala'])}, {int((y - geo['y0']) * geo['escala'])}"
    if nome == "wait":
        if t.ficha.esperar(max(0.0, min(float(a.get("duration", 1)), 30))):
            raise Cancelado()
        return "OK"
    _conferir_mouse(t)
    if nome in ("type", "key", "hold_key"):
        _conferir_comando(t, nome, str(a.get("text", "")))
    mods = a.get("text", "") if nome not in ("type", "key", "hold_key") else ""
    if nome in ("left_click", "right_click", "middle_click", "double_click", "triple_click"):
        p = ponto() or controle.posicao_cursor()
        botao = {"right_click": "right", "middle_click": "middle"}.get(nome, "left")
        vezes = {"double_click": 2, "triple_click": 3}.get(nome, 1)
        controle.clicar(p[0], p[1], botao, vezes, mods)
    elif nome == "left_click_drag":
        controle.arrastar(ponto("start_coordinate"), ponto(), mods)
    elif nome == "mouse_move":
        controle.mover(*ponto())
    elif nome == "left_mouse_down":
        controle.botao_esquerdo(True)
    elif nome == "left_mouse_up":
        controle.botao_esquerdo(False)
    elif nome == "scroll":
        p = ponto()
        controle.rolar(p[0] if p else None, p[1] if p else None, a.get("scroll_direction", "down"),
                       int(a.get("scroll_amount", 3)), mods)
    elif nome == "type":
        controle.digitar(str(a.get("text", "")))
    elif nome == "key":
        controle.pressionar(str(a.get("text", "")), int(a.get("repeat", 1) or 1))
    elif nome == "hold_key":
        controle.segurar(str(a.get("text", "")), float(a.get("duration", 1)))
    else:
        raise RuntimeError(f"ação desconhecida: {nome}")
    time.sleep(0.25)  # dá tempo da tela reagir
    t.ultimo_cursor = controle.posicao_cursor() if controle.WINDOWS else None
    return "OK"


# ====================================================================== ferramentas próprias do agente
DEF_AGENTE = [
    {"name": "plano_definir", "description": "Define o plano da tarefa (3 a 10 etapas curtas, em português).",
     "input_schema": {"type": "object", "properties": {"passos": {"type": "array", "items": {"type": "string"}}},
                      "required": ["passos"]}},
    {"name": "passo_atualizar", "description": "Marca o andamento de uma etapa do plano (índice começa em 0).",
     "input_schema": {"type": "object", "properties": {
         "indice": {"type": "integer"}, "estado": {"type": "string", "enum": ["fazendo", "feito", "erro", "pulado"]},
         "nota": {"type": "string"}}, "required": ["indice", "estado"]}},
    {"name": "pedir_confirmacao",
     "description": "Pergunta ao usuário (em voz) antes de uma ação sem volta: enviar, comprar, pagar, apagar, "
                    "publicar, enviar formulário com dados pessoais. Espera a resposta.",
     "input_schema": {"type": "object", "properties": {"pergunta": {"type": "string"}}, "required": ["pergunta"]}},
    {"name": "avisar", "description": "Fala uma frase curta para o usuário (só para algo importante no meio da tarefa).",
     "input_schema": {"type": "object", "properties": {"texto": {"type": "string"}}, "required": ["texto"]}},
    {"name": "concluir", "description": "Termina a tarefa com um resumo falado de 1 ou 2 frases.",
     "input_schema": {"type": "object", "properties": {
         "resumo": {"type": "string"}, "sucesso": {"type": "boolean"}}, "required": ["resumo"]}},
]


def _instrucoes(t: Tarefa) -> str:
    from . import personalidade

    tela = ("Você enxerga a tela e controla o mouse e o teclado pela ferramenta de computador (tire um screenshot "
            "antes de agir e confira depois das ações importantes). A tela é o monitor principal do Windows."
            if t.usar_tela else "Nesta tarefa você NÃO controla o mouse nem o teclado; use só as outras ferramentas.")
    return f"""{personalidade.identidade()}

# Modo agente
Você está executando sozinha, em segundo plano, uma tarefa que {config.DONO} pediu. {tela}

Como trabalhar:
1. Primeiro chame plano_definir com as etapas. Depois, a cada etapa, passo_atualizar (fazendo -> feito).
2. Faça o que foi pedido, no escopo pedido. Decisões pequenas são suas; pergunte só quando caminhos diferentes
   levariam a resultados bem diferentes.
3. ANTES de qualquer ação sem volta (enviar mensagem ou e-mail, comprar, pagar, apagar arquivos, publicar,
   enviar formulário, aceitar termos) chame pedir_confirmacao e só continue se a resposta for sim.
4. Nunca digite senhas, dados de cartão ou códigos de verificação: peça para {config.DONO} fazer essa parte.
5. Se travar (tela inesperada, login, captcha, erro que se repete), pare e explique em concluir.
6. Termine com concluir: um resumo curto e falado (sem markdown) do que foi feito e do que ficou faltando.

Agora: {datetime.now():%d/%m/%Y %H:%M}."""


def _executar_propria(t: Tarefa, nome: str, a: dict) -> str:
    if nome == "plano_definir":
        t.passos = [{"texto": str(p)[:120], "estado": "pendente"} for p in (a.get("passos") or [])][:12]
        t.estado = "executando"
        t.publicar()
        return f"Plano com {len(t.passos)} etapas registrado."
    if nome == "passo_atualizar":
        i = int(a.get("indice", -1))
        if not 0 <= i < len(t.passos):
            return "Erro: índice fora do plano."
        t.passos[i]["estado"] = a.get("estado", "feito")
        if a.get("nota"):
            t.passos[i]["nota"] = str(a["nota"])[:160]
        t.nota = t.passos[i]["texto"] if t.passos[i]["estado"] == "fazendo" else t.nota
        t.publicar()
        return "ok"
    if nome == "pedir_confirmacao":
        pergunta = str(a.get("pergunta", "Posso continuar?"))
        t.estado = "aguardando"
        t.publicar()
        fala.falar(pergunta, "pensativa", origem="agente")
        sim = acoes.pedir_confirmacao_agente(pergunta, 120, t.ficha)
        t.estado = "executando"
        t.publicar()
        t.ficha.conferir()
        return "O usuário disse SIM. Pode continuar." if sim else \
            "O usuário disse NÃO (ou não respondeu). Não faça essa ação; ajuste o plano ou conclua."
    if nome == "avisar":
        fala.falar(str(a.get("texto", ""))[:300], "neutra", origem="agente")
        return "ok"
    if nome == "concluir":
        t.resumo = str(a.get("resumo", ""))[:600]
        t.estado = "concluida" if a.get("sucesso", True) else "erro"
        return "ok"
    return f"Ferramenta desconhecida: {nome}"


# ====================================================================== laço do agente
def _params_base(t: Tarefa) -> dict:
    from . import ferramentas  # importado aqui: ferramentas.py também importa este módulo
    from .cerebro import ferramenta_busca_web

    outras = [ferramentas.POR_NOME[n] for n in FERRAMENTAS_AGENTE
              if n in ferramentas.POR_NOME and ferramentas._disponivel(n)]
    tools = DEF_AGENTE + sorted(outras, key=lambda d: d["name"]) + [ferramenta_busca_web(config.AGENTE_MODELO)]
    if t.usar_tela:
        tools = [{"type": "computer_toolset_20260801"}] + tools
    return {"model": config.AGENTE_MODELO, "max_tokens": 32000, "system": _instrucoes(t), "tools": tools,
            "output_config": {"effort": "high"}}


def _chamar(cliente, params: dict, extras: dict):
    """Chamada em streaming; se a API recusar um recurso opcional (400), tenta de novo sem ele."""
    import anthropic

    while True:
        betas = list(extras.get("betas", []))
        kwargs = dict(params)
        if "fallbacks" in extras:
            kwargs["fallbacks"] = extras["fallbacks"]
        if "context_management" in extras:
            kwargs["context_management"] = extras["context_management"]
        try:
            if betas:
                gerente = cliente.beta.messages.stream(betas=betas, **kwargs)
            else:
                gerente = cliente.messages.stream(**kwargs)
            with gerente as s:
                return s.get_final_message()
        except anthropic.BadRequestError as e:
            msg = str(e).lower()
            if "context_management" in extras and ("context" in msg or "clear_tool" in msg):
                extras.pop("context_management")
                extras["betas"] = [b for b in betas if not b.startswith("context-management")]
                continue
            if "fallbacks" in extras and "fallback" in msg:
                extras.pop("fallbacks")
                extras["betas"] = [b for b in extras.get("betas", []) if not b.startswith("server-side-fallback")]
                continue
            raise


def _rodar(t: Tarefa) -> None:
    from . import cerebro, ferramentas, identidade

    identidade.falante_atual.set(t.falante or identidade.DONO_PADRAO)
    token = ferramentas.CONTEXTO.set({"texto": f"tarefa: {t.objetivo}", "origem": "agente", "grupo": t.id,
                                      "modelo": config.AGENTE_MODELO})
    t.publicar()
    if t.usar_tela:
        eventos.publicar({"tipo": "agente_tela", "ativo": True})
    cliente = cerebro._claude()
    params = _params_base(t)
    extras: dict = {"betas": ["context-management-2025-06-27"],
                    "context_management": {"edits": [{"type": "clear_tool_uses_20250919"}]}}
    if cerebro._usa_fallbacks(config.AGENTE_MODELO):
        extras["betas"].append("server-side-fallback-2026-07-01")
        extras["fallbacks"] = "default"
    mensagens = [{"role": "user", "content": f"Tarefa: {t.objetivo}"}]
    try:
        for _ in range(MAX_RODADAS):
            t.ficha.conferir()
            r = _chamar(cliente, {**params, "messages": mensagens}, extras)
            t.ficha.conferir()
            conteudo = cerebro._eco(r.content)
            mensagens.append({"role": "assistant", "content": conteudo})
            if r.stop_reason == "refusal":
                t.estado, t.resumo = "erro", "Essa tarefa eu não posso fazer."
                break
            if r.stop_reason == "pause_turn":
                continue
            usos = [b for b in r.content if getattr(b, "type", None) == "tool_use"]
            if not usos or r.stop_reason == "max_tokens":
                texto = cerebro._texto_de(r.content).strip()
                t.resumo = t.resumo or texto[:600] or "Terminei."
                if t.ativa():
                    t.estado = "concluida"
                break
            resultados, falhou = [], False
            for b in usos:
                toolset = getattr(b, "toolset_name", None) or (getattr(b, "model_extra", None) or {}).get("toolset_name")
                base = {"type": "tool_result", "tool_use_id": b.id}
                if toolset:
                    base["toolset_name"] = toolset
                if falhou and toolset:
                    resultados.append({**base, "is_error": True,
                                       "content": "Not executed: an earlier computer action in this turn failed."})
                    continue
                args = b.input if isinstance(b.input, dict) else {}
                try:
                    if toolset:
                        conteudo_r = _acao_computador(t, b.name, args)
                    elif b.name in {d["name"] for d in DEF_AGENTE}:
                        conteudo_r = _executar_propria(t, b.name, args)
                    else:
                        conteudo_r = ferramentas.executar(b.name, args)
                    item = {**base, "content": conteudo_r if isinstance(conteudo_r, list)
                            else [{"type": "text", "text": str(conteudo_r)}]} if toolset else \
                        {**base, "content": conteudo_r}
                    resultados.append(item)
                except (Cancelado, Parada):
                    raise
                except Exception as e:
                    falhou = bool(toolset)
                    resultados.append({**base, "is_error": True, "content": f"Erro: {e}"})
            mensagens.append({"role": "user", "content": resultados})
            if not t.ativa():
                break
        else:
            t.estado, t.resumo = "erro", "A tarefa ficou longa demais e eu parei para não gastar à toa."
    except Cancelado:
        t.estado, t.resumo = "cancelada", "Tarefa cancelada."
    except Parada as p:
        t.estado, t.resumo = "cancelada", str(p)
    except Exception as e:
        print(f"[agente] erro: {e}")
        t.estado, t.resumo = "erro", f"A tarefa deu erro: {e}"
    finally:
        ferramentas.CONTEXTO.reset(token)
        estado.encerrar_ficha(t.ficha)
        if t.usar_tela:
            eventos.publicar({"tipo": "agente_tela", "ativo": False})
        t.publicar()
    if t.estado != "cancelada" or "mouse" in t.resumo:
        from . import avisos

        titulo = "Tarefa concluída" if t.estado == "concluida" else "Tarefa interrompida"
        avisos.alerta(t.resumo or "Terminei a tarefa.", "feliz" if t.estado == "concluida" else "pensativa",
                      titulo=titulo, tom=False)


# ====================================================================== ferramentas da Ametista
def iniciar(objetivo: str, usar_tela: bool = True) -> str:
    from . import controle, identidade

    if not config.ANTHROPIC_API_KEY:
        return "Erro: o modo agente precisa da chave da API da Anthropic."
    with _trava:
        if any(t.ativa() for t in _tarefas.values()):
            return "Erro: já tem uma tarefa em andamento. Espere terminar ou peça para cancelar."
        t = Tarefa(objetivo.strip(), bool(usar_tela) and controle.WINDOWS, identidade.falante_atual.get())
        _tarefas[t.id] = t
    threading.Thread(target=_rodar, args=(t,), daemon=True, name=f"agente-{t.id}").start()
    return f"Comecei a tarefa ({t.id}). Vou mostrando o andamento na tela; é só dizer \"para tudo\" para cancelar."


def cancelar(id: str = "") -> str:
    alvo = [t for t in _tarefas.values() if t.ativa() and (not id or t.id == id)]
    for t in alvo:
        t.ficha.cancelar()
    acoes.cancelar_pendente()
    return f"Cancelei {len(alvo)} tarefa(s)." if alvo else "Não há tarefa em andamento."


def cancelar_todas() -> int:
    alvo = [t for t in _tarefas.values() if t.ativa()]
    for t in alvo:
        t.ficha.cancelar()
    return len(alvo)


def listar() -> list[dict]:
    return [t.dict() for t in sorted(_tarefas.values(), key=lambda t: t.criada, reverse=True)][:20]


def listar_texto() -> str:
    itens = listar()
    if not itens:
        return "Nenhuma tarefa."
    return "\n".join(f"[{i['id']}] {i['objetivo']} — {i['estado']} ({i['progresso']}%)"
                     f"{': ' + i['resumo'] if i['resumo'] else ''}" for i in itens[:8])


def resumo_ativas() -> str:
    ativas = [t for t in _tarefas.values() if t.ativa()]
    return "; ".join(f"{t.objetivo} ({t.estado}, {t.dict()['progresso']}%)" for t in ativas)


DEFINICOES = [
    {"name": "agente_iniciar",
     "description": "Começa uma tarefa grande, com vários passos no computador, em segundo plano (modo agente). "
                    "Ex.: organizar pastas, pesquisar e montar uma planilha, preencher um formulário.",
     "input_schema": {"type": "object", "properties": {
         "objetivo": {"type": "string", "description": "A tarefa completa, com todos os detalhes que a pessoa deu"},
         "usar_tela": {"type": "boolean", "description": "false = não precisa de mouse/teclado"}},
         "required": ["objetivo"]}},
    {"name": "tarefas_listar", "description": "Mostra as tarefas do modo agente e o andamento.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "tarefa_cancelar", "description": "Cancela uma tarefa do modo agente (vazio = todas).",
     "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}}},
]
FUNCOES = {"agente_iniciar": iniciar, "tarefas_listar": listar_texto, "tarefa_cancelar": cancelar}
