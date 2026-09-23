"""Clona uma voz para a Ametista a partir de gravações.

Uso:
  1. Coloque as gravações na pasta  voz/amostras  (mp3, wav, m4a, ogg...).
     Ideal: 1 a 3 minutos no total, só a pessoa falando, sem música nem eco, em trechos variados.
  2. Rode:  python -m ametista.clonar_voz            (ElevenLabs, precisa de ELEVENLABS_API_KEY no .env)
     ou:    python -m ametista.clonar_voz --local    (XTTS-v2 no seu PC)

IMPORTANTE: só clone a voz de alguém com autorização dessa pessoa.
"""
import argparse
import asyncio
import re
import sys
import wave
from pathlib import Path

import numpy as np

from . import config

AMOSTRAS = config.RAIZ / "voz" / "amostras"
EXTENSOES = {".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac", ".aac", ".webm", ".mp4"}
FRASE_TESTE = "Oi! Eu sou a Ametista. A partir de agora, é com essa voz que eu vou falar com você."


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
    _salvar_env("ELEVENLABS_VOZ_ID", voz_id)
    _salvar_env("VOZ_PROVEDOR", "elevenlabs")
    config.ELEVENLABS_VOZ_ID, config.VOZ_PROVEDOR = voz_id, "elevenlabs"
    return voz_id


def preparar_local(arqs: list[Path]) -> None:
    """XTTS usa de 6 a 30 s de referência: separa os melhores trechos em voz/referencia/."""
    destino = config.VOZ_REFERENCIAS
    destino.mkdir(parents=True, exist_ok=True)
    for velho in destino.glob("*.wav"):
        velho.unlink()
    total = 0.0
    for i, a in enumerate(arqs):
        audio = _decodificar(a, 24000)
        # corta silêncios longos das pontas
        nivel = np.abs(audio)
        falas = np.where(nivel > max(0.02, nivel.max() * 0.05))[0]
        if len(falas) == 0:
            continue
        audio = audio[max(0, falas[0] - 2400): falas[-1] + 2400][: 24000 * 15]
        with wave.open(str(destino / f"ref_{i:02d}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
        total += len(audio) / 24000
        if total >= 30:
            break
    _salvar_env("VOZ_PROVEDOR", "local")
    config.VOZ_PROVEDOR = "local"
    print(f"  Referências prontas: {total:.0f} s em {destino}")


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
        preparar_local(arqs)
    else:
        print("\nEnviando para a ElevenLabs...")
        voz_id = clonar_elevenlabs(arqs, args.nome)
        print(f"  Voz criada: {voz_id} (salva no .env)")

    print("\nGerando um teste...")
    from . import voz

    b64 = asyncio.run(voz.sintetizar(FRASE_TESTE))
    if b64:
        import base64

        ext = "wav" if args.local else "mp3"
        saida = config.RAIZ / "voz" / f"teste.{ext}"
        saida.write_bytes(base64.b64decode(b64))
        print(f"  Ouça: {saida}")
    print("\nPronto! Reinicie a Ametista para usar a nova voz.")


if __name__ == "__main__":
    main()
