"""Ponte do celular no PC: status só quando alguém está olhando (economia)."""
import asyncio

from ametista import nuvem


def _rodar(n, segundos, monkeypatch, antes=None):
    monkeypatch.setattr(nuvem, "STATUS_S", 0.05)
    monkeypatch.setattr(nuvem, "VIVO_S", 0.3)
    monkeypatch.setattr(nuvem.Nuvem, "_info", staticmethod(lambda: {"cpu": 1}))
    enviados = []

    async def enviar(msg):
        enviados.append(msg["tipo"])

    async def cenario():
        n._pedir_status = asyncio.Event()
        n._enviar = enviar
        tarefa = asyncio.create_task(n._status_periodico())
        if antes:
            await antes(n)
        await asyncio.sleep(segundos)
        tarefa.cancel()

    asyncio.run(cenario())
    return enviados


def test_ponte_antiga_recebe_status_sempre(monkeypatch):
    n = nuvem.Nuvem()
    n.rele_novo, n.celulares = False, 0
    assert _rodar(n, 0.35, monkeypatch).count("status") >= 4


def test_sem_ninguem_olhando_so_estou_vivo(monkeypatch):
    n = nuvem.Nuvem()
    n.rele_novo, n.celulares = True, 0
    enviados = _rodar(n, 0.7, monkeypatch)
    assert "status" not in enviados and 1 <= enviados.count("vivo") <= 3


def test_celular_abriu_o_app_recebe_status_na_hora_e_depois_periodico(monkeypatch):
    n = nuvem.Nuvem()
    n.rele_novo, n.celulares = True, 0

    async def abriu(n):
        await asyncio.sleep(0.02)
        n.celulares = 1
        n._pedir_status.set()

    enviados = _rodar(n, 0.3, monkeypatch, antes=abriu)
    assert enviados and enviados[0] == "status" and enviados.count("status") >= 3 and "vivo" not in enviados
