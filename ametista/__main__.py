"""python -m ametista               -> app de desktop (sobreposição + bandeja)
python -m ametista --navegador   -> só servidor + ouvido, abre no navegador (para testar)
python -m ametista --diagnostico -> confere tudo e mostra um relatório
python -m ametista --autoinicio on|off
"""
import argparse
import sys

p = argparse.ArgumentParser(prog="ametista")
p.add_argument("--navegador", action="store_true", help="roda sem a janela de sobreposição")
p.add_argument("--diagnostico", action="store_true", help="confere cada peça e mostra um relatório")
p.add_argument("--autoinicio", choices=["on", "off"], help="liga/desliga iniciar com o Windows")
p.add_argument("--sem-ouvido", action="store_true", help="não usa o microfone")
p.add_argument("--versao", action="store_true")
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
