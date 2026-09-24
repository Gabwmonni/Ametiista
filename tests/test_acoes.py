"""Registro de ações, permissões por tipo de ação, confirmação e desfazer."""
from ametista import acoes, estado, memoria, pc
from ametista.identidade import DONO_PADRAO, Falante, falante_atual


def _desligar(acao, confirmado=False):
    return f"feito: {acao} (confirmado={confirmado})"


def test_acao_critica_espera_o_sim(dono, publicados):
    r = acoes.executar("pc_sistema", {"acao": "desligar"}, _desligar)
    assert r.startswith("PRECISA CONFIRMAR")
    assert acoes.pendente()["pergunta"] == "Posso desligar o PC?"
    assert any(e["tipo"] == "aguardando" for e in publicados)
    tratado, resposta = acoes.resolver_pendente("Sim, pode desligar", DONO_PADRAO)
    assert tratado and resposta == "feito: desligar (confirmado=True)"
    assert acoes.pendente() is None
    ultima = acoes.listar(1)[0]
    assert ultima["descricao"] == "Desligou o PC" and ultima["ok"] and ultima["desfazivel"]


def test_ia_nao_consegue_pular_a_confirmacao(dono):
    r = acoes.executar("pc_sistema", {"acao": "desligar", "confirmado": True}, _desligar)
    assert r.startswith("PRECISA CONFIRMAR")        # o parâmetro vindo da IA é ignorado


def test_nao_cancela_e_outra_fala_descarta(dono):
    acoes.executar("pc_fechar", {"programa": "chrome"}, lambda programa: "fechou")
    assert acoes.resolver_pendente("não, deixa", DONO_PADRAO) == (True, "Tudo bem, não fiz.")
    acoes.executar("pc_fechar", {"programa": "chrome"}, lambda programa: "fechou")
    assert acoes.resolver_pendente("toca uma música", DONO_PADRAO) == (False, None)
    assert acoes.pendente() is None


def test_confirmacao_expira(dono, monkeypatch):
    acoes.executar("pc_fechar", {"programa": "chrome"}, lambda programa: "fechou")
    acoes._pendente["criado"] -= acoes.VALIDADE_CONFIRMACAO + 1
    assert acoes.pendente() is None


def test_permissoes_por_nivel():
    visitante = Falante("Ana", "visitante")
    familia = Falante("Bia", "familia")
    token = falante_atual.set(visitante)
    try:
        assert acoes.executar("pc_abrir", {"alvo": "x"}, lambda alvo: "ok").startswith("NEGADO")
        assert acoes.executar("pc_volume", {"acao": "aumentar"}, lambda acao, valor=10: "ok") == "ok"
    finally:
        falante_atual.reset(token)
    # família não desliga o PC (e ação crítica é só do dono)
    assert acoes.executar("pc_sistema", {"acao": "desligar"}, _desligar, falante=familia).startswith("NEGADO")


def test_rotina_automatica_pula_acao_critica(dono):
    r = acoes.executar("pc_sistema", {"acao": "desligar"}, _desligar, automatico=True)
    assert r.startswith("PULADO") and acoes.pendente() is None


def test_desfazer_volume(dono, monkeypatch):
    chamadas = []
    monkeypatch.setattr(pc, "volume_atual", lambda: 35)
    monkeypatch.setattr(pc, "volume", lambda acao, valor=10: chamadas.append((acao, valor)) or f"Volume em {valor}%.")
    acoes.executar("pc_volume", {"acao": "definir", "valor": 80}, pc.volume)
    assert acoes.desfazer_ultima() == "Volume em 35%."
    assert chamadas[-1] == ("definir", 35)
    assert acoes.listar(1)[0]["desfeito"]
    assert acoes.desfazer_ultima().startswith("Não achei")


def test_desfazer_timer_e_fato(dono):
    from ametista import ferramentas

    ferramentas.executar("criar_timer", {"minutos": 5, "descricao": "bolo"})
    assert len(memoria.lembretes_pendentes()) == 1
    assert acoes.desfazer_ultima() == "Lembrete desfeito."
    assert memoria.lembretes_pendentes() == []
    ferramentas.executar("lembrar_fato", {"fato": "gosta de chá"})
    assert memoria.fatos() == ["gosta de chá"]
    acoes.desfazer_ultima()
    assert memoria.fatos() == []


def test_falha_fica_registrada_como_falha(dono):
    acoes.executar("pc_abrir", {"alvo": "xyz"}, lambda alvo: "Não achei nenhum programa ou site chamado xyz.")
    item = acoes.listar(1)[0]
    assert not item["ok"] and not item["desfazivel"]


def test_contexto_das_ultimas_acoes(dono):
    acoes.executar("pc_abrir", {"alvo": "Chrome"}, lambda alvo: "Abrindo Google Chrome.", motivo="abre o chrome")
    ctx = acoes.resumo_para_contexto()
    assert "Abriu Chrome" in ctx and "pc_abrir" in ctx
    assert acoes.ultima_repetivel()["args"] == {"alvo": "Chrome"}


def test_modo_privado_nao_guarda_o_motivo(dono):
    estado.definir_privado(True)
    acoes.executar("pc_abrir", {"alvo": "Chrome"}, lambda alvo: "Abrindo.", motivo="segredo")
    assert acoes.listar(1)[0]["motivo"] == ""
    estado.definir_privado(False)


def test_classificar_resposta():
    c = acoes.classificar_resposta
    assert c("sim") == c("Pode sim!") == c("Ametista, pode") == c("confirmo") == "sim"
    assert c("não") == c("melhor não") == c("cancela") == c("não pode") == "nao"
    assert c("toca Coldplay") is None
    assert c("sim, mas antes me diz quanto espaço tem no disco D e no disco C") is None


def test_confirmacao_do_agente(dono):
    import threading

    resultado = {}
    t = threading.Thread(target=lambda: resultado.update(ok=acoes.pedir_confirmacao_agente("Posso enviar?", 5)))
    t.start()
    for _ in range(50):
        if acoes.pendente():
            break
        threading.Event().wait(0.02)
    assert acoes.resolver_pendente("pode", DONO_PADRAO)[0]
    t.join(3)
    assert resultado["ok"] is True
