"""Servidor da voz clonada no próprio PC (XTTS-v2), rodando num Python separado (voz_local\\.venv).

Fica à parte porque o PyTorch com CUDA ocupa uns 3 GB e fixa versões próprias de várias bibliotecas: assim a
Ametista continua leve e uma atualização de um lado não quebra o outro. Só escuta em 127.0.0.1 e só atende quem
mandar a senha que a Ametista cria a cada vez que o abre. Fecha sozinho se a Ametista fechar.

    python -m ametista.voz_local_servidor --porta 8766 --referencias voz\\referencia --cache dados\\voz_local
    (senha na variável AMETISTA_VOZ_TOKEN; licença do XTTS aceita em COQUI_TOS_AGREED=1)

Só usa a biblioteca padrão, numpy, torch e o coqui-tts: nada do resto da Ametista.
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TAXA = 24000
LIMITE = 180                 # letras por pedaço: o XTTS corta frases em português acima de ~203
PAUSA_ENTRE = 0.12           # segundos de silêncio entre dois pedaços da mesma fala

estado = {"pronto": False, "etapa": "abrindo", "erro": None, "dispositivo": None, "gpu": None, "referencias": 0}
_trava = threading.Lock()
_modelo = None
_latentes = None
_parametros: dict = {}


# ====================================================================== texto
def dividir(texto: str, limite: int = LIMITE) -> list[str]:
    """Pedaços de até `limite` letras, cortando no fim das frases, depois em vírgulas e, por último, entre
    palavras."""
    texto = re.sub(r"\s+", " ", str(texto or "")).strip()
    if not texto:
        return []
    frases = re.findall(r"[^.!?…]+[.!?…]+[\"')\]]*|[^.!?…]+$", texto)
    pedacos: list[str] = []
    for f in (x.strip() for x in frases):
        if not f:
            continue
        while len(f) > limite:
            corte = max(f.rfind(s, 0, limite) for s in (", ", "; ", ": ", " — ", " - "))
            if corte < limite // 3:
                corte = f.rfind(" ", 0, limite)
            if corte <= 0:
                corte = limite
            pedacos.append(f[:corte + 1].strip())
            f = f[corte + 1:].strip()
        if pedacos and len(pedacos[-1]) + len(f) + 1 <= limite and len(pedacos[-1]) < 40:
            pedacos[-1] = f"{pedacos[-1]} {f}"         # frase curtinha junta com a anterior: soa mais natural
        else:
            pedacos.append(f)
    return [p for p in pedacos if re.search(r"\w", p)]


# ====================================================================== áudio
def _aparar(onda, taxa: int = TAXA):
    """Tira o silêncio (e o chiado) das pontas e suaviza o começo e o fim (sem estalos)."""
    import numpy as np

    onda = np.asarray(onda, dtype=np.float32).reshape(-1)
    if not len(onda):
        return onda
    janela = int(taxa * 0.02)
    n = len(onda) // janela
    if n >= 3:
        energia = np.sqrt(np.mean(onda[:n * janela].reshape(n, janela) ** 2, axis=1) + 1e-12)
        limiar = max(energia.max() * 0.03, 1e-4)
        vivos = np.where(energia > limiar)[0]
        if len(vivos):
            ini = max(0, vivos[0] * janela - int(taxa * 0.03))
            fim = min(len(onda), (vivos[-1] + 1) * janela + int(taxa * 0.08))
            onda = onda[ini:fim]
    rampa = min(len(onda) // 4, int(taxa * 0.012))
    if rampa > 0:
        onda[:rampa] *= np.linspace(0, 1, rampa, dtype=np.float32)
        onda[-rampa:] *= np.linspace(1, 0, rampa, dtype=np.float32)
    return onda


def para_wav(onda, taxa: int = TAXA) -> bytes:
    import numpy as np

    onda = np.asarray(onda, dtype=np.float32)
    pico = float(np.max(np.abs(onda))) if len(onda) else 0.0
    if pico > 0.97:                                   # sem estourar
        onda = onda * (0.97 / pico)
    pcm = (np.clip(onda, -1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


# ====================================================================== modelo
def _assinatura(refs: list[Path]) -> str:
    h = hashlib.sha1()
    for r in refs:
        st = r.stat()
        h.update(f"{r.name}|{st.st_size}|{int(st.st_mtime)}".encode())
    return h.hexdigest()[:16]


def carregar(pasta_refs: Path, cache: Path) -> None:
    global _modelo, _latentes, _parametros
    try:
        estado["etapa"] = "carregando o PyTorch"
        import torch

        refs = sorted(pasta_refs.glob("*.wav"))
        if not refs:
            raise RuntimeError(f"nenhuma amostra .wav em {pasta_refs} (rode o clonar_voz.bat)")
        estado["referencias"] = len(refs)
        dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
        estado["dispositivo"] = dispositivo
        estado["gpu"] = torch.cuda.get_device_name(0) if dispositivo == "cuda" else None
        estado["etapa"] = "carregando o XTTS-v2 (na primeira vez ele é baixado: ~1,8 GB)"
        from TTS.api import TTS

        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(dispositivo)
        modelo = tts.synthesizer.tts_model
        cfg = modelo.config
        estado["etapa"] = "aprendendo a voz das amostras"
        cache.mkdir(parents=True, exist_ok=True)
        arq = cache / f"latentes-{_assinatura(refs)}.pt"
        latentes = None
        if arq.exists():
            try:
                salvo = torch.load(arq, map_location=dispositivo)
                latentes = (salvo["gpt"].to(dispositivo), salvo["voz"].to(dispositivo))
            except Exception:
                latentes = None
        if latentes is None:
            gpt, voz = modelo.get_conditioning_latents(
                audio_path=[str(r) for r in refs], gpt_cond_len=getattr(cfg, "gpt_cond_len", 30),
                gpt_cond_chunk_len=getattr(cfg, "gpt_cond_chunk_len", 4),
                max_ref_length=getattr(cfg, "max_ref_len", 30), sound_norm_refs=getattr(cfg, "sound_norm_refs", False))
            latentes = (gpt, voz)
            try:
                torch.save({"gpt": gpt.cpu(), "voz": voz.cpu()}, arq)
            except Exception:
                pass
        _parametros = {"temperature": 0.7, "length_penalty": float(getattr(cfg, "length_penalty", 1.0)),
                       "repetition_penalty": float(getattr(cfg, "repetition_penalty", 5.0)),
                       "top_k": int(getattr(cfg, "top_k", 50)), "top_p": float(getattr(cfg, "top_p", 0.85))}
        _modelo, _latentes = modelo, latentes
        estado["etapa"] = "aquecendo"
        sintetizar("Oi.")                               # a primeira fala compila os kernels: fica mais rápida depois
        estado.update(pronto=True, etapa="pronta")
    except Exception as e:
        estado.update(erro=f"{type(e).__name__}: {e}", etapa="erro")
        print(f"[voz local] erro ao carregar: {e!r}", flush=True)


def sintetizar(texto: str, velocidade: float = 1.0) -> bytes:
    import numpy as np
    import torch

    partes = []
    silencio = np.zeros(int(TAXA * PAUSA_ENTRE), dtype=np.float32)
    with _trava, torch.inference_mode():
        for pedaco in dividir(texto):
            r = _modelo.inference(pedaco, "pt", _latentes[0], _latentes[1], speed=float(velocidade),
                                  enable_text_splitting=False, **_parametros)
            onda = r["wav"]
            if hasattr(onda, "cpu"):
                onda = onda.cpu().numpy()
            if partes:
                partes.append(silencio)
            partes.append(_aparar(onda))
    if not partes:
        raise ValueError("texto vazio")
    return para_wav(np.concatenate(partes))


# ====================================================================== servidor
class Tratador(BaseHTTPRequestHandler):
    token = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _responder(self, codigo: int, corpo: bytes, tipo: str = "application/json") -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, codigo: int, dados: dict) -> None:
        self._responder(codigo, json.dumps(dados, ensure_ascii=False).encode())

    def do_GET(self):
        if self.path == "/saude":
            return self._json(200, estado)
        self._json(404, {"erro": "não existe"})

    def do_POST(self):
        if self.headers.get("X-Token", "") != self.token:
            return self._json(403, {"erro": "senha errada"})
        tamanho = int(self.headers.get("Content-Length") or 0)
        try:
            pedido = json.loads(self.rfile.read(min(tamanho, 200_000)) or b"{}")
        except ValueError:
            return self._json(400, {"erro": "json inválido"})
        if self.path == "/sair":
            self._json(200, {"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if self.path != "/falar":
            return self._json(404, {"erro": "não existe"})
        if not estado["pronto"]:
            return self._json(503, {"erro": estado["erro"] or estado["etapa"]})
        try:
            inicio = time.time()
            audio = sintetizar(str(pedido.get("texto", ""))[:4000],
                               max(0.7, min(1.4, float(pedido.get("velocidade") or 1.0))))
            print(f"[voz local] {len(audio) // 48} ms de fala em {1000 * (time.time() - inicio):.0f} ms", flush=True)
        except ValueError as e:
            return self._json(400, {"erro": str(e)})
        except Exception as e:
            print(f"[voz local] erro: {e!r}", flush=True)
            return self._json(500, {"erro": f"{type(e).__name__}: {e}"})
        self._responder(200, audio, "audio/wav")


def _pai_vivo(pid: int) -> bool:
    if pid <= 0:
        return True
    if sys.platform == "win32":
        import ctypes

        h = ctypes.windll.kernel32.OpenProcess(0x1000 | 0x00100000, False, pid)   # QUERY_LIMITED | SYNCHRONIZE
        if not h:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(h, 0) == 0x102        # WAIT_TIMEOUT: ainda vivo
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--porta", type=int, default=8766)
    p.add_argument("--referencias", required=True)
    p.add_argument("--cache", required=True)
    p.add_argument("--pai", type=int, default=0, help="fecha sozinho quando esse processo (a Ametista) fechar")
    args = p.parse_args(argv)
    Tratador.token = os.environ.get("AMETISTA_VOZ_TOKEN", "")
    if not Tratador.token:
        print("[voz local] falta a senha (AMETISTA_VOZ_TOKEN)", flush=True)
        return 2
    servidor = ThreadingHTTPServer(("127.0.0.1", args.porta), Tratador)
    threading.Thread(target=carregar, args=(Path(args.referencias), Path(args.cache)), daemon=True).start()

    def vigiar_pai():
        while True:
            time.sleep(3)
            if not _pai_vivo(args.pai):
                print("[voz local] a Ametista fechou: saindo", flush=True)
                servidor.shutdown()
                return
    threading.Thread(target=vigiar_pai, daemon=True).start()
    print(f"[voz local] ouvindo em 127.0.0.1:{args.porta}", flush=True)
    servidor.serve_forever(poll_interval=0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
