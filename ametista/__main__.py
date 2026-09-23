"""python -m ametista              -> app de desktop (sobreposição + bandeja)
python -m ametista --navegador  -> só servidor + ouvido, abre no navegador (para testar)
python -m ametista --autoinicio on|off
"""
import argparse
import sys

p = argparse.ArgumentParser(prog="ametista")
p.add_argument("--navegador", action="store_true", help="roda sem a janela de sobreposição")
p.add_argument("--autoinicio", choices=["on", "off"], help="liga/desliga iniciar com o Windows")
p.add_argument("--sem-ouvido", action="store_true", help="não usa o microfone")
args = p.parse_args()

from . import config  # noqa: E402

if args.sem_ouvido:
    config.OUVIDO_LIGADO = False

if args.autoinicio:
    from . import autoinicio

    autoinicio.definir(args.autoinicio == "on")
    sys.exit(0)

if args.navegador:
    import threading
    import webbrowser

    import uvicorn

    if config.OUVIDO_LIGADO:
        from .ouvido import Ouvido

        Ouvido().iniciar()
    threading.Timer(2, lambda: webbrowser.open(f"http://127.0.0.1:{config.PORTA}")).start()
    uvicorn.run("ametista.servidor:app", host="127.0.0.1", port=config.PORTA, log_level="warning")
else:
    from .desktop import main

    sys.exit(main())
