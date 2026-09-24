"""Cada módulo precisa importar sozinho, em qualquer ordem (pega importações circulares que travariam o início)."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
MODULOS = sorted(p.stem for p in (RAIZ / "ametista").glob("*.py") if p.stem not in ("__main__", "__init__"))


@pytest.mark.parametrize("modulo", MODULOS)
def test_modulo_importa_primeiro(modulo):
    if modulo == "desktop" and importlib.util.find_spec("PySide6") is None:
        pytest.skip("PySide6 não instalado neste ambiente")
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    r = subprocess.run([sys.executable, "-c", f"import ametista.{modulo}"], cwd=RAIZ, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
