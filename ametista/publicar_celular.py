"""Publica o app do celular na sua conta Cloudflare (grátis) e liga o PC a ele.

Uso: python -m ametista.publicar_celular   (ou dois cliques em publicar_celular.bat)
Precisa do Node.js instalado (nodejs.org). Na primeira vez, o navegador abre para você entrar na Cloudflare.
"""
import re
import shutil
import subprocess
import sys

from . import config
from .clonar_voz import _salvar_env
from .nuvem import gerar_chave

PASTA = config.RAIZ / "celular"


def _rodar(cmd: str, entrada: str | None = None) -> str:
    print(f"\n> {cmd}")
    p = subprocess.run(cmd, cwd=PASTA, shell=True, input=entrada, text=True, capture_output=entrada is not None,
                       encoding="utf-8", errors="replace")
    saida = (p.stdout or "") + (p.stderr or "")
    if entrada is not None:
        print(saida[-1500:])
    if p.returncode != 0:
        sys.exit(f"Falhou: {cmd}")
    return saida


def main() -> None:
    if not shutil.which("npx"):
        sys.exit("Instale o Node.js (nodejs.org, versão LTS) e rode de novo.")

    chave = config.NUVEM_CHAVE
    if not chave:
        chave = gerar_chave()
        _salvar_env("NUVEM_CHAVE", chave)
        print("Chave secreta criada e salva no .env.")

    if not (PASTA / "node_modules").exists():
        _rodar("npm install --no-audit --no-fund")

    # login (abre o navegador só se ainda não estiver logado)
    who = subprocess.run("npx wrangler whoami", cwd=PASTA, shell=True, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if "not authenticated" in (who.stdout + who.stderr).lower():
        _rodar("npx wrangler login")

    saida = _rodar("npx wrangler deploy", entrada="")
    url = re.search(r"https://[\w.-]+\.workers\.dev", saida)
    _rodar("npx wrangler secret put CHAVE_PC", entrada=chave + "\n")
    if url:
        _salvar_env("NUVEM_URL", url.group(0))
        print(f"\nPronto! App publicado em {url.group(0)}")
    else:
        print("\nPublicado, mas não achei o endereço na saída acima. Copie o https://...workers.dev "
              "para NUVEM_URL no .env.")
    print("Reinicie a Ametista e use 💎 > Parear celular.")


if __name__ == "__main__":
    main()
