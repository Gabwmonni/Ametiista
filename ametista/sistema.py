"""O PC por dentro: programas abertos e quanto pesam, discos, fechar um programa travado e limpar temporários.

- pc_processos: programas agrupados (o Chrome abre dezenas de processos, aqui vira uma linha só).
- pc_encerrar: fecha à força um programa travado ou em segundo plano (pede confirmação; nunca mexe em processos
  do Windows nem na própria Ametista). Para fechar janelas com calma, a ferramenta é pc_fechar.
- limpeza_analisar / limpeza_executar: temporários do usuário e do Windows, Lixeira, cache dos navegadores,
  miniaturas e relatórios de erro. Nada de arquivos pessoais: Downloads, Documentos etc. ficam de fora.
"""
import glob
import os
import sys
import time
from pathlib import Path

from . import acoes

PROTEGIDOS = {"system", "system idle process", "idle", "registry", "secure system", "memory compression",
              "memcompression", "smss", "csrss", "wininit", "services", "lsass", "lsaiso", "winlogon", "svchost",
              "fontdrvhost", "dwm", "explorer", "sihost", "ctfmon", "audiodg", "spoolsv", "wudfhost", "msmpeng",
              "securityhealthservice", "securityhealthsystray", "searchindexer", "runtimebroker", "taskhostw",
              "startmenuexperiencehost", "shellexperiencehost", "textinputhost", "conhost", "dllhost", "wmiprvse",
              "nvcontainer", "nvdisplay.container", "atiesrxx", "amdrsserv", "igfxem", "systemsettings"}
AMIGAVEIS = {"chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox", "opera": "Opera", "brave": "Brave",
             "discord": "Discord", "spotify": "Spotify", "steam": "Steam", "steamwebhelper": "Steam",
             "code": "VS Code", "winword": "Word", "excel": "Excel", "powerpnt": "PowerPoint",
             "outlook": "Outlook", "teams": "Teams", "ms-teams": "Teams", "whatsapp": "WhatsApp",
             "acad": "AutoCAD", "revit": "Revit", "obs64": "OBS", "vlc": "VLC", "python": "Python",
             "pythonw": "Python (sem janela)", "ollama": "Ollama", "ollama app": "Ollama", "notepad": "Bloco de Notas"}


def _base(nome: str) -> str:
    n = (nome or "").lower()
    return n[:-4] if n.endswith(".exe") else n


def _gb(n: float) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.1f} GB".replace(".", ",")
    return f"{n / 1024 ** 2:.0f} MB"


def _uso_memoria(proc) -> int:
    try:
        mi = proc.memory_info()
    except Exception:
        return 0
    return getattr(mi, "private", 0) or mi.rss        # no Windows, "private" é o que o Gerenciador mostra


def _minha_familia() -> set[int]:
    import psutil

    eu = psutil.Process()
    pids = {eu.pid}
    try:
        pids |= {p.pid for p in eu.children(recursive=True)}
        pids |= {p.pid for p in eu.parents()}
    except Exception:
        pass
    return pids


def processos(ordenar: str = "memoria", quantidade: int = 12) -> str:
    """Programas abertos agrupados por nome, com memória e CPU."""
    import psutil

    lista = list(psutil.process_iter(["name"]))
    for p in lista:
        try:
            p.cpu_percent(None)
        except Exception:
            pass
    time.sleep(0.6)
    grupos: dict[str, dict] = {}
    nucleos = psutil.cpu_count() or 1
    for p in lista:
        base = _base(p.info.get("name") or "")
        if not base or base in ("system idle process", "idle"):
            continue
        try:
            cpu = p.cpu_percent(None) / nucleos
        except Exception:
            cpu = 0.0
        g = grupos.setdefault(base, {"mem": 0, "cpu": 0.0, "n": 0})
        g["mem"] += _uso_memoria(p)
        g["cpu"] += cpu
        g["n"] += 1
    chave = (lambda kv: -kv[1]["cpu"]) if ordenar == "cpu" else (lambda kv: -kv[1]["mem"])
    vm = psutil.virtual_memory()
    linhas = [f"Memória: {_gb(vm.used)} de {_gb(vm.total)} em uso ({vm.percent:.0f}%). "
              f"CPU: {psutil.cpu_percent(None):.0f}%. {len(lista)} processos abertos."]
    for base, g in sorted(grupos.items(), key=chave)[:max(1, min(int(quantidade or 12), 40))]:
        nome = AMIGAVEIS.get(base, base)
        vezes = f" ({g['n']} processos)" if g["n"] > 1 else ""
        linhas.append(f"- {nome}{vezes}: {_gb(g['mem'])} de memória, CPU {g['cpu']:.0f}%")
    return "\n".join(linhas)


def discos() -> str:
    import psutil

    linhas = []
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in part.opts or not part.fstype:
            continue
        try:
            u = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        linhas.append(f"- {part.mountpoint}: {_gb(u.free)} livres de {_gb(u.total)} ({u.percent:.0f}% usado)")
    return "Discos:\n" + "\n".join(linhas) if linhas else "Não consegui ler os discos."


def _achar(programa: str) -> list:
    import psutil

    alvo = _base(programa.strip())
    por_apelido = {k for k, v in AMIGAVEIS.items() if v.lower() == alvo}
    minha = _minha_familia()
    achados = []
    for p in psutil.process_iter(["name", "pid"]):
        base = _base(p.info.get("name") or "")
        if not base or p.info["pid"] in minha or base in PROTEGIDOS:
            continue
        if base == alvo or base in por_apelido or (len(alvo) >= 4 and alvo in base):
            achados.append(p)
    return achados


def encerrar(programa: str) -> str:
    """Fecha à força todos os processos de um programa (para os travados ou que ficam em segundo plano)."""
    alvo = _base(programa.strip())
    if not alvo:
        return "Erro: diga o nome do programa."
    if alvo in PROTEGIDOS:
        return f"NEGADO: {programa} é do Windows; fechar isso pode travar o PC."
    procs = _achar(programa)
    if not procs:
        return f"Não achei o programa {programa} aberto."
    import psutil

    for p in procs:
        try:
            p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _, vivos = psutil.wait_procs(procs, timeout=4)
    for p in vivos:
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _, vivos = psutil.wait_procs(vivos, timeout=3)
    if vivos:
        return f"Fechei {len(procs) - len(vivos)} de {len(procs)} processos de {programa}; o resto o Windows não deixou."
    return f"Fechei o {AMIGAVEIS.get(alvo, programa)} ({len(procs)} processos)."


def _pergunta_encerrar(a: dict) -> str:
    procs = _achar(str(a.get("programa", "")))
    mem = sum(_uso_memoria(p) for p in procs)
    extra = f" ({len(procs)} processos, {_gb(mem)})" if procs else ""
    return f"Posso fechar à força o {a.get('programa')}{extra}? O que não estiver salvo nele se perde."


# ====================================================================== limpeza
def _env(nome: str, padrao: str = "") -> str:
    return os.environ.get(nome) or padrao


def _locais() -> dict[str, dict]:
    local = _env("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    win = _env("SystemRoot", r"C:\Windows")
    caches = []
    for navegador in (("Google", "Chrome"), ("Microsoft", "Edge"), ("BraveSoftware", "Brave-Browser"),
                      ("Opera Software",)):
        for perfil in glob.glob(os.path.join(local, *navegador, "User Data", "*")):
            caches += [os.path.join(perfil, *c) for c in (("Cache", "Cache_Data"), ("Code Cache",), ("GPUCache",))]
    caches += glob.glob(os.path.join(local, "Mozilla", "Firefox", "Profiles", "*", "cache2"))
    return {
        "temporarios": {"rotulo": "arquivos temporários", "pastas": [_env("TEMP", _env("TMP"))], "horas": 24},
        "temporarios_windows": {"rotulo": "temporários do Windows", "pastas": [os.path.join(win, "Temp")],
                                "horas": 24},
        "cache_navegadores": {"rotulo": "cache dos navegadores", "pastas": caches, "horas": 0},
        "miniaturas": {"rotulo": "miniaturas de imagens", "arquivos": glob.glob(
            os.path.join(local, "Microsoft", "Windows", "Explorer", "thumbcache_*.db")), "horas": 0},
        "relatorios_erro": {"rotulo": "relatórios de erro", "pastas": [
            os.path.join(local, "CrashDumps"), os.path.join(local, "Microsoft", "Windows", "WER")], "horas": 0},
        "lixeira": {"rotulo": "Lixeira", "lixeira": True},
    }


# Só estas pastas são limpas (o nome da pasta tem que ser um destes): se a variável TEMP do Windows estiver
# apontando para um lugar errado, como o disco inteiro, nada é apagado.
PASTAS_LIMPAVEIS = {"temp", "tmp", "cache_data", "code cache", "gpucache", "cache2", "crashdumps", "wer"}


def limpavel(pasta: str) -> bool:
    if not pasta or not os.path.isdir(pasta):
        return False
    normal = os.path.normpath(os.path.abspath(pasta))
    return os.path.basename(normal).lower() in PASTAS_LIMPAVEIS and normal != os.path.splitdrive(normal)[0] + os.sep


def _varrer(pastas: list[str], horas: float, prazo: float, max_arquivos: int = 400_000):
    """Arquivos apagáveis (mais velhos que `horas`), sem seguir atalhos; para quando o tempo acaba."""
    limite = time.time() - horas * 3600
    vistos = 0
    pilha = [p for p in pastas if limpavel(p)]
    while pilha and time.time() < prazo and vistos < max_arquivos:
        atual = pilha.pop()
        try:
            with os.scandir(atual) as it:
                for e in it:
                    vistos += 1
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            pilha.append(e.path)
                        else:
                            st = e.stat(follow_symlinks=False)
                            if st.st_mtime <= limite:
                                yield e.path, st.st_size
                    except OSError:
                        continue
        except OSError:
            continue


def _lixeira_tamanho() -> tuple[int, int]:
    if sys.platform != "win32":
        return 0, 0
    import ctypes

    class SHQUERYRBINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("i64Size", ctypes.c_longlong), ("i64NumItems", ctypes.c_longlong)]

    info = SHQUERYRBINFO(ctypes.sizeof(SHQUERYRBINFO), 0, 0)
    if ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) != 0:
        return 0, 0
    return int(info.i64Size), int(info.i64NumItems)


def _esvaziar_lixeira() -> bool:
    if sys.platform != "win32":
        return False
    import ctypes

    return ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x1 | 0x2 | 0x4) in (0, -2147418113)


def _medir(chave: str, info: dict, prazo: float) -> tuple[int, int]:
    if info.get("lixeira"):
        return _lixeira_tamanho()
    total = n = 0
    for arq in info.get("arquivos", []):
        try:
            total += os.path.getsize(arq)
            n += 1
        except OSError:
            pass
    for _, tam in _varrer(info.get("pastas", []), info.get("horas", 0), prazo):
        total += tam
        n += 1
    return total, n


def analisar() -> str:
    prazo = time.time() + 12
    partes, soma = [], 0
    for chave, info in _locais().items():
        tam, n = _medir(chave, info, prazo)
        if tam >= 1024 ** 2:
            partes.append(f"- {info['rotulo']} [{chave}]: {_gb(tam)} ({n} itens)")
            soma += tam
    if not partes:
        return "Está tudo limpo: quase nada de temporário para apagar."
    return (f"Dá para liberar cerca de {_gb(soma)}:\n" + "\n".join(partes) +
            "\nArquivos pessoais (Downloads, Documentos...) não entram. Para limpar, use limpeza_executar.")


PADRAO_LIMPEZA = ["temporarios", "temporarios_windows", "cache_navegadores", "miniaturas", "relatorios_erro"]


def executar(locais: list | None = None) -> str:
    escolhidos = [l for l in (locais or PADRAO_LIMPEZA) if l in _locais()]
    if not escolhidos:
        return f"Erro: escolha entre {', '.join(_locais())}."
    info_por = _locais()
    prazo = time.time() + 120
    liberado = apagados = presos = 0
    for chave in escolhidos:
        info = info_por[chave]
        if info.get("lixeira"):
            tam, n = _lixeira_tamanho()
            if n and _esvaziar_lixeira():
                liberado += tam
                apagados += n
            continue
        alvos = list(info.get("arquivos", [])) + [c for c, _ in _varrer(info.get("pastas", []), info["horas"], prazo)]
        for arq in alvos:
            try:
                tam = os.path.getsize(arq)
                os.remove(arq)
                liberado += tam
                apagados += 1
            except OSError:
                presos += 1                # em uso por algum programa: fica para a próxima
        for pasta in info.get("pastas", []):   # pastas que ficaram vazias
            for raiz, subpastas, arquivos in os.walk(pasta, topdown=False) if limpavel(pasta) else []:
                if raiz != pasta and not subpastas and not arquivos:
                    try:
                        os.rmdir(raiz)
                    except OSError:
                        pass
    texto = f"Limpei {_gb(liberado)} ({apagados} arquivos)."
    if presos:
        texto += f" {presos} estavam em uso por programas abertos (ou são protegidos pelo Windows) e ficaram."
    return texto


def _pergunta_limpeza(a: dict) -> str:
    escolhidos = a.get("locais") or PADRAO_LIMPEZA
    rotulos = [_locais()[l]["rotulo"] for l in escolhidos if l in _locais()]
    return f"Posso apagar {', '.join(rotulos)}? Isso libera espaço e não dá para desfazer."


# ====================================================================== definições
DEFINICOES = [
    {"name": "pc_processos",
     "description": "Programas abertos no PC agrupados por nome, com quanto usam de memória e CPU (como o Gerenciador "
                    "de Tarefas). Use para 'o que está pesando?', 'quanto de memória o Chrome usa?', 'o PC está lento'.",
     "input_schema": {"type": "object", "properties": {
         "ordenar": {"type": "string", "enum": ["memoria", "cpu"]}, "quantidade": {"type": "integer"}}}},
    {"name": "pc_discos", "description": "Espaço livre e usado de cada disco (C:, D:...).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "pc_encerrar",
     "description": "Fecha à força um programa travado ou que fica em segundo plano (todos os processos dele). O "
                    "sistema pede confirmação. Processos do Windows são protegidos. Para fechar com calma use pc_fechar.",
     "input_schema": {"type": "object", "properties": {"programa": {"type": "string"}}, "required": ["programa"]}},
    {"name": "limpeza_analisar",
     "description": "Mede quanto dá para liberar: temporários do usuário e do Windows, cache dos navegadores, "
                    "miniaturas, relatórios de erro e Lixeira. Não apaga nada.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "limpeza_executar",
     "description": "Apaga os temporários escolhidos (o sistema pede confirmação). locais: temporarios, "
                    "temporarios_windows, cache_navegadores, miniaturas, relatorios_erro, lixeira. Sem 'locais', "
                    "limpa todos menos a Lixeira. Rode limpeza_analisar antes.",
     "input_schema": {"type": "object", "properties": {
         "locais": {"type": "array", "items": {"type": "string", "enum": [
             "temporarios", "temporarios_windows", "cache_navegadores", "miniaturas", "relatorios_erro",
             "lixeira"]}}}}},
]
FUNCOES = {"pc_processos": processos, "pc_discos": discos, "pc_encerrar": encerrar, "limpeza_analisar": analisar,
           "limpeza_executar": executar}

acoes.registrar_ferramenta("pc_processos", leitura=True)
acoes.registrar_ferramenta("pc_discos", leitura=True)
acoes.registrar_ferramenta("limpeza_analisar", leitura=True)
acoes.registrar_ferramenta("pc_encerrar", risco=acoes.CONFIRMAR, pergunta=_pergunta_encerrar,
                           descrever=lambda a: f"Fechou à força o {a.get('programa')}")
acoes.registrar_ferramenta("limpeza_executar", risco=acoes.CONFIRMAR, pergunta=_pergunta_limpeza,
                           descrever=lambda a: "Limpou arquivos temporários" +
                           (" e a Lixeira" if "lixeira" in (a.get("locais") or []) else ""))
