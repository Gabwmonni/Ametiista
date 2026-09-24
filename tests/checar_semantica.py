"""Confere a busca por significado com o modelo de verdade (baixa ~220 MB). Rodado pelo GitHub Actions."""
import os
import sys
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp())
os.environ.update(AMETISTA_DADOS=str(TMP / "dados"), AMETISTA_ENV=str(TMP / ".env"), BUSCA_SEMANTICA="1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ametista import memoria, semantica  # noqa: E402

assert semantica.disponivel(), "o modelo de busca por significado não carregou"
frases = ["Guardei a planta da obra de Jundiaí na pasta Projetos",
          "Meu notebook é um Dell com 16 GB de memória",
          "A reunião com o engenheiro foi remarcada para quinta"]
v = semantica.vetores(frases)
q = semantica.vetor("onde está o desenho técnico do projeto de Jundiaí?")
notas = v @ q
print("notas:", [round(float(n), 3) for n in notas])
assert notas.argmax() == 0, "a frase certa deveria ser a mais parecida"

t = memoria.nova_troca()
memoria.registrar(t, "user", "qual é o computador que eu uso no trabalho?", "Gabriel")
memoria.registrar(t, "assistant", "Você usa um notebook Dell com 16 GB.")
t2 = t + 1
memoria.registrar(t2, "user", "toca Coldplay", "Gabriel")
memoria.registrar(t2, "assistant", "Tocando Coldplay.")
for _ in range(100):
    if memoria._consulta("SELECT COUNT(*) AS n FROM vetores")[0]["n"] >= 2:
        break
    time.sleep(0.2)
achados = memoria.buscar_conversas("máquina do escritório")      # nenhuma palavra em comum
print("achados:", [a["pedido"] for a in achados])
assert achados and "computador" in achados[0]["pedido"]
print("OK: busca por significado funcionando")
