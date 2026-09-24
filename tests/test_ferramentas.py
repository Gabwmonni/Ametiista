"""Ferramentas: lista por permissão, lembretes novos, textos falados."""
import re
from datetime import datetime

from ametista import config, ferramentas, memoria
from ametista.identidade import DONO_PADRAO, Falante


def test_lista_de_ferramentas_e_estavel_e_respeita_o_nivel():
    dono = [d["name"] for d in ferramentas.definicoes_permitidas(DONO_PADRAO)]
    assert dono == sorted(dono)                      # ordem fixa = cache da API funciona
    assert dono == [d["name"] for d in ferramentas.definicoes_permitidas(DONO_PADRAO)]
    visitante = {d["name"] for d in ferramentas.definicoes_permitidas(Falante(None, "visitante"))}
    assert visitante <= {"clima", "noticias", "criar_timer", "pc_midia", "pc_volume", "chamar_modelo_forte"}
    familia = {d["name"] for d in ferramentas.definicoes_permitidas(Falante("Bia", "familia"))}
    assert "pc_ver_tela" not in familia and "memoria_buscar" not in familia and "criar_lembrete" in familia
    forte = {d["name"] for d in ferramentas.definicoes_permitidas(DONO_PADRAO, forte=True)}
    assert "chamar_modelo_forte" not in forte
    # sem Spotify, agenda e casa configurados, as ferramentas deles não aparecem
    assert not any(n.startswith(("spotify_", "agenda_", "casa_", "steam_")) for n in dono)


def test_todas_as_ferramentas_tem_funcao_e_esquema_valido():
    for d in ferramentas.DEFINICOES:
        assert d["name"] in ferramentas.FUNCOES, d["name"]
        assert d["input_schema"]["type"] == "object"
        assert re.fullmatch(r"[a-z_]+", d["name"])
        for obrig in d["input_schema"].get("required", []):
            assert obrig in d["input_schema"]["properties"], (d["name"], obrig)


def test_ferramenta_desconhecida(dono):
    assert ferramentas.executar("nao_existe", {}).startswith("Ferramenta desconhecida")


def test_timer_e_falavel(dono):
    r = ferramentas.executar("criar_timer", {"minutos": 10, "descricao": "bolo"})
    assert re.search(r"\(id [0-9a-f]{8}\)", r)
    assert ferramentas.falavel(r).startswith("Timer de 10 minutos criado") and "(id" not in ferramentas.falavel(r)
    assert ferramentas.falavel("Criado no Google Agenda: X [g:abc_123].") == "Criado no Google Agenda: X."


def test_lembrete_recorrente(dono):
    r = ferramentas.executar("lembrete_recorrente", {"texto": "remédio", "hora": "08:00", "frequencia": "semanal",
                                                     "dias_semana": ["segunda", "quarta-feira"]})
    assert r.startswith("Lembrete recorrente criado")
    item = memoria.lembretes_pendentes()[0]
    assert item["recorrencia"] == {"tipo": "semanal", "dias": [0, 2]}
    assert datetime.fromisoformat(item["quando"]).weekday() in (0, 2)
    assert ferramentas.executar("lembrete_recorrente", {"texto": "x", "hora": "8h", "frequencia": "diario"}).startswith("Erro")


def test_lembrete_condicao(dono):
    r = ferramentas.executar("lembrete_condicao", {"texto": "pagar a conta", "condicao": "ao_abrir_programa",
                                                   "programa": "AutoCAD"})
    assert "quando você abrir o AutoCAD" in r
    r = ferramentas.executar("lembrete_condicao", {"texto": "regar as plantas", "condicao": "ao_chegar_casa"})
    assert "Home Assistant" in r                 # sem HA, vira "ao chegar" com explicação
    conds = {l["condicao"] for l in memoria.lembretes_pendentes()}
    assert conds == {"ao_abrir:AutoCAD", "ao_chegar"}


def test_aniversario_com_vespera_e_idade(dono):
    ferramentas.executar("aniversario_adicionar", {"nome": "Maria", "dia": 12, "mes": 3, "ano": 1990})
    tipos = sorted(l["tipo"] for l in memoria.lembretes_pendentes())
    assert tipos == ["aniversario", "aniversario_vespera"]
    item = next(l for l in memoria.lembretes_pendentes() if l["tipo"] == "aniversario")
    fala = ferramentas.texto_do_alerta(item)
    assert fala.startswith("Hoje é aniversário de Maria!") and f"Faz {datetime.now().year - 1990} anos." in fala
    assert ferramentas.executar("aniversario_adicionar", {"nome": "X", "dia": 31, "mes": 2}).startswith("Erro")


def test_textos_de_alerta():
    t = ferramentas.texto_do_alerta
    assert t({"tipo": "timer", "texto": "Timer"}) == "Seu timer acabou!"
    assert t({"tipo": "timer", "texto": "bolo"}) == "Tempo esgotado: bolo"
    assert t({"tipo": "lembrete", "texto": "dentista", "atraso_min": 20, "quando": "2026-01-01T10:00:00"}) == \
        "Lembrete: dentista (era para as 10:00)"
    assert t({"tipo": "condicao", "texto": "ligar"}) == "Você me pediu para lembrar: ligar"


def test_memoria_buscar(dono):
    t = memoria.nova_troca()
    memoria.registrar(t, "user", "qual o orçamento da obra?", "Gabriel")
    memoria.registrar(t, "assistant", "Trinta mil reais.")
    hoje = datetime.now().date().isoformat()
    assert "orçamento" in ferramentas.memoria_buscar(data_inicio=hoje)
    assert "Trinta mil" in ferramentas.memoria_buscar("orcamento")
    assert ferramentas.memoria_buscar(data_inicio="ontem").startswith("Erro")


def test_imagem_vira_blocos(dono, monkeypatch):
    monkeypatch.setitem(ferramentas.FUNCOES, "pc_ver_tela", lambda monitor="principal": {"imagem_b64": "QUJD",
                                                                                          "texto": "print"})
    r = ferramentas.executar("pc_ver_tela", {})
    assert r[0]["type"] == "image" and r[1] == {"type": "text", "text": "print"}


def test_nao_perturbe_e_privado(dono):
    from ametista import estado

    assert "Não perturbe até" in ferramentas.executar("nao_perturbe", {"minutos": 30})
    assert estado.nao_perturbe_ate() and estado.silencio_agora()
    ferramentas.executar("nao_perturbe", {"minutos": 0})
    assert not estado.nao_perturbe_ate()
    ferramentas.executar("modo_privado", {"ligar": True})
    assert estado.privado()
    ferramentas.executar("modo_privado", {"ligar": False})
    assert not estado.privado()


def test_horario_de_silencio(monkeypatch):
    from ametista import estado

    monkeypatch.setattr(config, "HORARIO_SILENCIO", "22:00-07:00")
    assert estado.silencio_agora(datetime(2026, 1, 1, 23, 30))
    assert estado.silencio_agora(datetime(2026, 1, 1, 6, 59))
    assert not estado.silencio_agora(datetime(2026, 1, 1, 12, 0))
    monkeypatch.setattr(config, "HORARIO_SILENCIO", "13:00-14:00")
    assert estado.silencio_agora(datetime(2026, 1, 1, 13, 30))
