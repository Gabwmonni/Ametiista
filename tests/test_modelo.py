"""O modelo 3D dela (modelo/ametista.blend → web/ametista.glb): o que o rosto.js precisa para desenhar e animar."""
import re
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "modelo"))
import compactar_glb  # noqa: E402

GLB = RAIZ / "web" / "ametista.glb"
EXPRESSOES = ["piscar_direito", "piscar_esquerdo", "olhos_felizes", "arregalar", "olhar_esquerda", "olhar_direita",
              "olhar_cima", "olhar_baixo", "boca_a", "boca_e", "boca_i", "boca_o", "boca_u", "sorriso", "triste",
              "bravo", "sobrancelhas_cima", "sobrancelhas_bravas", "sobrancelhas_tristes", "sobrancelha_pensativa"]
MATERIAIS = ["pele", "cabelo", "roupa", "metal", "cristal", "vidro", "olho_branco", "iris", "pupila", "brilho_olho",
             "cilios", "sobrancelha", "boca_dentro", "dentes", "lingua", "linha_boca", "blush"]


def test_o_pc_e_o_celular_usam_o_mesmo_modelo_e_o_editavel_esta_junto():
    assert GLB.read_bytes() == (RAIZ / "celular" / "public" / "ametista.glb").read_bytes()
    assert (RAIZ / "modelo" / "ametista.blend").stat().st_size > 100_000, "o arquivo para editar no Blender"
    assert (RAIZ / "modelo" / "construir_ametista.py").exists()
    assert GLB.stat().st_size < 450_000, f"modelo pesado: {GLB.stat().st_size // 1024} KB"


def test_contrato_cabeca_materiais_e_expressoes():
    j, b = compactar_glb.ler(GLB)
    nos = {n.get("name"): n for n in j["nodes"]}
    assert "Cabeca" in nos and nos["Cabeca"].get("children"), "o nó Cabeca (o pescoço) com o rosto dentro"
    nomes_mat = {m["name"] for m in j["materials"]}
    faltam = [m for m in MATERIAIS if m not in nomes_mat]
    assert not faltam, f"materiais faltando: {faltam}"
    chaves = {n for m in j["meshes"] for n in m.get("extras", {}).get("targetNames", [])}
    faltam = [e for e in EXPRESSOES if e not in chaves]
    assert not faltam, f"shape keys faltando: {faltam}"
    assert "KHR_mesh_quantization" in j.get("extensionsUsed", []), "o modelo do app vai compactado"


def test_cada_expressao_mexe_alguma_coisa_e_a_malha_tem_um_tamanho_bom():
    j, b = compactar_glb.ler(GLB)
    tri = 0
    for m in j["meshes"]:
        nomes = m.get("extras", {}).get("targetNames", [])
        moveu = {n: 0.0 for n in nomes}
        for p in m["primitives"]:
            tri += j["accessors"][p["indices"]]["count"] // 3
            for n, t in zip(nomes, p.get("targets", [])):
                d = compactar_glb.acessor(j, b, t["POSITION"])
                moveu[n] = max(moveu[n], float(np.abs(d).max()))
        parados = [n for n, v in moveu.items() if v <= 0]
        assert not parados, f"{m['name']}: shape keys que não mexem nada: {parados}"
    assert 10_000 < tri < 40_000, f"{tri} triângulos"


def test_nomes_do_contrato_iguais_no_rosto_js_e_no_compactador():
    """Os materiais "desenhados" por cima do rosto são os mesmos para quem desenha e para quem compacta."""
    js = (RAIZ / "web" / "rosto.js").read_text(encoding="utf-8")
    bloco = re.search(r"const PLANOS = \{(.*?)\};", js, re.S).group(1)
    no_js = set(re.findall(r"(\w+): \[", bloco))
    assert no_js == set(compactar_glb.PLANOS), no_js ^ set(compactar_glb.PLANOS)
