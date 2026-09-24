"""Confere uma pasta que era a 1.0 e foi atualizada para a versão nova (usado pelo GitHub Actions).

Uso: <python da pasta> tests/checar_atualizacao.py <pasta>
"""
import subprocess
import sys
from pathlib import Path

pasta = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(pasta))

versao = subprocess.run([sys.executable, "-m", "ametista", "--versao"], cwd=pasta, capture_output=True, text=True,
                        encoding="utf-8").stdout.strip()
from ametista import __version__, autoinicio, config, identidade, memoria  # noqa: E402

assert versao == f"Ametista {__version__}" and __version__ != "1.0", versao

assert config.ANTHROPIC_API_KEY == "sk-ant-teste-da-v1" and config.TEMPO_SEGUIMENTO == 6 and config.CIDADE == "Jundiaí", \
    "o .env da 1.0 deveria continuar valendo"
assert config.CONVERSA_MINUTOS == 3 and config.CLAUDE_MODELO_FORTE == "claude-opus-5", "novas opções no padrão"
assert config.OLLAMA_MODELO == "qwen2.5:7b" and config.FOCO_TOLERANCIA_MIN == 3, "padrões da 3.0"
memoria.db()
assert memoria.fatos() == ["Gabriel prefere café sem açúcar", "A obra de Jundiaí fica na rua das Flores"], memoria.fatos()
lembretes = [r["texto"] for r in memoria._consulta("SELECT texto FROM lembretes")]
assert lembretes == ["ligar para o engenheiro"], lembretes
assert (config.DADOS / "memoria_v1_migrada.json").exists()
assert identidade.pessoas() == [{"nome": "Gabriel", "nivel": "dono", "amostras": 2}], identidade.pessoas()
assert config.VOSK_MODELO.exists() and config.MODELO_VOZ_ID.exists(), "modelos da 1.0 reaproveitados"
if sys.platform == "win32":
    assert autoinicio.ativo()
    assert "ametista.pyw" in autoinicio._comando()
print(f"OK: atualização da 1.0 para a {__version__} sem perder nada")
