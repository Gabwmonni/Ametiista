"""Instalador: pasta em lugar ruim (caminho longo, OneDrive) e dados de uma instalação em outra pasta."""
from pathlib import Path, PureWindowsPath

import pytest

from ametista import pasta_segura as ps

DESTINO_REAL = ps.destino_sugerido
PASTA_DO_ERRO = Path("C:\\Users\\I\\OneDrive - Etec Centro Paula Souza\\Documents\\projeto-ametista-v2.0\\ametista")


@pytest.fixture(autouse=True)
def sem_ametista_aberta(monkeypatch, tmp_path):
    monkeypatch.setattr(ps, "_ametista_aberta", lambda porta=8765: False)
    monkeypatch.setattr(ps, "destino_sugerido", lambda: tmp_path / "destino-sugerido")   # nunca fora do teste
    monkeypatch.delenv(ps.SEM_PERGUNTAR, raising=False)
    for k in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        monkeypatch.delenv(k, raising=False)


def test_pasta_do_erro_real_tem_os_dois_problemas():
    motivos = ps.problemas(PASTA_DO_ERRO)
    assert len(motivos) == 2 and "OneDrive" in motivos[0] and "87 letras" in motivos[1]


def test_pastas_boas_e_onedrive_com_outro_nome(monkeypatch):
    assert ps.problemas(Path("C:\\Ametista")) == []
    assert ps.problemas(Path("C:\\Users\\Gabriel\\Documents\\projeto-ametista-v2.0\\ametista")) == []
    monkeypatch.setenv("OneDriveCommercial", "C:\\Users\\Gabriel\\Nuvem da Empresa")
    assert len(ps.problemas(Path("C:\\Users\\Gabriel\\Nuvem da Empresa\\Ametista"))) == 1
    assert ps.problemas(DESTINO_REAL()) == []      # o destino sugerido de verdade (só calcula, não cria nada)


def test_limite_cobre_o_arquivo_mais_longo_da_instalacao():
    mais_longo = 175   # .venv\Lib\site-packages\ + 151 letras (PySide6, medido nas bibliotecas do Windows)
    assert ps.LIMITE + mais_longo <= 259 - 10       # folga para versões novas das bibliotecas


def test_pasta_da_instalacao_anterior_pelo_comando_de_iniciar_com_o_windows():
    cmd = '"C:\\Ametista v1\\.venv\\Scripts\\pythonw.exe" "C:\\Ametista v1\\ametista.pyw"'
    assert PureWindowsPath(str(ps._pasta_do_comando(cmd))) == PureWindowsPath("C:\\Ametista v1")
    assert ps._pasta_do_comando('"C:\\x\\python.exe" "C:\\x\\outra.py"') is None


def _instalacao(pasta: Path, memoria: str = "v2") -> Path:
    (pasta / "ametista" / "__pycache__").mkdir(parents=True)
    (pasta / "ametista" / "__init__.py").write_text('__version__ = "2.0"\n')
    (pasta / "ametista" / "__pycache__" / "velho.pyc").write_bytes(b"x")
    (pasta / "instalar.bat").write_text("@echo off\n")
    (pasta / ".venv" / "Lib").mkdir(parents=True)
    (pasta / ".venv" / "Lib" / "enorme.dll").write_bytes(b"x")
    (pasta / "celular" / "node_modules").mkdir(parents=True)
    (pasta / "celular" / "worker.js").write_text("//")
    (pasta / "dados").mkdir()
    (pasta / "dados" / "memoria.json").write_text(memoria)
    return pasta


def test_mover_copia_o_codigo_e_nao_apaga_dados_de_quem_ja_esta_la(tmp_path):
    origem = _instalacao(tmp_path / "onedrive" / "ametista", memoria="da pasta nova")
    (origem / "dados" / "so_na_origem.txt").write_text("novo")
    (origem / ".env").write_text("ANTHROPIC_API_KEY=da-origem\n")
    destino = tmp_path / "C_Ametista"
    (destino / "dados").mkdir(parents=True)
    (destino / "dados" / "memoria.json").write_text("memória de verdade")
    (destino / ".env").write_text("ANTHROPIC_API_KEY=do-destino\n")
    (destino / "ametista").mkdir()
    (destino / "ametista" / "__init__.py").write_text('__version__ = "1.0"\n')

    ps.mover(origem, destino)
    assert (destino / "ametista" / "__init__.py").read_text() == '__version__ = "2.0"\n'   # código novo
    assert (destino / "instalar.bat").exists() and (destino / "celular" / "worker.js").exists()
    assert not (destino / ".venv").exists() and not (destino / "celular" / "node_modules").exists()
    assert not (destino / "ametista" / "__pycache__").exists()
    assert (destino / "dados" / "memoria.json").read_text() == "memória de verdade"     # nada substituído
    assert (destino / "dados" / "so_na_origem.txt").read_text() == "novo"
    assert (destino / ".env").read_text() == "ANTHROPIC_API_KEY=do-destino\n"


def test_main_move_para_um_lugar_bom(tmp_path, monkeypatch):
    origem = _instalacao(tmp_path / "longa")
    destino = tmp_path / "Ametista"
    monkeypatch.setattr(ps, "problemas", lambda p: ["dentro do OneDrive"] if p == origem else [])
    monkeypatch.setattr(ps, "destino_sugerido", lambda: destino)
    arq = tmp_path / "destino.txt"

    monkeypatch.setattr("builtins.input", lambda texto="": "n")
    assert ps.main(["x", str(origem), str(arq)]) == 1 and not destino.exists()

    monkeypatch.setattr("builtins.input", lambda texto="": "S")
    assert ps.main(["x", str(origem), str(arq)]) == 10
    assert Path(arq.read_text(encoding="utf-8")) == destino and (destino / "instalar.bat").exists()


def test_sem_resposta_nao_move(tmp_path, monkeypatch):
    origem = _instalacao(tmp_path / "longa")
    monkeypatch.setattr(ps, "problemas", lambda p: ["longo demais"])

    def sem_teclado(texto=""):
        raise EOFError
    monkeypatch.setattr("builtins.input", sem_teclado)
    assert ps.main(["x", str(origem)]) == 1


def test_traz_memoria_vozes_e_configuracoes_da_versao_anterior(tmp_path, monkeypatch):
    nova = _instalacao(tmp_path / "Ametista-2.0")
    (nova / "dados" / "memoria.json").unlink()
    antiga = tmp_path / "Ametista-1.0"
    (antiga / "dados").mkdir(parents=True)
    (antiga / "dados" / "memoria.json").write_text('{"fatos": ["café sem açúcar"]}')
    (antiga / "dados" / "pessoas.json").write_text("[]")
    (antiga / "voz" / "amostras").mkdir(parents=True)
    (antiga / "voz" / "amostras" / "gravacao.mp3").write_bytes(b"mp3")
    (antiga / "modelos" / "vosk").mkdir(parents=True)
    (antiga / "modelos" / "vosk" / "am.bin").write_bytes(b"m")
    (antiga / ".env").write_text("ANTHROPIC_API_KEY=sk-da-v1\n")
    monkeypatch.setattr(ps, "instalacao_anterior", lambda p: antiga)
    monkeypatch.setattr(ps, "problemas", lambda p: [])       # a pasta nova está num lugar bom
    monkeypatch.setenv(ps.SEM_PERGUNTAR, "1")

    assert ps.main(["x", str(nova)]) == 0
    assert (nova / "dados" / "memoria.json").read_text() == '{"fatos": ["café sem açúcar"]}'
    assert (nova / "voz" / "amostras" / "gravacao.mp3").exists() and (nova / "modelos" / "vosk" / "am.bin").exists()
    assert (nova / ".env").read_text() == "ANTHROPIC_API_KEY=sk-da-v1\n"
    assert (antiga / "dados" / "memoria.json").exists()          # a antiga fica intacta


def test_fora_do_windows_nao_procura_instalacao_anterior(tmp_path):
    import sys

    if sys.platform != "win32":
        assert ps.instalacao_anterior(tmp_path) is None
