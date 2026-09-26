"""Mede quanto tempo ela leva para entender o que você disse, com o Whisper de verdade e frases faladas de verdade.

Rodado pelo GitHub Actions no Windows (baixa o modelo e usa a voz do Edge para "falar" as frases). Compara o
jeito antigo (0,9 s de silêncio, só então transcrever, Whisper frio e com os ajustes padrão) com o novo
(transcrição começando na pausa, Whisper aquecido e ajustado). O áudio entra no ritmo real do microfone.
"""
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp())
os.environ.update(AMETISTA_DADOS=str(TMP / "dados"), AMETISTA_ENV=str(TMP / ".env"), OUVIDO_LIGADO="0")
sys.path.insert(0, str(RAIZ))

import numpy as np  # noqa: E402

from ametista import config, ouvido, transcricao  # noqa: E402

FRASES = ["Ametista, que horas são agora?", "Ametista, toca uma música calma no Spotify.",
          "Ametista, abre o bloco de notas e anota que a prova de cálculo é na sexta."]


async def _falar(texto: str) -> bytes:
    import edge_tts

    mp3 = b""
    async for parte in edge_tts.Communicate(texto, "pt-BR-AntonioNeural").stream():
        if parte["type"] == "audio":
            mp3 += parte["data"]
    return mp3


def pcm_da_frase(texto: str) -> bytes:
    import io

    from faster_whisper.audio import decode_audio

    audio = decode_audio(io.BytesIO(asyncio.run(_falar(texto))), sampling_rate=ouvido.TAXA)
    audio = audio / max(1e-6, float(np.abs(audio).max())) * 0.5          # microfone com volume normal
    return (audio * 32767).astype(np.int16).tobytes()


def medir(o: "ouvido.Ouvido", pcm: bytes) -> tuple[float, str]:
    """Alimenta o ouvido no ritmo do microfone: 1 s de silêncio, o nome já detectado, a frase e silêncio até ela
    entender. Devolve (segundos entre o fim da sua fala e o pedido chegar, texto entendido)."""
    bloco = ouvido.AMOSTRAS * 2
    silencio = bytes(bloco)
    pedidos = []
    o.atender = lambda texto, falante, sem_nome=False: pedidos.append((time.perf_counter(), texto)) or {}
    for _ in range(12):
        o.alimentar(silencio)
    o._iniciar_gravacao("manual", [])                  # como se já tivesse ouvido o nome
    proximo = time.perf_counter()
    for i in range(0, len(pcm) - bloco + 1, bloco):
        o.alimentar(pcm[i:i + bloco])
        proximo += ouvido.DUR
        time.sleep(max(0.0, proximo - time.perf_counter()))
    # fim da fala: o fim de verdade é o último bloco com som
    niveis = [ouvido._nivel(pcm[i:i + bloco]) for i in range(0, len(pcm) - bloco + 1, bloco)]
    ultimo_som = max(i for i, n in enumerate(niveis) if n > o.limiar)
    fim_da_fala = proximo - (len(niveis) - ultimo_som) * ouvido.DUR
    limite = time.perf_counter() + 20
    while not pedidos and time.perf_counter() < limite:
        o.alimentar(silencio)
        proximo += ouvido.DUR
        time.sleep(max(0.0, proximo - time.perf_counter()))
    if not pedidos:
        raise SystemExit("FALHOU: ela não entendeu a frase em 20 s")
    while o.estado == "processando":
        time.sleep(0.02)
    o.estado = "espera"
    return pedidos[0][0] - fim_da_fala, pedidos[0][1]


def nome_pausa_e_pedido(o: "ouvido.Ouvido", pcm_nome: bytes, pcm_pedido: bytes) -> str:
    """ "Ametista" (o nome já detectado), uma pausa longa e o pedido dito enquanto ela ainda processa o nome."""
    bloco = ouvido.AMOSTRAS * 2
    silencio = bytes(bloco)
    pedidos = []
    o.atender = lambda texto, falante, sem_nome=False: pedidos.append(texto) or {}
    for _ in range(12):
        o.alimentar(silencio)
    o._iniciar_gravacao("nome", [])
    proximo = time.perf_counter()

    def no_ritmo(dados: bytes) -> None:
        nonlocal proximo
        o.alimentar(dados)
        proximo += ouvido.DUR
        time.sleep(max(0.0, proximo - time.perf_counter()))

    for i in range(0, len(pcm_nome) - bloco + 1, bloco):
        no_ritmo(pcm_nome[i:i + bloco])
    while o.estado != "processando":
        no_ritmo(silencio)
    for i in range(0, len(pcm_pedido) - bloco + 1, bloco):   # começa a falar logo: ela ainda está transcrevendo
        no_ritmo(pcm_pedido[i:i + bloco])
    limite = time.perf_counter() + 20
    while not pedidos and time.perf_counter() < limite:
        no_ritmo(silencio)
    while o.estado == "processando":
        time.sleep(0.02)
    o.estado = "espera"
    return pedidos[0] if pedidos else ""


def main() -> int:
    from faster_whisper import WhisperModel

    frases = [(f, pcm_da_frase(f)) for f in FRASES]
    print(f"frases faladas: {', '.join(f'{len(p) / 32000:.1f} s' for _, p in frases)}")

    # ---- jeito antigo
    t = time.time()
    velho = WhisperModel(config.WHISPER_MODELO, device="cpu", compute_type="int8")
    print(f"Whisper antigo carregou em {time.time() - t:.1f} s")

    def transcrever_velho(pcm):
        audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
        seg, _ = velho.transcribe(audio, language="pt", beam_size=1, condition_on_previous_text=False,
                                  initial_prompt=transcricao.prompt())
        return "".join(s.text for s in seg).strip()

    antigo = ouvido.Ouvido(atender=lambda *a, **k: {})
    antigo._whisper_pronto.set()
    antigo.transcrever = transcrever_velho
    fim, adiantar = ouvido.SILENCIO_FIM, ouvido.SILENCIO_ADIANTAR
    ouvido.SILENCIO_FIM, ouvido.SILENCIO_ADIANTAR = 0.9, 99.0
    tempos_antigos = [medir(antigo, pcm) for _, pcm in frases]
    ouvido.SILENCIO_FIM, ouvido.SILENCIO_ADIANTAR = fim, adiantar

    # ---- jeito novo
    novo = ouvido.Ouvido(atender=lambda *a, **k: {})
    t = time.time()
    novo._carregar_whisper()
    print(f"Whisper novo ({novo.dispositivo}, {transcricao.threads_cpu()} núcleos) carregou e aqueceu em "
          f"{time.time() - t:.1f} s")
    tempos_novos = [medir(novo, pcm) for _, pcm in frases]

    print(f"\n{'frase':52} {'antes':>7} {'agora':>7}")
    for (frase, _), (a, _), (n, texto) in zip(frases, tempos_antigos, tempos_novos):
        print(f"{frase[:50]:52} {a:6.2f}s {n:6.2f}s   entendeu: {texto!r}")
    media_a = sum(a for a, _ in tempos_antigos) / len(frases)
    media_n = sum(n for n, _ in tempos_novos) / len(frases)
    print(f"{'média':52} {media_a:6.2f}s {media_n:6.2f}s")

    for (frase, _), (_, texto) in zip(frases, tempos_novos):
        chave = frase.split(",")[1].split()[0].lower()           # "que", "toca", "abre"
        if chave not in texto.lower():
            print(f"FALHOU: entendeu errado: {texto!r} (esperava algo como {frase!r})")
            return 1
    if media_n >= media_a:
        print("FALHOU: não ficou mais rápido")
        return 1
    print(f"OK: ela entende {media_a - media_n:.2f} s mais rápido ({(1 - media_n / media_a) * 100:.0f}% menos espera)")

    # "Ametista" ... pausa ... pedido: o pedido dito enquanto ela processa o nome não se perde
    pedido = nome_pausa_e_pedido(novo, pcm_da_frase("Ametista."), pcm_da_frase("Que horas são agora?"))
    print(f"'Ametista', pausa e o pedido logo em seguida: entendeu {pedido!r}")
    if "horas" not in pedido.lower():
        print("FALHOU: o pedido dito depois da pausa se perdeu")
        return 1

    # o teste da placa (processo à parte) roda e responde certo: aqui não há placa NVIDIA
    t = time.time()
    ok, placa = transcricao.testar_placa(config.WHISPER_MODELO, limite=240), transcricao.tem_placa()
    print(f"teste da placa NVIDIA ({'tem' if placa else 'sem'} placa): {'serviu' if ok else 'não serviu'} "
          f"em {time.time() - t:.1f} s; guardado: {transcricao.placa_testada(config.WHISPER_MODELO)}")
    if ok and not placa or transcricao.placa_testada(config.WHISPER_MODELO) is not ok:
        print("FALHOU: o teste da placa respondeu errado")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
