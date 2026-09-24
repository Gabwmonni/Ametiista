"""Índice de arquivos e diagnóstico."""
import os
import time

import pytest

from ametista import arquivos, diagnostico


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    base = tmp_path / "Documentos"
    (base / "Projetos" / "Jundiaí").mkdir(parents=True)
    (base / "node_modules").mkdir()
    for caminho in ["Projetos/Jundiaí/Planta Jundiai rev3.dwg", "Projetos/Jundiaí/Planta Jundiai rev3.pdf",
                    "Orçamento obra 2026.xlsx", "foto da obra.jpg", "instalar.exe", "node_modules/lixo.js"]:
        (base / caminho).write_bytes(b"x")
    antigo = base / "Orçamento obra 2025.xlsx"
    antigo.write_bytes(b"x")
    os.utime(antigo, (time.time() - 400 * 86400, time.time() - 400 * 86400))
    monkeypatch.setattr(arquivos, "ARQUIVO", tmp_path / "arquivos.db")
    monkeypatch.setattr(arquivos, "pastas", lambda: [base])
    assert arquivos.indexar() == 6                          # node_modules fica de fora
    return base


def test_busca_por_nome_falado(pasta):
    achados = arquivos.buscar("planta de jundiaí")
    assert {a["nome"] for a in achados[:2]} == {"Planta Jundiai rev3.dwg", "Planta Jundiai rev3.pdf"}
    assert arquivos.buscar("planta jundiai", tipo="pdf")[0]["nome"] == "Planta Jundiai rev3.pdf"
    assert arquivos.buscar("planilha de orçamento")[0]["nome"] == "Orçamento obra 2026.xlsx"   # a mais recente
    assert not any(a["nome"] == "lixo.js" for a in arquivos.buscar("lixo"))                    # pasta ignorada


def test_abrir_so_dentro_das_pastas(pasta, tmp_path, monkeypatch):
    abertos = []
    monkeypatch.setattr(arquivos.subprocess, "Popen", lambda *a, **k: abertos.append(a[0]))
    monkeypatch.setattr(arquivos.os, "startfile", lambda p: abertos.append(p), raising=False)
    fora = tmp_path / "segredo.txt"
    fora.write_text("x")
    assert arquivos.abrir(str(fora)).startswith("Só abro arquivos")
    assert arquivos.abrir(str(pasta / "foto da obra.jpg")) == "Abrindo foto da obra.jpg."
    assert abertos


def test_executavel_pede_confirmacao():
    from ametista import acoes

    assert acoes.risco("arquivo_abrir", {"caminho": r"C:\Users\x\Downloads\instalar.exe"}) == acoes.CONFIRMAR
    assert acoes.risco("arquivo_abrir", {"caminho": r"C:\Users\x\Documents\a.pdf"}) == acoes.LIVRE


def test_resumo_do_diagnostico():
    itens = [{"item": "Internet", "situacao": "ok", "detalhe": "conectada"},
             {"item": "Microfone", "situacao": "erro", "detalhe": "não consegui abrir o microfone"},
             {"item": "Spotify", "situacao": "aviso", "detalhe": "não configurado (opcional)"},
             {"item": "Voz", "situacao": "aviso", "detalhe": "respondeu em 5000 ms"}]
    r = diagnostico.resumir(itens)
    assert "1 itens ok" in r and "Microfone, não consegui abrir o microfone" in r and "Voz" in r
    assert "Spotify" not in r                                  # opcional não vira reclamação
    assert diagnostico.resumir(itens[:1]) == "Fiz o diagnóstico: está tudo funcionando, 1 itens ok."
    assert "[ERRO] Microfone" in diagnostico.relatorio(itens)


def test_diagnostico_completo_nao_quebra(monkeypatch):
    import httpx

    def sem_rede(*a, **k):
        raise httpx.ConnectError("sem rede")
    monkeypatch.setattr(httpx, "get", sem_rede)
    itens = diagnostico.executar()
    nomes = {i["item"] for i in itens}
    assert {"Ametista", "Internet", "Cérebro na nuvem (Claude)", "Voz", "Memória", "Disco"} <= nomes
    assert next(i for i in itens if i["item"] == "Internet")["situacao"] == "erro"
    assert next(i for i in itens if i["item"] == "Cérebro na nuvem (Claude)")["situacao"] == "erro"
