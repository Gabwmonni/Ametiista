"""Cérebro: roteador local, escolha do modelo e Claude em streaming com ferramentas (simulado)."""
from types import SimpleNamespace

import pytest

from ametista import acoes, cerebro, config, controle, estado, ferramentas, memoria, pc, rotinas
from ametista.estado import Cancelado
from falsos import ClienteFalso, Resposta, SaidaFalsa, ferramenta, texto


@pytest.fixture
def claude(monkeypatch):
    """Instala um Claude falso; o teste preenche o roteiro."""
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-teste")
    cliente = ClienteFalso()
    monkeypatch.setattr(cerebro, "_cliente", cliente)
    monkeypatch.setattr(cerebro, "ollama_disponivel", lambda: False)
    return cliente


# ---------------------------------------------------------------- roteador local
def test_hora_e_data_sao_locais(dono):
    r = cerebro.roteador_local("Que horas são?")
    assert r["origem"] == "local" and r["texto"].startswith("São ")
    assert cerebro.roteador_local("que dia é hoje")["texto"].startswith("Hoje é ")


def test_timer_local_passa_pelo_registro(dono):
    r = cerebro.roteador_local("me avisa daqui a 10 minutos pra tirar o bolo")
    assert r["texto"].startswith("Timer de 10 minutos criado") and "(id" not in r["texto"]
    assert memoria.lembretes_pendentes()[0]["texto"] == "tirar o bolo"
    assert acoes.listar(1)[0]["ferramenta"] == "criar_timer"


def test_volume_local(dono, monkeypatch):
    monkeypatch.setattr(pc, "volume_atual", lambda: 10)
    monkeypatch.setattr(ferramentas.FUNCOES["pc_volume"], "__call__", None, raising=False)
    chamadas = []
    monkeypatch.setitem(ferramentas.FUNCOES, "pc_volume",
                        lambda acao, valor=10: chamadas.append((acao, valor)) or f"Volume do PC em {valor}%.")
    assert cerebro.roteador_local("coloca o volume em 30")["texto"] == "Volume do PC em 30%."
    assert cerebro.roteador_local("aumenta o volume bastante")["texto"] == "Volume do PC em 20%."
    assert chamadas == [("definir", 30), ("aumentar", 20)]


def test_fecha_essa_janela(dono, monkeypatch):
    monkeypatch.setitem(ferramentas.FUNCOES, "pc_janela", lambda acao, alvo="": f"{acao}:{alvo or 'frente'}")
    assert cerebro.roteador_local("fecha essa janela")["texto"] == "fechar:frente"
    assert cerebro.roteador_local("minimiza a janela")["texto"] == "minimizar:frente"


def test_desfazer_e_repetir(dono, monkeypatch):
    monkeypatch.setitem(ferramentas.FUNCOES, "pc_abrir", lambda alvo: f"Abrindo {alvo}.")
    assert cerebro.roteador_local("abre o Chrome")["texto"] == "Abrindo o Chrome."
    assert cerebro.roteador_local("abre de novo")["texto"] == "Abrindo o Chrome."
    assert cerebro.roteador_local("desfaz isso")["texto"].startswith("Não achei")


def test_abrir_local_que_falha_passa_para_a_nuvem_sem_sujar_o_historico(dono, monkeypatch):
    monkeypatch.setitem(ferramentas.FUNCOES, "pc_abrir",
                        lambda alvo: f"Não achei nenhum programa ou site chamado {alvo}.")
    assert cerebro.roteador_local("abre o autocad da obra") is None
    assert acoes.listar(5) == []
    monkeypatch.setitem(ferramentas.FUNCOES, "pc_abrir", lambda alvo: f"Abrindo {alvo}.")
    cerebro.roteador_local("abre o Excel")
    assert [a["descricao"] for a in acoes.listar(5)] == ["Abriu o Excel"]


def test_rotinas_por_frase(dono, monkeypatch):
    monkeypatch.setitem(ferramentas.FUNCOES, "rotina_executar", lambda nome, _grupo=None: f"rotina {nome}")
    assert cerebro.roteador_local("Modo filme")["texto"] == "rotina modo filme"
    assert cerebro.roteador_local("ativa o modo filme")["texto"] == "rotina modo filme"
    assert rotinas.achar_por_frase("bom dia Ametista") == "bom dia"
    assert rotinas.achar_por_frase("bom dia, tudo bem com você?") is None


def test_modo_privado_e_nao_perturbe_locais(dono):
    assert cerebro.roteador_local("modo privado")["texto"].startswith("Modo privado ligado")
    assert estado.privado()
    estado.definir_privado(False)
    assert cerebro.roteador_local("não perturbe por 2 horas")["texto"].startswith("Não perturbe até")


def test_conversa_sem_nome_so_aceita_controles_curtos(dono, monkeypatch):
    monkeypatch.setitem(ferramentas.FUNCOES, "pc_midia", lambda acao: f"mídia {acao}")
    assert cerebro.roteador_local("pausa", sem_nome=True)["texto"] == "mídia tocar_pausar"
    assert cerebro.roteador_local("abre o bloco de notas", sem_nome=True) is None
    assert cerebro.roteador_local("que horas são", sem_nome=True) is None


# ---------------------------------------------------------------- modelo
def test_escolha_do_modelo(monkeypatch):
    monkeypatch.setattr(config, "CLAUDE_MODELO", "claude-haiku-4-5")
    monkeypatch.setattr(config, "CLAUDE_MODELO_FORTE", "claude-opus-5")
    monkeypatch.setattr(config, "MODELO_AUTOMATICO", True)
    assert cerebro.modelo_para("toca Coldplay") == ("claude-haiku-4-5", "rapido")
    assert cerebro.modelo_para("me explica a diferença entre CLT e PJ") == ("claude-opus-5", "forte")
    assert cerebro.modelo_para("que erro é esse na minha tela?")[1] == "forte"
    monkeypatch.setattr(config, "MODELO_AUTOMATICO", False)
    assert cerebro.modelo_para("me explica tudo")[1] == "rapido"


def test_busca_web_por_modelo():
    assert cerebro.ferramenta_busca_web("claude-opus-5")["type"] == "web_search_20260209"
    assert cerebro.ferramenta_busca_web("claude-haiku-4-5")["type"] == "web_search_20250305"


# ---------------------------------------------------------------- Claude em streaming
def test_resposta_em_streaming(claude, dono):
    claude.roteiro = [Resposta(["[feliz] Oi, ", "Gabriel! Tudo ", "ótimo por aqui."])]
    saida = SaidaFalsa()
    r = cerebro.pensar("oi, tudo bem?", saida=saida)
    assert saida.pedacos == ["[feliz] Oi, ", "Gabriel! Tudo ", "ótimo por aqui."]
    assert r["texto"] == "Oi, Gabriel! Tudo ótimo por aqui." and r["emocao"] == "feliz" and r["origem"] == "nuvem"
    params = claude.chamadas[0]
    assert params["model"] == "claude-haiku-4-5" and not params["beta"]
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "Identidade da Ametista" in params["system"][0]["text"]
    assert "Contexto de agora" in params["system"][1]["text"]
    assert params["messages"][-1] == {"role": "user", "content": "oi, tudo bem?"}
    assert "output_config" not in params                     # Haiku: sem esforço/pensamento


def test_ferramentas_em_varias_rodadas(claude, dono, monkeypatch):
    monkeypatch.setitem(ferramentas.FUNCOES, "clima", lambda dias=1: "Agora em São Paulo: 22°C, céu limpo.")
    claude.roteiro = [
        Resposta(["[neutra] Deixa eu ver. "], [texto("[neutra] Deixa eu ver. "), ferramenta("clima", {"dias": 1})],
                 "tool_use"),
        Resposta(["Está fazendo vinte e dois graus."]),
    ]
    saida = SaidaFalsa()
    r = cerebro.pensar("como está o clima lá fora hein", saida=saida)
    assert saida.tudo == "[neutra] Deixa eu ver. \nEstá fazendo vinte e dois graus."   # frase fechada antes da ferramenta
    segunda = claude.chamadas[1]["messages"]
    assert segunda[-1]["content"][0] == {"type": "tool_result", "tool_use_id": "toolu_1",
                                         "content": "Agora em São Paulo: 22°C, céu limpo."}
    assert r["texto"] == "Deixa eu ver. Está fazendo vinte e dois graus."


def test_confirmacao_pedida_pela_ferramenta(claude, dono):
    claude.roteiro = [
        Resposta([], [ferramenta("pc_sistema", {"acao": "desligar"})], "tool_use"),
        Resposta(["[pensativa] Posso desligar o PC?"]),
    ]
    cerebro.pensar("desliga o computador", saida=SaidaFalsa())
    resultado = claude.chamadas[1]["messages"][-1]["content"][0]["content"]
    assert resultado.startswith("PRECISA CONFIRMAR") and acoes.pendente()["nome"] == "pc_sistema"


def test_modelo_rapido_chama_o_forte(claude, dono, monkeypatch):
    monkeypatch.setattr(config, "CLAUDE_MODELO_FORTE", "claude-opus-5")
    claude.roteiro = [
        Resposta(["Hmm, deixa eu pensar melhor. "], [texto("Hmm, deixa eu pensar melhor. "),
                                                     ferramenta("chamar_modelo_forte", {"motivo": "difícil"})], "tool_use"),
        Resposta(["[pensativa] A resposta completa."]),
    ]
    saida = SaidaFalsa()
    r = cerebro.pensar("de quantos BTUs eu preciso no meu escritório de vinte metros?", saida=saida)
    assert [c["model"] for c in claude.chamadas] == ["claude-haiku-4-5", "claude-opus-5"]
    forte = claude.chamadas[1]
    assert forte["beta"] and forte["betas"] == ["server-side-fallback-2026-07-01"] and forte["fallbacks"] == "default"
    assert forte["output_config"] == {"effort": "medium"}
    assert "chamar_modelo_forte" not in {t["name"] for t in forte["tools"] if "name" in t}
    assert "Latency-sensitive" in forte["system"][1]["text"]
    assert r["texto"] == "A resposta completa."


def test_recusa(claude, dono):
    claude.roteiro = [Resposta([], [], "refusal")]
    saida = SaidaFalsa()
    r = cerebro.pensar("pedido estranho", saida=saida)
    assert "não posso ajudar" in r["texto"] and "não posso ajudar" in saida.tudo


def test_pause_turn_continua(claude, dono):
    claude.roteiro = [Resposta(["Pesquisando. "], [texto("Pesquisando. ")], "pause_turn"),
                      Resposta(["Achei: o jogo sai em março."])]
    r = cerebro.pensar("quando sai o novo jogo do Zelda?", saida=SaidaFalsa())
    assert r["texto"] == "Pesquisando. Achei: o jogo sai em março."
    assert claude.chamadas[1]["messages"][-1]["role"] == "assistant"


def test_eco_depois_de_fallback():
    thinking = SimpleNamespace(type="thinking", thinking="")
    uso = ferramenta("clima", {})
    fb = SimpleNamespace(type="fallback")
    depois = texto("continuação")
    assert cerebro._eco([texto("antes"), thinking, uso, fb, depois]) == [texto("antes"), depois]
    assert cerebro._eco([texto("a")]) == [texto("a")]


def test_cancelamento_no_meio_da_resposta(claude, dono):
    ficha = estado.nova_ficha("x")
    claude.roteiro = [Resposta(["Primeira parte. ", "Segunda parte."])]
    claude.ao_emitir = lambda p: ficha.cancelar()
    with pytest.raises(Cancelado):
        cerebro.pensar("conta uma história", saida=SaidaFalsa(), ficha=ficha)


def test_conversa_sem_nome_pode_ser_ignorada(claude, dono):
    claude.roteiro = [Resposta(["[ign", "orar]"])]
    saida = SaidaFalsa()
    r = cerebro.pensar("você viu o jogo ontem?", saida=saida, sem_nome=True)
    assert r.get("ignorado") and saida.pedacos == []
    assert "SEM a pessoa dizer o seu nome" in claude.chamadas[0]["system"][1]["text"]
    claude.roteiro = [Resposta(["[feliz] Vi sim!"])]
    saida = SaidaFalsa()
    r = cerebro.pensar("você viu o jogo ontem?", saida=saida, sem_nome=True)
    assert not r.get("ignorado") and saida.tudo == "[feliz] Vi sim!"


def test_sem_chave_e_sem_ollama(dono, monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(cerebro, "ollama_disponivel", lambda: False)
    saida = SaidaFalsa()
    r = cerebro.pensar("me conta uma piada", saida=saida)
    assert r["origem"] == "erro" and "chave da API" in saida.tudo


def test_sem_internet_usa_ollama(claude, dono, monkeypatch):
    import anthropic
    import httpx2

    claude.erro_na_chamada = [anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com"))]
    monkeypatch.setattr(cerebro, "ollama_disponivel", lambda: True)
    monkeypatch.setattr(cerebro, "perguntar_ollama", lambda *a, **k: (k.get("saida") or a[2]).texto("[neutra] Oi!") or "[neutra] Oi!")
    saida = SaidaFalsa()
    r = cerebro.pensar("me conta uma novidade", saida=saida)
    assert r["origem"] == "local-ia" and estado.offline
    estado.definir_offline(False)


@pytest.mark.parametrize("classe, status, mensagem, esperado", [
    ("RateLimitError", 429, "rate limited", "limite de pedidos"),
    ("BadRequestError", 400, "Your credit balance is too low to access the Anthropic API.", "créditos"),
    ("InternalServerError", 529, "Overloaded", "sobrecarregados"),
    ("NotFoundError", 404, "model: claude-xyz", "modelo do Claude"),
])
def test_falha_do_claude_explica_o_motivo(claude, dono, classe, status, mensagem, esperado):
    import anthropic
    import httpx2

    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    erro = getattr(anthropic, classe)(mensagem, response=httpx2.Response(status, request=req), body=None)
    claude.erro_na_chamada = [erro]
    saida = SaidaFalsa()
    r = cerebro.pensar("me conta uma novidade", saida=saida)
    assert r["origem"] == "erro" and esperado in saida.tudo and not estado.offline


def test_contexto_tem_ultimas_acoes_e_fatos(claude, dono, monkeypatch):
    monkeypatch.setitem(ferramentas.FUNCOES, "pc_abrir", lambda alvo: f"Abrindo {alvo}.")
    ferramentas.executar("pc_abrir", {"alvo": "Excel"})
    memoria.lembrar_fato("trabalha na FJ Engenharia")
    claude.roteiro = [Resposta(["Ok."])]
    cerebro.pensar("não esse, o outro", saida=SaidaFalsa())
    ctx = claude.chamadas[0]["system"][1]["text"]
    assert "Abriu Excel" in ctx and "trabalha na FJ Engenharia" in ctx


def test_captura_de_tela_respeita_limites_do_modelo():
    assert controle.limites("claude-haiku-4-5") == (1568, 1_150_000)
    assert controle.limites("claude-opus-5") == (1920, 1920 * 1080)


# ---------------------------------------------------------------- frase de espera (ferramenta demorada)
def test_frase_de_espera_quando_a_ferramenta_demora_e_ela_nao_disse_nada(claude, dono, monkeypatch):
    monkeypatch.setitem(ferramentas.FUNCOES, "memoria_buscar", lambda **k: "Ontem: o relatório de vendas.")
    frases = []
    for _ in range(2):
        claude.roteiro = [Resposta([], [ferramenta("memoria_buscar", {"consulta": "ontem"})], "tool_use"),
                          Resposta(["Você pediu o relatório de vendas."])]
        saida = SaidaFalsa()
        r = cerebro.pensar("o que eu te pedi ontem", saida=saida)
        primeira, resto = saida.tudo.split("\n", 1)
        assert primeira in cerebro._FRASES_ESPERA["memoria"] and resto == "Você pediu o relatório de vendas."
        assert r["texto"] == "Você pediu o relatório de vendas.", "a frase de espera não entra no histórico"
        frases.append(primeira)
    assert frases[0] != frases[1], "não repete a mesma frase"


def test_sem_frase_de_espera_se_ela_ja_falou_ou_a_ferramenta_e_rapida(claude, dono, monkeypatch):
    monkeypatch.setitem(ferramentas.FUNCOES, "memoria_buscar", lambda **k: "nada")
    claude.roteiro = [Resposta(["Hmm, deixa eu lembrar. "], [texto("Hmm, deixa eu lembrar. "),
                                                            ferramenta("memoria_buscar", {"consulta": "x"})],
                               "tool_use"),
                      Resposta(["Não achei nada."])]
    saida = SaidaFalsa()
    cerebro.pensar("o que eu te falei sobre x", saida=saida)
    assert saida.tudo == "Hmm, deixa eu lembrar. \nNão achei nada."
    assert cerebro.frase_de_espera("pc_volume") is None and cerebro.frase_de_espera("pc_sistema") is None
    nomes = set(ferramentas.FUNCOES) | {"web_search"}
    assert set(cerebro._ESPERA_DE) <= nomes, set(cerebro._ESPERA_DE) - nomes


def test_frase_de_espera_na_busca_na_web(claude, dono):
    # (sem "vai chover" e afins: com internet o roteador local responde o clima sozinho)
    busca = SimpleNamespace(type="server_tool_use", id="srvtoolu_1", name="web_search", input={"query": "jogo"})
    claude.roteiro = [Resposta(["O Palmeiras ganhou de dois a um."], [busca, texto("O Palmeiras ganhou de dois a um.")])]
    saida = SaidaFalsa()
    pedido = "pesquisa quem ganhou o jogo do Palmeiras ontem"
    assert cerebro.roteador_local(pedido) is None
    cerebro.pensar(pedido, saida=saida)
    primeira, resto = saida.tudo.split("\n", 1)
    assert primeira in cerebro._FRASES_ESPERA["pesquisa"] and resto == "O Palmeiras ganhou de dois a um."
