"""Cérebro local (Ollama) com ferramentas: a Ametista faz as mesmas coisas no PC sem a nuvem.

- Modelos pequenos se perdem com dezenas de ferramentas, então cada pedido recebe só as do assunto (arquivos,
  notas, programas abertos, foco, música...) mais um núcleo curto. O assunto sai do pedido e da fala anterior
  ("acha o PDF da aula" -> "me manda ele").
- Confirmações passam pelo mesmo caminho do Claude (acoes): quando uma ação precisa de "sim", ela pergunta e para.
- O modelo fica carregado na placa de vídeo por 30 minutos (keep_alive): as respostas seguintes saem na hora.
- Se o modelo configurado não estiver baixado, usa o melhor que estiver (e o diagnóstico avisa).
"""
import json
import re
import threading
import time
import unicodedata

import httpx

from . import acoes, config, estado, ferramentas, memoria, personalidade
from .estado import Cancelado

# Do melhor para o mais leve, entre os que sabem usar ferramentas no Ollama.
PREFERIDOS = ("qwen2.5:14b", "qwen3:14b", "qwen2.5:7b", "qwen3:8b", "llama3.1:8b", "mistral-nemo", "qwen2.5:3b",
              "qwen3:4b", "llama3.2:3b", "qwen2.5:1.5b", "llama3.2:1b")
FAMILIAS_COM_FERRAMENTAS = ("qwen2", "qwen3", "llama3.1", "llama3.2", "llama3.3", "mistral", "mixtral",
                            "command-r", "granite3", "firefunction", "hermes3", "nemotron", "smollm2", "gpt-oss")
MAX_FERRAMENTAS = 22
MAX_RODADAS = 5
CONTEXTO_TOKENS = 8192
MANTER = "30m"
_cache: dict = {"modelos": (0.0, []), "capacidades": {}}


def _sem_acento(t: str) -> str:
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


# ====================================================================== modelos
def modelos_instalados(forcar: bool = False) -> list[str]:
    quando, lista = _cache["modelos"]
    if not forcar and time.time() - quando < 60:
        return lista
    try:
        r = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=3)
        lista = [m["name"] for m in r.json().get("models", [])] if r.status_code == 200 else []
    except Exception:
        lista = []
    _cache["modelos"] = (time.time(), lista)
    return lista


def _mesmo(a: str, b: str) -> bool:
    a, b = a.strip().lower(), b.strip().lower()
    return a == b or a == f"{b}:latest" or b == f"{a}:latest"


def modelo() -> str:
    """O modelo configurado, se estiver baixado; senão o melhor baixado (senão o configurado mesmo)."""
    instalados = modelos_instalados()
    desejado = config.OLLAMA_MODELO.strip()
    if not instalados or any(_mesmo(m, desejado) for m in instalados):
        return desejado
    for p in PREFERIDOS:
        achado = next((m for m in instalados if _mesmo(m, p)), None)
        if achado:
            return achado
    return next((m for m in instalados if "embed" not in m.lower()), desejado)


def capacidades(nome: str) -> set[str]:
    """O que o modelo sabe: tools, vision, thinking (Ollama 0.7+ informa; antes disso, pela família)."""
    if nome in _cache["capacidades"]:
        return _cache["capacidades"][nome]
    caps: set[str] = set()
    try:
        r = httpx.post(f"{config.OLLAMA_URL}/api/show", json={"model": nome}, timeout=5)
        dados = r.json() if r.status_code == 200 else {}
        caps = set(dados.get("capabilities") or [])
        if not caps and r.status_code == 200:
            familia = " ".join([str((dados.get("details") or {}).get("family", "")), nome]).lower()
            if any(f in familia for f in FAMILIAS_COM_FERRAMENTAS):
                caps = {"completion", "tools"}
    except Exception:
        return {"completion"}
    _cache["capacidades"][nome] = caps or {"completion"}
    return _cache["capacidades"][nome]


# ====================================================================== quais ferramentas mandar
NUCLEO = ["criar_timer", "criar_lembrete", "pc_abrir", "pc_volume", "pc_midia", "pc_pesquisar", "lembrar_fato",
          "memoria_buscar", "clima", "desfazer_acao", "nota_criar", "arquivos_buscar"]
GRUPOS: list[tuple[str, list[str]]] = [
    (r"arquiv|pasta|pdf|docx?\b|documento|planilha|excel|word|powerpoint|slide|\btxt\b|download|area de trabalho|"
     r"desktop|\bmov[ea]|copi[ae]|apag|renome|salv[ae]|\bl[eê] |leia|conteudo|escrev|edit",
     ["arquivos_buscar", "arquivo_ler", "arquivo_abrir", "arquivo_mostrar_na_pasta", "pasta_listar",
      "arquivo_escrever", "arquivo_mover", "arquivo_copiar", "arquivo_apagar"]),
    (r"nota|bloco|anot|lista de|conversa|historico",
     ["nota_criar", "nota_acrescentar", "nota_ler", "notas_listar", "nota_abrir", "conversa_exportar"]),
    (r"memoria ram|\bram\b|memoria do pc|processo|lento|pesad|\bcpu\b|travad|temporari|limp|disco|espaco|"
     r"armazenamento|gerenciador|encerr|\bmata\b|forca|instancia|rodando|aberto",
     ["pc_processos", "pc_discos", "pc_encerrar", "limpeza_analisar", "limpeza_executar", "pc_status", "pc_fechar"]),
    (r"celular|telefone|\bmanda|\benvia|me passa|\bpuxa", ["arquivo_enviar_celular", "arquivos_buscar"]),
    (r"estud|foco|focar|procrastin|distra|\bpausa\b|materia|prova|concentr",
     ["foco_iniciar", "foco_pausar", "foco_parar", "foco_relatorio"]),
    (r"tela|clica|clique|janela|digit|tecla|mouse|rola|area de transferencia|\bcola\b",
     ["pc_janela", "pc_fechar", "pc_clicar", "pc_teclas", "pc_digitar", "pc_rolar", "pc_area_transferencia"]),
    (r"musica|\btoca|spotify|playlist|proxima|anterior|volume|\bsom\b|curt|album|artista",
     ["spotify_tocar", "spotify_controle", "spotify_tocando", "spotify_fila", "spotify_curtir", "spotify_volume",
      "spotify_aparelhos", "spotify_transferir", "pc_midia", "pc_volume"]),
    (r"agenda|compromisso|reuniao|evento|agendar|marca", ["agenda_listar", "agenda_criar", "agenda_alterar",
                                                            "agenda_cancelar"]),
    (r"lembr|alarme|timer|temporizador|me avisa|aniversario|despert",
     ["criar_timer", "criar_lembrete", "lembrete_recorrente", "lembrete_condicao", "listar_lembretes",
      "cancelar_lembrete", "aniversario_adicionar"]),
    (r"\bluz|lampada|tomada|ar condicionado|ventilador|\bcasa\b|interruptor", ["casa_listar", "casa_controlar"]),
    (r"\bjogo|steam|instal", ["steam_buscar_jogo", "steam_instalar", "steam_abrir", "steam_status",
                              "steam_avisar_quando_pronto", "steam_unidades"]),
    (r"rotina|bom dia|boa noite|dormir|modo filme|perturbe|privado|silencio",
     ["rotina_executar", "rotina_listar", "rotina_criar", "rotina_apagar", "nao_perturbe", "modo_privado"]),
    (r"lembra|esquec|caderno|sabe sobre|guard", ["lembrar_fato", "esquecer_fato", "caderno_guardar",
                                                 "caderno_buscar", "caderno_listar", "memoria_buscar"]),
    (r"noticia|clima|tempo la fora|chuva|temperatura|previsao", ["noticias", "clima"]),
    (r"deslig|reinici|bloqueia|suspend|hibern", ["pc_sistema"]),
    (r"diagnost|cadastr|voz de|pessoas|tarefa|desfaz|o que voce fez|acoes",
     ["diagnostico", "pessoas_listar", "pessoas_cadastrar", "pessoas_remover", "pessoas_nivel", "tarefas_listar",
      "tarefa_cancelar", "acoes_listar", "desfazer_acao"]),
]
# Precisam enxergar imagens ou do Claude (o agente usa o Claude para mexer no mouse)
SO_NA_NUVEM = {"chamar_modelo_forte", "pc_ver_tela", "pc_apontar", "agente_iniciar"}


def escolher(texto: str, anterior: str = "", falante=None) -> list[dict]:
    """As definições (formato do Claude) que vão para o modelo local neste pedido."""
    permitidas = {d["name"]: d for d in ferramentas.definicoes_permitidas(falante) if d["name"] not in SO_NA_NUVEM}
    alvo = _sem_acento(f"{texto} {anterior}")
    nomes: list[str] = []
    for padrao, grupo in GRUPOS:
        if re.search(padrao, alvo):
            nomes += grupo
    nomes += NUCLEO
    saida, vistos = [], set()
    for n in nomes:
        if n in permitidas and n not in vistos:
            vistos.add(n)
            saida.append(permitidas[n])
        if len(saida) >= MAX_FERRAMENTAS:
            break
    return saida


def para_ollama(definicoes: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {"name": d["name"], "description": d["description"],
                                              "parameters": d.get("input_schema") or {"type": "object",
                                                                                      "properties": {}}}}
            for d in definicoes]


def ajustar_args(args, esquema: dict) -> dict:
    """Modelos pequenos mandam "30" no lugar de 30, "true" no lugar de true, a lista como texto..."""
    if isinstance(args, str):
        try:
            args = json.loads(args or "{}")
        except ValueError:
            args = {}
    if not isinstance(args, dict):
        return {}
    props = (esquema or {}).get("properties") or {}
    saida = {}
    for k, v in args.items():
        if k not in props and props:
            continue                                   # parâmetro inventado
        tipo = (props.get(k) or {}).get("type")
        try:
            if tipo == "number" and isinstance(v, str):
                v = float(v.replace(",", "."))
            elif tipo == "integer" and isinstance(v, (str, float)):
                v = int(float(str(v).replace(",", ".")))
            elif tipo == "boolean" and isinstance(v, str):
                v = v.strip().lower() in ("true", "sim", "1", "yes")
            elif tipo == "array" and isinstance(v, str):
                v = json.loads(v) if v.strip().startswith("[") else [x.strip() for x in v.split(",") if x.strip()]
            elif tipo == "string" and isinstance(v, (int, float)):
                v = str(v)
        except (ValueError, TypeError):
            pass
        if v is None:
            continue
        saida[k] = v
    return saida


# ====================================================================== prompt
CAPACIDADES_LOCAL = """# O que você consegue fazer (use as ferramentas!)
Você está ligada ao computador de {dono} e controla ele pelas ferramentas que recebeu neste pedido: arquivos e
pastas (ler, criar, editar, mover, apagar), blocos de notas, programas abertos e memória, limpeza de temporários,
mandar arquivos para o celular, foco nos estudos, lembretes, música, volume e janelas.
- Nunca diga que não consegue acessar o computador ou que é "só uma inteligência artificial": use a ferramenta.
- Nunca diga que fez algo sem ter chamado a ferramenta e recebido o resultado. Se ela falhar, diga o que houve.
- Para achar um arquivo pelo nome, use arquivos_buscar; depois use o caminho que ele devolver.
- Se não houver ferramenta para o pedido, diga com sinceridade o que dá para fazer.
- Responda curto, em português do Brasil, como quem fala."""


def _prompt(falante, sem_nome: bool, origem: str, troca_privada: bool, com_ferramentas: bool) -> str:
    from . import cerebro

    partes = [personalidade.sistema_base()]
    if com_ferramentas:
        partes.append(CAPACIDADES_LOCAL.format(dono=config.DONO))
    else:
        partes.append("Você está usando um modelo local que não sabe usar ferramentas: só conversa. Se pedirem uma "
                      "ação no PC, diga que com o modelo local atual não dá e sugira instalar o qwen2.5:7b no "
                      "Ollama (ollama pull qwen2.5:7b).")
    partes.append(cerebro._prompt_contexto(falante, sem_nome, "rapido", origem, troca_privada))
    if estado.offline:
        partes.append("- Você está sem internet agora: pesquisar na web não funciona.")
    return "\n\n".join(partes)


# ====================================================================== conversa
class ModeloAusente(Exception):
    pass


def _rodada(nome: str, mensagens: list, tools: list, saida, ficha, pensa: bool) -> tuple[str, list]:
    corpo = {"model": nome, "messages": mensagens, "stream": True, "keep_alive": MANTER,
             "options": {"num_ctx": CONTEXTO_TOKENS, "temperature": 0.5}}
    if tools:
        corpo["tools"] = tools
    if pensa:
        corpo["think"] = False                 # modelos que "pensam" (qwen3) demoram demais para a voz
    texto, chamadas = [], []
    segura = None            # None = ainda não sabe; True = parece uma chamada escrita como texto (não fala)
    with httpx.stream("POST", f"{config.OLLAMA_URL}/api/chat", json=corpo,
                      timeout=httpx.Timeout(120, connect=5)) as r:
        if r.status_code == 404:
            raise ModeloAusente(nome)
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
            if dado.get("error"):
                raise RuntimeError(dado["error"])
            msg = dado.get("message") or {}
            pedaco = msg.get("content") or ""
            if pedaco:
                texto.append(pedaco)
                if segura is None:
                    inicio = "".join(texto).lstrip()
                    if inicio:
                        segura = bool(_COMECO_DE_CHAMADA.match(inicio))
                        if not segura and saida is not None:
                            saida.texto("".join(texto))
                elif not segura and saida is not None:
                    saida.texto(pedaco)
            chamadas += [c for c in (msg.get("tool_calls") or []) if isinstance(c, dict)]
            if dado.get("done"):
                break
    dito = "".join(texto)
    if segura and not chamadas:
        chamadas = chamadas_no_texto(dito, {t["function"]["name"] for t in tools})
        if chamadas:
            dito = ""                                   # era uma chamada: não vira fala
        elif saida is not None:
            saida.texto(dito)                           # era texto mesmo: fala agora
    return dito, chamadas


# Modelos pequenos às vezes escrevem a chamada da ferramenta como texto, em vez de chamar de verdade:
#   {"name": "nota_criar", "arguments": {...}}   ou   <tool_call>{...}</tool_call>   ou   ```json {...} ```
_COMECO_DE_CHAMADA = re.compile(r"(\{|\[\s*\{|<tool_call>|```)")


def chamadas_no_texto(texto: str, nomes: set[str]) -> list[dict]:
    """As chamadas escritas como texto, só das ferramentas que o modelo recebeu."""
    t = texto.strip()
    blocos = (re.findall(r"<tool_call>\s*(.*?)\s*(?:</tool_call>|$)", t, re.S)
              or re.findall(r"```(?:json)?\s*(.*?)```", t, re.S) or [t])
    saida = []
    for bloco in blocos:
        try:
            objs = [json.loads(bloco)]
        except ValueError:
            objs = []
            for linha in bloco.splitlines():                 # um JSON por linha
                try:
                    objs.append(json.loads(linha))
                except ValueError:
                    continue
        for o in [x for obj in objs for x in (obj if isinstance(obj, list) else [obj])]:
            if isinstance(o, dict) and o.get("name") in nomes:
                args = o.get("arguments", o.get("parameters", {}))
                saida.append({"function": {"name": o["name"], "arguments": args if args is not None else {}}})
    return saida


def _resultado_texto(r) -> str:
    if isinstance(r, list):
        textos = [b.get("text", "") for b in r if isinstance(b, dict) and b.get("type") == "text"]
        return " ".join(t for t in textos if t) + " (O modelo local não enxerga imagens: descreva só o que o texto diz.)"
    return str(r)


def perguntar(texto: str, falante=None, saida=None, ficha=None, sem_nome: bool = False, origem: str = "pc",
              troca_privada: bool = False) -> str:
    """Conversa com o Ollama, com ferramentas quando o modelo sabe usar. Devolve o texto completo."""
    from . import cerebro

    nome = modelo()
    caps = capacidades(nome)
    historico = memoria.historico()
    anterior = next((m["content"] for m in reversed(historico) if m["role"] == "user"
                     and isinstance(m["content"], str)), "")
    definicoes = escolher(texto, anterior, falante) if "tools" in caps else []
    esquemas = {d["name"]: d.get("input_schema") or {} for d in definicoes}
    mensagens = [{"role": "system", "content": _prompt(falante, sem_nome, origem, troca_privada, bool(definicoes))}]
    mensagens += historico + [{"role": "user", "content": texto}]
    tools = para_ollama(definicoes)
    completo: list[str] = []
    feitas: set[str] = set()
    for rodada in range(MAX_RODADAS):
        dito, chamadas = _rodada(nome, mensagens, tools if rodada < MAX_RODADAS - 1 else [], saida, ficha,
                                 "thinking" in caps)
        completo.append(dito)
        if not chamadas:
            break
        if saida is not None and dito.strip():
            saida.texto("\n")
        mensagens.append({"role": "assistant", "content": dito, "tool_calls": chamadas})
        for c in chamadas:
            if ficha is not None and ficha.cancelado:
                raise Cancelado()
            fn = c.get("function") or {}
            ferramenta = str(fn.get("name") or "")
            if ferramenta not in esquemas:
                resultado = f"Ferramenta {ferramenta} não existe aqui. Use só as ferramentas que você recebeu."
            else:
                args = ajustar_args(fn.get("arguments"), esquemas[ferramenta])
                chave = ferramenta + json.dumps(args, sort_keys=True, ensure_ascii=False)
                if chave in feitas:
                    resultado = "Você já fez exatamente isso agora. Responda ao usuário com o que já tem."
                else:
                    feitas.add(chave)
                    cerebro._status(ferramenta)
                    resultado = _resultado_texto(ferramentas.executar(ferramenta, args))
            if resultado.startswith("PRECISA CONFIRMAR"):
                # Modelos pequenos às vezes seguem em frente; aqui a pergunta sai do sistema e a conversa para.
                p = acoes.pendente()
                pergunta = p["pergunta"] if p else "Posso fazer isso?"
                if saida is not None:
                    saida.texto(("\n" if "".join(completo).strip() else "") + "[pensativa] " + pergunta)
                completo.append("[pensativa] " + pergunta)
                return " ".join(x.strip() for x in completo if x.strip())
            mensagens.append({"role": "tool", "content": resultado, "tool_name": ferramenta})
    final = " ".join(x.strip() for x in completo if x.strip())
    if not final:
        final = "[pensativa] Pronto."
        if saida is not None:
            saida.texto(final)
    return final


# ====================================================================== baixar o modelo (em segundo plano)
TAMANHOS = {"qwen2.5:7b": "4,7 GB", "qwen2.5:14b": "9 GB", "qwen2.5:3b": "1,9 GB", "llama3.1:8b": "4,9 GB"}
_download: dict = {"modelo": None, "ativo": False, "pct": 0.0, "status": "", "erro": None, "tentativa": 0}
_trava_download = threading.Lock()


def estado_download() -> dict:
    return dict(_download)


def _executavel() -> str | None:
    import os
    import shutil

    achado = shutil.which("ollama")
    if achado:
        return achado
    padrao = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
    return padrao if os.path.isfile(padrao) else None


def httpx_ok() -> bool:
    try:
        return httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=1.5).status_code == 200
    except Exception:
        return False


def abrir_ollama(esperar: float = 15) -> bool:
    """Se o Ollama estiver fechado, abre o aplicativo dele (nunca um segundo servidor: dois brigam pela porta e
    derrubam os downloads um do outro). Devolve True se ele responder."""
    import os
    import subprocess

    if httpx_ok():
        return True
    exe = _executavel()
    if not exe:
        return False
    app = os.path.join(os.path.dirname(exe), "ollama app.exe")
    comando = [app] if os.path.isfile(app) else [exe, "serve"]
    try:
        subprocess.Popen(comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) |
                         getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True)
    except OSError:
        return False
    fim = time.time() + esperar
    while time.time() < fim:
        if httpx_ok():
            return True
        time.sleep(0.5)
    return False


def baixar(nome: str, tentativas: int = 10, espera_base: float = 5.0) -> bool:
    """Baixa um modelo pela API do Ollama. Se a conexão cair, tenta de novo: o Ollama continua de onde parou."""
    with _trava_download:
        if _download["ativo"]:
            return False
        _download.update(modelo=nome, ativo=True, pct=0.0, status="começando", erro=None, tentativa=0)
    try:
        for tentativa in range(1, tentativas + 1):
            _download["tentativa"] = tentativa
            try:
                if not httpx_ok() and not abrir_ollama():
                    raise RuntimeError("o Ollama não está aberto")
                with httpx.stream("POST", f"{config.OLLAMA_URL}/api/pull", json={"model": nome, "stream": True},
                                  timeout=httpx.Timeout(30, read=600)) as r:
                    r.raise_for_status()
                    for linha in r.iter_lines():
                        if not linha.strip():
                            continue
                        try:
                            d = json.loads(linha)
                        except ValueError:
                            continue
                        if d.get("error"):
                            raise RuntimeError(d["error"])
                        _download["status"] = str(d.get("status", ""))
                        if d.get("total"):
                            _download["pct"] = round(100 * float(d.get("completed") or 0) / float(d["total"]), 1)
                        if d.get("status") == "success":
                            _download.update(pct=100.0, status="pronto", erro=None)
                            _cache["modelos"] = (0.0, [])
                            return True
                raise RuntimeError("a conexão com o Ollama caiu no meio")
            except Exception as e:
                _download["erro"] = str(e)[:200]
                print(f"[ollama] download de {nome} (tentativa {tentativa}): {e}")
                time.sleep(min(120.0, espera_base * 2 ** (tentativa - 1)))
        return False
    finally:
        _download["ativo"] = False


def baixar_em_segundo_plano(nome: str | None = None) -> bool:
    """Começa a baixar o modelo sem travar nada. Devolve False se já estiver baixando ou já estiver baixado."""
    nome = (nome or config.OLLAMA_MODELO).strip()
    if _download["ativo"] or any(_mesmo(m, nome) for m in modelos_instalados(forcar=True)):
        return False

    def trabalho():
        from . import avisos

        if baixar(nome):
            from . import estado

            estado.lembrar("ollama_baixar", None)
            avisos.registrar(f"O modelo {nome} terminou de baixar: o cérebro no próprio PC está pronto.",
                             titulo="Ollama")
        elif _download.get("erro"):
            avisos.registrar(f"Não consegui baixar o modelo {nome}: {_download['erro']}. Ela tenta de novo na "
                             "próxima vez que abrir.", titulo="Ollama")
    threading.Thread(target=trabalho, daemon=True, name="ollama-download").start()
    return True


def ao_abrir(espera: float = 20) -> None:
    """Na abertura da Ametista: se ficou combinado baixar o modelo (no instalador ou no painel), continua."""
    from . import estado

    pedido = estado.obter("ollama_baixar")
    if not pedido or not _executavel():
        return

    def trabalho():
        time.sleep(espera)                             # deixa a Ametista abrir primeiro
        if abrir_ollama(30):
            baixar_em_segundo_plano(str(pedido))
    threading.Thread(target=trabalho, daemon=True, name="ollama-abrir").start()


# ====================================================================== instalação
def preparar() -> int:
    """Passo do instalar.bat: nunca baixa nada aqui (4,7 GB travariam a instalação). Se o modelo faltar, combina
    de a Ametista baixar em segundo plano, continuando de onde parar se a internet cair. Nunca falha."""
    from . import estado, pasta_segura

    try:
        config.migrar_env()
        config.recarregar()
    except OSError:
        pass
    if not _executavel():
        print("  Ollama não está instalado (opcional: é o cérebro no próprio PC; veja \"Cérebro no próprio PC\" "
              "no LEIA-ME).")
        return 0
    desejado = config.OLLAMA_MODELO.strip()
    if not abrir_ollama():
        print("  O Ollama está instalado, mas não respondeu. Abra o Ollama: a Ametista cuida do resto depois.")
    elif any(_mesmo(m, desejado) for m in modelos_instalados(forcar=True)):
        print(f"  Ollama pronto com {desejado}.")
        return 0
    extra = f" ({TAMANHOS[desejado]})" if desejado in TAMANHOS else ""
    if estado.obter("ollama_baixar") == desejado:
        print(f"  O modelo {desejado}{extra} continua baixando em segundo plano quando a Ametista estiver aberta.")
        return 0
    if pasta_segura.perguntar(f"  Baixar o modelo {desejado}{extra} em segundo plano, com a Ametista aberta? "
                              "(continua de onde parar se a internet cair) (S/N) "):
        estado.lembrar("ollama_baixar", desejado)
        print("  Combinado: o download começa quando a Ametista abrir. O andamento aparece no painel > Cérebro.")
    else:
        print("  Tudo bem. Dá para baixar depois pelo painel > Cérebro.")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(preparar() if "--preparar" in sys.argv else 0)
