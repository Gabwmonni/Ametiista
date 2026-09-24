"""Memória: conversas, privacidade, caderno, lembretes recorrentes e por condição."""
import json
import threading
import time
from datetime import datetime, timedelta

import pytest

from ametista import config, estado, memoria


def _troca(pedido, resposta, privado=False, deslocar=0):
    t = memoria.nova_troca() + deslocar
    memoria.registrar(t, "user", pedido, "Gabriel", privado=privado)
    memoria.registrar(t, "assistant", resposta, privado=privado)
    return t


def test_migra_memoria_da_v1():
    memoria.fechar()
    memoria.ARQUIVO_V1.write_text(json.dumps({"fatos": ["gosta de café"], "historico": [],
                                              "lembretes": [{"id": "abc12345", "texto": "dentista", "tipo": "lembrete",
                                                             "quando": "2099-01-01T10:00:00"}]}), encoding="utf-8")
    assert memoria.fatos() == ["gosta de café"]
    assert memoria.lembretes_pendentes()[0]["texto"] == "dentista"
    assert not memoria.ARQUIVO_V1.exists()
    for f in memoria.ARQUIVO_V1.parent.glob("memoria_v1_migrada.json"):
        f.unlink()


def test_historico_e_busca_por_palavras_sem_acento():
    _troca("toca Coldplay no Spotify", "Tocando Coldplay.")
    _troca("guardei a planta de Jundiaí na pasta Projetos", "Anotado!", deslocar=5)
    assert [m["role"] for m in memoria.historico()] == ["user", "assistant", "user", "assistant"]
    achados = memoria.buscar_conversas("planta jundiai")
    assert achados and "Jundiaí" in achados[0]["pedido"]


def test_busca_por_periodo_sem_consulta():
    _troca("que horas são", "São dez.")
    agora = datetime.now()
    achados = memoria.buscar_conversas("", agora - timedelta(hours=1), agora + timedelta(hours=1))
    assert len(achados) == 1 and achados[0]["resposta"] == "São dez."
    assert memoria.buscar_conversas("", agora - timedelta(days=3), agora - timedelta(days=2)) == []


def test_troca_privada_nao_vai_para_o_disco_mas_fica_no_contexto():
    _troca("minha senha do wifi é xyz", "Ok, não vou guardar.", privado=True)
    assert memoria.buscar_conversas("senha wifi") == []
    assert any("senha" in m["content"] for m in memoria.historico())


def test_nao_guarde_isso_apaga_troca_e_fatos_dela():
    t = _troca("meu código do cofre é 1234", "Guardei.")
    memoria.lembrar_fato("código do cofre 1234", t)
    memoria.apagar_troca(t)
    assert memoria.fatos() == []
    assert memoria.buscar_conversas("cofre") == []


def test_modo_privado_bloqueia_memoria():
    estado.definir_privado(True)
    assert "modo privado" in memoria.lembrar_fato("teste")
    assert "modo privado" in memoria.caderno_guardar("x", "y")
    _troca("oi", "oi")
    assert memoria.conversas_do_periodo(datetime.now() - timedelta(hours=1), datetime.now() + timedelta(hours=1)) == []
    estado.definir_privado(False)


def test_caderno_guardar_atualizar_buscar_apagar():
    memoria.caderno_guardar("Notebook Dell", "16 GB de RAM", "equipamento")
    memoria.caderno_guardar("Notebook Dell", "SSD de 1 TB", "equipamento", acrescentar=True)
    itens = memoria.caderno_buscar("dell memoria")
    assert itens[0]["detalhes"] == "16 GB de RAM\nSSD de 1 TB"
    assert memoria.caderno_apagar("notebook dell") == 1
    assert memoria.caderno_listar() == []


def test_recorrencias():
    p = memoria.proxima_ocorrencia
    assert p({"tipo": "diario"}, datetime(2026, 9, 24, 8), datetime(2026, 9, 24, 9)) == datetime(2026, 9, 25, 8)
    assert p({"tipo": "dias_uteis"}, datetime(2026, 9, 25, 8), datetime(2026, 9, 25, 9)) == datetime(2026, 9, 28, 8)
    assert p({"tipo": "semanal", "dias": [2]}, datetime(2026, 9, 24, 8), datetime(2026, 9, 24, 9)) == datetime(2026, 9, 30, 8)
    assert p({"tipo": "mensal", "dia": 31}, datetime(2026, 1, 31, 9), datetime(2026, 1, 31, 10)) == datetime(2026, 2, 28, 9)
    assert p({"tipo": "anual", "mes": 2, "dia": 29}, datetime(2024, 2, 29, 9), datetime(2025, 1, 1)) == datetime(2025, 2, 28, 9)
    # véspera de aniversário no dia 1º de março (ano bissexto)
    assert p({"tipo": "anual", "mes": 3, "dia": 1, "antes_dias": 1}, datetime(2028, 1, 1, 18),
             datetime(2028, 1, 1)) == datetime(2028, 2, 29, 18)


def test_retirar_vencidos_unico_e_recorrente():
    agora = datetime.now()
    memoria.criar_lembrete("único", agora - timedelta(minutes=1))
    rec = memoria.criar_lembrete("remédio", agora - timedelta(minutes=2), recorrencia={"tipo": "diario"})
    velho = memoria.criar_lembrete("perdido", agora - timedelta(hours=8), recorrencia={"tipo": "diario"})
    vencidos = {v["texto"] for v in memoria.retirar_vencidos(agora)}
    assert vencidos == {"único", "remédio"}      # o perdido há mais de 6 h é pulado em silêncio
    pend = {l["texto"]: l for l in memoria.lembretes_pendentes()}
    assert "único" not in pend
    assert datetime.fromisoformat(pend["remédio"]["quando"]) > agora
    assert datetime.fromisoformat(pend["perdido"]["quando"]) > agora
    assert rec["id"] and velho["id"]


def test_lembretes_por_condicao():
    memoria.criar_lembrete("abrir o projeto", None, "condicao", condicao="ao_abrir:AutoCAD")
    memoria.criar_lembrete("ligar para a mãe", None, "condicao", condicao="ao_chegar")
    assert memoria.retirar_condicionais("ao_abrir:Planilha.xlsx - Excel EXCEL.EXE") == []
    assert [i["texto"] for i in memoria.retirar_condicionais("ao_abrir:AutoCAD 2024 - Planta.dwg acad.exe")] == \
        ["abrir o projeto"]
    # criado agora: não dispara no "ao ligar" desta mesma sessão
    assert memoria.retirar_condicionais("ao_chegar", criado_antes=0) == []
    assert [i["texto"] for i in memoria.retirar_condicionais("ao_chegar")] == ["ligar para a mãe"]


def test_remover_lembrete_de_aniversario_remove_o_grupo():
    a = memoria.criar_lembrete("aniversário de Maria", datetime.now() + timedelta(days=3), "aniversario",
                               recorrencia={"tipo": "anual", "mes": 1, "dia": 1}, grupo="g1")
    memoria.criar_lembrete("aniversário de Maria", datetime.now() + timedelta(days=2), "aniversario_vespera",
                           recorrencia={"tipo": "anual", "mes": 1, "dia": 1, "antes_dias": 1}, grupo="g1")
    assert memoria.remover_lembrete(a["id"])
    assert memoria.lembretes_pendentes() == []


@pytest.fixture
def fastembed_lento(monkeypatch):
    """fastembed falso que demora para carregar (como no primeiro download) e gera vetores por palavra."""
    import sys
    import types

    import numpy as np

    from ametista import semantica

    liberar = threading.Event()

    class TextEmbedding:
        def __init__(self, modelo, cache_dir=None):
            liberar.wait(5)

        def embed(self, textos):
            for t in textos:
                v = np.zeros(16, dtype=np.float32)
                for p in t.lower().split():
                    v[sum(map(ord, p)) % 16] += 1
                yield v

    monkeypatch.setitem(sys.modules, "fastembed", types.SimpleNamespace(TextEmbedding=TextEmbedding))
    for nome, valor in (("_modelo", None), ("_falhou", False), ("_aquecendo", False)):
        monkeypatch.setattr(semantica, nome, valor)
    monkeypatch.setattr(semantica, "_ao_ficar_pronto", [])
    monkeypatch.setattr(semantica, "PASTA", memoria.ARQUIVO.parent / "embeddings")
    yield liberar
    liberar.set()


def test_modelo_de_significado_nunca_atrasa_um_pedido(fastembed_lento, monkeypatch):
    from ametista import semantica

    monkeypatch.setattr(config, "BUSCA_SEMANTICA", False)
    t = memoria.nova_troca()
    memoria.registrar(t, "user", "onde deixei a nota fiscal da betoneira?", "Gabriel")
    memoria.registrar(t, "assistant", "Na gaveta da garagem.")
    monkeypatch.setattr(config, "BUSCA_SEMANTICA", True)

    inicio = time.monotonic()
    assert semantica.vetor("betoneira") is None                  # o modelo ainda está carregando
    assert memoria.buscar_conversas("nota fiscal")               # a busca por palavras responde na hora
    assert time.monotonic() - inicio < 1 and semantica.situacao() == "carregando"

    feitos = []
    semantica.aquecer(depois=lambda: feitos.append(memoria.vetorizar_pendentes()))   # não perde o aviso
    fastembed_lento.set()
    for _ in range(100):
        if feitos and memoria._consulta("SELECT 1 FROM vetores WHERE tabela='troca' AND ref=?", (t,)):
            break
        time.sleep(0.05)
    assert feitos == [1] and semantica.pronto() and semantica.situacao() == "ativa"
    assert memoria._consulta("SELECT 1 FROM vetores WHERE tabela='troca' AND ref=?", (t,))
    assert semantica.vetor("betoneira") is not None
