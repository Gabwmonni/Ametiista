"""Confere o cérebro local contra um Ollama DE VERDADE (no GitHub Actions: CPU e um modelo pequeno).

    python tests/checar_ollama.py qwen2.5:1.5b

O que precisa dar certo: o Ollama aceita as ferramentas no formato que mandamos, o modelo chama a ferramenta,
o resultado volta no formato certo e ela responde. Modelos pequenos às vezes não chamam a ferramenta de
primeira, então são até 3 tentativas.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="ametista-ollama-"))
os.environ["AMETISTA_DADOS"] = str(TMP / "dados")
os.environ["AMETISTA_ENV"] = str(TMP / ".env")
os.environ["BUSCA_SEMANTICA"] = "0"
os.environ.pop("ANTHROPIC_API_KEY", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ametista import cerebro, cerebro_local, config, notas  # noqa: E402
from ametista.identidade import DONO_PADRAO, falante_atual  # noqa: E402


def main(modelo: str) -> int:
    config.OLLAMA_MODELO = modelo
    notas.pasta = lambda: TMP / "Notas"
    notas.abrir_no_bloco = lambda p: None
    falante_atual.set(DONO_PADRAO)

    instalados = cerebro_local.modelos_instalados(forcar=True)
    print("modelos:", instalados)
    if cerebro_local.modelo() != modelo:
        print(f"ERRO: {modelo} não está no Ollama")
        return 1
    caps = cerebro_local.capacidades(modelo)
    print("capacidades:", sorted(caps))
    if "tools" not in caps:
        print("ERRO: o Ollama não informou que o modelo usa ferramentas")
        return 1

    t0 = time.time()
    r = cerebro.pensar("Oi! Responda só com uma frase curta.", DONO_PADRAO)
    print(f"conversa ({time.time() - t0:.0f} s): {r}")
    if r["origem"] != "local-ia" or not r["texto"].strip():
        print("ERRO: a conversa simples não veio do Ollama")
        return 1

    for tentativa in range(1, 4):
        t0 = time.time()
        r = cerebro_local.perguntar("Use a ferramenta nota_criar para criar uma nota com o título Teste CI e o "
                                    "texto funcionou.", DONO_PADRAO)
        criadas = sorted(p.name for p in (TMP / "Notas").glob("*.txt")) if (TMP / "Notas").exists() else []
        print(f"tentativa {tentativa} ({time.time() - t0:.0f} s): {r!r} -> notas: {criadas}")
        if criadas:
            texto = (TMP / "Notas" / criadas[0]).read_text(encoding="utf-8")
            print("conteúdo:", repr(texto))
            return 0
    print("ERRO: em 3 tentativas o modelo não chamou a ferramenta")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "qwen2.5:1.5b"))
