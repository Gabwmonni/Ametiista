"""Barramento de eventos: liga o ouvido, o cérebro, a sobreposição (Qt) e a tela (WebSocket).

Qualquer parte do programa chama publicar({...}) de qualquer thread.
- Ouvintes internos (ouvido, janela Qt) recebem na hora, na thread de quem publicou.
- A tela recebe pelo WebSocket, a não ser que a mensagem tenha "interno": True.
"""
import asyncio
from typing import Awaitable, Callable

_ouvintes: list[Callable[[dict], None]] = []
_loop: asyncio.AbstractEventLoop | None = None
_transmissor: Callable[[dict], Awaitable[None]] | None = None


def ouvir(funcao: Callable[[dict], None]) -> None:
    _ouvintes.append(funcao)


def remover(funcao: Callable[[dict], None]) -> None:
    if funcao in _ouvintes:
        _ouvintes.remove(funcao)


def ligar_transmissor(loop: asyncio.AbstractEventLoop, transmissor: Callable[[dict], Awaitable[None]]) -> None:
    global _loop, _transmissor
    _loop, _transmissor = loop, transmissor


def publicar(msg: dict) -> None:
    for funcao in list(_ouvintes):
        try:
            funcao(msg)
        except Exception as e:
            print(f"[eventos] ouvinte falhou em {msg.get('tipo')}: {e}")
    if msg.get("interno") or not (_loop and _transmissor):
        return
    try:
        rodando = asyncio.get_running_loop()
    except RuntimeError:
        rodando = None
    if rodando is _loop:
        _loop.create_task(_transmissor(msg))
    else:
        asyncio.run_coroutine_threadsafe(_transmissor(msg), _loop)
