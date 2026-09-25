"""Clona uma voz para a Ametista a partir de gravações.

Uso:
  1. Coloque as gravações na pasta  voz/amostras  (mp3, wav, m4a, ogg...). Podem ser áudios comuns, com
     pausas e barulho: ela escolhe sozinha os melhores trechos (só fala, sem música, sem palavra cortada).
  2. Rode o clonar_voz.bat, ou:
       python -m ametista.clonar_voz --local    (XTTS-v2 no seu PC; grátis, rápido com placa NVIDIA)
       python -m ametista.clonar_voz            (ElevenLabs, precisa de ELEVENLABS_API_KEY no .env)

IMPORTANTE: só clone a voz de alguém com autorização dessa pessoa.
"""
import argparse
import asyncio
import re
import shutil
import sys
import urllib.request
import wave
from pathlib import Path

import numpy as np

from . import config

AMOSTRAS = config.RAIZ / "voz" / "amostras"
EXTENSOES = {".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac", ".aac", ".webm", ".mp4"}
FRASE_TESTE = "Oi! Eu sou a Ametista. A partir de agora, é com essa voz que eu vou falar com você."
VAD_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"
TAXA = 24000
ALVO_S = 26                  # segundos de referência no total (o XTTS usa até ~30)
TRECHO_MIN, TRECHO_MAX = 5.0, 11.5
PAUSA_MAX = 1.6              # frases separadas por até 1,6 s entram no mesmo trecho...
PAUSA_REF = 0.35             # ...mas a pausa entre elas fica com no máximo 0,35 s na referência
MAX_TRECHOS = 4


def _arquivos() -> list[Path]:
    return sorted(p for p in AMOSTRAS.glob("*") if p.suffix.lower() in EXTENSOES)


def _decodificar(arq: Path, taxa: int) -> np.ndarray:
    from faster_whisper.audio import decode_audio  # usa o PyAV, já instalado com o Whisper

    return decode_audio(str(arq), sampling_rate=taxa)


def _analisar(arqs: list[Path]) -> float:
    total = 0.0
    for a in arqs:
        try:
            dur = len(_decodificar(a, 16000)) / 16000
        except Exception as e:
            print(f"  ! não consegui ler {a.name}: {e}")
            continue
        total += dur
        print(f"  - {a.name}: {dur:.0f} s")
    print(f"  Total: {total / 60:.1f} min")
    if total < 30:
        print("  ! Pouco áudio: o resultado fica melhor com pelo menos 1 minuto.")
    return total


def _salvar_env(chave: str, valor: str) -> None:
    env = config.RAIZ / ".env"
    texto = env.read_text(encoding="utf-8") if env.exists() else ""
    if re.search(rf"^{chave}=.*$", texto, re.M):
        texto = re.sub(rf"^{chave}=.*$", f"{chave}={valor}", texto, flags=re.M)
    else:
        texto += f"\n{chave}={valor}\n"
    env.write_text(texto, encoding="utf-8")


def clonar_elevenlabs(arqs: list[Path], nome: str) -> str:
    import httpx

    if not config.ELEVENLABS_API_KEY:
        sys.exit("Coloque ELEVENLABS_API_KEY no .env (elevenlabs.io > Profile > API Keys).")
    arquivos = [("files", (a.name, a.read_bytes())) for a in arqs[:25]]
    r = httpx.post("https://api.elevenlabs.io/v1/voices/add",
                   headers={"xi-api-key": config.ELEVENLABS_API_KEY},
                   data={"name": nome, "description": "Voz da assistente Ametista (pt-BR)",
                         "remove_background_noise": "true"},
                   files=arquivos, timeout=180)
    if r.status_code >= 400:
        sys.exit(f"A ElevenLabs recusou: {r.status_code} {r.text[:300]}\n"
                 "(Clonagem exige plano pago Starter ou superior.)")
    voz_id = r.json()["voice_id"]
    config.salvar({"ELEVENLABS_VOZ_ID": voz_id, "VOZ_PROVEDOR": "elevenlabs"})
    return voz_id


# ====================================================================== escolher os melhores trechos
def _quadros_db(audio: np.ndarray, taxa: int, passo_s: float = 0.02) -> np.ndarray:
    n = int(taxa * passo_s)
    q = len(audio) // n
    if q == 0:
        return np.zeros(0)
    return 20 * np.log10(np.sqrt(np.mean(audio[:q * n].reshape(q, n) ** 2, axis=1)) + 1e-9)


def _falas_por_energia(audio: np.ndarray, taxa: int) -> list[tuple[float, float]]:
    """Reserva sem o modelo de detecção de voz: trechos acima do barulho de fundo."""
    db = _quadros_db(audio, taxa)
    if not len(db):
        return []
    limiar = max(np.percentile(db, 15) + 12, db.max() - 40)
    ativo = db > limiar
    falas, ini = [], None
    for i, a in enumerate(np.append(ativo, False)):
        if a and ini is None:
            ini = i
        elif not a and ini is not None:
            falas.append((ini * 0.02, i * 0.02))
            ini = None
    juntas: list[list[float]] = []
    for a, b in falas:                               # buracos de menos de 0,2 s são dentro da mesma fala
        if juntas and a - juntas[-1][1] < 0.2:
            juntas[-1][1] = b
        else:
            juntas.append([a, b])
    return [(a, b) for a, b in juntas if b - a >= 0.25]


def _modelo_vad() -> Path | None:
    destino = config.MODELOS / "silero_vad.onnx"
    if destino.exists():
        return destino
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(urllib.request.urlopen(VAD_URL, timeout=60).read())
        return destino
    except Exception:
        return None


def falas(audio16: np.ndarray) -> list[tuple[float, float]]:
    """(início, fim) em segundos de cada trecho com voz humana (Silero VAD; se não der, pela energia)."""
    modelo = _modelo_vad()
    if modelo is not None:
        try:
            import sherpa_onnx

            cfg = sherpa_onnx.VadModelConfig()
            cfg.silero_vad.model = str(modelo)
            cfg.silero_vad.min_silence_duration = 0.25
            cfg.silero_vad.min_speech_duration = 0.25
            cfg.silero_vad.max_speech_duration = 20
            cfg.sample_rate = 16000
            vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=max(60, len(audio16) / 16000 + 5))
            for i in range(0, len(audio16) - 512, 512):
                vad.accept_waveform(audio16[i:i + 512])
            vad.flush()
            saida = []
            while not vad.empty():
                s = vad.front
                saida.append((s.start / 16000, (s.start + len(s.samples)) / 16000))
                vad.pop()
            return saida
        except Exception as e:
            print(f"  (detecção de voz indisponível: {e}; usando a energia do som)")
    return _falas_por_energia(audio16, 16000)


def _f0(quadro: np.ndarray, taxa: int) -> float | None:
    """Frequência fundamental (tom de voz) de um pedaço de ~40 ms, por autocorrelação. None se não for vozeado."""
    q = quadro - quadro.mean()
    if np.sqrt(np.mean(q ** 2)) < 1e-3:
        return None
    ac = np.fft.irfft(np.abs(np.fft.rfft(q, 2 * len(q))) ** 2)[:len(q)]
    if ac[0] <= 0:
        return None
    ac /= ac[0]
    lo, hi = int(taxa / 450), int(taxa / 70)
    if hi + 1 >= len(ac):
        return None
    faixa = ac[lo:hi]
    maior = float(faixa.max())
    if maior <= 0.45:
        return None
    # o primeiro pico quase tão alto quanto o maior: evita confundir o tom com a oitava de baixo
    picos = np.where((faixa[1:-1] >= faixa[:-2]) & (faixa[1:-1] >= faixa[2:]) & (faixa[1:-1] >= 0.9 * maior))[0]
    lag = lo + 1 + int(picos[0]) if len(picos) else lo + int(np.argmax(faixa))
    return taxa / lag


def _tons(audio: np.ndarray, taxa: int, ini: float, fim: float) -> list[float]:
    n = int(taxa * 0.04)
    trecho = audio[int(ini * taxa):int(fim * taxa)]
    saida = []
    for i in range(0, len(trecho) - n, n):
        f = _f0(trecho[i:i + n], taxa)
        if f:
            saida.append(f)
    return saida


def candidatos(audio: np.ndarray, taxa: int, trechos_fala: list[tuple[float, float]], origem: str = "") -> list[dict]:
    """Janelas de 5 a 11,5 s que começam e terminam em pausas, com a nota de cada uma."""
    if not trechos_fala:
        return []
    db = _quadros_db(audio, taxa)
    fala_mask = np.zeros(len(db), dtype=bool)
    for a, b in trechos_fala:
        fala_mask[int(a / 0.02):int(b / 0.02) + 1] = True
    todos_tons = [f for a, b in trechos_fala for f in _tons(audio, taxa, a, b)]
    tom_tipico = float(np.median(todos_tons)) if todos_tons else 0.0
    saida = []
    for i in range(len(trechos_fala)):
        dur = 0.0
        for j in range(i, len(trechos_fala)):
            ini, fim = trechos_fala[i][0], trechos_fala[j][1]
            if j > i:
                pausa = trechos_fala[j][0] - trechos_fala[j - 1][1]
                if pausa > PAUSA_MAX:
                    break                            # pausa longa: vira outro trecho
                dur += min(pausa, PAUSA_REF)
            dur += trechos_fala[j][1] - trechos_fala[j][0]   # duração como vai ficar (pausas encurtadas)
            if dur > TRECHO_MAX:
                break
            if dur < TRECHO_MIN:
                continue
            a, b = int(ini / 0.02), int(fim / 0.02)
            viz_a, viz_b = max(0, a - 100), min(len(db), b + 100)     # 2 s em volta
            dentro = db[a:b][fala_mask[a:b]]
            fundo = db[viz_a:viz_b][~fala_mask[viz_a:viz_b]]
            if len(dentro) < 20:
                continue
            nivel_fala = float(np.percentile(dentro, 60))
            nivel_fundo = float(np.percentile(fundo, 50)) if len(fundo) >= 5 else float(np.percentile(db, 10))
            snr = nivel_fala - nivel_fundo
            cheia = float(fala_mask[a:b].mean())
            amostras = audio[int(ini * taxa):int(fim * taxa)]
            estouro = float(np.mean(np.abs(amostras) > 0.98))
            tons = _tons(audio, taxa, ini, fim)
            outra_voz = 0.0
            if tons and tom_tipico:
                desvios = np.abs(np.log2(np.asarray(tons) / tom_tipico))
                # outra pessoa: o tom do trecho inteiro fica longe do tom da gravação (ou boa parte dele fica)
                outra_voz = 1.0 if abs(np.log2(np.median(tons) / tom_tipico)) > 0.45 else float(np.mean(desvios > 0.7))
            variacao = float(np.std(dentro))
            nota = snr + 12 * cheia - 400 * estouro - 30 * outra_voz - 0.3 * max(0.0, variacao - 8) + 0.3 * dur
            saida.append({"origem": origem, "ini": ini, "fim": fim, "dur": dur, "snr": snr, "cheia": cheia,
                          "estouro": estouro, "outra_voz": outra_voz, "nota": nota,
                          "falas": [tuple(x) for x in trechos_fala[i:j + 1]]})
    return saida


def montar(audio: np.ndarray, c: dict, taxa: int = TAXA) -> np.ndarray:
    """O áudio do trecho com as pausas longas encurtadas (a emenda cai no silêncio, suavizada)."""
    falas = c.get("falas") or [(c["ini"], c["fim"])]
    partes = []
    for k, (a, b) in enumerate(falas):
        ini = a - 0.08 if k == 0 else a - min(PAUSA_REF, a - falas[k - 1][1]) / 2
        fim = b + 0.15 if k == len(falas) - 1 else b + min(PAUSA_REF, falas[k + 1][0] - b) / 2
        pedaco = audio[max(0, int(ini * taxa)):int(fim * taxa)].astype(np.float32).copy()
        rampa = min(len(pedaco) // 4, int(taxa * 0.005))
        if rampa and k > 0:
            pedaco[:rampa] *= np.linspace(0, 1, rampa, dtype=np.float32)
        if rampa and k < len(falas) - 1:
            pedaco[-rampa:] *= np.linspace(1, 0, rampa, dtype=np.float32)
        partes.append(pedaco)
    return np.concatenate(partes) if partes else np.zeros(0, dtype=np.float32)


def _limpo(c: dict) -> bool:
    return c["snr"] >= 18 and c["estouro"] < 0.002 and c["outra_voz"] < 0.15


def escolher(cands: list[dict], alvo_s: float = ALVO_S, max_trechos: int = MAX_TRECHOS) -> list[dict]:
    """Os melhores trechos sem sobreposição, até juntar uns 26 s. Primeiro só os limpos; os outros só completam
    se os limpos (sem contar sobreposições) não chegarem a 12 s."""
    escolhidos: list[dict] = []

    def total() -> float:
        return sum(e["dur"] for e in escolhidos)

    for grupo in ([c for c in cands if _limpo(c)], [c for c in cands if not _limpo(c)]):
        for c in sorted(grupo, key=lambda c: -c["nota"]):
            if total() >= alvo_s or len(escolhidos) >= max_trechos:
                return escolhidos
            if any(c["origem"] == e["origem"] and c["ini"] < e["fim"] + 0.3 and e["ini"] < c["fim"] + 0.3
                   for e in escolhidos):
                continue
            escolhidos.append(c)
        if total() >= 12:
            break
    return escolhidos


def _conferir_palavras(trecho: np.ndarray) -> str | None:
    """Com o Whisper da Ametista: o texto do trecho, ou None se não for fala clara (música, fala embolada)."""
    try:
        from faster_whisper import WhisperModel

        global _whisper
        if _whisper is None:
            _whisper = WhisperModel(config.WHISPER_MODELO, device="cpu", compute_type="int8")
        audio16 = np.interp(np.arange(0, len(trecho), TAXA / 16000), np.arange(len(trecho)), trecho).astype(np.float32)
        segs, _ = _whisper.transcribe(audio16, language="pt", beam_size=1, vad_filter=False)
        segs = list(segs)
    except Exception:
        return ""                                    # sem Whisper: fica só a análise do som
    texto = " ".join(s.text.strip() for s in segs).strip()
    if not texto or re.search(r"\[|m[úu]sica|♪", texto, re.I):
        return None
    # só descarta o que claramente não é fala: um Whisper pequeno erra palavras, mas isso não faz o trecho ruim
    media = sum(s.avg_logprob for s in segs) / len(segs) if segs else 0.0
    if segs and (media < -1.5 or max(s.no_speech_prob for s in segs) > 0.7):
        return None
    return texto


_whisper = None


def _normalizar(trecho: np.ndarray, taxa: int) -> np.ndarray:
    """Tira o ronco grave (abaixo de 70 Hz), deixa a fala em volume padrão e suaviza as pontas."""
    espectro = np.fft.rfft(trecho)
    freqs = np.fft.rfftfreq(len(trecho), 1 / taxa)
    espectro *= np.clip((freqs - 50) / 30, 0, 1)
    t = np.fft.irfft(espectro, len(trecho)).astype(np.float32)
    db = _quadros_db(t, taxa)
    nivel = np.percentile(db, 80) if len(db) else -20
    t *= 10 ** ((-18 - nivel) / 20)
    pico = np.max(np.abs(t)) if len(t) else 0
    if pico > 0.89:
        t *= 0.89 / pico
    rampa = int(taxa * 0.02)
    t[:rampa] *= np.linspace(0, 1, rampa)
    t[-rampa:] *= np.linspace(1, 0, rampa)
    return np.concatenate([t, np.zeros(int(taxa * 0.3), dtype=np.float32)])


def _gravar_wav(caminho: Path, audio: np.ndarray, taxa: int = TAXA) -> None:
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())


def preparar_local(arqs: list[Path], conferir: bool = True) -> list[dict]:
    """Separa os melhores trechos das gravações em voz/referencia/ (o XTTS aprende a voz com eles)."""
    audios, cands = {}, []
    for a in arqs:
        try:
            audio = _decodificar(a, TAXA)
            audio16 = _decodificar(a, 16000)
        except Exception as e:
            print(f"  ! não consegui ler {a.name}: {e}")
            continue
        audios[a.name] = audio
        trechos = falas(audio16)
        cands += candidatos(audio, TAXA, trechos, a.name)
        print(f"  {a.name}: {len(trechos)} falas, {sum(b - x for x, b in trechos):.0f} s de voz")
    if not cands:
        sys.exit("Não achei trechos de fala nas gravações. Grave de novo, num lugar mais silencioso.")
    escolhidos: list[dict] = []
    descartados: set[tuple] = set()
    for _ in range(8):                               # descarta o que o Whisper não entender e escolhe de novo
        escolhidos = escolher([c for c in cands if (c["origem"], c["ini"]) not in descartados])
        if not conferir:
            break
        ruins = []
        for c in escolhidos:
            if "texto" in c:
                continue
            texto = _conferir_palavras(montar(audios[c["origem"]], c))
            if texto is None:
                ruins.append(c)
            else:
                c["texto"] = texto
        if not ruins:
            break
        descartados |= {(c["origem"], c["ini"]) for c in ruins}
    escolhidos = [c for c in escolhidos if (c["origem"], c["ini"]) not in descartados]
    destino = config.VOZ_REFERENCIAS
    if destino.exists() and any(destino.glob("*.wav")):
        anterior = destino.parent / "referencia_anterior"
        shutil.rmtree(anterior, ignore_errors=True)
        shutil.copytree(destino, anterior)
    destino.mkdir(parents=True, exist_ok=True)
    for velho in destino.glob("*.wav"):
        velho.unlink()
    for i, c in enumerate(escolhidos, 1):
        _gravar_wav(destino / f"ametista_{i:02d}.wav", _normalizar(montar(audios[c["origem"]], c), TAXA))
        extra = f' — "{c["texto"][:70]}"' if c.get("texto") else ""
        print(f"  trecho {i}: {c['origem']} {c['ini']:.1f}-{c['fim']:.1f} s ({c['dur']:.1f} s, fundo "
              f"{c['snr']:.0f} dB abaixo da voz){extra}")
    total = sum(c["dur"] for c in escolhidos)
    print(f"  Referências prontas: {total:.0f} s em {destino}")
    if total < 12:
        print("  ! Pouca fala limpa: a voz pode sair menos parecida. Mais gravações ajudam.")
    return escolhidos


def testar_local() -> Path | None:
    """Abre o servidor da voz local, espera carregar e grava voz/teste.wav."""
    from . import voz_local

    if not voz_local.instalado():
        print("\n  A voz local ainda não está instalada: rode o instalar_voz_local.bat e depois este de novo.")
        return None
    srv = voz_local.servidor()
    srv.parar()
    srv.iniciar()
    print("  Carregando o modelo de voz (na primeira vez ele é baixado, ~1,8 GB)...")
    s = srv.esperar(900)
    if not s or not s.get("pronto"):
        print(f"  ! A voz local não abriu: {(s or {}).get('erro') or 'veja dados/voz_local.log'}")
        return None
    print(f"  Rodando {'na placa de vídeo (' + str(s.get('gpu')) + ')' if s.get('dispositivo') == 'cuda' else 'no processador (mais lento)'}.")
    wav = srv.falar(FRASE_TESTE, espera=300)
    saida = config.RAIZ / "voz" / "teste.wav"
    saida.write_bytes(wav)
    srv.parar()
    return saida


def main() -> None:
    p = argparse.ArgumentParser(description="Clona uma voz para a Ametista")
    p.add_argument("--local", action="store_true", help="usar XTTS-v2 no PC em vez da ElevenLabs")
    p.add_argument("--nome", default="Ametista")
    p.add_argument("--sim", action="store_true", help="pula a pergunta de autorização")
    args = p.parse_args()

    AMOSTRAS.mkdir(parents=True, exist_ok=True)
    arqs = _arquivos()
    if not arqs:
        sys.exit(f"Coloque as gravações em {AMOSTRAS} e rode de novo.")
    print(f"\nGravações encontradas ({len(arqs)}):")
    _analisar(arqs)

    if not args.sim:
        ok = input("\nVocê tem autorização da pessoa dona dessa voz para cloná-la? (s/n) ").strip().lower()
        if not ok.startswith("s"):
            sys.exit("Cancelado.")

    if args.local:
        print("\nEscolhendo os melhores trechos (só fala, sem música, sem palavra cortada)...")
        preparar_local(arqs)
        config.salvar({"VOZ_PROVEDOR": "local"})
        print("\nGerando um teste...")
        saida = testar_local()
        if saida:
            print(f"  Ouça: {saida}")
    else:
        print("\nEnviando para a ElevenLabs...")
        voz_id = clonar_elevenlabs(arqs, args.nome)
        print(f"  Voz criada: {voz_id} (salva no .env)")
        print("\nGerando um teste...")
        from . import voz

        b64 = asyncio.run(voz.sintetizar(FRASE_TESTE))
        if b64:
            import base64

            saida = config.RAIZ / "voz" / "teste.mp3"
            saida.write_bytes(base64.b64decode(b64))
            print(f"  Ouça: {saida}")
    print("\nPronto! Se a Ametista estiver aberta, reinicie (botão direito no ícone > Reiniciar) para usar a nova voz.")


if __name__ == "__main__":
    main()
