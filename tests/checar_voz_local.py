"""Confere a voz clonada no PC DE VERDADE (no GitHub Actions: Windows, sem placa de vídeo).

    python tests/checar_voz_local.py

Faz o mesmo caminho do instalar_voz_local.bat e do clonar_voz.bat: instala o PyTorch e o XTTS-v2 num Python
separado, escolhe os trechos de uma gravação de exemplo (uma voz pronta da Microsoft lendo um texto), abre o
servidor de voz e fala. No fim, a fala passa pela Ametista e sai em MP3.
"""
import asyncio
import base64
import io
import os
import sys
import time
import wave
from pathlib import Path

import numpy as np

os.environ.setdefault("AMETISTA_INSTALAR_SEM_PERGUNTAR", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ametista import clonar_voz, config, instalar_voz_local, voz, voz_local  # noqa: E402

TEXTO = ("Oi! Eu gravei este áudio para testar a clonagem de voz. Hoje o dia foi longo, mas deu tudo certo. "
         "De manhã eu estudei cálculo, depois almocei com calma e, à tarde, organizei as minhas anotações. "
         "Agora à noite eu quero descansar um pouco, ouvir uma música e, quem sabe, ler um livro antes de dormir. "
         "Amanhã tem aula cedo, então é melhor não ficar acordada até tarde. Até mais!")


def main() -> int:
    clonar_voz.AMOSTRAS.mkdir(parents=True, exist_ok=True)
    amostra = clonar_voz.AMOSTRAS / "exemplo.mp3"
    print("1. Gravação de exemplo (voz pronta)...", flush=True)
    audio = asyncio.run(voz._edge(TEXTO, "pt-BR-FranciscaNeural", "+0%", "+0Hz"))
    amostra.write_bytes(audio)

    print("2. Instalando a voz local...", flush=True)
    t0 = time.time()
    if instalar_voz_local.main(["--sem-teste"]) != 0:
        print("ERRO: a instalação falhou")
        return 1
    print(f"   instalada em {time.time() - t0:.0f} s: {voz_local.info_instalacao()}", flush=True)

    print("3. Escolhendo os trechos de referência...", flush=True)
    escolhidos = clonar_voz.preparar_local(clonar_voz._arquivos())
    if not escolhidos or not voz_local.referencias():
        print("ERRO: nenhum trecho escolhido")
        return 1

    print("4. Falando com a voz clonada...", flush=True)
    t0 = time.time()
    saida = clonar_voz.testar_local()
    if not saida:
        print("ERRO: a voz local não falou")
        return 1
    with wave.open(str(saida)) as w:
        dur = w.getnframes() / w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16) / 32767
    rms = float(np.sqrt(np.mean(pcm ** 2)))
    print(f"   {dur:.1f} s de fala, volume {rms:.3f}, em {time.time() - t0:.0f} s (com o carregamento)", flush=True)
    if dur < 2 or rms < 0.01:
        print("ERRO: a fala saiu curta ou muda")
        return 1

    print("5. Pela Ametista (MP3, como vai para a sobreposição e o celular)...", flush=True)
    config.VOZ_PROVEDOR = "local"
    srv = voz_local.servidor()
    srv.iniciar()
    s = srv.esperar(600)
    if not s or not s.get("pronto"):
        print(f"ERRO: o servidor não ficou pronto: {s}")
        return 1
    t0 = time.time()
    b64 = asyncio.run(voz.sintetizar("Oi, Gabriel! Tudo pronto por aqui."))
    srv.parar()
    mp3 = base64.b64decode(b64 or "")
    print(f"   {len(mp3)} bytes em {time.time() - t0:.1f} s", flush=True)
    if not (mp3[:3] == b"ID3" or mp3[:2] == b"\xff\xfb"):
        print("ERRO: não veio MP3 da voz clonada")
        return 1
    import av

    with av.open(io.BytesIO(mp3)) as c:
        fluxo = c.streams.audio[0]
        segundos = sum(q.samples for q in c.decode(fluxo)) / fluxo.rate
    print(f"   MP3 com {segundos:.1f} s", flush=True)
    return 0 if segundos > 1 else 1


if __name__ == "__main__":
    sys.exit(main())
