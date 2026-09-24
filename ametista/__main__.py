"""python -m ametista               -> app de desktop (sobreposição + bandeja)
python -m ametista --navegador   -> só servidor + ouvido, abre no navegador (para testar)
python -m ametista --diagnostico -> confere tudo e mostra um relatório
python -m ametista --autoinicio on|off
python -m ametista --abrir       -> abre a Ametista sem console e espera ela responder (usado pelo instalar.bat)
"""
import argparse
import sys

p = argparse.ArgumentParser(prog="ametista")
p.add_argument("--navegador", action="store_true", help="roda sem a janela de sobreposição")
p.add_argument("--diagnostico", action="store_true", help="confere cada peça e mostra um relatório")
p.add_argument("--autoinicio", choices=["on", "off"], help="liga/desliga iniciar com o Windows")
p.add_argument("--sem-ouvido", action="store_true", help="não usa o microfone")
p.add_argument("--versao", action="store_true")
p.add_argument("--abrir", action="store_true", help="abre a Ametista (sem console) e espera ela responder")
args = p.parse_args()

from . import __version__, config  # noqa: E402

if args.versao:
    print(f"Ametista {__version__}")
    sys.exit(0)

if args.sem_ouvido:
    config.OUVIDO_LIGADO = False

if args.autoinicio:
    from . import autoinicio

    autoinicio.definir(args.autoinicio == "on")
    sys.exit(0)


def _abrir() -> int:
    """Abre a Ametista desta pasta, solta do console (o instalar.bat pode fechar sem levar ela junto), e espera
    a versão nova responder."""
    import subprocess
    import time
    from pathlib import Path

    import httpx

    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    comeco = time.time()
    flags = 0x00000008 | 0x00000200 if sys.platform == "win32" else 0   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen([str(pyw if pyw.exists() else exe), str(config.RAIZ / "ametista.pyw")],
                            cwd=str(config.RAIZ), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, close_fds=True, creationflags=flags,
                            start_new_session=sys.platform != "win32")
    while time.time() < comeco + 120:
        respondeu = None
        try:
            respondeu = httpx.get(f"http://127.0.0.1:{config.PORTA}/api/saude", timeout=2).json()
            if respondeu.get("inicio", 0) >= comeco - 1:
                print(f" A Ametista {respondeu.get('versao')} abriu: o ícone dela fica perto do relógio.")
                return 0
        except Exception:
            pass
        if proc.poll() is not None:                    # a nova fechou sem abrir
            if respondeu is not None:
                print(" Outra Ametista continua aberta, então a nova não abriu. Feche a antiga pelo ícone perto do "
                      "relógio (botão direito > Sair) e dê dois cliques em iniciar.bat.")
            else:
                print(" A Ametista não conseguiu abrir. Dê dois cliques em diagnostico.bat para ver o motivo.")
            return 1
        time.sleep(1)
    print(" A Ametista está demorando para abrir. Se ela não aparecer, dê dois cliques em iniciar.bat.")
    return 1


if args.abrir:
    sys.exit(_abrir())


def _dpi() -> None:
    """Coordenadas do mouse e dos prints em pixels reais (telas com escala). O Qt já faz isso sozinho."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass


if args.diagnostico:
    from . import config, diagnostico, semantica

    if config.BUSCA_SEMANTICA:
        print("Carregando o modelo de busca por significado…")
        semantica.baixar()
    diagnostico.FORA_DO_APP = True
    itens = diagnostico.executar()
    print(diagnostico.relatorio(itens))
    print("\n" + diagnostico.resumir(itens))
    try:
        config.DADOS.mkdir(parents=True, exist_ok=True)
        (config.DADOS / "diagnostico.txt").write_text(diagnostico.relatorio(itens), encoding="utf-8")
    except OSError:
        pass
    sys.exit(0)

if args.navegador:
    _dpi()
    config.migrar_env()
    import threading
    import webbrowser

    import uvicorn

    if config.OUVIDO_LIGADO:
        from .ouvido import Ouvido

        Ouvido().iniciar()
    from . import nuvem

    nuvem.instancia().iniciar()
    threading.Timer(2, lambda: webbrowser.open(f"http://127.0.0.1:{config.PORTA}")).start()
    uvicorn.run("ametista.servidor:app", host="127.0.0.1", port=config.PORTA, log_level="warning")
else:
    from .desktop import main

    sys.exit(main())
