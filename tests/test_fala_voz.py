"""Fala em trechos (começa antes de terminar de pensar) e voz expressiva."""
import threading
import time

from ametista import config, estado, fala, voz


def _trechos(publicados, tipo="fala_trecho"):
    return [e for e in publicados if e["tipo"] == tipo]


def test_corta_em_frases_e_publica_em_ordem(publicados, monkeypatch):
    atrasos = {"Oi, Gabriel!": 0.15}   # a primeira frase demora mais para gerar e mesmo assim sai primeiro
    monkeypatch.setattr(voz, "sintetizar_sync", lambda t, espera=40: time.sleep(atrasos.get(t, 0)) or f"AUDIO:{t}")
    loc = fala.Locutor(origem="nuvem")
    for pedaco in ["[feliz] Oi, ", "Gabriel! São ", "três e meia. ", "Quer que eu ", "toque algo?"]:
        loc.texto(pedaco)
    texto = loc.terminar()
    assert texto == "Oi, Gabriel! São três e meia. Quer que eu toque algo?"
    trechos = _trechos(publicados)
    assert [t["texto"] for t in trechos] == ["Oi, Gabriel!", "São três e meia.", "Quer que eu toque algo?"]
    assert [t["seq"] for t in trechos] == [0, 1, 2]
    assert trechos[0]["audio"] == "AUDIO:Oi, Gabriel!" and trechos[0]["emocao"] == "feliz"
    tipos = [e["tipo"] for e in publicados if e["tipo"].startswith("fala_")]
    assert tipos[0] == "fala_inicio" and tipos[-1] == "fala_fim"
    assert _trechos(publicados, "fala_fim")[0]["total"] == 3


def test_primeira_frase_longa_corta_na_virgula(publicados):
    loc = fala.Locutor()
    loc.texto("Olha, eu dei uma olhada na sua agenda de amanhã e vi que você tem uma reunião cedo, então ")
    trechos = []
    for _ in range(50):
        trechos = _trechos(publicados)
        if trechos:
            break
        time.sleep(0.01)
    assert trechos and trechos[0]["texto"].endswith(",")      # já começou a falar
    loc.texto("é melhor dormir cedo.")
    loc.terminar()


def test_abreviacoes_nao_cortam(publicados):
    loc = fala.Locutor()
    loc.texto("Falei com o Dr. Silva hoje. Tudo certo.")
    loc.terminar()
    assert [t["texto"] for t in _trechos(publicados)] == ["Falei com o Dr. Silva hoje.", "Tudo certo."]


def test_markdown_e_etiquetas_somem_da_tela(publicados):
    loc = fala.Locutor()
    loc.texto("[pensativa] **Hmm**, deixa eu ver. [risada] Brincadeira!")
    assert loc.terminar() == "Hmm, deixa eu ver. Brincadeira!"
    assert loc.emocao_atual == "pensativa"


def test_cancelar_para_de_publicar(publicados, monkeypatch):
    liberar = threading.Event()
    monkeypatch.setattr(voz, "sintetizar_sync", lambda t, espera=40: liberar.wait(2) and None)
    ficha = estado.nova_ficha("x")
    loc = fala.Locutor(ficha=ficha)
    loc.texto("Primeira frase. Segunda frase. ")
    ficha.cancelar()
    liberar.set()
    loc.terminar()
    assert _trechos(publicados) == [] and not _trechos(publicados, "fala_fim")


def test_sem_publicar_so_junta_o_texto(publicados):
    loc = fala.Locutor(publicar=False)
    loc.texto("Resposta para o celular. Com duas frases.")
    assert loc.terminar() == "Resposta para o celular. Com duas frases."
    assert not [e for e in publicados if e["tipo"].startswith("fala_")]


def test_marcas_de_expressao(monkeypatch):
    monkeypatch.setattr(config, "VOZ_PROVEDOR", "elevenlabs")
    monkeypatch.setattr(config, "ELEVENLABS_MODELO", "eleven_v3")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k")
    monkeypatch.setattr(config, "ELEVENLABS_VOZ_ID", "v")
    monkeypatch.setattr(config, "VOZ_EXPRESSIVA", True)
    assert voz.expressiva()
    assert voz.preparar_texto("[risadinha] Essa foi boa. [pausa] Mas sério.", "elevenlabs") == \
        "[chuckles] Essa foi boa.… Mas sério."
    assert voz.preparar_texto("[risadinha] Essa foi boa. [pausa] Mas sério.", "edge") == "Essa foi boa., Mas sério."
    monkeypatch.setattr(config, "ELEVENLABS_MODELO", "eleven_flash_v2_5")
    assert not voz.expressiva()
    assert voz.preparar_texto("[suspiro] Tá bom.", "elevenlabs") == "Tá bom."
    assert voz.texto_para_mostrar("[feliz] Pronto! [risada]") == "Pronto!"


def test_elevenlabs_so_forca_idioma_nos_modelos_que_aceitam(monkeypatch):
    import asyncio

    enviados = []

    class Resp:
        content = b"mp3"

        def raise_for_status(self):
            pass

    class Http:
        async def post(self, url, params=None, headers=None, json=None):
            enviados.append(json)
            return Resp()

    monkeypatch.setattr(voz, "_http", Http())
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k")
    monkeypatch.setattr(config, "ELEVENLABS_VOZ_ID", "v")
    for modelo in ("eleven_flash_v2_5", "eleven_multilingual_v2", "eleven_v3"):
        monkeypatch.setattr(config, "ELEVENLABS_MODELO", modelo)
        asyncio.run(voz._elevenlabs("oi"))
    assert ["language_code" in j for j in enviados] == [True, False, False]


def test_mime():
    assert voz.mime_de("UklGRiQAAABXQVZF") == "audio/wav"
    assert voz.mime_de("SUQzBAAAAAAA") == "audio/mpeg"
