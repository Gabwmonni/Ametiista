"""Ouvido: palavra de ativação, interrupção por voz, conversa contínua e modo privado (sem microfone real)."""
import json
import time

import numpy as np
import pytest

from ametista import config, eventos, estado, identidade, ouvido
from ametista.identidade import DONO_PADRAO, Falante

ALTO = (np.ones(ouvido.AMOSTRAS) * 4000).astype(np.int16).tobytes()
MUDO = np.zeros(ouvido.AMOSTRAS, dtype=np.int16).tobytes()


class VoskFalso:
    """Reconhecedor de palavra de ativação: o teste diz o que ele "ouve"."""

    def __init__(self):
        self.parcial, self.final = "", None

    def AcceptWaveform(self, bloco):
        return self.final is not None

    def Result(self):
        t, self.final = self.final, None
        return json.dumps({"text": t})

    def PartialResult(self):
        return json.dumps({"partial": self.parcial})

    def Reset(self):
        self.parcial, self.final = "", None


@pytest.fixture
def o(monkeypatch):
    monkeypatch.setattr(config, "TEMPO_SEGUIMENTO", 1.0)
    monkeypatch.setattr(config, "CONVERSA_MINUTOS", 0.05)       # 3 s de conversa
    monkeypatch.setattr(config, "INTERROMPER_POR_VOZ", True)
    monkeypatch.setattr(identidade, "identificar", lambda pcm: DONO_PADRAO)
    pedidos = []
    ouv = ouvido.Ouvido(atender=lambda texto, falante, sem_nome=False: pedidos.append((texto, falante, sem_nome)) or {})
    ouv._vosk = VoskFalso()
    ouv._whisper_pronto.set()
    ouv.pedidos = pedidos
    yield ouv
    eventos.remover(ouv._evento)


def _alimentar(o, bloco, n):
    for _ in range(n):
        o.alimentar(bloco)


def _esperar(cond, limite=3.0):
    fim = time.time() + limite
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.01)
    return False


def _falar_pedido(o, transcricao, monkeypatch):
    monkeypatch.setattr(o, "transcrever", lambda pcm: transcricao)
    _alimentar(o, ALTO, 10)
    _alimentar(o, MUDO, 14)


def test_palavra_de_ativacao_e_pedido(o, monkeypatch, publicados):
    _alimentar(o, MUDO, 5)
    assert o.estado == "espera"
    o._vosk.parcial = "ametista"
    o.alimentar(MUDO)
    assert o.estado == "gravando" and any(e["tipo"] == "acordou" for e in publicados)
    _falar_pedido(o, "Ametista, que horas são?", monkeypatch)
    assert _esperar(lambda: o.pedidos)
    assert o.pedidos[0][0] == "que horas são" and o.pedidos[0][2] is False


def test_vosk_se_enganou(o, monkeypatch):
    o._vosk.parcial = "ametista"
    o.alimentar(MUDO)
    _falar_pedido(o, "a mesa está pronta", monkeypatch)
    assert _esperar(lambda: o.estado == "espera")
    assert o.pedidos == []


def test_interromper_dizendo_o_nome(o, publicados):
    ficha = estado.nova_ficha("resposta longa", "pc")
    o.estado = "processando"
    eventos.publicar({"tipo": "fala_inicio", "id": "r1"})
    eventos.publicar({"tipo": "fala_trecho", "id": "r1", "texto": "Deixa eu te contar uma história."})
    assert o.estado == "falando"
    o._vosk.parcial = "ametista"
    o.alimentar(MUDO)
    assert o.estado == "gravando" and o.origem == "nome"
    assert ficha.cancelado and any(e["tipo"] == "calar" for e in publicados)


def test_eco_da_propria_voz_nao_interrompe(o):
    o.estado = "processando"
    eventos.publicar({"tipo": "fala_inicio", "id": "r1"})
    eventos.publicar({"tipo": "fala_trecho", "id": "r1", "texto": "Eu sou a Ametista, sua assistente."})
    o._vosk.parcial = "sou a ametista"
    o.alimentar(MUDO)
    assert o.estado == "falando"


def test_interromper_com_para(o, publicados):
    o.estado = "processando"
    eventos.publicar({"tipo": "fala_inicio", "id": "r1"})
    o._vosk.final = "para"
    o.alimentar(MUDO)
    assert o.estado == "seguimento"
    assert any(e["tipo"] == "calar" for e in publicados)


def test_seguimento_e_conversa_continua(o, monkeypatch, publicados):
    o.estado = "processando"
    eventos.publicar({"tipo": "fala_inicio", "id": "r1"})
    eventos.publicar({"tipo": "fala_terminou", "id": "r1"})
    assert o.estado == "seguimento"
    # logo depois da resposta: fala sem o nome é para ela
    _falar_pedido(o, "e amanhã?", monkeypatch)
    assert _esperar(lambda: o.pedidos)
    assert o.pedidos[-1] == ("e amanhã?", DONO_PADRAO, False)
    # passou o seguimento curto: vira conversa (pode não ser para ela)
    o.estado = "seguimento"
    _alimentar(o, MUDO, 20)                          # 1,6 s > TEMPO_SEGUIMENTO
    assert any(e["tipo"] == "conversa" for e in publicados)
    _falar_pedido(o, "você viu o jogo ontem?", monkeypatch)
    assert _esperar(lambda: len(o.pedidos) == 2)
    assert o.pedidos[-1][2] is True                  # sem_nome
    # acabou a conversa: volta a esperar o nome
    o.estado = "seguimento"
    _alimentar(o, MUDO, 60)
    assert o.estado == "espera"


def test_aviso_no_meio_da_resposta_mantem_o_seguimento(o):
    o.estado = "processando"
    eventos.publicar({"tipo": "fala_inicio", "id": "r1"})
    eventos.publicar({"tipo": "fala_trecho", "id": "r1", "texto": "Amanhã vai chover."})
    eventos.publicar({"tipo": "alerta", "id": "a1", "texto": "Lembrete: reunião em dez minutos."})
    assert o.estado == "falando" and "reuniao" in o._texto_falando and "chover" in o._texto_falando
    eventos.publicar({"tipo": "fala_terminou", "id": "a1"})     # a sobreposição só avisa no fim de tudo
    assert o.estado == "seguimento"


def test_aviso_sozinho_volta_a_esperar_o_nome(o):
    eventos.publicar({"tipo": "alerta", "id": "a1", "texto": "Seu timer acabou."})
    assert o.estado == "falando"
    eventos.publicar({"tipo": "fala_terminou", "id": "a1"})
    assert o.estado == "espera"


def test_conversa_ignora_voz_desconhecida(o, monkeypatch):
    monkeypatch.setattr(identidade, "tem_cadastro", lambda: True)
    monkeypatch.setattr(identidade, "identificar", lambda pcm: Falante(None, "visitante", 0.3))
    o._conversa_ate = o.relogio + 100
    o._seg_ate = o.relogio - 1
    o.estado = "seguimento"
    _falar_pedido(o, "liga a televisão", monkeypatch)
    assert _esperar(lambda: o.estado == "seguimento")
    time.sleep(0.05)
    assert o.pedidos == []


def test_modo_privado_desliga_o_microfone(o):
    estado.definir_privado(True)
    assert o.mudo
    o._vosk.parcial = "ametista"
    o.alimentar(MUDO)
    assert o.estado == "espera"
    estado.definir_privado(False)
    assert not o.mudo


def test_tirar_nome():
    assert ouvido.tirar_nome("Ametista, toca Coldplay") == ("toca Coldplay", True)
    assert ouvido.tirar_nome("Ô Ametista que horas são") == ("que horas são", True)
    assert ouvido.tirar_nome("toca Coldplay") == ("toca Coldplay", False)
    assert ouvido.PARAR_FALA.match("para") and not ouvido.PARAR_FALA.match("para o carro ali")


def test_reconhecedor_descansa_no_silencio_e_nao_perde_o_comeco(o):
    chamadas = []
    original = o._vosk.AcceptWaveform
    o._vosk.AcceptWaveform = lambda bloco: chamadas.append(bloco) or original(bloco)
    _alimentar(o, MUDO, 100)                               # 8 s de silêncio
    assert len(chamadas) == ouvido.BLOCOS_ATE_DESCANSAR       # depois de 1,5 s ele para de processar
    chamadas.clear()
    o._vosk.parcial = "ametista"
    o.alimentar(ALTO)                                      # primeiro som: acorda com o áudio anterior
    assert len(chamadas) == ouvido.PREROLL_ACORDAR + 1 and chamadas[-1] == ALTO
    assert o.estado == "gravando"
