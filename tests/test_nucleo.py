"""Núcleo: o caminho completo de um pedido (com o Claude simulado)."""
import threading
import time

import pytest

from ametista import acoes, cerebro, config, estado, ferramentas, memoria, nucleo
from ametista.identidade import DONO_PADRAO, Falante
from falsos import ClienteFalso, Resposta, ferramenta


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-teste")
    cliente = ClienteFalso()
    monkeypatch.setattr(cerebro, "_cliente", cliente)
    monkeypatch.setattr(cerebro, "ollama_disponivel", lambda: False)
    return cliente


def _falas(publicados):
    return " ".join(e["texto"] for e in publicados if e["tipo"] == "fala_trecho")


def test_pedido_completo_fala_e_guarda(claude, publicados):
    claude.roteiro = [Resposta(["[feliz] Claro! ", "Anotado."])]
    r = nucleo.atender("anota que amanhã tem obra", DONO_PADRAO)
    assert r["texto"] == "Claro! Anotado." and r["emocao"] == "feliz"
    tipos = [e["tipo"] for e in publicados]
    assert tipos.index("transcricao") < tipos.index("pensando") < tipos.index("fala_inicio") < tipos.index("fala_fim")
    assert _falas(publicados) == "Claro! Anotado."
    assert memoria.buscar_conversas("obra")[0]["resposta"] == "Claro! Anotado."
    assert not estado.ocupado


def test_confirmacao_de_ponta_a_ponta(claude, publicados, monkeypatch):
    executado = []
    monkeypatch.setitem(ferramentas.FUNCOES, "pc_sistema",
                        lambda acao, confirmado=False: executado.append((acao, confirmado)) or "O PC desliga em 30 segundos.")
    claude.roteiro = [Resposta([], [ferramenta("pc_sistema", {"acao": "desligar"})], "tool_use"),
                      Resposta(["[pensativa] Quer mesmo que eu desligue o PC?"])]
    r = nucleo.atender("desliga o computador", DONO_PADRAO)
    assert r["aguardando"] and executado == []
    r = nucleo.atender("sim", DONO_PADRAO)
    assert executado == [("desligar", True)]
    assert r["texto"] == "O PC desliga em 30 segundos."
    assert acoes.listar(1)[0]["descricao"] == "Desligou o PC"


def test_nao_guarde_isso_depois(claude):
    claude.roteiro = [Resposta(["Ok, anotado."])]
    nucleo.atender("o código do portão é 4321", DONO_PADRAO)
    assert memoria.buscar_conversas("portao")
    r = nucleo.atender("não guarde isso", DONO_PADRAO)
    assert r["texto"] == "Tudo bem, não guardei."
    assert memoria.buscar_conversas("portao") == []


def test_nao_guarde_isso_junto_com_o_pedido(claude):
    claude.roteiro = [Resposta(["Entendi."])]
    nucleo.atender("não guarde isso: estou planejando uma surpresa para a Maria", DONO_PADRAO)
    assert memoria.buscar_conversas("surpresa maria") == []
    assert "NÃO guardar" in claude.chamadas[0]["system"][1]["text"]


def test_despedida_encerra_a_conversa(publicados):
    r = nucleo.atender("obrigado Ametista", DONO_PADRAO)
    assert r["texto"] == "De nada!"
    assert any(e["tipo"] == "fim_conversa" for e in publicados)


def test_fala_ignorada_na_conversa(claude, publicados):
    claude.roteiro = [Resposta(["[ignorar]"])]
    r = nucleo.atender("mãe, cadê a chave do carro?", DONO_PADRAO, sem_nome=True)
    assert r == {"ignorado": True}
    assert not [e for e in publicados if e["tipo"] in ("fala_inicio", "transcricao", "pensando")]
    assert memoria.historico() == []


def test_pedido_do_celular_volta_com_texto_e_sem_falar_no_pc(claude, publicados):
    claude.roteiro = [Resposta(["O PC está tranquilo."])]
    r = nucleo.atender("como está o PC?", DONO_PADRAO, origem="celular")
    assert r["texto"] == "O PC está tranquilo." and "audio" in r
    assert not [e for e in publicados if e["tipo"].startswith("fala_") or e["tipo"] == "pensando"]


def test_parar_tudo_cancela_pedido_em_andamento(claude, publicados):
    comecou, liberar = threading.Event(), threading.Event()
    claude.roteiro = [Resposta(["Uma história bem comprida. ", "Continua. ", "E continua."])]

    def devagar(_):
        comecou.set()
        liberar.wait(2)
    claude.ao_emitir = devagar
    resultado = {}
    t = threading.Thread(target=lambda: resultado.update(r=nucleo.atender("me conta uma história", DONO_PADRAO)))
    t.start()
    assert comecou.wait(2)
    r = nucleo.atender("para tudo", DONO_PADRAO)
    liberar.set()
    t.join(3)
    assert r["texto"] == "Parei tudo."
    assert resultado["r"] == {"cancelado": True}
    assert any(e["tipo"] == "calar" for e in publicados)
    assert acoes.listar(1)[0]["ferramenta"] == "parar_tudo"


def test_pedido_novo_substitui_o_anterior(claude):
    comecou, liberar = threading.Event(), threading.Event()
    claude.roteiro = [Resposta(["Primeira resposta. ", "Mais texto."]), Resposta(["Segunda."])]
    claude.ao_emitir = lambda p: (comecou.set(), liberar.wait(2)) if p.startswith("Primeira") else None
    res = {}
    t = threading.Thread(target=lambda: res.update(r=nucleo.atender("pergunta um", DONO_PADRAO)))
    t.start()
    assert comecou.wait(2)
    segundo = threading.Thread(target=lambda: res.update(r2=nucleo.atender("pergunta dois", DONO_PADRAO)))
    segundo.start()
    time.sleep(0.1)
    liberar.set()
    t.join(3)
    segundo.join(3)
    assert res["r"] == {"cancelado": True} and res["r2"]["texto"] == "Segunda."


def test_visitante_nao_confirma_acao_do_dono(monkeypatch):
    acoes.executar("pc_fechar", {"programa": "chrome"}, lambda programa: "fechou", falante=DONO_PADRAO)
    tratado, resposta = acoes.resolver_pendente("sim", Falante("Visita", "visitante"))
    assert tratado and resposta == "Essa confirmação é de outra pessoa."


def test_lembrete_na_proxima_conversa(claude, publicados):
    memoria.criar_lembrete("ligar para o engenheiro", None, "condicao", condicao="proxima_conversa")
    claude.roteiro = [Resposta(["Tudo bem por aqui."])]
    nucleo.atender("tudo bem?", DONO_PADRAO)
    assert _falas(publicados).startswith("Você me pediu para lembrar: ligar para o engenheiro")
    assert memoria.condicionais() == []
