"""Deixa o .glb exportado pelo Blender bem mais leve para o app, sem mudar nada do que aparece.

- posições e shape keys em 16 bits (KHR_mesh_quantization, o jeito padrão do glTF para isso);
- coordenadas da textura em 16 bits, ossos e pesos em 8 bits, normais (se o material usar luz) em 8 bits;
- a pintura (a textura) vai como está (o Blender já exporta em WebP);
- materiais com transparência (cílios, íris, brilhos, rubor) marcados como tal.

Uso: python modelo/compactar_glb.py web/ametista.glb  [saída.glb]
(o construir_ametista.py já faz isso sozinho; use à mão depois de exportar do Blender, se quiser.)
"""
import json
import struct
import sys

import numpy as np

COMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
TIPO = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
MAXN = {5120: 127, 5121: 255, 5122: 32767, 5123: 65535}
# materiais com partes transparentes (o mesmo contrato do rosto.js)
TRANSPARENTES = ("cilios", "iris", "brilho", "blush")


def ler(caminho):
    d = open(caminho, "rb").read()
    assert d[:4] == b"glTF", "não é um .glb"
    off, j, b = 12, None, b""
    while off + 8 <= len(d):
        n, t = struct.unpack("<II", d[off:off + 8])
        if t == 0x4E4F534A:
            j = json.loads(d[off + 8:off + 8 + n])
        elif t == 0x004E4942:
            b = d[off + 8:off + 8 + n]
        off += 8 + n
    return j, b


def acessor(j, b, i):
    a = j["accessors"][i]
    nc, T = COMP[a["type"]], TIPO[a["componentType"]]
    out = np.zeros((a["count"], nc), np.float64)
    if "bufferView" in a:
        bv = j["bufferViews"][a["bufferView"]]
        tam = nc * np.dtype(T).itemsize
        passo = bv.get("byteStride", tam)
        ini = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        if passo == tam:
            out[:] = np.frombuffer(b, T, a["count"] * nc, ini).reshape(-1, nc)
        else:
            linhas = np.frombuffer(b, np.uint8, (a["count"] - 1) * passo + tam, ini)
            for k in range(a["count"]):
                out[k] = np.frombuffer(linhas[k * passo:k * passo + tam].tobytes(), T)
    if "sparse" in a:
        s = a["sparse"]
        bi, bvv = j["bufferViews"][s["indices"]["bufferView"]], j["bufferViews"][s["values"]["bufferView"]]
        idx = np.frombuffer(b, TIPO[s["indices"]["componentType"]], s["count"],
                            bi.get("byteOffset", 0) + s["indices"].get("byteOffset", 0))
        val = np.frombuffer(b, T, s["count"] * nc, bvv.get("byteOffset", 0) + s["values"].get("byteOffset", 0))
        out[idx.astype(int)] = val.reshape(-1, nc)
    if a.get("normalized"):
        out /= MAXN[a["componentType"]]
    return out


def bytes_da_view(j, b, i):
    bv = j["bufferViews"][i]
    ini = bv.get("byteOffset", 0)
    return b[ini:ini + bv["byteLength"]]


def trs(n):
    if "matrix" in n:
        return np.array(n["matrix"], float).reshape(4, 4).T
    t = np.array(n.get("translation", [0, 0, 0]), float)
    x, y, z, w = n.get("rotation", [0, 0, 0, 1])
    s = np.array(n.get("scale", [1, 1, 1]), float)
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = R * s
    m[:3, 3] = t
    return m


class Escritor:
    def __init__(self):
        self.bin, self.views, self.accs = bytearray(), [], []

    def view(self, dados, alvo=None, passo=None):
        while len(self.bin) % 4:
            self.bin += b"\0"
        v = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(dados)}
        if alvo:
            v["target"] = alvo
        if passo:
            v["byteStride"] = passo
        self.bin += dados
        self.views.append(v)
        return len(self.views) - 1

    def acc(self, **a):
        self.accs.append(a)
        return len(self.accs) - 1

    def atributo(self, arr, tipo_np, comp, normalizado, tipo_gl, minmax=False):
        """Vértices com cada elemento alinhado a 4 bytes (a regra do glTF)."""
        n, nc = arr.shape
        tam = nc * np.dtype(tipo_np).itemsize
        passo = (tam + 3) // 4 * 4
        buf = np.zeros((n, passo), np.uint8)
        buf[:, :tam] = np.ascontiguousarray(arr.astype(tipo_np)).view(np.uint8).reshape(n, tam)
        v = self.view(buf.tobytes(), 34962, passo if passo != tam else None)
        extra = {"min": arr.min(0).tolist(), "max": arr.max(0).tolist()} if minmax else {}
        return self.acc(bufferView=v, componentType=tipo_gl, count=n, type=comp, normalized=normalizado, **extra) \
            if normalizado else self.acc(bufferView=v, componentType=tipo_gl, count=n, type=comp, **extra)


def pesos_8bits(w):
    """Pesos dos ossos em 8 bits, somando exatamente 255 em cada vértice."""
    w = np.clip(w, 0, None)
    w = w / np.maximum(w.sum(1, keepdims=True), 1e-12)
    q = np.floor(w * 255)
    falta = (255 - q.sum(1)).astype(int)
    resto = w * 255 - q
    ordem = np.argsort(-resto, axis=1)
    for k in range(w.shape[1]):
        q[np.arange(len(q)), ordem[:, k]] += (falta > k)
    return q


def compactar(entrada, saida=None):
    j, b = ler(entrada)
    if "KHR_mesh_quantization" in j.get("extensionsUsed", []):
        return entrada
    E = Escritor()
    nos = j.get("nodes", [])
    pele_da_malha = {n["mesh"]: n["skin"] for n in nos if "mesh" in n and "skin" in n}
    lidas = {}
    for mi, mesh in enumerate(j.get("meshes", [])):
        prims = []
        for p in mesh["primitives"]:
            pos = acessor(j, b, p["attributes"]["POSITION"])
            alvos = [acessor(j, b, t["POSITION"]) if "POSITION" in t else np.zeros_like(pos)
                     for t in p.get("targets", [])]
            prims.append((p, pos, alvos))
        lidas[mi] = prims
    # uma caixa por malha (todas as partes e todas as expressões cabem nela); as malhas com ossos dividem a
    # mesma caixa (a do esqueleto), porque o "desfazer" da quantização vai nas matrizes dos ossos
    def caixa(meshes):
        pts = np.vstack([pos + d for mi in meshes for _, pos, alvos in lidas[mi]
                         for d in [np.zeros_like(pos)] + alvos])
        lo, hi = pts.min(0), pts.max(0)
        return (lo + hi) / 2, np.maximum((hi - lo) / 2, 1e-6) * 1.0001
    deq = {}
    for sk in set(pele_da_malha.values()):
        c_h = caixa([mi for mi, s in pele_da_malha.items() if s == sk])
        for mi, s in pele_da_malha.items():
            if s == sk:
                deq[mi] = c_h
    for mi in lidas:
        if mi not in deq:
            deq[mi] = caixa([mi])
    novas_meshes = []
    for mi, mesh in enumerate(j.get("meshes", [])):
        c, h = deq[mi]
        novos = []
        for p, pos, alvos in lidas[mi]:
            q = np.clip(np.round((pos - c) / h * 32767), -32767, 32767)
            at = {"POSITION": E.atributo(q, np.int16, "VEC3", True, 5122)}
            E.accs[at["POSITION"]]["min"] = q.min(0).tolist()
            E.accs[at["POSITION"]]["max"] = q.max(0).tolist()
            pa = p["attributes"]
            mat = j.get("materials", [])[p["material"]] if "material" in p else {}
            sem_luz = "KHR_materials_unlit" in mat.get("extensions", {})
            if "NORMAL" in pa and not sem_luz:                  # sem luz, o app não usa normais
                nrm = acessor(j, b, pa["NORMAL"])
                nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
                at["NORMAL"] = E.atributo(np.round(nrm * 127), np.int8, "VEC3", True, 5120)
            if "TEXCOORD_0" in pa:
                uv = np.clip(acessor(j, b, pa["TEXCOORD_0"]), 0, 1)
                at["TEXCOORD_0"] = E.atributo(np.round(uv * 65535), np.uint16, "VEC2", True, 5123)
            if "COLOR_0" in pa:
                cor = acessor(j, b, pa["COLOR_0"])
                if cor.shape[1] == 3:
                    cor = np.hstack([cor, np.ones((len(cor), 1))])
                at["COLOR_0"] = E.atributo(np.round(np.clip(cor, 0, 1) * 255), np.uint8, "VEC4", True, 5121)
            if "JOINTS_0" in pa and "WEIGHTS_0" in pa:
                jt = acessor(j, b, pa["JOINTS_0"])
                w = acessor(j, b, pa["WEIGHTS_0"])
                w[w < 0.5 / 255] = 0
                jt[w == 0] = 0
                at["JOINTS_0"] = E.atributo(jt, np.uint8, "VEC4", False, 5121)
                at["WEIGHTS_0"] = E.atributo(pesos_8bits(w), np.uint8, "VEC4", True, 5121)
            novo = {"attributes": at, "mode": p.get("mode", 4)}
            if "material" in p:
                novo["material"] = p["material"]
            if "indices" in p:
                idx = acessor(j, b, p["indices"]).astype(np.uint32).ravel()
                tipo = (np.uint16, 5123) if idx.max() < 65535 else (np.uint32, 5125)
                v = E.view(idx.astype(tipo[0]).tobytes(), 34963)
                novo["indices"] = E.acc(bufferView=v, componentType=tipo[1], count=len(idx), type="SCALAR")
            ts = []
            for d in alvos:
                qd = np.clip(np.round(d / h * 32767), -32767, 32767).astype(np.int16)
                mexe = np.nonzero(np.any(qd != 0, axis=1))[0]
                if len(mexe) == 0:
                    ts.append({"POSITION": E.acc(componentType=5122, count=len(pos), type="VEC3", normalized=True,
                                                 min=[0, 0, 0], max=[0, 0, 0])})
                    continue
                vi = E.view(mexe.astype(np.uint16 if len(pos) < 65535 else np.uint32).tobytes())
                vv = E.view(qd[mexe].tobytes())
                ts.append({"POSITION": E.acc(
                    componentType=5122, count=len(pos), type="VEC3", normalized=True,
                    min=qd.min(0).astype(float).tolist(), max=qd.max(0).astype(float).tolist(),
                    sparse={"count": int(len(mexe)),
                            "indices": {"bufferView": vi, "componentType": 5123 if len(pos) < 65535 else 5125},
                            "values": {"bufferView": vv}})})
            if ts:
                novo["targets"] = ts
            novos.append(novo)
        m = {k: v for k, v in mesh.items() if k not in ("primitives", "weights")}
        m["primitives"] = novos
        novas_meshes.append(m)
    # desfazer a quantização: nas malhas soltas, a matriz do nó; nas com ossos, as matrizes dos ossos
    def matriz_deq(mi):
        c, h = deq[mi]
        D = np.eye(4)
        D[:3, :3] = np.diag(h)
        D[:3, 3] = c
        return D
    for n in nos:
        if "mesh" not in n or "skin" in n:
            continue
        M = trs(n) @ matriz_deq(n["mesh"])
        for k in ("translation", "rotation", "scale"):
            n.pop(k, None)
        n["matrix"] = M.T.ravel().tolist()
    for si, sk in enumerate(j.get("skins", [])):
        mi = next(m for m, s in pele_da_malha.items() if s == si)
        D = matriz_deq(mi)
        n = len(sk["joints"])
        ibm = acessor(j, b, sk["inverseBindMatrices"]).reshape(n, 4, 4).transpose(0, 2, 1) \
            if "inverseBindMatrices" in sk else np.tile(np.eye(4), (n, 1, 1))
        novo = np.array([m @ D for m in ibm]).transpose(0, 2, 1).reshape(n, 16).astype(np.float32)
        sk["inverseBindMatrices"] = E.acc(bufferView=E.view(novo.tobytes()), componentType=5126, count=n,
                                          type="MAT4")
    for im in j.get("images", []):
        if "bufferView" in im:
            im["bufferView"] = E.view(bytes_da_view(j, b, im["bufferView"]))
    for m in j.get("materials", []):
        nome = m.get("name", "").lower()
        if any(nome == k or nome.startswith(k + "_") for k in TRANSPARENTES):
            m["alphaMode"] = "BLEND"
    j["meshes"] = novas_meshes
    j["accessors"], j["bufferViews"] = E.accs, E.views
    j["buffers"] = [{"byteLength": len(E.bin)}]
    for k in ("extensionsUsed", "extensionsRequired"):
        j[k] = sorted(set(j.get(k, [])) | {"KHR_mesh_quantization"})
    texto = json.dumps(j, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    texto += b" " * ((4 - len(texto) % 4) % 4)
    binario = bytes(E.bin) + b"\0" * ((4 - len(E.bin) % 4) % 4)
    total = 12 + 8 + len(texto) + 8 + len(binario)
    saida = saida or entrada
    with open(saida, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(texto), 0x4E4F534A) + texto)
        f.write(struct.pack("<II", len(binario), 0x004E4942) + binario)
    return saida


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    import os
    antes = os.path.getsize(sys.argv[1])
    out = compactar(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(f"{sys.argv[1]}: {antes // 1024} KB -> {out}: {os.path.getsize(out) // 1024} KB")
