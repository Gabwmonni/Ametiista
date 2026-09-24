"""Configurações (.env pelo painel) e documento de identidade."""
from ametista import config, personalidade


def test_salvar_mantem_comentarios_e_detecta_reinicio(env_limpo):
    env_limpo.write_text("# comentário do usuário\nAMETISTA_DONO=Gabriel\nPORTA=8765\n", encoding="utf-8")
    config.recarregar()
    reiniciar = config.salvar({"AMETISTA_DONO": "Gabi", "PORTA": "9000", "CIDADE": "Jundiaí"})
    texto = env_limpo.read_text(encoding="utf-8")
    assert "# comentário do usuário" in texto
    assert "AMETISTA_DONO=Gabi" in texto
    assert "CIDADE=Jundiaí" in texto            # chave nova vai para o fim
    assert reiniciar == ["PORTA"]                # só a porta precisa reiniciar
    assert config.DONO == "Gabi" and config.PORTA == 9000 and config.CIDADE == "Jundiaí"


def test_valores_com_caracteres_especiais_sao_protegidos(env_limpo):
    config.salvar({"HA_TOKEN": 'abc#def "x"', "NOTICIAS_RSS": "https://exemplo.com/rss?a=1&b=2"})
    assert config.HA_TOKEN == 'abc#def "x"'
    assert config.NOTICIAS_RSS == "https://exemplo.com/rss?a=1&b=2"


def test_conversores_e_padroes(env_limpo):
    env_limpo.write_text("LIMIAR_MIN=abc\nMODELO_AUTOMATICO=0\nPROATIVIDADE=\n", encoding="utf-8")
    config.recarregar()
    assert config.LIMIAR_MIN == 350.0           # valor inválido cai no padrão
    assert config.MODELO_AUTOMATICO is False
    assert config.PROATIVIDADE == 2             # vazio usa o padrão
    assert config.VOSK_MODELO.is_absolute()


def test_chave_desconhecida_e_recusada(env_limpo):
    import pytest

    with pytest.raises(KeyError):
        config.salvar({"NAO_EXISTE": "1"})


def test_identidade_preenche_nomes_e_tira_notas(tmp_path, monkeypatch):
    doc = tmp_path / "id.md"
    doc.write_text("> nota para o dono\nVocê é {nome}, assistente de {dono}.\n", encoding="utf-8")
    monkeypatch.setattr(config, "IDENTIDADE_DOC", doc)
    personalidade._cache["mtime"] = None
    t = personalidade.identidade()
    assert "nota para o dono" not in t
    assert f"Você é {config.NOME}, assistente de {config.DONO}." in t


def test_identidade_ausente_usa_padrao(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IDENTIDADE_DOC", tmp_path / "nao-existe.md")
    assert config.NOME in personalidade.identidade()


def test_documento_real_e_carregado():
    personalidade._cache["mtime"] = None
    t = personalidade.sistema_base(expressiva=True)
    assert "Identidade da Ametista" in t and "[risada]" in t and "[feliz]" in t
    assert "Regras técnicas de fala" in personalidade.sistema_base(expressiva=False)
    assert "[risada]" not in personalidade.sistema_base(expressiva=False)
