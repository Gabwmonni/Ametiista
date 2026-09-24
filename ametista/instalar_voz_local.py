"""Instala a voz clonada no próprio PC (XTTS-v2) num Python separado: voz_local\\.venv.

    python -m ametista.instalar_voz_local            (o instalar_voz_local.bat chama assim)

- Placa NVIDIA: PyTorch 2.8 com CUDA 12.8 (funciona nas RTX 50, como a 5060 Ti, e nas anteriores).
- Sem placa NVIDIA: PyTorch para processador (funciona, mas cada frase demora alguns segundos).
- coqui-tts e transformers ficam em versões conferidas juntas (versões novas do transformers quebram o XTTS).
- Baixa o modelo XTTS-v2 (~1,8 GB). A licença dele (CPML) é só para uso não comercial: ela pergunta antes.
Pode rodar de novo quantas vezes quiser: o que já está instalado fica.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import config, pasta_segura, voz_local

TORCH = "torch==2.8.0 torchaudio==2.8.0"
COQUI = ["coqui-tts==0.27.5", "transformers==4.57.6"]
INDICE = {"cuda": "https://download.pytorch.org/whl/cu128", "cpu": "https://download.pytorch.org/whl/cpu"}
MODELO = "tts_models/multilingual/multi-dataset/xtts_v2"
LICENCA = """  O modelo de voz XTTS-v2 é da Coqui e usa a licença CPML (Coqui Public Model License):
  pode usar de graça para fins pessoais e NÃO comerciais. Texto completo: https://coqui.ai/cpml"""


def placa_nvidia() -> str | None:
    """Nome da placa NVIDIA (pelo nvidia-smi, que vem com o driver), ou None."""
    exe = shutil.which("nvidia-smi") or r"C:\Windows\System32\nvidia-smi.exe"
    try:
        r = subprocess.run([exe, "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True,
                           timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    nome = r.stdout.strip().splitlines()[0].strip() if r.returncode == 0 and r.stdout.strip() else ""
    return nome or None


def _python_base() -> str:
    """O Python "de verdade" por trás do ambiente da Ametista (para criar outro ambiente ao lado)."""
    return getattr(sys, "_base_executable", None) or sys.executable


def _rodar(args: list[str], **kw) -> bool:
    print("  > " + " ".join(a if " " not in a else f'"{a}"' for a in args[1:]), flush=True)
    return subprocess.run(args, **kw).returncode == 0


def _pip(py: Path, *args: str) -> bool:
    return _rodar([str(py), "-m", "pip", "install", "--disable-pip-version-check", *args])


def _conferir(py: Path) -> dict | None:
    codigo = ("import json, torch, transformers; from TTS.api import TTS; "
              "print(json.dumps({'torch': torch.__version__, 'cuda': torch.cuda.is_available(), "
              "'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None, "
              "'transformers': transformers.__version__}))")
    r = subprocess.run([str(py), "-c", codigo], capture_output=True, text=True,
                       env={**os.environ, "PYTHONUTF8": "1"})
    if r.returncode != 0:
        print(r.stderr[-1500:])
        return None
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


def instalar() -> int:
    print(LICENCA)
    if not pasta_segura.perguntar("  Você concorda com essa licença? (S/N) "):
        print("  Tudo bem: a voz clonada no PC não foi instalada.")
        return 1
    py = voz_local.python()
    if not py.exists():
        print("\n  [1/4] Criando o Python da voz...")
        if not _rodar([_python_base(), "-m", "venv", str(voz_local.PASTA / ".venv")]) or not py.exists():
            print("  Não consegui criar o ambiente Python da voz.")
            return 1
    else:
        print("\n  [1/4] Python da voz já existe: conferindo.")
    _pip(py, "--upgrade", "pip", "-q")

    gpu = placa_nvidia()
    alvo = "cuda" if gpu else "cpu"
    print(f"\n  [2/4] PyTorch para {'a placa ' + gpu if gpu else 'o processador (não achei placa NVIDIA)'}"
          " - é o download maior, pode demorar...")
    atual = _conferir(py)
    if not atual or (alvo == "cuda" and not atual.get("cuda")) or not str(atual.get("torch", "")).startswith("2.8"):
        trocar = ["--force-reinstall"] if atual else []          # tinha a versão sem placa de vídeo: troca
        if not _pip(py, *TORCH.split(), *trocar, "--index-url", INDICE[alvo]):
            print("  Falha ao instalar o PyTorch. Confira a internet e rode de novo.")
            return 1

    print("\n  [3/4] Coqui TTS (XTTS-v2)...")
    if not _pip(py, *COQUI, "-q"):
        print("  Falha ao instalar o Coqui TTS. Confira a internet e rode de novo.")
        return 1
    info = _conferir(py)
    if not info:
        print("  A instalação não ficou funcionando (veja o erro acima).")
        return 1
    if gpu and not info.get("cuda"):
        print(f"  ! O PyTorch não enxergou a placa {gpu}. Atualize o driver da NVIDIA e rode de novo. "
              "Por enquanto a voz roda no processador.")

    print("\n  [4/4] Baixando o modelo de voz XTTS-v2 (~1,8 GB)...")
    baixar = f"from TTS.utils.manage import ModelManager; ModelManager().download_model('{MODELO}')"
    if not _rodar([str(py), "-c", baixar], env={**os.environ, "COQUI_TOS_AGREED": "1", "PYTHONUTF8": "1"}):
        print("  Falha ao baixar o modelo. Confira a internet e rode de novo.")
        return 1

    voz_local.PASTA.mkdir(parents=True, exist_ok=True)
    voz_local.MARCA.write_text(json.dumps({**info, "licenca_aceita": True, "instalado_em": time.strftime("%Y-%m-%d %H:%M")},
                                          ensure_ascii=False, indent=1), encoding="utf-8")
    onde = f"na placa {info['gpu']}" if info.get("cuda") else "no processador"
    print(f"\n  Voz clonada instalada (PyTorch {info['torch']}, rodando {onde}).")
    return 0


def main(argv: list[str]) -> int:
    codigo = instalar()
    if codigo or "--sem-teste" in argv:
        return codigo
    if not voz_local.referencias():
        print("\n  Agora coloque os áudios da voz em voz\\amostras e rode o clonar_voz.bat (opção 1).")
        return 0
    if pasta_segura.perguntar("\n  Já existem amostras da voz. Usar a voz clonada agora? (S/N) "):
        from . import clonar_voz

        config.salvar({"VOZ_PROVEDOR": "local"})
        saida = clonar_voz.testar_local()
        if saida:
            print(f"  Ouça o teste: {saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
