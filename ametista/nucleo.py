"""Atende um pedido, venha ele da voz, do atalho, da caixa de texto ou do celular."""
import asyncio
import threading

from . import cerebro, eventos, voz
from .identidade import DONO_PADRAO, Falante, falante_atual

_trava = threading.Lock()


def atender(texto: str, falante: Falante = DONO_PADRAO, mostrar_pedido: bool = True,
            origem: str = "pc") -> dict:
    """Bloqueante: roda numa thread de trabalho, nunca no loop do servidor.

    falante: quem pediu (a voz identificada). Texto digitado no PC e o celular pareado contam como o dono.
    origem: "pc" ou "celular" (a resposta do celular volta só para o celular).
    """
    texto = (texto or "").strip()
    if not texto:
        return {}
    with _trava:  # um pedido por vez
        token = falante_atual.set(falante)
        try:
            if origem == "pc":
                if mostrar_pedido:
                    eventos.publicar({"tipo": "transcricao", "texto": texto,
                                      "quem": falante.nome if falante.nome != DONO_PADRAO.nome else ""})
                eventos.publicar({"tipo": "pensando"})
            r = cerebro.pensar(texto, falante)
            r["audio"] = asyncio.run(voz.sintetizar(r["texto"]))
            r["tipo"] = "resposta"
            if origem == "pc":
                eventos.publicar(r)
            return r
        finally:
            falante_atual.reset(token)
