"""Confere uma pasta que era a 2.0 e foi atualizada para a 3.0 (usado pelo GitHub Actions).

Uso: <python da pasta> tests/checar_v2_para_v3.py <pasta>
"""
import subprocess
import sys
from pathlib import Path

pasta = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(pasta))

versao = subprocess.run([sys.executable, "-m", "ametista", "--versao"], cwd=pasta, capture_output=True, text=True,
                        encoding="utf-8").stdout.strip()
assert versao == "Ametista 3.0", versao

import pypdf  # noqa: E402,F401  (biblioteca nova da 3.0 instalada pelo instalar.bat)

from ametista import config, ferramentas, memoria  # noqa: E402

texto = (pasta / ".env").read_text(encoding="utf-8")
assert texto.startswith("# versão das configurações: 3\n"), texto[:200]
assert config.CIDADE == "Jundiaí" and config.VOZ_TOM == "+4Hz", "o que a pessoa escolheu continua"
assert config.OLLAMA_MODELO == "qwen2.5:7b", "o modelo padrão antigo do Ollama passou para o novo"
assert config.FOCO_TOLERANCIA_MIN == 3 and config.CEREBRO_PRINCIPAL == "claude", "opções novas no padrão"
memoria.db()
assert memoria.fatos() == ["Gabriel estuda engenharia"], memoria.fatos()
assert memoria.caderno_buscar("Jundiaí")[0]["detalhes"] == "fica na rua das Flores"
assert "que horas são?" in [r["texto"] for r in memoria._consulta("SELECT texto FROM conversas")], \
    "histórico de conversas continua"
assert {"arquivo_ler", "nota_criar", "pc_processos", "foco_iniciar"} <= set(ferramentas.FUNCOES)
print("OK: atualização da 2.0 para a 3.0 sem perder nada")
