"""Servidor local: segurança (Host, chave, origem) e API do painel."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ametista import acoes, config, servidor

BASE = f"http://127.0.0.1:{config.PORTA}"


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(servidor, "iniciar_servicos", lambda: None)
    with TestClient(servidor.app, base_url=BASE) as c:
        c.headers.update({"X-Ametista-Token": servidor.TOKEN})
        yield c


def test_host_estranho_e_bloqueado(cliente):
    r = cliente.get("/api/saude", headers={"host": "ataque.exemplo.com"})
    assert r.status_code == 403


def test_api_exige_a_chave(cliente):
    assert cliente.get("/api/config", headers={"X-Ametista-Token": "errada"}).status_code == 401
    assert cliente.get("/api/saude", headers={"X-Ametista-Token": ""}).status_code == 200
    assert cliente.get("/api/config").status_code == 200


def test_paginas_recebem_a_chave(cliente):
    html = cliente.get("/").text
    assert servidor.TOKEN in html and "{{TOKEN}}" not in html
    assert servidor.TOKEN in cliente.get("/painel").text
    assert cliente.get("/").headers["x-frame-options"] == "DENY"


def test_config_esconde_segredos_e_salva(cliente, env_limpo):
    config.salvar({"ANTHROPIC_API_KEY": "sk-ant-1234567890abcd"})
    dados = cliente.get("/api/config").json()
    chave = next(c for c in dados["campos"] if c["chave"] == "ANTHROPIC_API_KEY")
    assert chave["valor"] == "" and chave["definido"] and chave["dica"] == "••••abcd"
    assert "sk-ant" not in cliente.get("/api/config").text
    assert "Cérebro" in dados["secoes"] and not any(c["chave"] == "VOSK_MODELO" for c in dados["campos"])
    r = cliente.post("/api/config", json={"valores": {"ANTHROPIC_API_KEY": "", "AMETISTA_DONO": "Gabi", "PORTA": "9999"}})
    assert r.json() == {"ok": True, "reiniciar": ["PORTA"]}
    assert config.ANTHROPIC_API_KEY == "sk-ant-1234567890abcd"     # em branco = mantém
    assert config.DONO == "Gabi"
    assert cliente.post("/api/config", json={"valores": {"VOSK_MODELO": "x"}}).status_code == 400
    config.salvar({"PORTA": "8765"})


def test_identidade(cliente, tmp_path, monkeypatch):
    doc = tmp_path / "id.md"
    monkeypatch.setattr(config, "IDENTIDADE_DOC", doc)
    assert cliente.post("/api/identidade", json={"texto": "curto"}).status_code == 400
    texto = "Você é {nome}. " * 10
    assert cliente.post("/api/identidade", json={"texto": texto}).json() == {"ok": True}
    assert cliente.get("/api/identidade").json()["texto"] == texto


def test_rotinas_validadas(cliente):
    r = cliente.post("/api/rotinas", json={"rotinas": [{"nome": "x", "passos": [{"ferramenta": "nao_existe"}]}]})
    assert r.status_code == 400
    ok = cliente.post("/api/rotinas", json={"rotinas": [{"nome": "teste", "passos": [{"falar": "oi"}],
                                                         "horario": "07:30", "frases": ["teste"]}]})
    assert ok.status_code == 200
    assert cliente.get("/api/rotinas").json()["rotinas"][0]["nome"] == "teste"
    config.ROTINAS_ARQ.unlink()


def test_acoes_e_desfazer(cliente, dono):
    from ametista import ferramentas

    ferramentas.executar("criar_timer", {"minutos": 3})
    acao = cliente.get("/api/acoes").json()["acoes"][0]
    assert acao["descricao"].startswith("Criou timer") and acao["desfazivel"]
    assert cliente.post("/api/acoes/desfazer", json={"id": acao["id"]}).json()["resultado"] == "Lembrete desfeito."


def test_privado_e_nao_perturbe(cliente):
    assert cliente.post("/api/privado", json={"valor": True}).json()["privado"] is True
    assert cliente.post("/api/privado", json={"valor": False}).json()["privado"] is False
    r = cliente.post("/api/nao-perturbe", json={"minutos": 30}).json()
    assert r["nao_perturbe"]
    cliente.post("/api/nao-perturbe", json={"minutos": 0})


def test_websocket_confere_origem_e_chave(cliente):
    with pytest.raises(WebSocketDisconnect):
        with cliente.websocket_connect(f"/ws?token={servidor.TOKEN}", headers={"origin": "https://mal.com"}) as ws:
            ws.receive_json()
    with pytest.raises(WebSocketDisconnect):
        with cliente.websocket_connect("/ws?token=errada", headers={"origin": BASE}) as ws:
            ws.receive_json()
    with cliente.websocket_connect(f"/ws?token={servidor.TOKEN}", headers={"origin": BASE}) as ws:
        inicial = ws.receive_json()
        assert inicial["tipo"] == "inicial" and inicial["nome"] == config.NOME
        assert {"avisos", "tarefas", "acoes", "conversa", "privado"} <= set(inicial)


def test_websocket_responde_confirmacao(cliente, dono):
    import time

    feito = []
    acoes.executar("pc_fechar", {"programa": "chrome"}, lambda programa: feito.append(programa) or "Fechei.")
    with cliente.websocket_connect(f"/ws?token={servidor.TOKEN}", headers={"origin": BASE}) as ws:
        ws.receive_json()
        ws.send_json({"tipo": "responder", "resposta": "sim"})
        for _ in range(100):
            if feito:
                break
            time.sleep(0.02)
    assert feito == ["chrome"]


def test_ouvir_combinacao_de_voz_antes_de_salvar(cliente, monkeypatch):
    from ametista import voz

    pedidos = []
    monkeypatch.setattr(voz, "amostra_edge", lambda texto, v, vel, tom: pedidos.append((v, vel, tom)) or "SUQzAAAA")
    r = cliente.post("/api/testar-voz", json={"provedor": "edge", "voz": "pt-BR-ThalitaMultilingualNeural",
                                               "velocidade": "-4%", "tom": "+12Hz"})
    assert r.status_code == 200 and r.json()["audio"] == "SUQzAAAA"
    assert pedidos == [("pt-BR-ThalitaMultilingualNeural", "-4%", "+12Hz")]
    ruim = cliente.post("/api/testar-voz", json={"provedor": "edge", "voz": "x; rm -rf", "tom": "+8Hz"})
    assert ruim.status_code == 400
