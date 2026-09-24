"""Busca por significado, 100% no PC (opcional).

Transforma frases em vetores com um modelo multilíngue pequeno (fastembed + ONNX, ~220 MB, baixado
uma vez para modelos/embeddings). "Onde está o desenho da obra de Jundiaí?" acha "guardei a planta de
Jundiaí na pasta Projetos" mesmo sem palavras em comum.

Se o fastembed não estiver instalado ou o modelo não baixar, tudo continua funcionando com a busca por
palavras (FTS) da memória.
"""
import threading

import numpy as np

from . import config

MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
PASTA = config.MODELOS / "embeddings"

_modelo = None
_falhou = False
_trava = threading.Lock()


def _carregar():
    global _modelo, _falhou
    with _trava:
        if _modelo is not None or _falhou:
            return _modelo
        try:
            from fastembed import TextEmbedding

            PASTA.mkdir(parents=True, exist_ok=True)
            _modelo = TextEmbedding(MODELO, cache_dir=str(PASTA))
        except Exception as e:
            print(f"[semantica] busca por significado indisponível: {e}")
            _falhou = True
        return _modelo


def disponivel() -> bool:
    return bool(config.BUSCA_SEMANTICA) and _carregar() is not None


def vetores(textos: list[str]) -> np.ndarray | None:
    """Uma linha normalizada por texto (ou None se a busca por significado estiver desligada)."""
    if not textos or not config.BUSCA_SEMANTICA:
        return None
    m = _carregar()
    if m is None:
        return None
    try:
        v = np.asarray(list(m.embed([t[:1000] for t in textos])), dtype=np.float32)
    except Exception as e:
        print(f"[semantica] erro ao gerar vetores: {e}")
        return None
    v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
    return v


def vetor(texto: str) -> np.ndarray | None:
    v = vetores([texto])
    return None if v is None else v[0]


def baixar() -> bool:
    """Usado pelo instalar.bat: baixa o modelo antes do primeiro uso."""
    return _carregar() is not None
