"""A voz clonada no próprio PC, vista da Ametista: abre o servidor de voz (voz_local_servidor.py, no Python
separado em voz_local\\.venv), espera ele ficar pronto e pede as falas.

- Instalação: instalar_voz_local.bat (PyTorch para a placa NVIDIA, com CUDA 12.8 para as RTX 50; sem placa, a
  versão para processador). Ele grava voz_local\\instalado.json quando tudo funciona.
- Enquanto o modelo carrega (uns 20 segundos com placa de vídeo), as falas saem na voz pronta da Microsoft.
- O servidor fecha sozinho quando a Ametista fecha (e ela fecha ele na saída).
"""
import atexit
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

from . import config

PASTA = config.RAIZ / "voz_local"
MARCA = PASTA / "instalado.json"
LOG = config.DADOS / "voz_local.log"


class Carregando(RuntimeError):
    """O servidor ainda está abrindo: esta fala sai na voz de reserva."""


def python() -> Path:
    return PASTA / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def info_instalacao() -> dict:
    try:
        return json.loads(MARCA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def instalado() -> bool:
    return python().exists() and bool(info_instalacao())


def referencias() -> list[Path]:
    return sorted(config.VOZ_REFERENCIAS.glob("*.wav")) if config.VOZ_REFERENCIAS.exists() else []


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Servidor:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.porta = 0
        self.token = ""
        self._trava = threading.Lock()
        self._saude: tuple[float, dict | None] = (0.0, None)

    # ---------------------------------------------------------------- ciclo
    def rodando(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def iniciar(self) -> bool:
        """Abre o servidor (se ainda não estiver aberto). Devolve False se a voz local não estiver instalada."""
        with self._trava:
            if self.rodando():
                return True
            if not instalado() or not referencias():
                return False
            self.porta, self.token = _porta_livre(), secrets.token_urlsafe(24)
            env = {**os.environ, "AMETISTA_VOZ_TOKEN": self.token, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
            if info_instalacao().get("licenca_aceita"):
                env["COQUI_TOS_AGREED"] = "1"
            LOG.parent.mkdir(parents=True, exist_ok=True)
            saida = open(LOG, "a", encoding="utf-8", errors="replace")
            saida.write(f"\n===== {time.strftime('%d/%m/%Y %H:%M:%S')} abrindo a voz local\n")
            saida.flush()
            self.proc = subprocess.Popen(
                [str(python()), "-m", "ametista.voz_local_servidor", "--porta", str(self.porta),
                 "--referencias", str(config.VOZ_REFERENCIAS), "--cache", str(config.DADOS / "voz_local"),
                 "--pai", str(os.getpid())],
                cwd=str(config.RAIZ), env=env, stdout=saida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            saida.close()
            self._saude = (0.0, None)
            return True

    def parar(self) -> None:
        with self._trava:
            proc, self.proc = self.proc, None
        if proc is None or proc.poll() is not None:
            return
        try:
            httpx.post(f"http://127.0.0.1:{self.porta}/sair", headers={"X-Token": self.token}, json={}, timeout=2)
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    # ---------------------------------------------------------------- estado
    def saude(self, cache_s: float = 2.0) -> dict | None:
        quando, dados = self._saude
        if time.time() - quando < cache_s and dados is not None:
            return dados
        if not self.rodando():
            return None
        try:
            dados = httpx.get(f"http://127.0.0.1:{self.porta}/saude", timeout=2).json()
        except Exception:
            dados = {"pronto": False, "etapa": "abrindo", "erro": None}
        self._saude = (time.time(), dados)
        return dados

    def pronto(self) -> bool:
        s = self.saude()
        return bool(s and s.get("pronto"))

    def esperar(self, segundos: float = 180) -> dict | None:
        """Espera o modelo carregar (para o clonar_voz e os testes)."""
        fim = time.time() + segundos
        while time.time() < fim:
            s = self.saude(cache_s=0)
            if s is None or s.get("pronto") or s.get("erro"):
                return s
            time.sleep(1)
        return self.saude(cache_s=0)

    # ---------------------------------------------------------------- falar
    def falar(self, texto: str, velocidade: float = 1.0, espera: float = 35) -> bytes:
        if not self.rodando():
            if not self.iniciar():
                raise RuntimeError("a voz local não está instalada (rode o instalar_voz_local.bat)")
            raise Carregando("abrindo a voz local")
        s = self.saude()
        if not s or not s.get("pronto"):
            if s and s.get("erro"):
                raise RuntimeError(f"a voz local deu erro: {s['erro']}")
            raise Carregando((s or {}).get("etapa", "abrindo"))
        r = httpx.post(f"http://127.0.0.1:{self.porta}/falar", headers={"X-Token": self.token},
                       json={"texto": texto, "velocidade": velocidade}, timeout=espera)
        if r.status_code == 503:
            raise Carregando(r.json().get("erro", "carregando"))
        r.raise_for_status()
        return r.content


_servidor = Servidor()
atexit.register(_servidor.parar)


def servidor() -> Servidor:
    return _servidor


def falar(texto: str) -> bytes:
    return _servidor.falar(texto)


def aquecer() -> None:
    """Na abertura da Ametista: se a voz escolhida é a local, já começa a carregar o modelo."""
    if config.VOZ_PROVEDOR == "local" and instalado():
        threading.Thread(target=_servidor.iniciar, daemon=True, name="voz-local").start()


def resumo() -> dict:
    """Para o diagnóstico e o painel."""
    info = info_instalacao()
    s = _servidor.saude() if _servidor.rodando() else None
    return {"instalado": instalado(), "referencias": len(referencias()), "gpu": info.get("gpu"),
            "cuda": info.get("cuda"), "rodando": _servidor.rodando(), "pronto": bool(s and s.get("pronto")),
            "etapa": (s or {}).get("etapa"), "erro": (s or {}).get("erro"), "dispositivo": (s or {}).get("dispositivo")}
