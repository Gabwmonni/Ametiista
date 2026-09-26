"""App do celular: arquivos em sincronia e leveza."""
import gzip
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def test_rosto_do_celular_e_do_pc_sao_o_mesmo_arquivo():
    for nome in ("rosto.js", "rosto2d.js", "ametista.glb", "ametista-retrato.webp"):
        assert (RAIZ / "celular" / "public" / nome).read_bytes() == (RAIZ / "web" / nome).read_bytes(), \
            f"copie web/{nome} para celular/public/{nome}"


def test_service_worker_tem_a_impressao_digital_dos_arquivos_atuais():
    """Se falhar: python -c "from ametista import publicar_celular as p; p.atualizar_sw()" """
    from ametista import publicar_celular

    sw = (RAIZ / "celular" / "public" / "sw.js").read_text(encoding="utf-8")
    assert f'const CACHE = "ametista-casca-{publicar_celular.impressao_casca()}";' in sw
    casca = re.search(r"const CASCA = \[(.*?)\];", sw).group(1)
    assert [c.strip(' "') for c in casca.split(",")] == ["/"] + [f"/{n}" for n in publicar_celular.CASCA[1:]]


def test_app_leve():
    """O que o celular baixa na primeira vez (compactado, como o Cloudflare entrega) não passa do combinado: o
    código do app, o modelo 3D dela (o busto com as duas texturas; é a maior parte) e o ícone. Tudo fica guardado
    no celular depois da primeira vez. O rosto de reserva (rosto2d.js e a ilustração) só é baixado por aparelhos
    sem WebGL."""
    from ametista import publicar_celular

    publico = RAIZ / "celular" / "public"
    tamanho = {p.name: len(gzip.compress(p.read_bytes(), 9)) for p in publico.iterdir()}
    casca = [n for n in publicar_celular.CASCA] + ["sw.js"]
    codigo = sum(tamanho[n] for n in casca if not n.endswith((".png", ".webp", ".jpg", ".glb")))
    assert codigo < 30_000, f"o código do app do celular cresceu para {codigo} bytes (compactado)"
    assert tamanho["ametista.glb"] < 800_000, f"o modelo 3D dela ficou pesado: {tamanho['ametista.glb']} bytes"
    assert tamanho["ametista-retrato.webp"] < 40_000, "a ilustração de reserva ficou pesada"
    primeira_vez = sum(tamanho[n] for n in casca)
    assert primeira_vez < 860_000, f"a primeira abertura do app cresceu para {primeira_vez} bytes (compactado)"
    html = (publico / "index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis" not in html and "http" not in re.sub(r"<!--.*?-->", "", html, flags=re.S)
