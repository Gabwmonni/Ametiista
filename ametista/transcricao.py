"""Transcrição (faster-whisper): onde roda e com que ajustes, para ela ouvir rápido.

- "auto" (padrão): usa a placa NVIDIA quando ela funciona de verdade; senão, o processador. A placa é testada
  num processo à parte (uma combinação ruim de placa e driver pode derrubar o processo em vez de dar erro), com
  o processador já ouvindo enquanto isso; o resultado fica guardado até o CTranslate2 ou o modelo mudarem.
- As bibliotecas da NVIDIA (cuBLAS e cuDNN) vêm de onde já estiverem no PC: da voz clonada (o PyTorch com CUDA
  do voz_local\\.venv), dos pacotes nvidia-* do pip ou do CUDA instalado.
- No processador: int8 e metade dos núcleos (de 4 a 8), em vez de 4 fixos.
- Aquecimento: o modelo transcreve um pedacinho de áudio logo ao carregar, então a primeira frase de verdade já
  sai rápida.

Teste da placa (o que o app roda sozinho):  python -m ametista.transcricao --testar-gpu small
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

from . import config, estado

TAXA = 16000
CHAVE_GPU = "whisper_gpu"          # no estado: {"chave": versão|modelo, "ok": bool}
ABRINDO = "whisper_gpu_abrindo"    # no estado enquanto abre na placa: se o app cair ali, da próxima vez não tenta
_pastas_prontas = False


def prompt() -> str:
    return (f"{config.NOME}, abre a Steam, toca no Spotify, abre o YouTube, "
            "o que tem na minha agenda amanhã? Que horas são?")


def opcoes(**extra) -> dict:
    """Ajustes de velocidade: busca gulosa, sem marcas de tempo e sem repetir com outra "temperatura"
    (repetir chega a dobrar o tempo num áudio difícil e quase nunca melhora um pedido curto)."""
    return {"language": "pt", "beam_size": 1, "condition_on_previous_text": False, "without_timestamps": True,
            "temperature": 0.0, "initial_prompt": prompt(), **extra}


def texto(modelo, audio: np.ndarray) -> str:
    segmentos, _ = modelo.transcribe(audio, **opcoes())
    return "".join(s.text for s in segmentos).strip()


def threads_cpu() -> int:
    return max(4, min(8, (os.cpu_count() or 4) // 2))


# ------------------------------------------------------------------ bibliotecas da NVIDIA
def pastas_cuda() -> list[Path]:
    """Pastas com cuBLAS/cuDNN que já existem no PC."""
    candidatas = []
    venv = config.RAIZ / "voz_local" / ".venv"
    candidatas += [venv / "Lib" / "site-packages" / "torch" / "lib"]                      # Windows
    candidatas += sorted((venv / "lib").glob("python3*/site-packages/torch/lib"))         # Linux
    for base in sys.path:
        nvidia = Path(base or ".") / "nvidia"
        for pacote in ("cublas", "cudnn", "cuda_runtime"):
            candidatas += [nvidia / pacote / "bin", nvidia / pacote / "lib"]
    if os.environ.get("CUDA_PATH"):
        candidatas.append(Path(os.environ["CUDA_PATH"]) / "bin")
    vistas, pastas = set(), []
    for p in candidatas:
        try:
            if p.is_dir() and str(p) not in vistas:
                vistas.add(str(p))
                pastas.append(p)
        except OSError:
            pass
    return pastas


def preparar_cuda() -> list[Path]:
    """Deixa as bibliotecas da NVIDIA ao alcance do CTranslate2 (uma vez por processo)."""
    global _pastas_prontas
    pastas = pastas_cuda()
    if _pastas_prontas:
        return pastas
    _pastas_prontas = True
    caminho = os.environ.get("PATH", "")
    novas = [str(p) for p in pastas if str(p) not in caminho]
    if novas:
        os.environ["PATH"] = os.pathsep.join(novas + [caminho])
    if hasattr(os, "add_dll_directory"):
        for p in pastas:
            try:
                os.add_dll_directory(str(p))
            except OSError:
                pass
    return pastas


def tem_placa() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def _tipo_gpu() -> str:
    try:
        import ctranslate2

        tipos = ctranslate2.get_supported_compute_types("cuda")
    except Exception:
        return "default"
    for t in ("int8_float16", "float16"):
        if t in tipos:
            return t
    return "default"


# ------------------------------------------------------------------ abrir o modelo
def _aquecer(modelo) -> None:
    ruido = (np.random.default_rng(0).standard_normal(TAXA) * 0.01).astype(np.float32)
    texto(modelo, ruido)


def abrir(dispositivo: str, nome: str | None = None):
    """Carrega e aquece o modelo no dispositivo ("cpu" ou "cuda"). Levanta exceção se não der."""
    from faster_whisper import WhisperModel

    nome = nome or config.WHISPER_MODELO
    if dispositivo == "cuda":
        preparar_cuda()
        modelo = WhisperModel(nome, device="cuda", compute_type=_tipo_gpu())
    else:
        modelo = WhisperModel(nome, device="cpu", compute_type="int8", cpu_threads=threads_cpu())
    _aquecer(modelo)
    return modelo


def _abrir_na_placa(nome: str):
    """Abre na placa marcando no estado; se o processo cair no meio, a marca fica e a próxima vez sabe."""
    estado.lembrar(ABRINDO, True)
    try:
        return abrir("cuda", nome)
    finally:
        estado.lembrar(ABRINDO, False)


def _chave(nome: str) -> str:
    try:
        import ctranslate2

        versao = ctranslate2.__version__
    except Exception:
        versao = "?"
    return f"{versao}|{nome}"


def placa_testada(nome: str) -> bool | None:
    """True/False se a placa já foi testada com este CTranslate2 e este modelo; None se ainda não."""
    r = estado.obter(CHAVE_GPU)
    if isinstance(r, dict) and r.get("chave") == _chave(nome):
        return bool(r.get("ok"))
    return None


def testar_placa(nome: str, limite: float = 300) -> bool:
    """Testa a placa num processo à parte (carrega, aquece e transcreve) e guarda o resultado."""
    preparar_cuda()
    try:
        r = subprocess.run([sys.executable, "-m", "ametista.transcricao", "--testar-gpu", nome],
                           cwd=str(config.RAIZ), capture_output=True, text=True, timeout=limite,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        ok = r.returncode == 0 and "PLACA OK" in r.stdout
        if not ok:
            print(f"[ouvido] a placa NVIDIA não serviu para transcrever: {(r.stdout + r.stderr).strip()[-300:]}")
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"[ouvido] teste da placa NVIDIA não terminou: {e}")
        ok = False
    estado.lembrar(CHAVE_GPU, {"chave": _chave(nome), "ok": ok})
    return ok


class Carregador:
    """Abre o Whisper do jeito mais rápido que funcionar neste PC e avisa quando trocar para a placa."""

    def __init__(self, ao_trocar=None):
        self.ao_trocar = ao_trocar          # chamado com o modelo da placa, quando ele ficar pronto depois
        self.dispositivo = "cpu"

    def carregar(self):
        nome, pedido = config.WHISPER_MODELO, (config.WHISPER_DISPOSITIVO or "auto").lower()
        if estado.obter(ABRINDO):  # da última vez o app caiu abrindo na placa: desta vez, processador
            print("[ouvido] da última vez o app caiu ao abrir o Whisper na placa NVIDIA; usando o processador")
            estado.lembrar(ABRINDO, False)
            estado.lembrar(CHAVE_GPU, {"chave": _chave(nome), "ok": False})
            pedido = "cpu"
        if pedido == "cuda" or (pedido == "auto" and tem_placa() and placa_testada(nome)):
            try:
                modelo = _abrir_na_placa(nome)
                self.dispositivo = "cuda"
                return modelo
            except Exception as e:
                print(f"[ouvido] Whisper na placa NVIDIA falhou ({e}); usando o processador")
                if pedido == "auto":
                    estado.lembrar(CHAVE_GPU, {"chave": _chave(nome), "ok": False})
        modelo = abrir("cpu", nome)
        self.dispositivo = "cpu"
        if pedido == "auto" and placa_testada(nome) is None and tem_placa():
            # primeira vez com esta placa: o processador já ouve; a placa é testada à parte e entra se servir
            threading.Thread(target=self._tentar_placa, args=(nome,), daemon=True, name="whisper-placa").start()
        return modelo

    def _tentar_placa(self, nome: str) -> None:
        if not testar_placa(nome):
            return
        try:
            modelo = _abrir_na_placa(nome)
        except Exception as e:
            print(f"[ouvido] Whisper na placa NVIDIA falhou ({e}); continuando no processador")
            estado.lembrar(CHAVE_GPU, {"chave": _chave(nome), "ok": False})
            return
        self.dispositivo = "cuda"
        print("[ouvido] Whisper passou para a placa NVIDIA")
        if self.ao_trocar:
            self.ao_trocar(modelo)


def _testar_gpu_aqui(nome: str) -> int:
    t = time.time()
    modelo = abrir("cuda", nome)
    carga = time.time() - t
    fala = (np.sin(np.linspace(0, 440 * 2 * np.pi * 3, TAXA * 3)) * 0.1).astype(np.float32)
    t = time.time()
    texto(modelo, fala)
    print(f"PLACA OK ({_tipo_gpu()}; carregou em {carga:.1f} s, 3 s de áudio em {time.time() - t:.2f} s)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--testar-gpu":
        sys.exit(_testar_gpu_aqui(sys.argv[2]))
    print(__doc__)
