"""Mouse, teclado e janelas do Windows (usado pela IA e pelo modo agente).

Coordenadas: a IA vê um print reduzido da tela. Tudo o que ela aponta ou clica está nas coordenadas
DAQUELE print; aqui convertemos para os pixels reais da tela antes de agir.
"""
import os
import re
import sys
import threading
import time

from . import eventos

WINDOWS = sys.platform == "win32"
ultima_captura: dict | None = None   # {"x0", "y0", "escala", "largura", "altura", "quando"}
_trava = threading.Lock()


# ====================================================================== captura da tela
def limites(modelo: str | None) -> tuple[int, int]:
    """(maior lado, total de pixels) que o modelo aceita sem reduzir a imagem por conta própria."""
    if modelo and modelo.startswith(("claude-opus-5", "claude-sonnet-5", "claude-fable", "claude-mythos",
                                     "claude-opus-4-7", "claude-opus-4-8")):
        return 1920, 1920 * 1080          # 1080p: bom equilíbrio entre precisão e custo
    return 1568, 1_150_000


def capturar(monitor: str = "principal", modelo: str | None = None):
    """Print da tela reduzido para caber no modelo. Devolve (imagem PIL, geometria)."""
    import math

    import mss
    from PIL import Image

    with (getattr(mss, "MSS", None) or mss.mss)() as s:  # mss 10+ renomeou para MSS
        alvo = s.monitors[0] if monitor == "todos" or len(s.monitors) < 2 else s.monitors[1]
        bruto = s.grab(alvo)
        img = Image.frombytes("RGB", bruto.size, bruto.rgb)
    max_lado, max_px = limites(modelo)
    w, h = img.size
    escala = min(1.0, max_lado / max(w, h), math.sqrt(max_px / (w * h)))
    if escala < 1.0:
        img = img.resize((max(1, int(w * escala)), max(1, int(h * escala))), Image.LANCZOS)
    geo = {"x0": alvo["left"], "y0": alvo["top"], "escala": escala, "largura": img.size[0],
           "altura": img.size[1], "quando": time.time()}
    return img, geo


def lembrar_captura(geo: dict) -> None:
    global ultima_captura
    with _trava:
        ultima_captura = geo


def para_tela(x: float, y: float, geo: dict | None = None) -> tuple[int, int]:
    """Coordenada do print -> pixel real da tela."""
    geo = geo or ultima_captura
    if not geo:
        raise RuntimeError("Olhe a tela antes (pc_ver_tela) para eu saber onde fica cada coisa.")
    x = min(max(float(x), 0), geo["largura"] - 1)
    y = min(max(float(y), 0), geo["altura"] - 1)
    return int(round(geo["x0"] + x / geo["escala"])), int(round(geo["y0"] + y / geo["escala"]))


def _exigir_windows() -> None:
    if not WINDOWS:
        raise RuntimeError("controle do mouse e das janelas só funciona no Windows")


# ====================================================================== mouse
_BOTOES = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}


def posicao_cursor() -> tuple[int, int]:
    _exigir_windows()
    import ctypes
    import ctypes.wintypes

    p = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def mover(sx: int, sy: int) -> None:
    _exigir_windows()
    import ctypes

    ctypes.windll.user32.SetCursorPos(int(sx), int(sy))


def _com_modificadores(modificadores: str, acao) -> None:
    teclas = [traduzir_tecla(t) for t in re.split(r"[+ ]+", modificadores or "") if t.strip()]
    if not teclas:
        acao()
        return
    import keyboard

    for t in teclas:
        keyboard.press(t)
    try:
        acao()
    finally:
        for t in reversed(teclas):
            keyboard.release(t)


def clicar(sx: int, sy: int, botao: str = "left", vezes: int = 1, modificadores: str = "") -> None:
    _exigir_windows()
    import ctypes

    desce, sobe = _BOTOES.get(botao, _BOTOES["left"])
    mover(sx, sy)
    time.sleep(0.03)

    def cliques():
        for i in range(max(1, int(vezes))):
            ctypes.windll.user32.mouse_event(desce, 0, 0, 0, 0)
            time.sleep(0.02)
            ctypes.windll.user32.mouse_event(sobe, 0, 0, 0, 0)
            if i < vezes - 1:
                time.sleep(0.06)
    _com_modificadores(modificadores, cliques)


def botao_esquerdo(apertar: bool) -> None:
    _exigir_windows()
    import ctypes

    ctypes.windll.user32.mouse_event(0x0002 if apertar else 0x0004, 0, 0, 0, 0)


def arrastar(de: tuple[int, int], para: tuple[int, int], modificadores: str = "") -> None:
    _exigir_windows()

    def arrasto():
        mover(*de)
        time.sleep(0.05)
        botao_esquerdo(True)
        passos = 12
        for i in range(1, passos + 1):
            mover(de[0] + (para[0] - de[0]) * i // passos, de[1] + (para[1] - de[1]) * i // passos)
            time.sleep(0.015)
        botao_esquerdo(False)
    _com_modificadores(modificadores, arrasto)


def rolar(sx: int | None, sy: int | None, direcao: str, quantidade: int = 3, modificadores: str = "") -> None:
    _exigir_windows()
    import ctypes

    if sx is not None and sy is not None:
        mover(sx, sy)
    direcao = {"cima": "up", "baixo": "down", "esquerda": "left", "direita": "right"}.get(direcao, direcao)
    n = max(1, min(int(quantidade), 50))

    def rolagem():
        for _ in range(n):
            if direcao in ("up", "down"):
                ctypes.windll.user32.mouse_event(0x0800, 0, 0, 120 if direcao == "up" else -120, 0)
            else:
                ctypes.windll.user32.mouse_event(0x1000, 0, 0, 120 if direcao == "right" else -120, 0)
            time.sleep(0.02)
    _com_modificadores(modificadores, rolagem)


# ====================================================================== teclado
_TECLAS = {
    "return": "enter", "kp_enter": "enter", "enter": "enter", "escape": "esc", "esc": "esc",
    "backspace": "backspace", "back_space": "backspace", "delete": "delete", "del": "delete", "tab": "tab",
    "space": "space", "up": "up", "down": "down", "left": "left", "right": "right",
    "page_up": "page up", "prior": "page up", "pageup": "page up", "page_down": "page down", "next": "page down",
    "pagedown": "page down", "home": "home", "end": "end", "insert": "insert",
    "super": "windows", "super_l": "windows", "super_r": "windows", "win": "windows", "windows": "windows",
    "cmd": "windows", "meta": "windows", "control": "ctrl", "control_l": "ctrl", "control_r": "ctrl", "ctrl": "ctrl",
    "alt": "alt", "alt_l": "alt", "alt_r": "alt", "shift": "shift", "shift_l": "shift", "shift_r": "shift",
    "menu": "menu", "print": "print screen", "caps_lock": "caps lock", "minus": "-", "plus": "+",
    "equal": "=", "comma": ",", "period": ".", "slash": "/", "backslash": "\\", "semicolon": ";",
}


def traduzir_tecla(nome: str) -> str:
    n = nome.strip()
    chave = n.lower().replace(" ", "_")
    if chave in _TECLAS:
        return _TECLAS[chave]
    if re.fullmatch(r"f\d{1,2}", chave):
        return chave
    return n.lower() if len(n) > 1 else n


def pressionar(combinacao: str, repetir: int = 1) -> None:
    _exigir_windows()
    import keyboard

    combo = "+".join(traduzir_tecla(t) for t in combinacao.split("+") if t.strip())
    for _ in range(max(1, min(int(repetir), 100))):
        keyboard.send(combo)
        time.sleep(0.03)


def segurar(combinacao: str, segundos: float) -> None:
    _exigir_windows()
    import keyboard

    teclas = [traduzir_tecla(t) for t in combinacao.split("+") if t.strip()]
    for t in teclas:
        keyboard.press(t)
    try:
        time.sleep(max(0.0, min(float(segundos), 30)))
    finally:
        for t in reversed(teclas):
            keyboard.release(t)


def digitar(texto: str) -> None:
    _exigir_windows()
    import keyboard

    keyboard.write(texto, delay=0.004)


# ====================================================================== janelas
_u32 = None


def _user32():
    """user32 com os tipos dos parâmetros declarados (HWND é um ponteiro de 64 bits)."""
    global _u32
    if _u32 is None:
        import ctypes
        import ctypes.wintypes as w

        u = ctypes.WinDLL("user32", use_last_error=True)
        H = w.HWND
        for nome, args, ret in (
                ("GetWindowTextLengthW", [H], ctypes.c_int), ("GetWindowTextW", [H, w.LPWSTR, ctypes.c_int], ctypes.c_int),
                ("IsWindowVisible", [H], w.BOOL), ("IsIconic", [H], w.BOOL),
                ("GetWindowLongW", [H, ctypes.c_int], ctypes.c_long),
                ("PostMessageW", [H, w.UINT, w.WPARAM, w.LPARAM], w.BOOL), ("ShowWindow", [H, ctypes.c_int], w.BOOL),
                ("SetForegroundWindow", [H], w.BOOL), ("GetForegroundWindow", [], H),
                ("GetWindowThreadProcessId", [H, ctypes.POINTER(w.DWORD)], w.DWORD),
                ("GetWindowRect", [H, ctypes.POINTER(w.RECT)], w.BOOL)):
            f = getattr(u, nome)
            f.argtypes, f.restype = args, ret
        _u32 = u
    return _u32


def _titulo(hwnd) -> str:
    import ctypes

    u = _user32()
    n = u.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _pid(hwnd) -> int:
    import ctypes
    import ctypes.wintypes

    pid = ctypes.wintypes.DWORD()
    _user32().GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _escondida(hwnd) -> bool:
    import ctypes

    u = _user32()
    if not u.IsWindowVisible(hwnd):
        return True
    if u.GetWindowLongW(hwnd, -20) & 0x80:  # WS_EX_TOOLWINDOW
        return True
    try:
        cloaked = ctypes.c_int(0)
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value:
            return True
    except Exception:
        pass
    return False


def janelas() -> list[dict]:
    """Janelas visíveis, da mais à frente para a mais atrás (menos as da própria Ametista)."""
    _exigir_windows()
    import ctypes
    import ctypes.wintypes

    import psutil

    u = _user32()
    saida = []
    meu = os.getpid()
    PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

    def cada(hwnd, _):
        if not hwnd:
            return True
        try:
            titulo = _titulo(hwnd)
            if not titulo or _escondida(hwnd) or titulo in ("Program Manager",):
                return True
            pid = _pid(hwnd)
            if pid == meu:
                return True
            try:
                prog = psutil.Process(pid).name()
            except Exception:
                prog = ""
            saida.append({"hwnd": int(hwnd), "titulo": titulo, "programa": prog,
                          "minimizada": bool(u.IsIconic(hwnd))})
        except Exception:
            pass
        return True
    u.EnumWindows(PROC(cada), 0)
    return saida


def janela_alvo(alvo: str = "") -> int | None:
    """A janela da frente (que não seja a Ametista), ou a que tem `alvo` no título ou no programa."""
    if not WINDOWS:
        return None
    lista = janelas()
    if alvo.strip():
        a = alvo.strip().lower()
        for j in lista:
            if a in j["titulo"].lower() or a in j["programa"].lower().rsplit(".", 1)[0]:
                return j["hwnd"]
        return None
    frente = _user32().GetForegroundWindow()
    if frente and _pid(frente) != os.getpid() and any(j["hwnd"] == int(frente) for j in lista):
        return int(frente)
    return next((j["hwnd"] for j in lista if not j["minimizada"]), None)


def _focar(hwnd: int) -> None:
    u = _user32()
    if u.IsIconic(hwnd):
        u.ShowWindow(hwnd, 9)
    u.keybd_event(0x12, 0, 0, 0)          # ALT: o Windows deixa trocar o foco
    u.SetForegroundWindow(hwnd)
    u.keybd_event(0x12, 0, 0x0002, 0)


def janela_acao(acao: str, alvo: str = "", hwnd: int | None = None) -> str:
    _exigir_windows()
    if acao == "listar":
        lista = janelas()[:15]
        return "\n".join(f"{j['titulo'][:70]} ({j['programa']}){' [minimizada]' if j['minimizada'] else ''}"
                         for j in lista) or "Nenhuma janela aberta."
    hwnd = hwnd or janela_alvo(alvo)
    if not hwnd:
        return f"Não achei a janela {alvo}." if alvo else "Não achei nenhuma janela aberta."
    titulo = _titulo(hwnd)[:60] or "a janela"
    u = _user32()
    if acao == "fechar":
        u.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE: como clicar no X (o programa pergunta se quer salvar)
        return f"Fechei {titulo}."
    if acao == "minimizar":
        u.ShowWindow(hwnd, 6)
        return f"Minimizei {titulo}."
    if acao == "maximizar":
        u.ShowWindow(hwnd, 3)
        return f"Maximizei {titulo}."
    if acao == "restaurar":
        u.ShowWindow(hwnd, 9)
        return f"Restaurei {titulo}."
    if acao == "focar":
        _focar(hwnd)
        return f"Trouxe {titulo} para a frente."
    return f"Ação desconhecida: {acao}"


# ====================================================================== ferramentas (IA principal)
def _geo_recente() -> dict:
    if not ultima_captura or time.time() - ultima_captura["quando"] > 180:
        raise RuntimeError("Olhe a tela antes (pc_ver_tela) para eu saber onde fica cada coisa.")
    return ultima_captura


def ferramenta_clicar(x: float, y: float, botao: str = "esquerdo", duplo: bool = False) -> str:
    sx, sy = para_tela(x, y, _geo_recente())
    clicar(sx, sy, {"esquerdo": "left", "direito": "right", "meio": "middle"}.get(botao, "left"), 2 if duplo else 1)
    return "Cliquei."


def ferramenta_teclas(teclas: str, repetir: int = 1) -> str:
    pressionar(teclas, repetir)
    return f"Apertei {teclas}."


def ferramenta_rolar(direcao: str = "baixo", quantidade: int = 3, x: float | None = None,
                     y: float | None = None) -> str:
    sx = sy = None
    if x is not None and y is not None:
        sx, sy = para_tela(x, y, _geo_recente())
    rolar(sx, sy, direcao, quantidade)
    return "Rolei."


def ferramenta_janela(acao: str, alvo: str = "") -> str:
    return janela_acao(acao, alvo)


def ferramenta_apontar(x: float, y: float, rotulo: str = "") -> str:
    sx, sy = para_tela(x, y, _geo_recente())
    eventos.publicar({"tipo": "apontar", "x": sx, "y": sy, "rotulo": rotulo[:60], "interno": True})
    return "Mostrei na tela onde é (um círculo piscando)."


DEFINICOES = [
    {"name": "pc_janela",
     "description": "Fecha, minimiza, maximiza, restaura ou traz para a frente uma janela; ou lista as janelas. "
                    "Sem alvo = a janela da frente ('fecha essa janela').",
     "input_schema": {"type": "object", "properties": {
         "acao": {"type": "string", "enum": ["fechar", "minimizar", "maximizar", "restaurar", "focar", "listar"]},
         "alvo": {"type": "string", "description": "Parte do título ou nome do programa (opcional)"}},
         "required": ["acao"]}},
    {"name": "pc_apontar",
     "description": "Mostra na tela onde clicar (um círculo piscando). x e y em pixels do último pc_ver_tela.",
     "input_schema": {"type": "object", "properties": {
         "x": {"type": "number"}, "y": {"type": "number"}, "rotulo": {"type": "string"}}, "required": ["x", "y"]}},
    {"name": "pc_clicar",
     "description": "Clica num ponto da tela. x e y em pixels do último pc_ver_tela (olhe a tela antes).",
     "input_schema": {"type": "object", "properties": {
         "x": {"type": "number"}, "y": {"type": "number"},
         "botao": {"type": "string", "enum": ["esquerdo", "direito", "meio"]}, "duplo": {"type": "boolean"}},
         "required": ["x", "y"]}},
    {"name": "pc_teclas",
     "description": "Aperta uma tecla ou atalho no programa da frente (ex.: 'ctrl+s', 'enter', 'alt+tab').",
     "input_schema": {"type": "object", "properties": {
         "teclas": {"type": "string"}, "repetir": {"type": "integer"}}, "required": ["teclas"]}},
    {"name": "pc_rolar", "description": "Rola a página/janela (opcional: no ponto x, y do último pc_ver_tela).",
     "input_schema": {"type": "object", "properties": {
         "direcao": {"type": "string", "enum": ["cima", "baixo", "esquerda", "direita"]},
         "quantidade": {"type": "integer"}, "x": {"type": "number"}, "y": {"type": "number"}},
         "required": ["direcao"]}},
]
FUNCOES = {"pc_janela": ferramenta_janela, "pc_apontar": ferramenta_apontar, "pc_clicar": ferramenta_clicar,
           "pc_teclas": ferramenta_teclas, "pc_rolar": ferramenta_rolar}
