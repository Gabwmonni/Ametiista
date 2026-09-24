"""Cria dados com a Ametista 2.0 de verdade (usado pelo teste de atualização 2.0 -> 3.0 do GitHub Actions).

Uso: <python da 2.0> tests/semear_v2.py <pasta da 2.0>
"""
import sys
from pathlib import Path

pasta = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(pasta))

from ametista import __version__, config, memoria  # noqa: E402

assert __version__ == "2.0", f"esperava a 2.0, achei {__version__}"
memoria.lembrar_fato("Gabriel estuda engenharia")
memoria.caderno_guardar("obra de Jundiaí", "fica na rua das Flores", "projeto")
troca = memoria.nova_troca()
memoria.registrar(troca, "user", "que horas são?", quem="Gabriel")
memoria.registrar(troca, "assistant", "São dez horas.")
config.salvar({"CIDADE": "Jundiaí", "VOZ_TOM": "+4Hz"})
texto = (pasta / ".env").read_text(encoding="utf-8")
assert "OLLAMA_MODELO=qwen2.5:3b" in texto and "# versão das configurações: 2" in texto, texto[:300]
print(f"2.0 com dados: {memoria.fatos()}, caderno e conversa")
