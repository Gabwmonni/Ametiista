"""Ligação do PC com o app do celular (via Cloudflare).

O PC abre uma conexão de saída para o Worker (NUVEM_URL) e fica esperando pedidos do celular.
Sem portas abertas no roteador. Tudo autenticado com a NUVEM_CHAVE.
"""
import asyncio
import base64
import hashlib
import io
import json
import secrets
import threading
import time

from . import config, eventos

ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sem 0/O, 1/I para não confundir


def configurada() -> bool:
    return bool(config.NUVEM_URL and config.NUVEM_CHAVE)


class Nuvem:
    def __init__(self):
        self.ws = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.conectada = False
        eventos.ouvir(self._evento)

    # ------------------------------------------------------------ ciclo
    def iniciar(self) -> None:
        if not configurada():
            print("[nuvem] celular não configurado (NUVEM_URL/NUVEM_CHAVE)")
            return
        threading.Thread(target=lambda: asyncio.run(self._manter()), daemon=True, name="nuvem").start()

    async def _manter(self) -> None:
        import websockets

        self.loop = asyncio.get_running_loop()
        url = config.NUVEM_URL.rstrip("/").replace("https://", "wss://").replace("http://", "ws://") + \
            "/api/ws?papel=pc"
        espera = 2
        while True:
            try:
                try:
                    conexao = websockets.connect(url, additional_headers={"x-chave": config.NUVEM_CHAVE},
                                                 max_size=8 * 1024 * 1024, ping_interval=25)
                except TypeError:  # versões antigas do websockets
                    conexao = websockets.connect(url, extra_headers={"x-chave": config.NUVEM_CHAVE},
                                                 max_size=8 * 1024 * 1024, ping_interval=25)
                async with conexao as ws:
                    self.ws, self.conectada, espera = ws, True, 2
                    print("[nuvem] conectada ao celular")
                    await self._enviar({"tipo": "ola", "ligado_desde": self._boot_ms(), "info": self._info()})
                    status = asyncio.create_task(self._status_periodico())
                    try:
                        async for bruto in ws:
                            try:
                                msg = json.loads(bruto)
                            except ValueError:
                                continue
                            threading.Thread(target=self._tratar, args=(msg,), daemon=True).start()
                    finally:
                        status.cancel()
            except Exception as e:
                if self.conectada:
                    print(f"[nuvem] conexão caiu: {e}")
            self.ws, self.conectada = None, False
            await asyncio.sleep(espera)
            espera = min(espera * 2, 60)

    async def _enviar(self, msg: dict) -> None:
        if self.ws is not None:
            await self.ws.send(json.dumps(msg))

    def enviar(self, msg: dict) -> bool:
        """Pode ser chamado de qualquer thread."""
        if not (self.loop and self.ws):
            return False
        try:
            asyncio.run_coroutine_threadsafe(self._enviar(msg), self.loop).result(timeout=15)
            return True
        except Exception as e:
            print(f"[nuvem] não consegui enviar: {e}")
            return False

    async def _status_periodico(self) -> None:
        while True:
            await asyncio.sleep(30)
            info = await asyncio.to_thread(self._info)
            await self._enviar({"tipo": "status", "info": info})

    # ------------------------------------------------------------ informações do PC
    @staticmethod
    def _boot_ms() -> int:
        import psutil

        return int(psutil.boot_time() * 1000)

    @staticmethod
    def _info() -> dict:
        import platform

        import psutil

        from . import pc, spotify

        info = {"nome": platform.node(), "cpu": round(psutil.cpu_percent(interval=0.3)),
                "ram": round(psutil.virtual_memory().percent)}
        bat = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
        if bat:
            info["bateria"] = round(bat.percent)
        if config.NUVEM_MOSTRAR_JANELA:
            titulo, prog = pc.janela_ativa()
            if titulo and not prog.lower().startswith("python"):
                info["janela"] = titulo[:60]
        if spotify.conectado():
            try:
                atual = spotify.cliente().current_playback()
                if atual and atual.get("is_playing") and atual.get("item"):
                    f = atual["item"]
                    info["tocando"] = f"{f['name']} - {f['artists'][0]['name']}"[:60]
            except Exception:
                pass
        return info

    # ------------------------------------------------------------ pedidos do celular
    def _tratar(self, msg: dict) -> None:
        tipo, para, pid = msg.get("tipo"), msg.get("de"), msg.get("id")
        try:
            if tipo == "pedido":
                self._pedido(msg, para, pid)
            elif tipo == "tela":
                self._tela(para, pid)
            elif tipo == "celular_pareado":
                eventos.publicar({"tipo": "aviso", "texto": f"Celular conectado: {msg.get('nome', '')}."})
        except Exception as e:
            print(f"[nuvem] erro no pedido: {e}")
            self.enviar({"tipo": "erro", "para": para, "id": pid, "texto": f"Deu erro no PC: {e}"})

    def _pedido(self, msg: dict, para: str, pid: str) -> None:
        from . import nucleo
        from .identidade import DONO_PADRAO
        from .ouvido import tirar_nome, transcrever_bytes

        texto = (msg.get("texto") or "").strip()
        if msg.get("audio"):
            texto = transcrever_bytes(base64.b64decode(msg["audio"]))
            texto = tirar_nome(texto)[0] or texto
            self.enviar({"tipo": "transcricao", "para": para, "id": pid, "texto": texto})
            if not texto:
                self.enviar({"tipo": "erro", "para": para, "id": pid, "texto": "Não entendi o áudio."})
                return
        eventos.publicar({"tipo": "aviso_celular", "texto": texto, "interno": True})
        # O celular pareado é do dono: atende com permissão total
        r = nucleo.atender(texto, DONO_PADRAO, origem="celular")
        audio = r.get("audio")
        mime = "audio/wav" if audio and audio.startswith("UklGR") else "audio/mpeg"  # UklGR = "RIFF"
        self.enviar({"tipo": "resposta", "para": para, "id": pid, "texto": r.get("texto", ""),
                     "emocao": r.get("emocao", "neutra"), "audio": audio, "mime": mime})

    def _tela(self, para: str, pid: str) -> None:
        from PIL import Image

        from . import pc

        cap = pc.ver_tela()
        img = Image.open(io.BytesIO(base64.b64decode(cap["imagem_b64"])))
        img.thumbnail((1280, 1280))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=70)
        titulo, prog = pc.janela_ativa()
        self.enviar({"tipo": "tela", "para": para, "id": pid, "imagem": base64.b64encode(buf.getvalue()).decode(),
                     "janela": f"{titulo} ({prog})" if titulo else ""})

    # ------------------------------------------------------------ avisos para o celular
    def _evento(self, msg: dict) -> None:
        tipo = msg.get("tipo")
        if tipo == "alerta":
            self._notificar("Ametista", msg.get("texto", ""))
        elif tipo == "notificar_celular":
            self._notificar(msg.get("titulo", "Ametista"), msg.get("texto", ""))

    def _notificar(self, titulo: str, texto: str) -> None:
        if self.conectada and texto:
            threading.Thread(target=self.enviar, args=({"tipo": "notificar", "titulo": titulo, "texto": texto},),
                             daemon=True).start()

    # ------------------------------------------------------------ pareamento
    def novo_codigo(self) -> tuple[str, str]:
        """Gera um código de uso único (10 minutos). Devolve (código, link para o QR)."""
        codigo = "".join(secrets.choice(ALFABETO) for _ in range(8))
        ok = self.enviar({"tipo": "parear_codigo", "hash": hashlib.sha256(codigo.encode()).hexdigest()})
        if not ok:
            raise RuntimeError("O PC não está conectado ao serviço do celular (confira NUVEM_URL e a internet).")
        return codigo, f"{config.NUVEM_URL.rstrip('/')}/#parear={codigo}"

    def revogar_celulares(self) -> bool:
        return self.enviar({"tipo": "revogar_celulares"})


_instancia: Nuvem | None = None


def instancia() -> Nuvem:
    global _instancia
    if _instancia is None:
        _instancia = Nuvem()
    return _instancia


def gerar_chave() -> str:
    return secrets.token_urlsafe(32)


if __name__ == "__main__":  # teste rápido: python -m ametista.nuvem
    n = instancia()
    n.iniciar()
    time.sleep(3)
    print("conectada:", n.conectada)
