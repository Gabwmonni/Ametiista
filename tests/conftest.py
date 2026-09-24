"""Configuração dos testes: a Ametista roda com dados e .env temporários, sem microfone, sem voz e sem internet."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="ametista-testes-"))
os.environ["AMETISTA_DADOS"] = str(_TMP / "dados")
os.environ["AMETISTA_ENV"] = str(_TMP / ".env")
for chave in ("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOZ_ID", "NUVEM_URL", "NUVEM_CHAVE", "HA_URL",
              "HA_TOKEN", "HA_PESSOA", "SPOTIFY_CLIENT_ID", "MS_CLIENT_ID", "VOZ_PROVEDOR", "PROATIVIDADE",
              "BUSCA_SEMANTICA", "OUVIDO_LIGADO", "PASTAS_INDICE", "STEAM_PASTA"):
    os.environ.pop(chave, None)
os.environ["BUSCA_SEMANTICA"] = "0"
os.environ["STEAM_PASTA"] = str(_TMP / "sem-steam")

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(autouse=True)
def isolamento(monkeypatch):
    """Cada teste começa com a Ametista "zerada" e sem voz de verdade."""
    from ametista import acoes, config, estado, eventos, memoria, proatividade, voz

    monkeypatch.setattr(voz, "sintetizar_sync", lambda texto, espera=40: None)
    config.recarregar()
    memoria.fechar()
    for sufixo in ("", "-wal", "-shm"):
        p = Path(str(memoria.ARQUIVO) + sufixo)
        if p.exists():
            p.unlink()
    memoria._recente.clear()
    memoria._trocas_privadas.clear()
    acoes._tabela_pronta = False
    acoes._pendente = None
    estado._persistente.clear()
    estado.offline = estado.ocupado = estado.falando = False
    estado._fichas.clear()
    proatividade._historico.clear()
    proatividade._por_chave.clear()
    antes = list(eventos._ouvintes)
    yield
    eventos._ouvintes[:] = antes
    memoria.fechar()


@pytest.fixture
def publicados():
    """Lista com todos os eventos publicados durante o teste."""
    from ametista import eventos

    lista: list[dict] = []
    eventos.ouvir(lista.append)
    return lista


@pytest.fixture
def env_limpo():
    env = Path(os.environ["AMETISTA_ENV"])
    if env.exists():
        env.unlink()
    yield env
    if env.exists():
        env.unlink()
    from ametista import config

    config.recarregar()


@pytest.fixture
def dono():
    from ametista.identidade import DONO_PADRAO, falante_atual

    token = falante_atual.set(DONO_PADRAO)
    yield DONO_PADRAO
    falante_atual.reset(token)


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)
