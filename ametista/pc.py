"""Controle do próprio PC (Windows): volume, mídia, programas, sites, tela, sistema."""
import base64
import difflib
import io
import json
import os
import re
import subprocess
import sys
import unicodedata
import webbrowser
from pathlib import Path

WINDOWS = sys.platform == "win32"
_SEM_JANELA = 0x08000000 if WINDOWS else 0  # CREATE_NO_WINDOW


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ",
                                      "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


def _tecla(nome: str, vezes: int = 1) -> None:
    import keyboard

    for _ in range(vezes):
        keyboard.send(nome)


# ================================================================== volume e mídia
def _volume_endpoint():
    from pycaw.pycaw import AudioUtilities

    alto_falante = AudioUtilities.GetSpeakers()
    if hasattr(alto_falante, "EndpointVolume"):  # pycaw recente
        return alto_falante.EndpointVolume
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import IAudioEndpointVolume

    interface = alto_falante.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def volume(acao: str, valor: int = 10) -> str:
    """acao: definir | aumentar | diminuir | mudo | som"""
    try:
        import comtypes

        comtypes.CoInitialize()  # necessário em threads de trabalho
        ep = _volume_endpoint()
        atual = round(ep.GetMasterVolumeLevelScalar() * 100)
        if acao == "mudo":
            ep.SetMute(1, None)
            return "Som mutado."
        if acao == "som":
            ep.SetMute(0, None)
            return f"Som de volta, volume em {atual}%."
        novo = {"definir": valor, "aumentar": atual + valor, "diminuir": atual - valor}.get(acao, atual)
        novo = max(0, min(100, int(novo)))
        ep.SetMute(0, None)
        ep.SetMasterVolumeLevelScalar(novo / 100, None)
        return f"Volume do PC em {novo}%."
    except ImportError:
        # Sem pycaw: usa as teclas de volume (cada toque = 2%)
        passos = max(1, int(valor) // 2)
        if acao == "aumentar":
            _tecla("volume up", passos)
        elif acao == "diminuir":
            _tecla("volume down", passos)
        elif acao in ("mudo", "som"):
            _tecla("volume mute")
        else:
            return "Para definir um valor exato, instale o pycaw."
        return "Feito."


def midia(acao: str) -> str:
    """Teclas de mídia: funcionam com qualquer player (YouTube, Spotify, VLC...)."""
    teclas = {"tocar_pausar": "play/pause media", "proxima": "next track", "anterior": "previous track",
              "parar": "stop media"}
    if acao not in teclas:
        return f"Ação desconhecida: {acao}"
    _tecla(teclas[acao])
    return "Feito."


# ================================================================== programas
SITES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com", "gmail": "https://mail.google.com",
    "whatsapp": "https://web.whatsapp.com", "whatsapp web": "https://web.whatsapp.com",
    "instagram": "https://www.instagram.com", "netflix": "https://www.netflix.com",
    "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai", "github": "https://github.com",
    "drive": "https://drive.google.com", "google drive": "https://drive.google.com",
    "agenda": "https://calendar.google.com", "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com", "twitch": "https://www.twitch.tv", "x": "https://x.com",
    "twitter": "https://x.com", "linkedin": "https://www.linkedin.com", "outlook": "https://outlook.live.com",
    "prime video": "https://www.primevideo.com", "disney": "https://www.disneyplus.com",
}
PASTAS = {
    "downloads": "Downloads", "documentos": "Documents", "area de trabalho": "Desktop", "desktop": "Desktop",
    "imagens": "Pictures", "fotos": "Pictures", "musicas": "Music", "videos": "Videos",
}
APELIDOS = {  # como a pessoa fala -> nome no Menu Iniciar
    "calculadora": "calculadora calculator", "bloco de notas": "bloco de notas notepad",
    "explorador": "explorador de arquivos file explorer", "configuracoes": "configuracoes settings",
    "chrome": "google chrome", "edge": "microsoft edge", "word": "word", "excel": "excel",
    "vs code": "visual studio code", "vscode": "visual studio code", "terminal": "terminal",
    "gerenciador de tarefas": "gerenciador de tarefas task manager", "zap": "whatsapp",
    "photoshop": "adobe photoshop", "fotoshop": "adobe photoshop",
}
_apps_cache: list[dict] | None = None


def _apps_instalados() -> list[dict]:
    """Todos os apps do Menu Iniciar (inclui os da Microsoft Store) via Get-StartApps."""
    global _apps_cache
    if _apps_cache is not None:
        return _apps_cache
    apps: list[dict] = []
    if WINDOWS:
        try:
            saida = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
                capture_output=True, timeout=20, creationflags=_SEM_JANELA).stdout.decode("utf-8", "ignore")
            dados = json.loads(saida or "[]")
            apps = [{"nome": d["Name"], "id": d["AppID"]} for d in (dados if isinstance(dados, list) else [dados])]
        except Exception as e:
            print(f"[pc] Get-StartApps falhou: {e}")
        if not apps:  # alternativa: atalhos .lnk do Menu Iniciar
            for base in (os.environ.get("APPDATA", ""), os.environ.get("PROGRAMDATA", "")):
                pasta = Path(base) / "Microsoft/Windows/Start Menu/Programs"
                for lnk in pasta.rglob("*.lnk"):
                    apps.append({"nome": lnk.stem, "caminho": str(lnk)})
    _apps_cache = apps
    return apps


def _achar_app(nome: str) -> dict | None:
    alvo = _norm(APELIDOS.get(_norm(nome), nome))
    apps = _apps_instalados()
    if not apps:
        return None
    nomes = [_norm(a["nome"]) for a in apps]
    for i, n in enumerate(nomes):  # igual
        if n == alvo:
            return apps[i]
    candidatos = [i for i, n in enumerate(nomes) if alvo in n or all(p in n for p in alvo.split())]
    if candidatos:  # contém: pega o nome mais curto (ex.: "Word" em vez de "Word Viewer")
        return apps[min(candidatos, key=lambda i: len(nomes[i]))]
    for pedaco in alvo.split():  # APELIDOS com alternativas separadas por espaço
        parecidos = difflib.get_close_matches(pedaco, nomes, n=1, cutoff=0.75)
        if parecidos:
            return apps[nomes.index(parecidos[0])]
    parecidos = difflib.get_close_matches(alvo, nomes, n=1, cutoff=0.6)
    return apps[nomes.index(parecidos[0])] if parecidos else None


def abrir(alvo: str) -> str:
    """Abre programa, site ou pasta pelo nome falado."""
    a = _norm(re.sub(r"^(o|a|os|as)\s+", "", alvo.strip(), flags=re.I))
    a = re.sub(r"\s+(pra mim|por favor|ai)$", "", a)
    if not a:
        return "Abrir o quê?"
    if re.match(r"^(https?://|www\.)|\.(com|br|org|net|io|ai)(/|$)", alvo.strip(), re.I):
        url = alvo.strip() if alvo.strip().startswith("http") else "https://" + alvo.strip()
        webbrowser.open(url)
        return f"Abrindo {alvo.strip()}."
    if a in PASTAS:
        caminho = Path.home() / PASTAS[a]
        _abrir_caminho(str(caminho))
        return f"Abrindo a pasta {alvo.strip()}."
    app = _achar_app(a)
    if a in SITES and (not app or _norm(app["nome"]) != a):  # "youtube" é site, a não ser que haja o app
        webbrowser.open(SITES[a])
        return f"Abrindo {alvo.strip()} no navegador."
    if app:
        if "id" in app:
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app['id']}"], creationflags=_SEM_JANELA)
        else:
            _abrir_caminho(app["caminho"])
        return f"Abrindo {app['nome']}."
    if a in SITES:
        webbrowser.open(SITES[a])
        return f"Abrindo {alvo.strip()} no navegador."
    return f"Não achei nenhum programa ou site chamado {alvo.strip()}."


def _abrir_caminho(caminho: str) -> None:
    if WINDOWS:
        os.startfile(caminho)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", caminho])


def fechar(programa: str) -> str:
    """Fecha um programa de forma educada (como clicar no X), sem forçar."""
    import psutil

    alvo = _norm(APELIDOS.get(_norm(programa), programa)).split()
    achados = set()
    for p in psutil.process_iter(["name"]):
        nome = _norm((p.info["name"] or "").rsplit(".", 1)[0])
        if nome and any(pedaco.replace(" ", "") in nome.replace(" ", "") for pedaco in alvo if len(pedaco) > 2):
            achados.add(p.info["name"])
    protegidos = {"explorer.exe", "python.exe", "pythonw.exe", "svchost.exe", "csrss.exe", "winlogon.exe"}
    achados -= protegidos
    if not achados:
        return f"Não encontrei {programa} aberto."
    for exe in achados:
        subprocess.run(["taskkill", "/im", exe], capture_output=True, creationflags=_SEM_JANELA)
    return f"Pedi para fechar: {', '.join(sorted(achados))}."


def pesquisar(consulta: str, onde: str = "google") -> str:
    from urllib.parse import quote_plus

    urls = {"google": "https://www.google.com/search?q=", "youtube": "https://www.youtube.com/results?search_query=",
            "maps": "https://www.google.com/maps/search/", "imagens": "https://www.google.com/search?tbm=isch&q="}
    webbrowser.open(urls.get(onde, urls["google"]) + quote_plus(consulta))
    return f"Pesquisando {consulta} no {onde}."


# ================================================================== sistema
def sistema(acao: str, confirmado: bool = False) -> str:
    """bloquear | suspender | desligar | reiniciar | cancelar_desligamento | minimizar_tudo"""
    if acao in ("desligar", "reiniciar", "suspender") and not confirmado:
        return f"PRECISA CONFIRMAR: pergunte ao usuário se ele quer mesmo {acao} o PC antes de repetir com confirmado=true."
    if not WINDOWS:
        return f"(simulado fora do Windows) {acao}"
    import ctypes

    if acao == "bloquear":
        ctypes.windll.user32.LockWorkStation()
        return "PC bloqueado."
    if acao == "minimizar_tudo":
        _tecla("windows+d")
        return "Janelas minimizadas."
    if acao == "suspender":
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=_SEM_JANELA)
        return "Suspendendo."
    if acao == "desligar":
        subprocess.run(["shutdown", "/s", "/t", "30"], creationflags=_SEM_JANELA)
        return "O PC desliga em 30 segundos. Diga 'cancela o desligamento' se mudar de ideia."
    if acao == "reiniciar":
        subprocess.run(["shutdown", "/r", "/t", "30"], creationflags=_SEM_JANELA)
        return "O PC reinicia em 30 segundos."
    if acao == "cancelar_desligamento":
        subprocess.run(["shutdown", "/a"], creationflags=_SEM_JANELA)
        return "Desligamento cancelado."
    return f"Ação desconhecida: {acao}"


def status() -> str:
    import psutil

    partes = [f"CPU {psutil.cpu_percent(interval=0.5):.0f}%",
              f"memória {psutil.virtual_memory().percent:.0f}% usada"]
    disco = psutil.disk_usage(str(Path.home().anchor or "/"))
    partes.append(f"disco com {disco.free / 1e9:.0f} GB livres")
    bateria = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if bateria:
        partes.append(f"bateria {bateria.percent:.0f}%{' carregando' if bateria.power_plugged else ''}")
    pesados = sorted(psutil.process_iter(["name", "memory_info"]),
                     key=lambda p: p.info["memory_info"].rss if p.info["memory_info"] else 0, reverse=True)[:3]
    partes.append("mais pesados: " + ", ".join(p.info["name"] for p in pesados))
    return "; ".join(partes) + "."


# ================================================================== tela e texto
def janela_ativa() -> tuple[str, str]:
    """(título, programa) da janela em foco."""
    if not WINDOWS:
        return "", ""
    try:
        import ctypes
        import ctypes.wintypes

        import psutil

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return buf.value, psutil.Process(pid.value).name()
    except Exception:
        return "", ""


def janela_ativa_texto() -> str:
    titulo, prog = janela_ativa()
    if not titulo or prog.lower().startswith("python"):
        return ""
    return f"Janela em foco no PC: \"{titulo[:120]}\" ({prog})."


def ver_tela(monitor: str = "principal") -> dict:
    """Print da tela (principal ou todas), reduzido, para a IA analisar."""
    import mss
    from PIL import Image

    with mss.mss() as s:
        alvo = s.monitors[0] if monitor == "todos" or len(s.monitors) < 2 else s.monitors[1]
        bruto = s.grab(alvo)
        img = Image.frombytes("RGB", bruto.size, bruto.rgb)
    img.thumbnail((1568, 1568))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    titulo = janela_ativa_texto()
    return {"imagem_b64": base64.b64encode(buf.getvalue()).decode(),
            "texto": f"Print da tela do usuário agora. {titulo}".strip()}


def area_transferencia(acao: str = "ler", texto: str = "") -> str:
    import pyperclip

    if acao == "escrever":
        pyperclip.copy(texto)
        return "Copiado para a área de transferência."
    conteudo = pyperclip.paste() or ""
    return conteudo[:6000] if conteudo else "A área de transferência está vazia."


def digitar(texto: str) -> str:
    """Digita o texto no campo onde o cursor estiver (ditado)."""
    import keyboard

    keyboard.write(texto, delay=0.005)
    return "Digitado."


# ================================================================== definições para o Claude
DEFINICOES = [
    {"name": "pc_volume", "description": "Volume geral do Windows.",
     "input_schema": {"type": "object", "properties": {
         "acao": {"type": "string", "enum": ["definir", "aumentar", "diminuir", "mudo", "som"]},
         "valor": {"type": "integer", "description": "Percentual (definir) ou quanto mudar (padrão 10)"}},
         "required": ["acao"]}},
    {"name": "pc_midia", "description": "Teclas de mídia do PC (qualquer player: YouTube, VLC...). "
                                        "Para o Spotify prefira as ferramentas spotify_*.",
     "input_schema": {"type": "object", "properties": {
         "acao": {"type": "string", "enum": ["tocar_pausar", "proxima", "anterior", "parar"]}},
         "required": ["acao"]}},
    {"name": "pc_abrir", "description": "Abre um programa instalado, site ou pasta (Downloads, Documentos...).",
     "input_schema": {"type": "object", "properties": {"alvo": {"type": "string"}}, "required": ["alvo"]}},
    {"name": "pc_fechar", "description": "Fecha um programa (como clicar no X). Confirme antes se houver risco "
                                         "de perder trabalho não salvo.",
     "input_schema": {"type": "object", "properties": {"programa": {"type": "string"}}, "required": ["programa"]}},
    {"name": "pc_pesquisar", "description": "Abre uma pesquisa no navegador.",
     "input_schema": {"type": "object", "properties": {
         "consulta": {"type": "string"},
         "onde": {"type": "string", "enum": ["google", "youtube", "maps", "imagens"]}},
         "required": ["consulta"]}},
    {"name": "pc_sistema", "description": "Bloquear, minimizar tudo, suspender, desligar, reiniciar ou cancelar "
                                          "desligamento. Desligar/reiniciar/suspender: SEMPRE pergunte antes e só "
                                          "use confirmado=true depois que o usuário disser sim.",
     "input_schema": {"type": "object", "properties": {
         "acao": {"type": "string", "enum": ["bloquear", "minimizar_tudo", "suspender", "desligar", "reiniciar",
                                              "cancelar_desligamento"]},
         "confirmado": {"type": "boolean"}}, "required": ["acao"]}},
    {"name": "pc_status", "description": "Uso de CPU, memória, disco, bateria e programas mais pesados.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "pc_ver_tela", "description": "Tira um print da tela para você ver o que o usuário está vendo "
                                           "(ex.: 'o que é esse erro?', 'resume essa página', 'o que tem na tela?').",
     "input_schema": {"type": "object", "properties": {
         "monitor": {"type": "string", "enum": ["principal", "todos"]}}}},
    {"name": "pc_area_transferencia", "description": "Lê o texto copiado (Ctrl+C) ou copia um texto.",
     "input_schema": {"type": "object", "properties": {
         "acao": {"type": "string", "enum": ["ler", "escrever"]}, "texto": {"type": "string"}},
         "required": ["acao"]}},
    {"name": "pc_digitar", "description": "Digita um texto onde o cursor estiver (ditado).",
     "input_schema": {"type": "object", "properties": {"texto": {"type": "string"}}, "required": ["texto"]}},
]

FUNCOES = {
    "pc_volume": volume, "pc_midia": midia, "pc_abrir": abrir, "pc_fechar": fechar, "pc_pesquisar": pesquisar,
    "pc_sistema": sistema, "pc_status": status, "pc_ver_tela": ver_tela,
    "pc_area_transferencia": area_transferencia, "pc_digitar": digitar,
}
