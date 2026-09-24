"""Rotinas (com agendamento e desfazer) e iniciativa com limites."""
import time
from datetime import datetime

import pytest

from ametista import acoes, avisos, config, estado, ferramentas, memoria, pc, proatividade, rotinas


@pytest.fixture
def rotinas_limpas():
    if config.ROTINAS_ARQ.exists():
        config.ROTINAS_ARQ.unlink()
    yield
    if config.ROTINAS_ARQ.exists():
        config.ROTINAS_ARQ.unlink()


def test_rotinas_padrao_sao_criadas(rotinas_limpas):
    nomes = [r["nome"] for r in rotinas.carregar()]
    assert nomes == ["bom dia", "vou dormir", "modo filme"]
    assert config.ROTINAS_ARQ.exists()
    for r in rotinas.carregar():
        rotinas.validar_passos(r["passos"])


def test_validacao_de_passos(rotinas_limpas):
    with pytest.raises(ValueError):
        rotinas.validar_passos([{"ferramenta": "nao_existe"}])
    with pytest.raises(ValueError):
        rotinas.validar_passos([{"ferramenta": "rotina_executar", "args": {"nome": "x"}}])   # sem laços
    with pytest.raises(ValueError):
        rotinas.validar_passos([{"falar": "a", "resumo": True}])
    with pytest.raises(ValueError):
        rotinas.validar_passos([])


def test_modo_filme_e_desfazer(rotinas_limpas, dono, monkeypatch):
    monkeypatch.setattr(pc, "volume_atual", lambda: 25)
    volumes = []
    monkeypatch.setitem(ferramentas.FUNCOES, "pc_volume", lambda acao, valor=10: volumes.append(valor) or f"Volume {valor}")
    monkeypatch.setattr(pc, "volume", ferramentas.FUNCOES["pc_volume"])
    fala = ferramentas.executar("rotina_executar", {"nome": "modo filme"})
    assert fala == "Modo filme ligado. Bom filme!"
    assert estado.nao_perturbe_ate() and volumes == [70]
    item = acoes.listar(1)[0]
    assert item["ferramenta"] == "rotina_executar" and item["desfazivel"]
    assert acoes.desfazer(item["id"]) == "Desfiz a rotina."
    assert volumes == [70, 25] and not estado.nao_perturbe_ate()


def test_rotina_para_na_confirmacao(rotinas_limpas, dono, monkeypatch):
    monkeypatch.setattr(pc, "volume_atual", lambda: None)
    monkeypatch.setitem(ferramentas.FUNCOES, "pc_volume", lambda acao, valor=10: "ok")
    fala = ferramentas.executar("rotina_executar", {"nome": "vou dormir"})
    assert fala.endswith("Posso desligar o PC?")
    assert fala.startswith(f"Boa noite, {config.DONO}")
    assert acoes.pendente()["nome"] == "pc_sistema"


def test_rotina_agendada_pula_acao_critica(rotinas_limpas, monkeypatch):
    monkeypatch.setitem(ferramentas.FUNCOES, "pc_volume", lambda acao, valor=10: "ok")
    monkeypatch.setattr(pc, "volume_atual", lambda: None)
    faladas = []
    monkeypatch.setattr(avisos, "proativo", lambda texto, emocao="neutra", **k: faladas.append(texto))
    lista = rotinas.carregar()
    lista[1]["horario"] = "23:00"
    rotinas.salvar(lista)
    assert rotinas.agendadas(datetime(2026, 9, 24, 23, 0)) == ["vou dormir"]
    assert acoes.pendente() is None                       # desligar foi pulado
    assert rotinas.agendadas(datetime(2026, 9, 24, 23, 0)) == []   # uma vez por dia
    assert faladas and "Durma bem" in faladas[0]


def test_criar_rotina_por_voz(rotinas_limpas, dono):
    r = ferramentas.executar("rotina_criar", {"nome": "modo jogo", "frases": ["hora do jogo"],
                                              "passos": [{"ferramenta": "pc_abrir", "args": {"alvo": "Steam"}},
                                                         {"falar": "Bom jogo!"}], "horario": "20:00",
                                              "dias": ["sexta", "sábado"]})
    assert r == "Rotina modo jogo criada com 2 passos. Ela roda sozinha às 20:00."
    assert rotinas.achar_por_frase("hora do jogo") == "modo jogo"
    assert rotinas.obter("modo jogo")["dias"] == [4, 5]
    assert ferramentas.executar("rotina_criar", {"nome": "ruim", "passos": [{"x": 1}]}).startswith("Erro")


# ---------------------------------------------------------------- iniciativa
def _livre(monkeypatch):
    monkeypatch.setattr(config, "PROATIVIDADE", 2)
    monkeypatch.setattr(config, "HORARIO_SILENCIO", "03:00-03:01")
    monkeypatch.setattr(config, "PROATIVO_MAX_HORA", 3)
    monkeypatch.setattr(config, "PROATIVO_INTERVALO_MIN", 20)


def test_regras_da_iniciativa(monkeypatch):
    _livre(monkeypatch)
    ok = dict(ocioso=5, tela_cheia=False)
    assert proatividade.pode_falar(**ok)
    assert not proatividade.pode_falar(ocioso=5, tela_cheia=True)                 # jogo/filme em tela cheia
    assert proatividade.pode_falar(proatividade.URGENTE, ocioso=5, tela_cheia=True)
    assert not proatividade.pode_falar(ocioso=900, tela_cheia=False)              # não está no PC
    estado.definir_privado(True)
    assert not proatividade.pode_falar(proatividade.URGENTE, **ok)                # privado: nunca
    estado.definir_privado(False)
    monkeypatch.setattr(config, "PROATIVIDADE", 1)
    assert not proatividade.pode_falar(nivel_min=2, **ok)
    assert proatividade.pode_falar(nivel_min=1, **ok)


def test_limite_de_frequencia(monkeypatch):
    _livre(monkeypatch)
    agora = time.time()
    proatividade.marcar("a", agora - 600)
    assert not proatividade.pode_falar(agora=agora, ocioso=5, tela_cheia=False)   # menos de 20 min
    proatividade._historico[:] = [agora - 3000, agora - 2500, agora - 2000]
    assert not proatividade.pode_falar(agora=agora, ocioso=5, tela_cheia=False)   # 3 na última hora
    proatividade._historico[:] = []
    proatividade.marcar("chuva", agora - 3600)
    assert not proatividade.pode_falar(chave="chuva", intervalo_chave_h=6, agora=agora, ocioso=5, tela_cheia=False)


def test_resumo_do_dia(monkeypatch):
    monkeypatch.setattr(ferramentas, "clima", lambda dias=1: "Agora em São Paulo: 18°C (sensação 17°C), nublado, "
                                                             "umidade 80%.\nHoje: mínima 15°C, máxima 22°C, chuva, "
                                                             "chance de chuva 80%.")
    agora = datetime.now().replace(hour=8, minute=0)
    memoria.criar_lembrete("reunião", agora.replace(hour=15), "lembrete")
    texto = proatividade.resumo_do_dia(agora)
    assert texto.startswith(f"Bom dia, {config.DONO}!")
    assert "Agora faz 18°C." in texto and "80 por cento de chance de chuva" in texto
    assert "reunião às 15:00" in texto


def test_vigia_dispara_condicoes_e_resumo(monkeypatch):
    _livre(monkeypatch)
    ditos = []
    monkeypatch.setattr(avisos, "alerta", lambda texto, *a, **k: ditos.append(("alerta", texto)))
    monkeypatch.setattr(avisos, "proativo", lambda texto, *a, **k: ditos.append(("proativo", texto)))
    monkeypatch.setattr(proatividade, "resumo_do_dia", lambda agora=None: "resumo!")
    ocioso = {"v": 5}
    monkeypatch.setattr(pc, "tempo_ocioso", lambda: ocioso["v"])
    monkeypatch.setattr(pc, "tela_cheia", lambda: False)
    monkeypatch.setattr(pc, "janela_ativa", lambda: ("Planta.dwg - AutoCAD", "acad.exe"))
    memoria.criar_lembrete("salvar backup", None, "condicao", condicao="ao_abrir:autocad")
    item = memoria.criar_lembrete("ligar pra mãe", None, "condicao", condicao="ao_chegar")
    memoria._exec("UPDATE lembretes SET criado=? WHERE id=?", ("2000-01-01T00:00:00", item["id"]))
    v = proatividade.Vigia()
    v._chuva = v._disco = v._bateria = lambda *a: None
    v.rodada()
    assert ("alerta", "Você me pediu para lembrar: ligar pra mãe") in ditos      # "ao chegar" = ao ligar o PC
    assert ("alerta", "Você me pediu para lembrar: salvar backup") in ditos
    assert ("proativo", "resumo!") in ditos
    ditos.clear()
    v.rodada()
    assert ditos == []                                                           # resumo só uma vez por dia
    # saiu do PC e voltou
    memoria.criar_lembrete("tomar água", None, "condicao", condicao="ao_voltar")
    ocioso["v"] = 900
    v.rodada()
    ocioso["v"] = 2
    v.rodada()
    assert ("alerta", "Você me pediu para lembrar: tomar água") in ditos


def test_sugere_pausa(monkeypatch):
    _livre(monkeypatch)
    monkeypatch.setattr(config, "PAUSA_MINUTOS", 120)
    ditos = []
    monkeypatch.setattr(avisos, "proativo", lambda texto, *a, **k: ditos.append(texto))
    monkeypatch.setattr(pc, "tempo_ocioso", lambda: 3)
    monkeypatch.setattr(pc, "tela_cheia", lambda: False)
    monkeypatch.setattr(pc, "janela_ativa", lambda: ("", ""))
    estado.lembrar("resumo_dia", datetime.now().date().isoformat())
    v = proatividade.Vigia()
    v._chuva = v._disco = v._bateria = lambda *a: None
    v.sessao_desde = time.time() - 121 * 60
    v.rodada()
    assert ditos and "2 horas direto no computador" in ditos[0]
