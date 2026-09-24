"""Baixa os modelos de voz offline (roda uma vez, pelo instalar.bat)."""
import io
import sys
import urllib.request
import zipfile

from . import config

VOSK_URL = "https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip"
VOZ_ID_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
              "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx")


def baixar_vosk() -> None:
    destino = config.VOSK_MODELO
    if destino.exists():
        print(f"Modelo de ativação já existe em {destino}")
        return
    print("Baixando modelo de palavra de ativação (Vosk, ~31 MB)...")
    dados = urllib.request.urlopen(VOSK_URL, timeout=120).read()
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        z.extractall(destino.parent)
    print("  ok")


def baixar_identificacao() -> None:
    destino = config.MODELO_VOZ_ID
    if destino.exists():
        print("Modelo de reconhecimento de quem fala já existe")
        return
    print("Baixando modelo de reconhecimento de quem fala (~40 MB)...")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(urllib.request.urlopen(VOZ_ID_URL, timeout=180).read())
    print("  ok")


def baixar_whisper() -> None:
    print(f"Baixando modelo de transcrição (Whisper '{config.WHISPER_MODELO}', ~250 a 500 MB)...")
    from faster_whisper import WhisperModel

    WhisperModel(config.WHISPER_MODELO, device="cpu", compute_type="int8")
    print("  ok")


def baixar_significado() -> None:
    """Opcional: modelo da busca por significado na memória (~220 MB)."""
    if not config.BUSCA_SEMANTICA:
        return
    import importlib.util

    if importlib.util.find_spec("fastembed") is None:
        print("Busca por significado: fastembed não instalado (a memória usa busca por palavras)")
        return
    print("Baixando modelo de busca por significado (~220 MB)...")
    from . import semantica

    print("  ok" if semantica.baixar() else "  não deu agora; ela tenta de novo sozinha quando ligar")


if __name__ == "__main__":
    erros = []
    for nome, baixar, essencial in (("palavra de ativação", baixar_vosk, True),
                                    ("reconhecimento de quem fala", baixar_identificacao, False),
                                    ("transcrição", baixar_whisper, True),
                                    ("busca por significado", baixar_significado, False)):
        try:
            baixar()
        except Exception as e:
            print(f"ERRO ao baixar o modelo de {nome}: {e}")
            if essencial:
                erros.append(nome)
    if erros:
        print("Sem internet ou bloqueado? Rode o instalar.bat de novo depois (ele continua de onde parou).")
        sys.exit(1)
