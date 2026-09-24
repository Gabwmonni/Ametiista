"""Liga/desliga a Ametista junto com o Windows (registro do usuário, sem precisar de administrador)."""
import sys
from pathlib import Path

from . import config

CHAVE = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOME = "Ametista"


def _comando() -> str:
    # pythonw.exe = sem janela preta de console
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe") if exe.name.lower() == "python.exe" else exe
    return f'"{pythonw}" "{config.RAIZ / "ametista.pyw"}"'


def ativo() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE) as k:
            winreg.QueryValueEx(k, NOME)
            return True
    except OSError:
        return False


def definir(ligar: bool) -> None:
    if sys.platform != "win32":
        print("[autoinicio] só funciona no Windows")
        return
    import winreg

    if ligar:  # a chave Run pode não existir num perfil novo do Windows: cria
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, CHAVE, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, NOME, 0, winreg.REG_SZ, _comando())
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, NOME)
        except OSError:
            pass  # já estava desligado
    print(f"[autoinicio] {'ligado' if ligar else 'desligado'}")
