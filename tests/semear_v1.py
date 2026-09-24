"""Cria dados com a Ametista 1.0 de verdade (usado pelo teste de atualização do GitHub Actions).

Uso: <python da 1.0> tests/semear_v1.py <pasta da 1.0>
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

pasta = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(pasta))

from ametista import __version__, config, memoria  # noqa: E402

assert __version__.startswith("1."), f"esperava a 1.0, achei {__version__}"
memoria.lembrar_fato("Gabriel prefere café sem açúcar")
memoria.lembrar_fato("A obra de Jundiaí fica na rua das Flores")
memoria.criar_lembrete("ligar para o engenheiro", datetime.now() + timedelta(days=1))
(config.DADOS / "pessoas.json").write_text(json.dumps([{"nome": "Gabriel", "nivel": "dono", "criado": "2026-09-01 10:00",
                                                        "amostras": [[0.1] * 192, [0.2] * 192]}]), encoding="utf-8")
env = pasta / ".env"
texto = env.read_text(encoding="utf-8")
for chave, valor in (("ANTHROPIC_API_KEY", "sk-ant-teste-da-v1"), ("TEMPO_SEGUIMENTO", "6"), ("CIDADE", "Jundiaí")):
    texto = "\n".join(f"{chave}={valor}" if linha.startswith(chave + "=") else linha for linha in texto.splitlines())
env.write_text(texto + "\n", encoding="utf-8")
print(f"1.0 com dados: {memoria.fatos()}, {len(memoria.lembretes_pendentes())} lembrete, 1 voz cadastrada")
