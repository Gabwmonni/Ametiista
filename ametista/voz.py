"""Voz da Ametista (fala).

VOZ_PROVEDOR no .env:
  elevenlabs -> voz clonada na ElevenLabs (melhor qualidade em português; plano pago a partir de ~US$ 5/mês)
  local      -> voz clonada rodando no seu PC com XTTS-v2 (grátis; precisa de placa NVIDIA para ficar rápido)
  edge       -> vozes neurais prontas da Microsoft (grátis, sem clonagem)

Se o provedor escolhido falhar, cai automaticamente no "edge", e depois na voz do sistema.
Para clonar uma voz: python -m ametista.clonar_voz  (veja o LEIA-ME)
"""
import asyncio
import base64
import hashlib
import io
import threading
import wave

import httpx

from . import config

CACHE = config.DADOS / "cache_voz"
CACHE.mkdir(exist_ok=True)


# ------------------------------------------------------------------ edge-tts (padrão, sem clonagem)
async def _edge(texto: str) -> bytes | None:
    import edge_tts

    partes = bytearray()
    async for pedaco in edge_tts.Communicate(texto, config.VOZ, rate="+5%").stream():
        if pedaco["type"] == "audio":
            partes.extend(pedaco["data"])
    return bytes(partes) or None


# ------------------------------------------------------------------ ElevenLabs (voz clonada na nuvem)
async def _elevenlabs(texto: str) -> bytes | None:
    if not (config.ELEVENLABS_API_KEY and config.ELEVENLABS_VOZ_ID):
        raise RuntimeError("ELEVENLABS_API_KEY/ELEVENLABS_VOZ_ID não configurados")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOZ_ID}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": config.ELEVENLABS_API_KEY},
            json={"text": texto, "model_id": config.ELEVENLABS_MODELO, "language_code": "pt",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.85, "style": 0.15,
                                     "use_speaker_boost": True}})
        r.raise_for_status()
        return r.content


# ------------------------------------------------------------------ XTTS-v2 (voz clonada no PC)
_xtts = None
_trava_xtts = threading.Lock()


def _xtts_sintetizar(texto: str) -> bytes:
    global _xtts
    with _trava_xtts:
        if _xtts is None:
            import torch
            from TTS.api import TTS

            dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
            _xtts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(dispositivo)
        refs = sorted(str(p) for p in config.VOZ_REFERENCIAS.glob("*.wav"))
        if not refs:
            raise RuntimeError(f"Nenhuma amostra .wav em {config.VOZ_REFERENCIAS}")
        amostras = _xtts.tts(text=texto, speaker_wav=refs, language="pt")
    return _para_wav(amostras, 24000)


def _para_wav(amostras, taxa: int) -> bytes:
    import numpy as np

    pcm = (np.clip(np.asarray(amostras, dtype=np.float32), -1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


async def _local(texto: str) -> bytes | None:
    return await asyncio.to_thread(_xtts_sintetizar, texto)


PROVEDORES = {"edge": _edge, "elevenlabs": _elevenlabs, "local": _local}


def _chave_cache(provedor: str, texto: str) -> str:
    voz = {"edge": config.VOZ, "elevenlabs": config.ELEVENLABS_VOZ_ID, "local": "xtts"}.get(provedor, "")
    return hashlib.sha1(f"{provedor}|{voz}|{texto}".encode()).hexdigest()


async def sintetizar(texto: str) -> str | None:
    """Devolve o áudio (mp3 ou wav) em base64, ou None para usar a voz do sistema."""
    if not texto:
        return None
    ordem = [config.VOZ_PROVEDOR] + (["edge"] if config.VOZ_PROVEDOR != "edge" else [])
    for provedor in ordem:
        funcao = PROVEDORES.get(provedor)
        if not funcao:
            continue
        chave = _chave_cache(provedor, texto)
        arq = CACHE / chave
        if len(texto) <= 80 and arq.exists():  # frases curtas repetidas ("Pronto!") saem do cache
            return base64.b64encode(arq.read_bytes()).decode()
        try:
            audio = await funcao(texto)
        except Exception as e:
            print(f"[voz] {provedor} falhou: {e}")
            continue
        if audio:
            if len(texto) <= 80:
                try:
                    arq.write_bytes(audio)
                except OSError:
                    pass
            return base64.b64encode(audio).decode()
    return None
