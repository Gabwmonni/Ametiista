# Inicia a Ametista sem janela de console (usado pelo "Iniciar com o Windows").
import os
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)

# pythonw não tem console: manda as mensagens para um arquivo de log
os.makedirs(os.path.join(RAIZ, "dados"), exist_ok=True)
log = open(os.path.join(RAIZ, "dados", "ametista.log"), "a", encoding="utf-8", buffering=1)
sys.stdout = sys.stderr = log

from ametista.desktop import main  # noqa: E402

sys.exit(main())
