"""Transcrição: placa NVIDIA quando funciona (testada à parte), processador quando não, ajustes de velocidade."""
import time

import pytest

from ametista import config, estado, transcricao


class Modelo:
    def __init__(self, onde):
        self.onde = onde


@pytest.fixture
def pc(monkeypatch):
    """PC falso: diz se tem placa, se o teste da placa passa e se abrir na placa dá certo."""
    p = {"placa": True, "teste_ok": True, "cuda_quebra": False, "testes": 0, "abertos": []}

    def abrir(dispositivo, nome=None):
        if dispositivo == "cuda" and p["cuda_quebra"]:
            raise RuntimeError("cuDNN não encontrado")
        p["abertos"].append(dispositivo)
        return Modelo(dispositivo)

    def testar_placa(nome, limite=300):
        p["testes"] += 1
        estado.lembrar(transcricao.CHAVE_GPU, {"chave": transcricao._chave(nome), "ok": p["teste_ok"]})
        return p["teste_ok"]

    monkeypatch.setattr(transcricao, "abrir", abrir)
    monkeypatch.setattr(transcricao, "testar_placa", testar_placa)
    monkeypatch.setattr(transcricao, "tem_placa", lambda: p["placa"])
    monkeypatch.setattr(config, "WHISPER_DISPOSITIVO", "auto")
    return p


def _esperar(cond, limite=10.0):
    fim = time.time() + limite
    while time.time() < fim and not cond():
        time.sleep(0.01)
    return cond()


def test_sem_placa_usa_o_processador(pc):
    pc["placa"] = False
    c = transcricao.Carregador()
    assert c.carregar().onde == "cpu" and c.dispositivo == "cpu"
    time.sleep(0.05)
    assert pc["testes"] == 0


def test_primeira_vez_ouve_no_processador_e_passa_para_a_placa_se_ela_servir(pc):
    trocas = []
    c = transcricao.Carregador(ao_trocar=trocas.append)
    assert c.carregar().onde == "cpu", "não espera o teste da placa para começar a ouvir"
    assert _esperar(lambda: trocas)
    assert trocas[0].onde == "cuda" and c.dispositivo == "cuda" and pc["testes"] == 1
    # da próxima vez já abre direto na placa, sem testar de novo
    c2 = transcricao.Carregador()
    assert c2.carregar().onde == "cuda" and pc["testes"] == 1


def test_placa_que_nao_serve_fica_no_processador_e_nao_e_testada_de_novo(pc):
    pc["teste_ok"] = False
    trocas = []
    transcricao.Carregador(ao_trocar=trocas.append).carregar()
    assert _esperar(lambda: pc["testes"] == 1)
    time.sleep(0.05)
    assert trocas == []
    assert transcricao.Carregador().carregar().onde == "cpu"
    time.sleep(0.05)
    assert pc["testes"] == 1


def test_placa_testada_mas_que_falha_ao_abrir_volta_ao_processador(pc):
    estado.lembrar(transcricao.CHAVE_GPU, {"chave": transcricao._chave(config.WHISPER_MODELO), "ok": True})
    pc["cuda_quebra"] = True
    c = transcricao.Carregador()
    assert c.carregar().onde == "cpu" and c.dispositivo == "cpu"
    assert transcricao.placa_testada(config.WHISPER_MODELO) is False


def test_versao_nova_do_ctranslate2_testa_a_placa_de_novo(pc, monkeypatch):
    estado.lembrar(transcricao.CHAVE_GPU, {"chave": "0.0.1|small", "ok": False})
    monkeypatch.setattr(config, "WHISPER_MODELO", "small")
    assert transcricao.placa_testada("small") is None
    transcricao.Carregador().carregar()
    assert _esperar(lambda: pc["testes"] == 1 and "cuda" in pc["abertos"])


def test_escolhas_manuais(pc, monkeypatch):
    monkeypatch.setattr(config, "WHISPER_DISPOSITIVO", "cpu")
    assert transcricao.Carregador().carregar().onde == "cpu"
    monkeypatch.setattr(config, "WHISPER_DISPOSITIVO", "cuda")
    assert transcricao.Carregador().carregar().onde == "cuda", "na placa, mesmo sem teste"
    pc["cuda_quebra"] = True
    assert transcricao.Carregador().carregar().onde == "cpu", "se a placa falhar, não fica surda"


def test_acha_as_bibliotecas_da_nvidia_da_voz_clonada(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    lib = tmp_path / "voz_local" / ".venv" / "Lib" / "site-packages" / "torch" / "lib"
    lib.mkdir(parents=True)
    assert lib in transcricao.pastas_cuda()


def test_ajustes_de_velocidade():
    o = transcricao.opcoes()
    assert o["beam_size"] == 1 and o["without_timestamps"] and o["temperature"] == 0.0
    assert o["language"] == "pt" and config.NOME in o["initial_prompt"]
    assert 4 <= transcricao.threads_cpu() <= 8


def test_migracao_passa_o_processador_para_o_automatico(env_limpo):
    env_limpo.write_text("# versão das configurações: 3\nWHISPER_DISPOSITIVO=cpu\n", encoding="utf-8")
    assert "WHISPER_DISPOSITIVO" in config.migrar_env()
    assert "WHISPER_DISPOSITIVO=auto" in env_limpo.read_text(encoding="utf-8")


def test_se_o_app_caiu_abrindo_na_placa_da_proxima_vez_usa_o_processador(pc, monkeypatch):
    estado.lembrar(transcricao.CHAVE_GPU, {"chave": transcricao._chave(config.WHISPER_MODELO), "ok": True})
    estado.lembrar(transcricao.ABRINDO, True)          # ficou marcado: o processo caiu no meio
    c = transcricao.Carregador()
    assert c.carregar().onde == "cpu"
    assert transcricao.placa_testada(config.WHISPER_MODELO) is False
    assert not estado.obter(transcricao.ABRINDO)
    time.sleep(0.05)
    assert pc["testes"] == 0, "não testa a placa de novo (só com versão nova)"


def test_abrir_na_placa_limpa_a_marca(pc):
    estado.lembrar(transcricao.CHAVE_GPU, {"chave": transcricao._chave(config.WHISPER_MODELO), "ok": True})
    assert transcricao.Carregador().carregar().onde == "cuda"
    assert not estado.obter(transcricao.ABRINDO)
