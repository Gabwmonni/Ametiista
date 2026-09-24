"""App do celular: arquivos em sincronia e leveza."""
import gzip
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def test_rosto_do_celular_e_do_pc_sao_o_mesmo_arquivo():
    assert (RAIZ / "celular" / "public" / "rosto.js").read_bytes() == (RAIZ / "web" / "rosto.js").read_bytes(), \
        "copie web/rosto.js para celular/public/rosto.js"


def test_service_worker_tem_a_impressao_digital_dos_arquivos_atuais():
    """Se falhar: python -c "from ametista import publicar_celular as p; p.atualizar_sw()" """
    from ametista import publicar_celular

    sw = (RAIZ / "celular" / "public" / "sw.js").read_text(encoding="utf-8")
    assert f'const CACHE = "ametista-casca-{publicar_celular.impressao_casca()}";' in sw
    casca = re.search(r"const CASCA = \[(.*?)\];", sw).group(1)
    assert [c.strip(' "') for c in casca.split(",")] == ["/"] + [f"/{n}" for n in publicar_celular.CASCA[1:]]


def test_app_leve():
    """O que o celular baixa na primeira vez (compactado, como o Cloudflare entrega) continua pequeno."""
    publico = RAIZ / "celular" / "public"
    total = sum(len(gzip.compress(p.read_bytes(), 9)) for p in publico.iterdir() if p.name != "icone-512.png")
    assert total < 55_000, f"o app do celular cresceu para {total} bytes (compactado)"
    html = (publico / "index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis" not in html and "http" not in re.sub(r"<!--.*?-->", "", html, flags=re.S)
