"""Antes de instalar: confere se a pasta é um bom lugar e traz os dados de uma instalação anterior.

Roda com o Python do sistema, antes de existir o ambiente da Ametista, então só usa a biblioteca padrão.

    python -m ametista.pasta_segura <pasta> <arquivo_destino>

Saída: 0 = pode instalar aqui; 1 = parar; 10 = copiada para outra pasta (o caminho vai no arquivo_destino).

Por que existe:
- O Windows não aceita caminhos com mais de 259 letras. A instalação tem arquivos com até ~175 letras dentro
  da pasta (bibliotecas da parte gráfica), então a pasta precisa ter um caminho curto.
- Dentro do OneDrive, ele tentaria enviar uns 2 GB de bibliotecas e modelos para a nuvem, e a sincronização
  pode estragar o banco de memória.
- Quem descompacta a versão nova numa pasta nova perderia memória, vozes e configurações da anterior.
"""
import ntpath
import os
import shutil
import socket
import sys
from pathlib import Path

LIMITE = 70                          # letras no caminho da pasta (175 + 70 fica com folga abaixo de 259)
DADOS_USUARIO = ("dados", "modelos", "voz")
NAO_COPIAR = {".venv", "__pycache__", "node_modules", ".wrangler", ".git", *DADOS_USUARIO}
SEM_PERGUNTAR = "AMETISTA_INSTALAR_SEM_PERGUNTAR"   # instalação automática: responde "sim" a tudo


def _texto_pasta(pasta: Path) -> str:
    return str(pasta).rstrip("\\/") + "\\"


def _pastas_onedrive() -> list[str]:
    return [os.environ[k].rstrip("\\/").lower() for k in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer")
            if os.environ.get(k)]


def problemas(pasta: Path) -> list[str]:
    """Motivos (em português) pelos quais essa pasta não serve para instalar. Vazio = pode instalar."""
    texto = _texto_pasta(pasta)
    minusculo = texto.lower()
    motivos = []
    if "onedrive" in minusculo or any(minusculo.startswith(p + "\\") for p in _pastas_onedrive()):
        motivos.append("ela está dentro do OneDrive: ele tentaria enviar uns 2 GB de arquivos para a nuvem, "
                       "e a sincronização pode estragar a memória da Ametista")
    if len(texto) > LIMITE:
        motivos.append(f"o caminho é longo demais ({len(texto)} letras): o Windows não aceita alguns arquivos da "
                       "instalação")
    return motivos


def _eh_ametista(pasta: Path) -> bool:
    return (pasta / "ametista" / "__init__.py").exists()


def destino_sugerido() -> Path:
    """Onde instalar: C:\\Ametista (ou uma pasta curta parecida, se essa estiver ocupada por outra coisa)."""
    candidatos = [Path("C:/Ametista"), Path(os.path.expanduser("~")) / "Ametista", Path("C:/Ametista-2")]
    for p in candidatos:
        livre = not p.exists() or _eh_ametista(p) or (p.is_dir() and not any(p.iterdir()))
        if livre and not problemas(p):
            return p
    return candidatos[-1]


def _pasta_do_comando(comando: str) -> Path | None:
    """Do comando de "Iniciar com o Windows" ("...pythonw.exe" "C:\\X\\ametista.pyw"), tira a pasta C:\\X."""
    for parte in comando.split('"'):
        if parte.strip().lower().endswith("ametista.pyw"):
            return Path(ntpath.dirname(parte.strip()))
    return None


def instalacao_anterior(pasta: Path) -> Path | None:
    """A Ametista que liga com o Windows hoje, se estiver em outra pasta e tiver dados."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            comando, _ = winreg.QueryValueEx(k, "Ametista")
    except OSError:
        return None
    anterior = _pasta_do_comando(str(comando))
    if not anterior or not anterior.exists():
        return None
    try:
        if anterior.resolve() == pasta.resolve():
            return None
    except OSError:
        return None
    if (anterior / ".env").exists() or (anterior / "dados").exists():
        return anterior
    return None


def _copiar_o_que_falta(origem: Path, destino: Path) -> int:
    """Copia só os arquivos que ainda não existem no destino (nunca apaga nem substitui nada)."""
    n = 0
    if not origem.is_dir():
        return 0
    for raiz, pastas, arquivos in os.walk(origem):
        pastas[:] = [p for p in pastas if p not in ("__pycache__", "node_modules")]
        alvo = destino / Path(raiz).relative_to(origem)
        for a in arquivos:
            if not (alvo / a).exists():
                alvo.mkdir(parents=True, exist_ok=True)
                shutil.copy2(Path(raiz) / a, alvo / a)
                n += 1
    return n


def trazer_dados(de: Path, para: Path) -> int:
    """Memória, vozes, modelos e configurações de outra instalação (sem apagar nada do destino)."""
    n = sum(_copiar_o_que_falta(de / d, para / d) for d in DADOS_USUARIO)
    if (de / ".env").exists() and not (para / ".env").exists():
        shutil.copy2(de / ".env", para / ".env")
        n += 1
    return n


def mover(origem: Path, destino: Path) -> None:
    """Copia a Ametista para `destino`. O código novo substitui o que houver lá; os dados só completam."""
    destino.mkdir(parents=True, exist_ok=True)
    for item in origem.iterdir():
        if item.name in NAO_COPIAR or item.name == ".env":
            continue
        if item.is_dir():
            shutil.copytree(item, destino / item.name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "node_modules", ".wrangler"))
        else:
            shutil.copy2(item, destino / item.name)
    trazer_dados(origem, destino)


def _ametista_aberta(porta: int = 8765) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def perguntar(texto: str) -> bool:
    if os.environ.get(SEM_PERGUNTAR):
        print(texto + "S")
        return True
    try:
        return input(texto).strip().lower() in ("s", "sim", "y", "yes")
    except EOFError:
        return False


def _esperar_fechar() -> None:
    if _ametista_aberta():
        print(" A Ametista está aberta. Feche pelo ícone perto do relógio (botão direito > Sair).")
        try:
            input(" Depois aperte Enter para continuar...")
        except EOFError:
            pass


def main(argv: list[str]) -> int:
    pasta = Path(argv[1] if len(argv) > 1 else os.getcwd()).resolve()
    arquivo_destino = Path(argv[2]) if len(argv) > 2 else None

    motivos = problemas(pasta)
    if motivos:
        destino = destino_sugerido()
        print("\n Esta pasta não é um bom lugar para a Ametista:")
        for m in motivos:
            print(f"   - {m}")
        print(f"\n Posso copiar a Ametista para {destino} e continuar a instalação de lá.")
        if _eh_ametista(destino):
            print(f" Já existe uma Ametista em {destino}: ela é atualizada, e a memória e as vozes dela ficam.")
        if not perguntar(f" Copiar para {destino}? [S/N] "):
            print("\n Tudo bem. Mova a pasta para um lugar como C:\\Ametista e rode o instalar.bat de novo.")
            return 1
        _esperar_fechar()
        try:
            mover(pasta, destino)
        except OSError as e:
            print(f"\n Não consegui copiar para {destino}: {e}")
            print(" Mova a pasta para um lugar como C:\\Ametista e rode o instalar.bat de novo.")
            return 1
        if arquivo_destino:
            arquivo_destino.write_text(str(destino), encoding="utf-8")
        print(f" Copiado. Continuando a instalação em {destino}...\n")
        return 10

    anterior = instalacao_anterior(pasta)
    if anterior:
        print(f"\n Achei outra Ametista instalada em {anterior}.")
        if perguntar(" Trazer a memória, as vozes cadastradas e as configurações de lá? [S/N] "):
            _esperar_fechar()
            n = trazer_dados(anterior, pasta)
            print(f" Pronto: {n} arquivos trazidos. A pasta antiga não é mais usada e pode ser apagada depois.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
