"""Modo agente com o Claude simulado e um "computador" falso."""
import threading
import time

import pytest

from ametista import acoes, agente, cerebro, config, controle
from ametista.identidade import DONO_PADRAO
from falsos import ClienteFalso, Resposta, ferramenta


@pytest.fixture
def pc_falso(monkeypatch):
    """Tela e mouse de mentira: registra o que o agente fez."""
    class Feito(list):
        pass
    feito = Feito()
    geo = {"x0": 0, "y0": 0, "escala": 0.5, "largura": 1920, "altura": 1080, "quando": time.time()}

    class Img:
        def convert(self, _):
            return self

        def save(self, buf, *_a, **_k):
            buf.write(b"jpeg")
    monkeypatch.setattr(controle, "WINDOWS", True)
    monkeypatch.setattr(controle, "janela_de_comando", lambda: "")   # na frente: um programa comum, não um terminal
    monkeypatch.setattr(controle, "capturar", lambda monitor="principal", modelo=None: (Img(), dict(geo)))
    monkeypatch.setattr(controle, "clicar", lambda x, y, botao="left", vezes=1, mods="": feito.append(("clique", x, y, botao, vezes)))
    monkeypatch.setattr(controle, "digitar", lambda t: feito.append(("digitar", t)))
    monkeypatch.setattr(controle, "pressionar", lambda t, repetir=1: feito.append(("tecla", t)))
    cursor = {"p": (0, 0)}
    monkeypatch.setattr(controle, "posicao_cursor", lambda: cursor["p"])
    feito.cursor = cursor
    return feito


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-teste")
    monkeypatch.setattr(config, "AGENTE_MODELO", "claude-opus-5")
    cliente = ClienteFalso()
    monkeypatch.setattr(cerebro, "_cliente", cliente)
    return cliente


def _rodar(objetivo="organiza a pasta", usar_tela=True):
    t = agente.Tarefa(objetivo, usar_tela, DONO_PADRAO)
    agente._tarefas[t.id] = t
    agente._rodar(t)
    return t


def test_plano_acoes_na_tela_e_conclusao(claude, pc_falso, publicados):
    claude.roteiro = [
        Resposta([], [ferramenta("plano_definir", {"passos": ["Abrir a pasta", "Criar subpastas"]}, "t1")], "tool_use"),
        Resposta([], [ferramenta("screenshot", {}, "t2", "computer"),
                      ferramenta("left_click", {"coordinate": [100, 50]}, "t3", "computer"),
                      ferramenta("type", {"text": "Documentos"}, "t4", "computer")], "tool_use"),
        Resposta([], [ferramenta("passo_atualizar", {"indice": 0, "estado": "feito"}, "t5"),
                      ferramenta("concluir", {"resumo": "Organizei a pasta em 3 subpastas.", "sucesso": True}, "t6")],
                 "tool_use"),
    ]
    t = _rodar()
    assert t.estado == "concluida" and t.resumo == "Organizei a pasta em 3 subpastas."
    assert pc_falso == [("clique", 200, 100, "left", 1), ("digitar", "Documentos")]   # coordenada / 0,5
    chamada = claude.chamadas[0]
    assert chamada["beta"] and "context-management-2025-06-27" in chamada["betas"]
    assert chamada["tools"][0] == {"type": "computer_toolset_20260801"}
    assert chamada["output_config"] == {"effort": "high"} and chamada["fallbacks"] == "default"
    resultados = claude.chamadas[2]["messages"][-1]["content"]
    assert [r.get("toolset_name") for r in resultados] == ["computer"] * 3
    assert resultados[0]["content"][0]["type"] == "image"
    assert resultados[1]["content"] == [{"type": "text", "text": "OK"}]
    tipos = [e["tipo"] for e in publicados]
    assert "tarefa" in tipos and {"tipo": "agente_tela", "ativo": True} in publicados
    assert publicados[-1]["tipo"] == "alerta" or any(e["tipo"] == "alerta" for e in publicados)


def test_lote_para_depois_de_uma_falha(claude, pc_falso, monkeypatch):
    def falha(*a, **k):
        raise RuntimeError("tela travada")
    monkeypatch.setattr(controle, "clicar", falha)
    claude.roteiro = [
        Resposta([], [ferramenta("left_click", {"coordinate": [1, 1]}, "a", "computer"),
                      ferramenta("type", {"text": "x"}, "b", "computer")], "tool_use"),
        Resposta([], [ferramenta("concluir", {"resumo": "Não deu.", "sucesso": False}, "c")], "tool_use"),
    ]
    t = _rodar()
    res = claude.chamadas[1]["messages"][-1]["content"]
    assert res[0]["is_error"] and "tela travada" in res[0]["content"]
    assert res[1] == {"type": "tool_result", "tool_use_id": "b", "toolset_name": "computer", "is_error": True,
                      "content": "Not executed: an earlier computer action in this turn failed."}
    assert ("digitar", "x") not in pc_falso and t.estado == "erro"


def test_mouse_mexido_interrompe(claude, pc_falso):
    t = agente.Tarefa("x", True, DONO_PADRAO)
    t.ultimo_cursor = (10, 10)
    pc_falso.cursor["p"] = (300, 300)
    with pytest.raises(agente.Parada):
        agente._acao_computador(t, "left_click", {"coordinate": [5, 5]})


def test_pedir_confirmacao_no_meio_da_tarefa(claude, pc_falso, publicados, monkeypatch):
    from ametista import fala

    monkeypatch.setattr(fala, "falar", lambda *a, **k: "")
    claude.roteiro = [
        Resposta([], [ferramenta("pedir_confirmacao", {"pergunta": "Posso enviar o e-mail?"}, "a")], "tool_use"),
        Resposta([], [ferramenta("concluir", {"resumo": "E-mail enviado."}, "b")], "tool_use"),
    ]
    t = agente.Tarefa("manda o e-mail", False, DONO_PADRAO)
    th = threading.Thread(target=agente._rodar, args=(t,))
    th.start()
    for _ in range(200):
        if acoes.pendente():
            break
        time.sleep(0.01)
    assert t.estado == "aguardando"
    acoes.resolver_pendente("sim", DONO_PADRAO)
    th.join(3)
    assert "SIM" in claude.chamadas[1]["messages"][-1]["content"][0]["content"]
    assert t.estado == "concluida"


def test_agente_pede_sim_antes_de_digitar_no_terminal(claude, pc_falso, monkeypatch):
    from ametista import fala

    monkeypatch.setattr(fala, "falar", lambda *a, **k: "")
    monkeypatch.setattr(controle, "janela_de_comando", lambda: "terminal")
    respostas = iter([False, True, True])
    perguntas = []
    monkeypatch.setattr(acoes, "pedir_confirmacao_agente",
                        lambda pergunta, esperar=120, ficha=None: perguntas.append(pergunta) or next(respostas))
    t = agente.Tarefa("limpar", True, DONO_PADRAO)
    with pytest.raises(RuntimeError, match="não autorizou"):
        agente._acao_computador(t, "type", {"text": "rmdir /s /q C:\\obra"})
    assert ("digitar", "rmdir /s /q C:\\obra") not in pc_falso and "terminal" in perguntas[0]
    assert agente._acao_computador(t, "key", {"text": "Return"}) == "OK"
    assert ("tecla", "Return") in pc_falso and len(perguntas) == 2

    monkeypatch.setattr(controle, "janela_de_comando", lambda: "")
    agente._acao_computador(t, "type", {"text": "relatorio.pdf"})       # janela comum: sem perguntar
    assert len(perguntas) == 2
    agente._acao_computador(t, "key", {"text": "super+r"})             # abrir o Executar: pergunta
    assert len(perguntas) == 3


def test_cancelar_tarefa(claude, pc_falso):
    liberar = threading.Event()
    claude.roteiro = [Resposta([], [ferramenta("wait", {"duration": 20}, "a", "computer")], "tool_use")]
    t = agente.Tarefa("esperar", True, DONO_PADRAO)
    agente._tarefas[t.id] = t
    th = threading.Thread(target=agente._rodar, args=(t,))
    th.start()
    time.sleep(0.2)
    assert agente.cancelar_todas() == 1
    th.join(3)
    liberar.set()
    assert t.estado == "cancelada"


def test_recurso_opcional_recusado_tenta_sem_ele(claude, pc_falso):
    import anthropic
    import httpx2

    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    erro = anthropic.BadRequestError("context_management not supported", response=httpx2.Response(400, request=req), body=None)
    claude.erro_na_chamada = [erro, None]
    claude.roteiro = [Resposta([], [ferramenta("concluir", {"resumo": "ok"}, "a")], "tool_use")]
    t = _rodar(usar_tela=False)
    assert t.estado == "concluida"
    assert "context_management" not in claude.chamadas[1] and "context-management-2025-06-27" not in claude.chamadas[1]["betas"]


def test_uma_tarefa_por_vez(monkeypatch, claude):
    monkeypatch.setattr(threading.Thread, "start", lambda self: None)
    assert agente.iniciar("tarefa um").startswith("Comecei")
    assert agente.iniciar("tarefa dois").startswith("Erro")
    agente.cancelar_todas()
    for t in agente._tarefas.values():
        t.estado = "cancelada"


def test_para_tela_converte_coordenadas():
    geo = {"x0": 1920, "y0": 0, "escala": 0.75, "largura": 1440, "altura": 810, "quando": time.time()}
    assert controle.para_tela(720, 405, geo) == (1920 + 960, 540)
    assert controle.para_tela(99999, -5, geo) == (1920 + 1919, 0)      # fica dentro da tela
    assert controle.traduzir_tecla("Return") == "enter" and controle.traduzir_tecla("Page_Down") == "page down"
    assert controle.traduzir_tecla("super") == "windows" and controle.traduzir_tecla("F5") == "f5"
