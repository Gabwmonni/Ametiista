"""Foco nos estudos: o que é distração, horários, chamados, pausa, resumo e relatório."""
import time
from datetime import datetime, timedelta

import pytest

from ametista import acoes, avisos, config, estado, ferramentas, foco, proatividade
from ametista.identidade import Falante, falante_atual


@pytest.fixture
def falas(monkeypatch):
    lista = []
    monkeypatch.setattr(avisos, "proativo", lambda texto, emocao="neutra", celular=False, titulo="Ametista":
                        lista.append(texto))
    return lista


@pytest.fixture
def mon(monkeypatch):
    monkeypatch.setattr(foco.Monitor, "ligar", lambda self: None)       # sem thread nos testes
    monkeypatch.setattr(foco, "_monitor", None)
    return foco.monitor()


YOUTUBE = ("Gato tocando piano - YouTube - Google Chrome", "chrome.exe", "")
AULA = ("Aula 3 - Derivadas - YouTube - Google Chrome", "chrome.exe", "")
PDF = ("Lista 2.pdf - Adobe Acrobat Reader", "AcroRd32.exe", "")
EXPLORER = ("Downloads", "explorer.exe", "")


def rodar(m, inicio, segundos, janela, ocioso=5.0, passo=15):
    """Simula o vigia rodando de 15 em 15 segundos."""
    t = inicio
    while t < inicio + segundos:
        t += passo
        m.rodada(agora=t, janela=janela, ocioso=ocioso, tela_cheia=False)
    return t


# ---------------------------------------------------------------- o que é distração
@pytest.mark.parametrize("janela, classe, rotulo", [
    (YOUTUBE, "distracao", "YouTube"),
    (AULA, "estudo", ""),
    (PDF, "estudo", ""),
    (("Planta.dwg - AutoCAD 2025", "acad.exe", ""), "estudo", ""),
    (("(3) Instagram • Google Chrome", "chrome.exe", ""), "distracao", "Instagram"),
    (("Página inicial / X - Google Chrome", "chrome.exe", ""), "distracao", "X"),
    (("Hollow Knight", "hollow_knight.exe", r"C:\Program Files (x86)\Steam\steamapps\common\Hollow Knight\hk.exe"),
     "distracao", "Hollow Knight"),
    (("VALORANT", "VALORANT-Win64-Shipping.exe", ""), "distracao", "Valorant"),
    (("#geral | Grupo de Estudos - Discord", "Discord.exe", ""), "estudo", ""),
    (("Amigos - Discord", "Discord.exe", ""), "distracao", "Discord"),
    (EXPLORER, "neutro", ""),
    (("Ametista", "pythonw.exe", ""), "neutro", ""),
    (("Notícias - Google Chrome", "chrome.exe", ""), "neutro", ""),
    (("Maximizar produtividade - Google Chrome", "chrome.exe", ""), "neutro", ""),   # "max" não é o HBO Max
    (("", "", ""), "neutro", ""),
])
def test_classificar(janela, classe, rotulo):
    c, r, _ = foco.classificar(*janela)
    assert (c, r) == (classe, rotulo)


def test_tela_cheia_de_programa_desconhecido_e_jogo():
    assert foco.classificar("Jogo Qualquer", "jogo.exe", "", tela_cheia=True)[:2] == ("distracao", "Jogo Qualquer")
    assert foco.classificar("Jogo Qualquer", "jogo.exe", "", tela_cheia=False)[0] == "neutro"
    assert foco.classificar("Filme - YouTube", "chrome.exe", "", tela_cheia=True)[:2] == ("distracao", "YouTube")


def test_listas_do_painel_e_materia(monkeypatch):
    monkeypatch.setattr(config, "FOCO_ESTUDO", "cursinho do joão; projeto final")
    monkeypatch.setattr(config, "FOCO_DISTRACOES", "uol; clashroyale.exe")
    assert foco.classificar("Cursinho do João - YouTube", "chrome.exe")[0] == "estudo"
    assert foco.classificar("UOL - O melhor conteúdo", "msedge.exe")[:2] == ("distracao", "uol")
    assert foco.classificar("Clash Royale", "ClashRoyale.exe")[0] == "distracao"
    assert foco.classificar("Cálculo I - Stewart - YouTube", "chrome.exe", materia="cálculo")[0] == "estudo"
    assert foco.classificar("Cálculo I - Stewart - YouTube", "chrome.exe")[0] == "distracao"


# ---------------------------------------------------------------- horários
def test_horarios():
    h = foco.horarios("seg-sex 19:00-22:00; sáb 9h-12h; todos os dias 6-7; segunda a quarta 20:30 às 21:15; lixo")
    assert [(sorted(d), a.strftime("%H:%M"), b.strftime("%H:%M")) for d, a, b in h] == [
        ([0, 1, 2, 3, 4], "19:00", "22:00"), ([5], "09:00", "12:00"), (list(range(7)), "06:00", "07:00"),
        ([0, 1, 2], "20:30", "21:15")]
    assert sorted(foco.horarios("sex-seg 10-11")[0][0]) == [0, 4, 5, 6]          # passa pelo fim de semana
    assert sorted(foco.horarios("fim de semana 14-16")[0][0]) == [5, 6]
    assert foco.horarios("") == [] and foco.horarios("25:00-26:00") == []


def test_janela_de_estudo_passa_da_meia_noite():
    texto = "sex 23:00-01:00"
    sexta = datetime(2026, 9, 25, 23, 30)                   # 25/09/2026 é sexta
    assert foco.janela_de_estudo(sexta, texto) == (datetime(2026, 9, 25, 23), datetime(2026, 9, 26, 1))
    assert foco.janela_de_estudo(sexta + timedelta(hours=1), texto)[0] == datetime(2026, 9, 25, 23)
    assert foco.janela_de_estudo(sexta + timedelta(hours=2), texto) is None
    assert foco.janela_de_estudo(datetime(2026, 9, 24, 23, 30), texto) is None      # quinta


# ---------------------------------------------------------------- sessão
def test_sessao_chama_de_volta_com_calma(mon, falas):
    t0 = time.time()
    assert "Sessão de foco de cálculo começou, por 1 hora" in mon.iniciar(60, "cálculo", agora=t0)
    t = rodar(mon, t0, 120, AULA)
    t = rodar(mon, t, 150, YOUTUBE)                          # 2,5 min: ainda não
    assert falas == []
    t = rodar(mon, t, 45, YOUTUBE)                           # passou de 3 min
    assert len(falas) == 1 and "no YouTube" in falas[0] and "cálculo" in falas[0]
    t = rodar(mon, t, 5 * 60, YOUTUBE)                       # não repete antes de 8 min
    assert len(falas) == 1
    t = rodar(mon, t, 3 * 60, YOUTUBE)
    assert len(falas) == 2 and "voltou a ficar no YouTube" in falas[1] and "Faltam" in falas[1]
    # voltou a estudar: 1 min estudando zera a contagem
    t = rodar(mon, t, 75, PDF)
    assert mon.sessao.seq_distracao == 0
    t = rodar(mon, t, 60, EXPLORER)                          # neutro não conta como distração
    assert len(falas) == 2 and mon.sessao.seq_distracao == 0
    s = mon.sessao
    assert s.tempos["estudo"] == pytest.approx(195, abs=15) and s.distracoes["YouTube"] == pytest.approx(675, abs=15)


def test_saiu_do_pc_nao_e_distracao(mon, falas):
    t0 = time.time()
    mon.iniciar(0, "", agora=t0)
    t = rodar(mon, t0, 150, YOUTUBE)
    t = rodar(mon, t, 600, YOUTUBE, ocioso=900)             # vídeo aberto, mas ninguém no PC
    assert falas == [] and mon.sessao.tempos["ausente"] >= 585
    rodar(mon, t, 600, PDF, ocioso=700)                      # lendo um PDF parado ainda é estudo
    assert mon.sessao.tempos["estudo"] >= 585


def test_pausa_e_fim_da_sessao_com_resumo(mon, falas):
    t0 = time.time()
    mon.iniciar(30, "física", agora=t0)
    t = rodar(mon, t0, 600, PDF)
    assert mon.pausar(10, agora=t) == "Pausa de 10 minutos. Eu te chamo quando acabar."
    t = rodar(mon, t, 585, YOUTUBE)                          # na pausa pode tudo
    assert falas == [] and mon.sessao.tempos["pausa"] >= 570
    t = rodar(mon, t, 30, PDF)
    assert falas == ["A pausa acabou, Gabriel. Bora voltar para física?"]
    rodar(mon, t, 11 * 60, PDF)                              # chega nos 30 min
    assert mon.sessao is None
    assert falas[-1].startswith("Sessão de física encerrada: 30 minutos no total, ")
    assert "Nenhuma distração" in falas[-1]
    sessoes = foco.sessoes_do_periodo(datetime.now() - timedelta(days=1), datetime.now() + timedelta(days=1))
    assert len(sessoes) == 1 and sessoes[0]["materia"] == "física" and sessoes[0]["pausa"] >= 570


def test_resumo_conta_as_distracoes(mon):
    t0 = time.time()
    mon.iniciar(0, "", agora=t0)
    t = rodar(mon, t0, 20 * 60, PDF)
    t = rodar(mon, t, 10 * 60, YOUTUBE)
    assert mon.encerrar(agora=t) == ("Sessão encerrada: 30 minutos no total, 20 minutos estudando e 10 minutos "
                                     "em distrações, mais no YouTube. Dá para melhorar na próxima.")
    assert mon.encerrar(agora=t) == ""


def test_modo_privado_nao_olha_nada(mon, falas):
    t0 = time.time()
    mon.iniciar(0, "", agora=t0)
    estado._persistente["privado"] = True
    rodar(mon, t0, 20 * 60, YOUTUBE)
    assert falas == [] and mon.sessao.tempos["distracao"] == 0


def test_nao_perturbe_segura_o_chamado(mon, falas):
    t0 = time.time()
    mon.iniciar(0, "", agora=t0)
    estado.definir_nao_perturbe(datetime.now() + timedelta(hours=1))
    rodar(mon, t0, 10 * 60, YOUTUBE)
    assert falas == []


def test_horario_de_estudo_comeca_sozinho_uma_vez(mon, falas, monkeypatch):
    agora = datetime.now().replace(second=0, microsecond=0)
    ini, fim = agora - timedelta(minutes=5), agora + timedelta(minutes=55)
    if ini.date() != agora.date() or fim.date() != agora.date():
        pytest.skip("perto da meia-noite")
    monkeypatch.setattr(config, "FOCO_HORARIOS", f"todos os dias {ini:%H:%M}-{fim:%H:%M}")
    t = agora.timestamp()
    t = rodar(mon, t, 30, PDF, ocioso=1500)                 # longe do PC: começa, mas sem anunciar
    assert mon.sessao is not None and mon.sessao.origem == "horario" and falas == []
    t = rodar(mon, t, 15, PDF)
    assert falas == [f"Hora de estudar, Gabriel! Eu fico de olho nas distrações até as {fim:%H:%M}."]
    mon.encerrar(agora=t)
    rodar(mon, t, 60, PDF)                                   # parou antes do fim: não recomeça
    assert mon.sessao is None


def test_fora_da_sessao_percebe_sozinha(mon, falas, monkeypatch):
    monkeypatch.setattr(config, "PROATIVIDADE", 2)
    monkeypatch.setattr(config, "HORARIO_SILENCIO", "00:00-00:00")
    monkeypatch.setattr(proatividade, "pc", None, raising=False)
    from ametista import pc

    monkeypatch.setattr(pc, "tempo_ocioso", lambda: 5.0)
    t0 = time.time()
    t = rodar(mon, t0, 12 * 60, PDF)
    t = rodar(mon, t, 14 * 60, YOUTUBE)
    assert falas == []
    rodar(mon, t, 90, YOUTUBE)
    assert len(falas) == 1 and "você estava estudando" in falas[0] and "no YouTube" in falas[0]
    monkeypatch.setattr(config, "FOCO_PERCEBER", False)
    outro = foco.Monitor()
    t = rodar(outro, t0, 12 * 60, PDF)
    rodar(outro, t, 20 * 60, YOUTUBE)
    assert len(falas) == 1


def test_sessao_sobrevive_ao_reinicio(mon):
    t0 = time.time() - 120
    mon.iniciar(60, "química", agora=t0)
    rodar(mon, t0, 90, PDF)
    novo = foco.Monitor()                                    # reiniciou logo depois (atualização)
    assert novo.sessao is not None and novo.sessao.materia == "química" and novo.sessao.tempos["estudo"] >= 45
    estado.lembrar("foco_sessao", None)
    t0 = time.time() - 7200
    mon.encerrar(agora=t0)
    mon.iniciar(0, "física", agora=t0)
    rodar(mon, t0, 600, PDF)
    velho = foco.Monitor()                                   # ficou desligada mais de meia hora: fecha a sessão
    assert velho.sessao is None and estado.obter("foco_sessao") is None
    sessoes = foco.sessoes_do_periodo(datetime.now() - timedelta(days=1), datetime.now() + timedelta(days=1))
    assert [x["materia"] for x in sessoes] == ["física"] and sessoes[0]["estudo"] >= 500


# ---------------------------------------------------------------- ferramentas
def test_ferramentas_e_relatorio(mon, dono):
    assert "nenhuma sessão" in ferramentas.executar("foco_relatorio", {"periodo": "hoje"})
    fala = ferramentas.executar("foco_iniciar", {"minutos": 45, "materia": "cálculo"})
    assert fala.startswith("Sessão de foco de cálculo começou, por 45 minutos")
    assert "cálculo" in foco.resumo_contexto() and "foco_parar" in foco.resumo_contexto()
    assert "continua (cálculo), agora até as" in ferramentas.executar("foco_iniciar", {"minutos": 90})
    s = mon.sessao
    s.inicio -= 3600
    s.tempos.update(estudo=3000, distracao=600)
    s.distracoes.update({"YouTube": 400, "Instagram": 200})
    s.preps.update({"YouTube": "no", "Instagram": "no"})
    assert ferramentas.executar("foco_parar", {}).startswith("Sessão de cálculo encerrada: 1 hora no total, "
                                                             "50 minutos estudando e só 10 minutos de distração")
    assert foco.resumo_contexto() == ""
    rel = ferramentas.executar("foco_relatorio", {"periodo": "semana"})
    assert rel.startswith("Nos últimos 7 dias: 1 sessão de foco, 50 minutos estudando e 10 minutos em distrações "
                          "(83% de foco).")
    assert "YouTube (7 minutos), Instagram (3 minutos)" in rel and "cálculo (50 minutos)" in rel
    registradas = [a["ferramenta"] for a in acoes.listar(10)]
    assert "foco_iniciar" in registradas and "foco_parar" in registradas and "foco_relatorio" not in registradas
    assert ferramentas.executar("foco_parar", {}) == "Não havia sessão de foco em andamento."


def test_familia_nao_mexe_no_foco(mon):
    token = falante_atual.set(Falante("Ana", "familia"))
    try:
        assert "foco_iniciar" not in {d["name"] for d in ferramentas.definicoes_permitidas()}
        assert "não" in ferramentas.executar("foco_iniciar", {"minutos": 30}).lower()
        assert mon.sessao is None
    finally:
        falante_atual.reset(token)
