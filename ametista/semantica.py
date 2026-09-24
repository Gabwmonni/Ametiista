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
_aquecendo = False
_ao_ficar_pronto: list = []
_trava = threading.Lock()          # carregamento do modelo
_trava_aviso = threading.Lock()    # fila de quem espera o modelo ficar pronto


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


def pronto() -> bool:
    """O modelo já está na memória (usar agora não trava ninguém)."""
    return _modelo is not None


def aquecer(depois=None) -> None:
    """Carrega (e baixa, na primeira vez) o modelo em segundo plano, sem atrasar nenhum pedido.
    `depois` roda uma vez, em segundo plano, quando o modelo estiver pronto."""
    global _aquecendo
    if not config.BUSCA_SEMANTICA or _falhou:
        return
    with _trava_aviso:
        if _modelo is not None:
            if depois:
                threading.Thread(target=_avisar, args=([depois],), daemon=True).start()
            return
        if depois:
            _ao_ficar_pronto.append(depois)
        if _aquecendo:
            return
        _aquecendo = True
    threading.Thread(target=_rodar_aquecimento, daemon=True, name="semantica").start()


def _rodar_aquecimento() -> None:
    global _aquecendo
    _carregar()
    with _trava_aviso:
        _aquecendo = False
        esperando = _ao_ficar_pronto[:]
        _ao_ficar_pronto.clear()
    if _modelo is not None:
        _avisar(esperando)


def _avisar(funcoes) -> None:
    for f in funcoes:
        try:
            f()
        except Exception as e:
            print(f"[semantica] erro depois de carregar: {e}")


def situacao() -> str:
    if not config.BUSCA_SEMANTICA:
        return "desligada"
    if _modelo is not None:
        return "ativa"
    if _falhou:
        return "indisponível"
    return "carregando"


def disponivel() -> bool:
    return bool(config.BUSCA_SEMANTICA) and _modelo is not None


def vetores(textos: list[str], esperar: bool = False) -> np.ndarray | None:
    """Uma linha normalizada por texto, ou None se a busca por significado estiver desligada ou ainda
    carregando. esperar=True (só em segundo plano) espera o modelo carregar."""
    if not textos or not config.BUSCA_SEMANTICA:
        return None
    if _modelo is None:
        if not esperar:
            aquecer()
            return None
        if _carregar() is None:
            return None
    try:
        v = np.asarray(list(_modelo.embed([t[:1000] for t in textos])), dtype=np.float32)
    except Exception as e:
        print(f"[semantica] erro ao gerar vetores: {e}")
        return None
    v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
    return v


def vetor(texto: str, esperar: bool = False) -> np.ndarray | None:
    v = vetores([texto], esperar=esperar)
    return None if v is None else v[0]


def baixar() -> bool:
    """Usado pelo instalar.bat: baixa o modelo antes do primeiro uso."""
    return _carregar() is not None
