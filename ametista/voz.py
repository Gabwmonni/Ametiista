"""Voz da Ametista (fala).

VOZ_PROVEDOR no .env (ou no painel):
  elevenlabs -> voz clonada na ElevenLabs (melhor qualidade em português; plano pago a partir de ~US$ 5/mês)
  local      -> voz clonada rodando no seu PC com XTTS-v2 (grátis; precisa de placa NVIDIA para ficar rápido)
  edge       -> vozes neurais prontas da Microsoft (grátis, sem clonagem)

Se o provedor escolhido falhar, cai automaticamente no "edge", e depois na voz do sistema.
Voz expressiva: com a ElevenLabs v3, marcas como [risada] e [suspiro] viram risadas e suspiros de verdade;
nas outras vozes elas são removidas antes de falar.
"""
import asyncio
import base64
import hashlib
import io
import re
import threading
import wave

import httpx

from . import config

CACHE = config.DADOS / "cache_voz"
CACHE.mkdir(exist_ok=True)

# marca em português -> etiqueta de áudio da ElevenLabs v3
ETIQUETAS_V3 = {"risada": "[laughs]", "risadinha": "[chuckles]", "suspiro": "[sighs]", "sussurrando": "[whispers]",
                "animada": "[excited]", "surpresa_voz": "[surprised]", "pausa": "…"}
_MARCA = re.compile(r"\[\s*([a-zà-ú_]+)\s*\]", re.I)


def expressiva() -> bool:
    """A voz atual entende risadas, suspiros e pausas?"""
    return bool(config.VOZ_EXPRESSIVA) and config.VOZ_PROVEDOR == "elevenlabs" and \
        config.ELEVENLABS_MODELO == "eleven_v3" and bool(config.ELEVENLABS_API_KEY and config.ELEVENLABS_VOZ_ID)


def preparar_texto(texto: str, provedor: str) -> str:
    """Troca as marcas de expressão pelo formato do provedor (ou remove)."""
    v3 = provedor == "elevenlabs" and expressiva()

    def troca(m: re.Match) -> str:
        chave = m.group(1).lower()
        if chave == "pausa":
            return "…" if v3 else ","
        if v3 and chave in ETIQUETAS_V3:
            return ETIQUETAS_V3[chave]
        return ""
    t = _MARCA.sub(troca, texto)
    t = re.sub(r"\s+([,.!?…])", r"\1", t)
    t = re.sub(r"^[\s,]+", "", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def texto_para_mostrar(texto: str) -> str:
    """Tira todas as marcas [..] do texto que aparece na tela."""
    t = _MARCA.sub("", texto)
    t = re.sub(r"\s+([,.!?…])", r"\1", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def mime_de(audio_b64: str | None) -> str:
    return "audio/wav" if audio_b64 and audio_b64.startswith("UklGR") else "audio/mpeg"  # UklGR = "RIFF"


# ------------------------------------------------------------------ edge-tts (padrão, sem clonagem)
async def _edge(texto: str, voz: str | None = None, velocidade: str | None = None, tom: str | None = None) -> bytes | None:
    import edge_tts

    partes = bytearray()
    async for pedaco in edge_tts.Communicate(texto, voz or config.VOZ, rate=velocidade or config.VOZ_VELOCIDADE or "+0%",
                                             pitch=tom or config.VOZ_TOM or "+0Hz").stream():
        if pedaco["type"] == "audio":
            partes.extend(pedaco["data"])
    return bytes(partes) or None


def amostra_edge(texto: str, voz: str, velocidade: str, tom: str) -> str | None:
    """Para o painel: ouvir uma combinação de voz pronta antes de salvar (sem cache)."""
    try:
        audio = asyncio.run_coroutine_threadsafe(_edge(preparar_texto(texto, "edge"), voz, velocidade, tom),
                                                 _loop_voz()).result(timeout=30)
    except Exception as e:
        print(f"[voz] amostra falhou: {e}")
        return None
    return base64.b64encode(audio).decode() if audio else None


# ------------------------------------------------------------------ ElevenLabs (voz clonada na nuvem)
_http: httpx.AsyncClient | None = None


async def _elevenlabs(texto: str) -> bytes | None:
    global _http
    if not (config.ELEVENLABS_API_KEY and config.ELEVENLABS_VOZ_ID):
        raise RuntimeError("ELEVENLABS_API_KEY/ELEVENLABS_VOZ_ID não configurados")
    if _http is None:
        _http = httpx.AsyncClient(timeout=25)
    modelo = config.ELEVENLABS_MODELO
    corpo = {"text": texto, "model_id": modelo,
             "voice_settings": {"stability": 0.5 if modelo != "eleven_v3" else 0.45, "similarity_boost": 0.85,
                                "style": 0.15, "use_speaker_boost": True}}
    if "flash" in modelo or "turbo" in modelo:  # só esses aceitam forçar o idioma
        corpo["language_code"] = "pt"
    r = await _http.post(f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOZ_ID}",
                         params={"output_format": "mp3_44100_128"},
                         headers={"xi-api-key": config.ELEVENLABS_API_KEY}, json=corpo)
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
    voz = {"edge": f"{config.VOZ}{config.VOZ_VELOCIDADE}{config.VOZ_TOM}",
           "elevenlabs": f"{config.ELEVENLABS_VOZ_ID}{config.ELEVENLABS_MODELO}", "local": "xtts"}.get(provedor, "")
    return hashlib.sha1(f"{provedor}|{voz}|{texto}".encode()).hexdigest()


async def sintetizar(texto: str) -> str | None:
    """Devolve o áudio (mp3 ou wav) em base64, ou None para usar a voz do sistema."""
    if not texto or not texto.strip():
        return None
    ordem = [config.VOZ_PROVEDOR] + (["edge"] if config.VOZ_PROVEDOR != "edge" else [])
    for provedor in ordem:
        funcao = PROVEDORES.get(provedor)
        if not funcao:
            continue
        falado = preparar_texto(texto, provedor)
        if not re.search(r"\w", falado):
            return None
        chave = _chave_cache(provedor, falado)
        arq = CACHE / chave
        if len(falado) <= 80 and arq.exists():  # frases curtas repetidas ("Pronto!") saem do cache
            return base64.b64encode(arq.read_bytes()).decode()
        try:
            audio = await funcao(falado)
        except Exception as e:
            print(f"[voz] {provedor} falhou: {e}")
            continue
        if audio:
            if len(falado) <= 80:
                try:
                    arq.write_bytes(audio)
                except OSError:
                    pass
            return base64.b64encode(audio).decode()
    return None


# ------------------------------------------------------------------ uso a partir de threads comuns
_loop: asyncio.AbstractEventLoop | None = None
_trava_loop = threading.Lock()


def _loop_voz() -> asyncio.AbstractEventLoop:
    """Um laço assíncrono só da voz, para várias frases serem geradas ao mesmo tempo."""
    global _loop
    with _trava_loop:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, daemon=True, name="voz").start()
        return _loop


def sintetizar_sync(texto: str, espera: float = 40) -> str | None:
    """Versão bloqueante de sintetizar() (para threads de trabalho)."""
    try:
        return asyncio.run_coroutine_threadsafe(sintetizar(texto), _loop_voz()).result(timeout=espera)
    except Exception as e:
        print(f"[voz] não gerou a fala: {e}")
        return None
