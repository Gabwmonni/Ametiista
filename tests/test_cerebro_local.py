"""Cérebro local (Ollama) com ferramentas, contra um Ollama falso que fala o mesmo protocolo (/api/chat em NDJSON)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ametista import acoes, cerebro, cerebro_local, config, diagnostico, foco, notas
from ametista.identidade import DONO_PADRAO, Falante, falante_atual
from falsos import SaidaFalsa


class OllamaFalso:
    def __init__(self):
        self.modelos = ["qwen2.5:7b"]
        self.capacidades = {"qwen2.5:7b": ["completion", "tools"]}
        self.roteiro: list[list[dict]] = []          # cada item: os pedaços de uma resposta do /api/chat
        self.pedidos: list[dict] = []
        falso = self

        class Tratador(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, dados, codigo=200):
                corpo = json.dumps(dados).encode()
                self.send_response(codigo)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def do_GET(self):
                if self.path == "/api/tags":
                    return self._json({"models": [{"name": m} for m in falso.modelos]})
                self._json({"error": "não achei"}, 404)

            def do_POST(self):
                pedido = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/api/show":
                    if pedido["model"] not in falso.capacidades:
                        return self._json({"error": "model not found"}, 404)
                    return self._json({"capabilities": falso.capacidades[pedido["model"]],
                                       "details": {"family": "qwen2"}})
                falso.pedidos.append(pedido)
                if pedido["model"] not in falso.modelos:
                    return self._json({"error": f"model '{pedido['model']}' not found"}, 404)
                pedacos = falso.roteiro.pop(0) if falso.roteiro else [{"message": {"content": "(fim do roteiro)"}}]
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                for p in pedacos + [{"done": True}]:
                    p.setdefault("done", False)
                    p.setdefault("message", {"role": "assistant", "content": ""})
                    self.wfile.write((json.dumps(p) + "\n").encode())
                    self.wfile.flush()

        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Tratador)
        threading.Thread(target=self.servidor.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}"

    def falar(self, *textos: str):
        self.roteiro.append([{"message": {"role": "assistant", "content": t}} for t in textos])

    def chamar(self, nome: str, args, texto: str = ""):
        self.roteiro.append([{"message": {"role": "assistant", "content": texto,
                                          "tool_calls": [{"function": {"name": nome, "arguments": args}}]}}])


@pytest.fixture
def ollama(monkeypatch):
    o = OllamaFalso()
    monkeypatch.setattr(config, "OLLAMA_URL", o.url)
    monkeypatch.setattr(config, "OLLAMA_MODELO", "qwen2.5:7b")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    cerebro_local._cache.update(modelos=(0.0, []), capacidades={})
    yield o
    o.servidor.shutdown()
    cerebro_local._cache.update(modelos=(0.0, []), capacidades={})


@pytest.fixture
def notas_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(notas, "pasta", lambda: tmp_path / "Notas")
    monkeypatch.setattr(notas, "abrir_no_bloco", lambda p: None)
    return tmp_path / "Notas"


# ---------------------------------------------------------------- modelo e ferramentas escolhidas
def test_usa_o_modelo_baixado_quando_o_configurado_falta(ollama):
    assert cerebro_local.modelo() == "qwen2.5:7b"
    ollama.modelos = ["nomic-embed-text:latest", "qwen2.5:3b", "llama3.2:latest"]
    cerebro_local._cache["modelos"] = (0.0, [])
    assert cerebro_local.modelo() == "qwen2.5:3b"
    ollama.modelos = ["nomic-embed-text:latest", "gemma3:latest"]
    cerebro_local._cache["modelos"] = (0.0, [])
    assert cerebro_local.modelo() == "gemma3:latest"
    assert cerebro_local._mesmo("llama3.2", "llama3.2:latest")


def test_capacidades(ollama):
    assert "tools" in cerebro_local.capacidades("qwen2.5:7b")
    ollama.capacidades["gemma3:latest"] = ["completion", "vision"]
    assert "tools" not in cerebro_local.capacidades("gemma3:latest")


def test_ferramentas_do_assunto(dono):
    nomes = [d["name"] for d in cerebro_local.escolher("lê o arquivo resumo.pdf da área de trabalho")]
    assert nomes[:3] == ["arquivos_buscar", "arquivo_ler", "arquivo_abrir"] and len(nomes) <= 22
    assert "criar_timer" in nomes and "pc_ver_tela" not in nomes and "chamar_modelo_forte" not in nomes
    nomes = [d["name"] for d in cerebro_local.escolher("quanto de memória ram o chrome está usando?")]
    assert "pc_processos" in nomes and "pc_encerrar" in nomes
    nomes = [d["name"] for d in cerebro_local.escolher("vou estudar cálculo")]
    assert "foco_iniciar" in nomes
    # a fala anterior conta: "acha o pdf da aula" -> "abre ele"
    nomes = [d["name"] for d in cerebro_local.escolher("abre ele", anterior="acha o pdf da aula")]
    assert "arquivo_abrir" in nomes
    token = falante_atual.set(Falante("Ana", "familia"))
    try:
        assert "arquivo_ler" not in [d["name"] for d in cerebro_local.escolher("lê o arquivo x.txt")]
    finally:
        falante_atual.reset(token)


def test_ajustar_argumentos_de_modelo_pequeno():
    esquema = {"properties": {"minutos": {"type": "number"}, "abrir": {"type": "boolean"},
                              "locais": {"type": "array"}, "quantidade": {"type": "integer"},
                              "titulo": {"type": "string"}}}
    assert cerebro_local.ajustar_args('{"minutos": "5,5", "abrir": "true", "locais": "temporarios, lixeira", '
                                      '"quantidade": "3", "titulo": 2024, "inventado": 1}', esquema) == {
        "minutos": 5.5, "abrir": True, "locais": ["temporarios", "lixeira"], "quantidade": 3, "titulo": "2024"}
    assert cerebro_local.ajustar_args("isso não é json", esquema) == {}
    assert cerebro_local.ajustar_args({"minutos": None}, esquema) == {}


# ---------------------------------------------------------------- conversa com ferramentas
def test_cria_nota_de_verdade_pelo_ollama(ollama, dono, notas_tmp):
    ollama.chamar("nota_criar", {"titulo": "Compras", "texto": "arroz e feijão"}, texto="Vou anotar. ")
    ollama.falar("[feliz] Pronto, ", "anotei na nota Compras.")
    saida = SaidaFalsa()
    r = cerebro_local.perguntar("anota num bloco de notas: arroz e feijão, título compras", DONO_PADRAO, saida)
    assert (notas_tmp / "Compras.txt").read_text(encoding="utf-8") == "arroz e feijão"
    assert r == "Vou anotar. [feliz] Pronto, anotei na nota Compras."
    assert saida.tudo == "Vou anotar. \n[feliz] Pronto, anotei na nota Compras."
    p1, p2 = ollama.pedidos
    assert p1["stream"] and p1["keep_alive"] == "30m" and p1["options"]["num_ctx"] >= 8192 and "think" not in p1
    assert "nota_criar" in [t["function"]["name"] for t in p1["tools"]]
    assert p1["tools"][0]["type"] == "function" and "properties" in p1["tools"][0]["function"]["parameters"]
    sistema = p1["messages"][0]
    assert sistema["role"] == "system" and "Nunca diga que não consegue acessar o computador" in sistema["content"]
    ferramenta_msg = p2["messages"][-1]
    assert ferramenta_msg["role"] == "tool" and ferramenta_msg["tool_name"] == "nota_criar"
    assert ferramenta_msg["content"].startswith("Criei a nota Compras")
    assert p2["messages"][-2]["tool_calls"][0]["function"]["name"] == "nota_criar"
    assert acoes.listar(1)[0]["ferramenta"] == "nota_criar"


def test_confirmacao_para_a_conversa(ollama, dono, tmp_path):
    arq = tmp_path / "velho.txt"
    arq.write_text("x")
    ollama.chamar("arquivo_apagar", {"caminho": str(arq)})
    ollama.falar("apaguei!")                     # um modelo pequeno diria isso: não pode chegar a falar
    r = cerebro_local.perguntar("apaga o arquivo velho.txt", DONO_PADRAO, SaidaFalsa())
    assert r == "[pensativa] Posso mandar velho.txt para a Lixeira?"
    assert len(ollama.pedidos) == 1 and arq.exists() and acoes.pendente()["nome"] == "arquivo_apagar"
    acoes.cancelar_pendente()


def test_nao_repete_a_mesma_acao_nem_inventa_ferramenta(ollama, dono, notas_tmp):
    ollama.chamar("nota_criar", {"titulo": "A"})
    ollama.chamar("nota_criar", {"titulo": "A"})
    ollama.chamar("ferramenta_que_nao_existe", {})
    ollama.falar("Feito.")
    cerebro_local.perguntar("cria a nota A", DONO_PADRAO, SaidaFalsa())
    assert [p.name for p in notas_tmp.iterdir()] == ["A.txt"]
    assert "Você já fez exatamente isso" in ollama.pedidos[2]["messages"][-1]["content"]
    assert "não existe aqui" in ollama.pedidos[3]["messages"][-1]["content"]


def test_ultima_rodada_vai_sem_ferramentas(ollama, dono, monkeypatch):
    monkeypatch.setattr(cerebro_local, "MAX_RODADAS", 2)
    ollama.chamar("clima", {})
    ollama.falar("Está sol.")
    monkeypatch.setattr(cerebro_local.ferramentas, "executar", lambda n, a: "Sol, 25 graus.")
    assert cerebro_local.perguntar("como está o tempo?", DONO_PADRAO) == "Está sol."
    assert "tools" in ollama.pedidos[0] and "tools" not in ollama.pedidos[1]


def test_modelo_sem_ferramentas_so_conversa(ollama, dono):
    ollama.modelos = ["gemma3:latest"]
    ollama.capacidades = {"gemma3:latest": ["completion"]}
    ollama.falar("Oi!")
    assert cerebro_local.perguntar("oi", DONO_PADRAO) == "Oi!"
    assert "tools" not in ollama.pedidos[0] and "qwen2.5:7b" in ollama.pedidos[0]["messages"][0]["content"]


def test_modelo_que_pensa_responde_sem_pensar(ollama, dono):
    ollama.modelos = ["qwen3:8b"]
    ollama.capacidades = {"qwen3:8b": ["completion", "tools", "thinking"]}
    ollama.falar("Oi!")
    cerebro_local.perguntar("oi", DONO_PADRAO)
    assert ollama.pedidos[0]["think"] is False and ollama.pedidos[0]["model"] == "qwen3:8b"


# ---------------------------------------------------------------- pensar(): quem responde
def test_ollama_como_cerebro_principal(ollama, dono, monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-teste")
    monkeypatch.setattr(config, "CEREBRO_PRINCIPAL", "ollama")
    monkeypatch.setattr(cerebro, "perguntar_claude", lambda *a, **k: pytest.fail("não era para usar o Claude"))
    ollama.falar("[feliz] Oi, Gabriel!")
    r = cerebro.pensar("oi tudo bem", DONO_PADRAO)
    assert r["texto"] == "Oi, Gabriel!" and r["origem"] == "local-ia" and r["emocao"] == "feliz"


def test_sem_chave_usa_o_ollama_com_ferramentas(ollama, dono, notas_tmp):
    ollama.chamar("nota_criar", {"titulo": "Ideias"})
    ollama.falar("[feliz] Criei.")
    r = cerebro.pensar("cria uma nota chamada ideias", DONO_PADRAO)
    assert r["texto"] == "Criei." and (notas_tmp / "Ideias.txt").exists()


def test_ollama_como_principal_falha_e_o_claude_assume(ollama, dono, monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-teste")
    monkeypatch.setattr(config, "CEREBRO_PRINCIPAL", "ollama")
    ollama.modelos = []                                        # nada baixado: o Ollama devolve 404
    chamou = []
    monkeypatch.setattr(cerebro, "perguntar_claude",
                        lambda *a, **k: chamou.append(1) or "[neutra] Resposta do Claude.")
    r = cerebro.pensar("oi", DONO_PADRAO)
    assert chamou and r["texto"] == "Resposta do Claude." and r["origem"] == "nuvem"


def test_diagnostico_do_ollama(ollama):
    assert diagnostico._ollama()["detalhe"] == "pronto com qwen2.5:7b, com ferramentas"
    ollama.modelos = ["qwen2.5:3b"]
    ollama.capacidades = {"qwen2.5:3b": ["completion", "tools"]}
    cerebro_local._cache.update(modelos=(0.0, []), capacidades={})
    assert "qwen2.5:7b não está baixado: ollama pull qwen2.5:7b" in diagnostico._ollama()["detalhe"]
    ollama.modelos = ["gemma3:latest"]
    ollama.capacidades = {"gemma3:latest": ["completion"]}
    cerebro_local._cache.update(modelos=(0.0, []), capacidades={})
    d = diagnostico._ollama()
    assert d["situacao"] == "aviso" and "não sabe usar ferramentas" in d["detalhe"]


def test_diagnostico_ollama_fechado(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_URL", "http://127.0.0.1:9")
    cerebro_local._cache.update(modelos=(0.0, []), capacidades={})
    assert diagnostico._ollama()["situacao"] == "aviso"
    monkeypatch.setattr(config, "CEREBRO_PRINCIPAL", "ollama")
    assert diagnostico._ollama()["situacao"] == "erro"


# ---------------------------------------------------------------- frases de estudo sem IA nenhuma
@pytest.mark.parametrize("frase, materia, minutos", [
    ("Vou estudar cálculo por 50 minutos", "cálculo", 50),
    ("vou estudar por uma hora", "", 60),
    ("vou estudar para a prova de química", "prova de química", 0),
    ("bora estudar física durante meia hora", "física", 30),
    ("quero focar", "", 0),
    ("vou estudar agora", "", 0),
])
def test_frases_de_estudo(frase, materia, minutos, dono, monkeypatch):
    chamadas = []
    monkeypatch.setitem(cerebro.ferramentas.FUNCOES, "foco_iniciar",
                        lambda minutos=0, materia="": chamadas.append((materia, minutos)) or "ok")
    assert cerebro.roteador_local(frase)["texto"] == "ok"
    assert chamadas == [(materia, minutos)]


def test_terminei_e_pausa(dono, monkeypatch):
    monkeypatch.setattr(foco.Monitor, "ligar", lambda self: None)
    monkeypatch.setattr(foco, "_monitor", None)
    assert cerebro.roteador_local("pausa de 10 minutos") is None           # sem sessão: não é com o foco
    cerebro.roteador_local("vou estudar")
    assert cerebro.roteador_local("pausa de dez minutos")["texto"].startswith("Pausa de 10 minutos")
    assert cerebro.roteador_local("terminei de estudar")["texto"].startswith("Sessão encerrada")
    assert cerebro.roteador_local("encerra o foco")["texto"] == "Não havia sessão de foco em andamento."
