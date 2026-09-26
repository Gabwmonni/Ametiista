"""O modelo 3D dela (modelo/ametista.blend → web/ametista.glb): o que o rosto.js precisa para desenhar e animar."""
import json
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
MATERIAIS = ["corpo", "rosto", "olho", "iris", "cilios", "boca_dentro", "blush", "brilho"]
OSSOS = ["raiz", "peito", "pescoco", "cabeca"]


def _mundo(j, i):
    pai = {c: k for k, n in enumerate(j["nodes"]) for c in n.get("children", [])}
    m = compactar_glb.trs(j["nodes"][i])
    while i in pai:
        i = pai[i]
        m = compactar_glb.trs(j["nodes"][i]) @ m
    return m


def test_o_pc_e_o_celular_usam_o_mesmo_modelo_e_o_editavel_esta_junto():
    assert GLB.read_bytes() == (RAIZ / "celular" / "public" / "ametista.glb").read_bytes()
    assert (RAIZ / "modelo" / "ametista.blend").stat().st_size > 100_000, "o arquivo para editar no Blender"
    for f in ("construir_ametista.py", "renderizar_rosto.py", "preparar_rosto.py", "fonte/ametista_3d.glb",
              "fonte/cor_corpo.webp", "rosto/frente.png", "rosto/marcas.json", "rosto/atlas.png", "rosto/atlas.json"):
        assert (RAIZ / "modelo" / f).exists(), f
    assert GLB.stat().st_size < 1_400_000, f"modelo pesado: {GLB.stat().st_size // 1024} KB"


def test_contrato_ossos_materiais_texturas_e_expressoes():
    j, b = compactar_glb.ler(GLB)
    juntas = {j["nodes"][k]["name"] for s in j["skins"] for k in s["joints"]}
    assert set(OSSOS) <= juntas, f"ossos faltando: {set(OSSOS) - juntas}"
    for s in j["skins"]:
        for k in s["joints"]:
            assert "rotation" not in j["nodes"][k], "ossos em pé, sem giro de repouso (o app gira em volta do pivô)"
    nomes_mat = {m["name"] for m in j["materials"]}
    faltam = [m for m in MATERIAIS if m not in nomes_mat]
    assert not faltam, f"materiais faltando: {faltam}"
    assert len(j["images"]) == 2 and all(im["mimeType"] == "image/webp" for im in j["images"]), \
        "duas texturas em WebP: a cor do corpo e o atlas do rosto"
    chaves = {n for m in j["meshes"] for n in m.get("extras", {}).get("targetNames", [])}
    faltam = [e for e in EXPRESSOES if e not in chaves]
    assert not faltam, f"shape keys faltando: {faltam}"
    assert "KHR_mesh_quantization" in j.get("extensionsUsed", []), "o modelo do app vai compactado"
    raiz = next(n for n in j["nodes"] if n.get("extras", {}).get("quadro_tudo"))
    assert len(raiz["extras"]["quadro_tudo"]) == 3 and len(raiz["extras"]["quadro_rosto"]) == 3


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
    assert 15_000 < tri < 45_000, f"{tri} triângulos"


def test_parada_cada_peca_fica_no_lugar_e_os_pesos_somam_um():
    """Com os ossos em repouso, a máscara do rosto fica em cima do rosto do modelo (na frente dele), e os pesos de
    cada vértice somam 1."""
    j, b = compactar_glb.ler(GLB)
    sk = j["skins"][0]
    n = len(sk["joints"])
    ibm = compactar_glb.acessor(j, b, sk["inverseBindMatrices"]).reshape(n, 4, 4).transpose(0, 2, 1)
    M = np.array([_mundo(j, k) @ ibm[i] for i, k in enumerate(sk["joints"])])
    lugar = {}
    for no in j["nodes"]:
        if "mesh" not in no:
            continue
        p = j["meshes"][no["mesh"]]["primitives"][0]
        pos = compactar_glb.acessor(j, b, p["attributes"]["POSITION"])
        jt = compactar_glb.acessor(j, b, p["attributes"]["JOINTS_0"]).astype(int)
        w = compactar_glb.acessor(j, b, p["attributes"]["WEIGHTS_0"])
        assert np.allclose(w.sum(1), 1, atol=0.01), no["name"]
        ph = np.hstack([pos, np.ones((len(pos), 1))])
        V = sum(w[:, k:k + 1] * np.einsum("nij,nj->ni", M[jt[:, k]], ph) for k in range(4))[:, :3]
        lugar[no["name"]] = V
    corpo, rosto = lugar["Corpo"], lugar["Rosto"]
    assert 0.9 < corpo[:, 1].max() - corpo[:, 1].min() < 1.05, "o busto tem ~1 unidade de altura"
    # a máscara cobre o rosto: entre o queixo e a testa, na frente (z do glTF para a câmera)
    assert 0.55 < rosto[:, 1].min() and rosto[:, 1].max() < 0.8
    assert rosto[:, 2].max() > 0.12, "a máscara está na frente do rosto"
    for olho in ("Olho_D", "Olho_E"):
        o = lugar[olho]
        assert 0.68 < o[:, 1].mean() < 0.76 and o[:, 2].mean() > 0.08, olho


def test_nomes_do_contrato_iguais_no_rosto_js_e_no_compactador():
    """Os materiais com transparência são os mesmos para quem desenha e para quem compacta."""
    js = (RAIZ / "web" / "rosto.js").read_text(encoding="utf-8")
    bloco = re.search(r"function tipoMaterial\(nome\) \{(.*?)\n  \}", js, re.S).group(1)
    no_js = set(re.findall(r'e\("(\w+)"\)', bloco))
    assert set(compactar_glb.TRANSPARENTES) <= no_js, set(compactar_glb.TRANSPARENTES) - no_js
    assert "rosto" in no_js, "a máscara do rosto"


def test_marcacoes_do_rosto_coerentes():
    m = json.loads((RAIZ / "modelo" / "rosto" / "marcas.json").read_text(encoding="utf-8"))
    for olho in ("olho_d", "olho_e"):
        o = m[olho]
        assert o["cima"][0] == o["baixo"][0] and o["cima"][-1] == o["baixo"][-1], "os cantos do olho se encontram"
        cx, cy, r = o["iris"]
        assert min(p[0] for p in o["cima"]) < cx < max(p[0] for p in o["cima"])
    b = m["boca"]
    assert b["fresta_cima"][0] == b["fresta_baixo"][0] and b["fresta_cima"][-1] == b["fresta_baixo"][-1]
