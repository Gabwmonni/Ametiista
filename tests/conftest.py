"""Configuração dos testes: a Ametista roda com dados e .env temporários, sem microfone nem internet."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="ametista-testes-"))
os.environ["AMETISTA_DADOS"] = str(_TMP / "dados")
os.environ["AMETISTA_ENV"] = str(_TMP / ".env")
for chave in ("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "NUVEM_URL", "NUVEM_CHAVE", "HA_URL", "HA_TOKEN",
              "SPOTIFY_CLIENT_ID", "MS_CLIENT_ID"):
    os.environ.pop(chave, None)
os.environ["BUSCA_SEMANTICA"] = "0"
os.environ["PROATIVIDADE"] = "2"

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


@pytest.fixture
def memoria_limpa():
    """Banco de memória novo e vazio para cada teste."""
    from ametista import acoes, memoria

    memoria.fechar()
    for sufixo in ("", "-wal", "-shm"):
        p = Path(str(memoria.ARQUIVO) + sufixo)
        if p.exists():
            p.unlink()
    memoria._recente.clear()
    memoria._trocas_privadas.clear()
    acoes._tabela_pronta = False
    acoes.cancelar_pendente()
    yield memoria
    memoria.fechar()


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


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)
