"""Voz clonada no PC: o servidor à parte (com um PyTorch e um XTTS de mentira), a escolha dos trechos de
referência e a conversão para MP3."""
import asyncio
import base64
import io
import json
import subprocess
import sys
import textwrap
import time
import wave
from pathlib import Path

import numpy as np
import pytest

from ametista import clonar_voz, config, diagnostico, voz, voz_local, voz_local_servidor

RAIZ = Path(__file__).resolve().parent.parent

TORCH_FALSO = '''
import contextlib, pickle
class _Cuda:
    @staticmethod
    def is_available(): return False
    @staticmethod
    def get_device_name(i=0): return "falsa"
cuda = _Cuda()
def inference_mode(): return contextlib.nullcontext()
def save(obj, f):
    with open(f, "wb") as fh: pickle.dump(obj, fh)
def load(f, map_location=None):
    with open(f, "rb") as fh: return pickle.load(fh)
'''
TTS_FALSO = '''
import os, time
import numpy as np
class T:
    def __init__(self, v): self.v = v
    def cpu(self): return self
    def to(self, d): return self
class Cfg:
    gpt_cond_len = 30; gpt_cond_chunk_len = 4; max_ref_len = 30; sound_norm_refs = False
    repetition_penalty = 5.0; top_k = 50; top_p = 0.85; length_penalty = 1.0
class Xtts:
    config = Cfg()
    def get_conditioning_latents(self, audio_path, **kw):
        with open(os.environ["VOZ_FALSA_LOG"], "a") as f: f.write("latentes %d\\n" % len(audio_path))
        return T(len(audio_path)), T(1)
    def inference(self, text, language, gpt, voz, speed=1.0, **kw):
        assert language == "pt" and len(text) <= 203, text
        with open(os.environ["VOZ_FALSA_LOG"], "a") as f: f.write("falar %s\\n" % text)
        n = int(24000 * 0.05 * len(text) / speed)
        t = np.arange(n) / 24000
        onda = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        return {"wav": np.concatenate([np.zeros(4800, np.float32), onda, np.zeros(9600, np.float32)])}
class _Sint:
    def __init__(self): self.tts_model = Xtts()
class TTS:
    def __init__(self, nome):
        assert nome.endswith("xtts_v2")
        time.sleep(float(os.environ.get("VOZ_FALSA_DEMORA", "0")))
        self.synthesizer = _Sint()
    def to(self, d): return self
'''


def _wav(caminho: Path, segundos: float = 2.0, taxa: int = 24000) -> None:
    t = np.arange(int(taxa * segundos)) / taxa
    pcm = (0.2 * np.sin(2 * np.pi * 230 * t) * 32767).astype(np.int16)
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm.tobytes())


def _duracao(wav: bytes) -> float:
    with wave.open(io.BytesIO(wav)) as w:
        return w.getnframes() / w.getframerate()


@pytest.fixture
def voz_falsa(tmp_path, monkeypatch):
    """Um "voz_local\\.venv" de mentira: o Python dos testes com torch e TTS falsos no caminho."""
    falsos = tmp_path / "falsos"
    (falsos / "torch").mkdir(parents=True)
    (falsos / "torch" / "__init__.py").write_text(TORCH_FALSO, encoding="utf-8")
    (falsos / "TTS").mkdir()
    (falsos / "TTS" / "__init__.py").write_text("", encoding="utf-8")
    (falsos / "TTS" / "api.py").write_text(TTS_FALSO, encoding="utf-8")
    refs = tmp_path / "referencia"
    refs.mkdir()
    _wav(refs / "ametista_01.wav")
    _wav(refs / "ametista_02.wav")
    marca = tmp_path / "instalado.json"
    marca.write_text(json.dumps({"licenca_aceita": True, "cuda": False, "gpu": None}), encoding="utf-8")
    log = tmp_path / "log.txt"
    log.write_text("", encoding="utf-8")
    monkeypatch.setattr(voz_local, "python", lambda: Path(sys.executable))
    monkeypatch.setattr(voz_local, "MARCA", marca)
    monkeypatch.setattr(config, "VOZ_REFERENCIAS", refs)
    monkeypatch.setenv("PYTHONPATH", str(falsos))
    monkeypatch.setenv("VOZ_FALSA_LOG", str(log))
    srv = voz_local.Servidor()
    monkeypatch.setattr(voz_local, "_servidor", srv)
    yield srv, log
    srv.parar()


# ---------------------------------------------------------------- servidor de verdade (modelo de mentira)
def test_servidor_abre_fala_e_fecha(voz_falsa):
    srv, log = voz_falsa
    assert srv.iniciar() and srv.rodando()
    s = srv.esperar(60)
    assert s and s["pronto"] and s["dispositivo"] == "cpu" and s["referencias"] == 2, s
    longo = ("Oi! Esta é uma frase de teste bem comprida, com várias vírgulas, pausas e ideias, para ver se o "
             "servidor divide o texto em pedaços que o XTTS aguenta, sem cortar palavra nenhuma no meio, e junta "
             "tudo de novo numa fala só. Fim.")
    wav = srv.falar(longo)
    assert wav[:4] == b"RIFF" and _duracao(wav) > 5
    falas = [l for l in log.read_text(encoding="utf-8").splitlines() if l.startswith("falar ")]
    assert len(falas) >= 3 and "Oi." in falas[0]                              # o "Oi." é o aquecimento
    assert all(len(l) - 6 <= voz_local_servidor.LIMITE for l in falas)
    assert "latentes 2" in log.read_text(encoding="utf-8")
    proc = srv.proc
    srv.parar()
    assert proc.wait(timeout=10) is not None and not srv.rodando()


def test_latentes_ficam_guardados(voz_falsa, tmp_path):
    srv, log = voz_falsa
    srv.iniciar()
    assert srv.esperar(60)["pronto"]
    srv.parar()
    srv.iniciar()
    assert srv.esperar(60)["pronto"]
    assert log.read_text(encoding="utf-8").count("latentes") == 1          # a segunda vez veio do disco


def test_senha_e_carregando(voz_falsa, monkeypatch):
    import httpx

    srv, _ = voz_falsa
    monkeypatch.setenv("VOZ_FALSA_DEMORA", "3")
    srv.iniciar()
    with pytest.raises(voz_local.Carregando):
        srv.falar("oi")
    time.sleep(0.8)
    r = httpx.post(f"http://127.0.0.1:{srv.porta}/falar", json={"texto": "oi"}, headers={"X-Token": "errada"})
    assert r.status_code == 403
    r = httpx.post(f"http://127.0.0.1:{srv.porta}/falar", json={"texto": "oi"}, headers={"X-Token": srv.token})
    assert r.status_code == 503
    assert srv.esperar(60)["pronto"]
    assert srv.falar("oi")[:4] == b"RIFF"


def test_enquanto_carrega_fala_com_a_voz_pronta(voz_falsa, monkeypatch):
    srv, _ = voz_falsa
    monkeypatch.setenv("VOZ_FALSA_DEMORA", "3")
    monkeypatch.setattr(config, "VOZ_PROVEDOR", "local")

    async def edge(texto):
        return b"EDGE-" + texto.encode()
    monkeypatch.setitem(voz.PROVEDORES, "edge", edge)
    audio = base64.b64decode(asyncio.run(voz.sintetizar("Olá, tudo bem com você hoje?")))
    assert audio.startswith(b"EDGE-") and srv.rodando()                      # já começou a carregar
    assert srv.esperar(60)["pronto"]
    audio = base64.b64decode(asyncio.run(voz.sintetizar("Olá, tudo bem com você hoje?")))
    assert audio[:3] == b"ID3" or audio[:2] == b"\xff\xfb"                   # voz clonada, em MP3


def test_servidor_fecha_sozinho_quando_a_ametista_fecha(voz_falsa, tmp_path):
    morto = subprocess.Popen([sys.executable, "-c", "pass"])
    morto.wait()
    import os

    env = {**os.environ, "AMETISTA_VOZ_TOKEN": "x"}
    proc = subprocess.Popen([sys.executable, "-m", "ametista.voz_local_servidor", "--porta", "0", "--referencias",
                             str(config.VOZ_REFERENCIAS), "--cache", str(tmp_path / "cache"), "--pai", str(morto.pid)],
                            cwd=str(RAIZ), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert proc.wait(timeout=20) == 0
    finally:
        proc.kill()


def test_sem_instalacao_nao_abre(monkeypatch, tmp_path):
    monkeypatch.setattr(voz_local, "MARCA", tmp_path / "nao_existe.json")
    srv = voz_local.Servidor()
    assert not srv.iniciar() and not srv.rodando()
    with pytest.raises(RuntimeError, match="instalar_voz_local"):
        srv.falar("oi")


def test_diagnostico_da_voz_local(voz_falsa, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "VOZ_PROVEDOR", "local")
    d = diagnostico._voz()
    assert d["situacao"] == "ok" and "voz clonada no PC, no processador" in d["detalhe"], d
    monkeypatch.setattr(voz_local, "MARCA", tmp_path / "nao_existe.json")
    assert "instalar_voz_local.bat" in diagnostico._voz()["detalhe"]


# ---------------------------------------------------------------- texto e áudio
def test_dividir_texto():
    assert voz_local_servidor.dividir("") == []
    assert voz_local_servidor.dividir("Oi. Tudo bem? Que bom!") == ["Oi. Tudo bem? Que bom!"]
    frase = "Palavra " * 60 + "fim."
    pedacos = voz_local_servidor.dividir(frase)
    assert all(len(p) <= voz_local_servidor.LIMITE for p in pedacos) and " ".join(pedacos) == frase.strip()
    texto = ("Primeiro eu vou ler o arquivo inteiro com bastante calma, depois vou resumir os pontos principais "
             "da matéria, separando o que é urgente do que pode esperar, e no fim te mando tudo num bloco de notas "
             "organizado. Combinado? Ok.")
    pedacos = voz_local_servidor.dividir(texto)
    assert pedacos[0].endswith("urgente do que pode esperar,") and pedacos[-1] == "Combinado? Ok."
    assert len(pedacos) == 3 and " ".join(pedacos) == texto


def test_aparar_tira_silencio_e_estalos():
    t = np.arange(24000) / 24000
    onda = np.concatenate([np.zeros(12000), 0.5 * np.sin(2 * np.pi * 200 * t), np.zeros(24000)]).astype(np.float32)
    aparada = voz_local_servidor._aparar(onda)
    assert 1.0 <= len(aparada) / 24000 <= 1.2 and abs(aparada[0]) < 1e-3 and abs(aparada[-1]) < 1e-3


def test_wav_para_mp3_fica_menor():
    buf = io.BytesIO()
    t = np.arange(24000 * 3) / 24000
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes((0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16).tobytes())
    mp3 = voz.wav_para_mp3(buf.getvalue())
    assert mp3 and len(mp3) < len(buf.getvalue()) / 4 and voz.mime_de(base64.b64encode(mp3).decode()) == "audio/mpeg"
    assert voz.wav_para_mp3(b"isso nao e wav") is None


# ---------------------------------------------------------------- escolher os trechos de referência
def _fala(segundos, f0, taxa=24000, amp=0.25, seed=0):
    """Som parecido com voz: tom com harmônicos e sílabas (volume subindo e descendo 4 vezes por segundo)."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(taxa * segundos)) / taxa
    f = f0 * (1 + 0.05 * np.sin(2 * np.pi * 0.7 * t))
    fase = 2 * np.pi * np.cumsum(f) / taxa
    onda = sum(np.sin(k * fase) / k for k in range(1, 6))
    silabas = 0.55 + 0.45 * np.sin(2 * np.pi * 4 * t + rng.uniform(0, 6))
    return (amp * onda * silabas / 2).astype(np.float32)


def _gravacao(pecas, taxa=24000, ruido=0.002):
    rng = np.random.default_rng(1)
    partes = []
    for p in pecas:
        partes.append(p if isinstance(p, np.ndarray) else np.zeros(int(taxa * p), dtype=np.float32))
    audio = np.concatenate(partes)
    return (audio + ruido * rng.standard_normal(len(audio))).astype(np.float32)


def test_escolhe_os_trechos_limpos(tmp_path, monkeypatch):
    monkeypatch.setattr(clonar_voz, "_modelo_vad", lambda: None)
    monkeypatch.setattr(config, "VOZ_REFERENCIAS", tmp_path / "referencia")
    taxa = 24000
    estourado = np.clip(_fala(7, 230, amp=3.0, seed=3), -1, 1)
    audio = _gravacao([1.0, _fala(7, 230, seed=1), 1.5, _fala(8, 110, seed=2), 1.5, estourado, 1.5,
                       _fala(8, 240, seed=4), 1.5, _fala(6.5, 225, seed=5), 1.5, _fala(2, 230, seed=6), 1.0])
    arq = tmp_path / "gravacao.wav"
    with wave.open(str(arq), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes((audio * 32767).astype(np.int16).tobytes())
    escolhidos = clonar_voz.preparar_local([arq], conferir=False)
    inicios = sorted(int(c["ini"]) for c in escolhidos)
    # fala limpa em 1 s, 27,5 s e 37 s; a voz grave (9,5 s), a estourada (19 s) e a curtinha (45 s) ficam de fora
    assert inicios == [1, 27, 37], [(round(c["ini"], 1), round(c["outra_voz"], 2), round(c["estouro"], 3))
                                     for c in escolhidos]
    wavs = sorted((tmp_path / "referencia").glob("*.wav"))
    assert [w.name for w in wavs] == ["ametista_01.wav", "ametista_02.wav", "ametista_03.wav"]
    with wave.open(str(wavs[0])) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 24000)
        dados = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16) / 32767
    assert 0.1 < np.max(np.abs(dados)) <= 0.9 and abs(dados[0]) < 0.01
    # clonar de novo guarda as anteriores
    clonar_voz.preparar_local([arq], conferir=False)
    assert len(list((tmp_path / "referencia_anterior").glob("*.wav"))) == 3


def test_whisper_descarta_musica(monkeypatch):
    class Seg:
        def __init__(self, texto, logprob=-0.3, silencio=0.05):
            self.text, self.avg_logprob, self.no_speech_prob = texto, logprob, silencio

    class Falso:
        def __init__(self, respostas):
            self.respostas = list(respostas)

        def transcribe(self, *a, **k):
            return iter(self.respostas.pop(0)), None

    monkeypatch.setattr(clonar_voz, "_whisper", Falso([[Seg(" Eu tenho tanta coisa pra te falar.")],
                                                       [Seg(" [Música]")], [Seg(" hmm", logprob=-1.6)], []]))
    trecho = np.zeros(24000, dtype=np.float32)
    assert clonar_voz._conferir_palavras(trecho) == "Eu tenho tanta coisa pra te falar."
    assert clonar_voz._conferir_palavras(trecho) is None
    assert clonar_voz._conferir_palavras(trecho) is None
    assert clonar_voz._conferir_palavras(trecho) is None                      # nada entendido


def test_tom_de_voz():
    t = np.arange(960) / 24000
    assert abs(clonar_voz._f0(np.sin(2 * np.pi * 220 * t).astype(np.float32), 24000) - 220) < 8
    assert clonar_voz._f0(np.zeros(960, dtype=np.float32), 24000) is None


def test_bat_e_instalador_apontam_um_para_o_outro():
    bat = (RAIZ / "clonar_voz.bat").read_text(encoding="utf-8")
    assert "ametista.instalar_voz_local --sem-teste" in bat and "ametista.clonar_voz --local" in bat
    assert "ametista.instalar_voz_local" in (RAIZ / "instalar_voz_local.bat").read_text(encoding="utf-8")
    from ametista import instalar_voz_local

    assert "cu128" in instalar_voz_local.INDICE["cuda"] and instalar_voz_local.TORCH.startswith("torch==2.8")
    assert "transformers==4.57.6" in instalar_voz_local.COQUI
    fonte = textwrap.dedent((RAIZ / "ametista" / "voz_local_servidor.py").read_text(encoding="utf-8"))
    assert "from . import" not in fonte and "import config" not in fonte     # roda sem o resto da Ametista
