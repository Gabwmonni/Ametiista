"""Gera amostras das vozes candidatas e mede cada uma (rodado pelo GitHub Actions, que alcança o serviço de voz).

Mede o tom médio (F0), quanto o tom varia (voz monótona soa robótica) e a velocidade (sílabas por segundo).
Referência: voz feminina adulta calorosa fica por volta de 190 a 240 Hz; bem acima de ~280 Hz começa a soar
infantil. Fala tranquila e atenciosa em português fica por volta de 4,5 a 5,5 sílabas por segundo.

Uso: python tests/amostras_de_voz.py <pasta_de_saida>
"""
import asyncio
import io
import re
import sys
from pathlib import Path

import numpy as np

TEXTO = ("Oi, Gabriel! Que bom te ouvir. Já deixei tudo pronto pra você: amanhã vai fazer sol, e a sua reunião "
         "é às dez. Se precisar de mais alguma coisa, é só me chamar, tá bom?")

CANDIDATAS = [
    ("1_francisca_atual", "pt-BR-FranciscaNeural", "+5%", "+0Hz"),
    ("2_francisca_leve", "pt-BR-FranciscaNeural", "-3%", "+6Hz"),
    ("3_thalita_natural", "pt-BR-ThalitaMultilingualNeural", "+0%", "+0Hz"),
    ("4_thalita_calma", "pt-BR-ThalitaMultilingualNeural", "-4%", "+0Hz"),
    ("5_thalita_calma_leve", "pt-BR-ThalitaMultilingualNeural", "-4%", "+4Hz"),
    ("6_thalita_calma_mais_leve", "pt-BR-ThalitaMultilingualNeural", "-4%", "+8Hz"),
    ("7_thalita_bem_leve", "pt-BR-ThalitaMultilingualNeural", "-4%", "+12Hz"),
]


def silabas(texto: str) -> int:
    return len(re.findall(r"[aeiouáéíóúâêôãõà]+", texto.lower()))


def decodificar(mp3: bytes) -> tuple[np.ndarray, int]:
    import av

    with av.open(io.BytesIO(mp3)) as c:
        taxa = c.streams.audio[0].rate
        partes = [f.to_ndarray().astype(np.float32).mean(axis=0) for f in c.decode(audio=0)]
    x = np.concatenate(partes)
    return x / (np.abs(x).max() + 1e-9), taxa


def medir_f0(x: np.ndarray, taxa: int) -> list[float]:
    quadro, passo = int(0.04 * taxa), int(0.01 * taxa)
    janela = np.hanning(quadro)
    minimo, maximo = int(taxa / 400), int(taxa / 70)
    rms_geral = np.sqrt(np.mean(x ** 2))
    f0s = []
    for i in range(0, len(x) - quadro, passo):
        seg = x[i:i + quadro] * janela
        if np.sqrt(np.mean(seg ** 2)) < 0.3 * rms_geral:
            continue
        espectro = np.fft.rfft(seg, 2 * quadro)
        ac = np.fft.irfft(espectro * np.conj(espectro))[:quadro]
        if ac[0] <= 0:
            continue
        pico = minimo + int(np.argmax(ac[minimo:maximo]))
        if ac[pico] / ac[0] > 0.45:               # trecho com voz (periódico)
            f0s.append(taxa / pico)
    return f0s


def _semitons(f0s: list[float]) -> float:
    s = 12 * np.log2(np.array(f0s) / np.median(f0s))
    return float(np.percentile(s, 90) - np.percentile(s, 10))


async def main(saida: Path) -> None:
    import edge_tts

    saida.mkdir(parents=True, exist_ok=True)
    vozes = await edge_tts.list_voices()
    pt = [(v["ShortName"], v.get("Gender")) for v in vozes if v["Locale"].startswith("pt-")]
    print("Vozes em português disponíveis:", pt)
    nomes = {v for v, _ in pt}
    linhas = [f"{'amostra':30} {'voz':34} {'vel':>5} {'tom':>6} {'F0 med':>7} {'F0 10-90%':>12} {'variação':>9} "
              f"{'síl/s':>6} {'dur':>5}"]
    for nome, voz, vel, tom in CANDIDATAS:
        if voz not in nomes:
            print(f"(pulando {nome}: voz {voz} não existe mais)")
            continue
        partes = bytearray()
        async for p in edge_tts.Communicate(TEXTO, voz, rate=vel, pitch=tom).stream():
            if p["type"] == "audio":
                partes.extend(p["data"])
        (saida / f"{nome}.mp3").write_bytes(bytes(partes))
        x, taxa = decodificar(bytes(partes))
        f0s = medir_f0(x, taxa)
        dur = len(x) / taxa
        linhas.append(f"{nome:30} {voz:34} {vel:>5} {tom:>6} {np.median(f0s):7.0f} "
                      f"{np.percentile(f0s, 10):5.0f}-{np.percentile(f0s, 90):<5.0f} {_semitons(f0s):7.1f}st "
                      f"{silabas(TEXTO) / dur:6.2f} {dur:5.1f}")
    relatorio = "\n".join(linhas)
    print(relatorio)
    (saida / "medidas.txt").write_text(relatorio + "\n\nTexto: " + TEXTO + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1] if len(sys.argv) > 1 else "amostras")))
