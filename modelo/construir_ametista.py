"""Constrói a Ametista em malha 3D, no Blender: tudo editável e animável.

Gera:
  modelo/ametista.blend       o arquivo para abrir e editar no Blender
  web/ametista.glb            o que o app usa (e celular/public/ametista.glb, a mesma coisa)

Uso (qualquer um dos dois):
  blender --background --python modelo/construir_ametista.py
  python modelo/construir_ametista.py          (com o módulo bpy instalado: pip install bpy)

Como o app entende o modelo (o "contrato", veja modelo/LEIA-ME-MODELO.md):
  - O objeto vazio "Cabeca" é o pescoço: o app gira a cabeça em volta dele (acenar, negar, inclinar, respirar).
  - Os NOMES dos materiais dizem como pintar: pele, cabelo, roupa, metal e cristal são sombreados como anime
    (luz e sombra chapadas, contorno); olho_*, iris*, boca_*, cilios... são "desenhados" por cima do rosto.
  - Os NOMES das shape keys são as expressões: piscar_direito, piscar_esquerdo, olhos_felizes, arregalar,
    olhar_esquerda/direita/cima/baixo, boca_a/e/i/o/u, sorriso, triste, bravo, sobrancelhas_cima/bravas/tristes,
    sobrancelha_pensativa.
Coordenadas: Blender (Z para cima, ela olha para -Y). A cabeça tem uns 2,3 de altura; o centro do crânio é a origem.
"""
import math
import os
import shutil
import sys

import bpy
import bmesh  # noqa: E402  (o bmesh só existe depois do bpy)
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
rng = np.random.default_rng(7)


# ====================================================================== utilidades
def pchip(xs, ys):
    """Interpolação suave que não passa do ponto (monótona por trechos): devolve f(x)."""
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    ordem = np.argsort(xs)
    xs, ys = xs[ordem], ys[ordem]
    h = np.diff(xs)
    d = np.diff(ys) / h
    m = np.zeros_like(ys)
    for k in range(1, len(xs) - 1):
        if d[k - 1] * d[k] > 0:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    m[0], m[-1] = d[0], d[-1]

    def f(x):
        x = np.clip(np.asarray(x, float), xs[0], xs[-1])
        k = np.clip(np.searchsorted(xs, x) - 1, 0, len(xs) - 2)
        t = (x - xs[k]) / h[k]
        h00, h10 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t
        h01, h11 = -2 * t**3 + 3 * t**2, t**3 - t**2
        return h00 * ys[k] + h10 * h[k] * m[k] + h01 * ys[k + 1] + h11 * h[k] * m[k + 1]
    return f


def catmull(pontos, n):
    """Curva suave passando pelos pontos (Catmull-Rom centrípeta), reamostrada com n pontos por comprimento."""
    P = np.asarray(pontos, float)
    P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    dens = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in np.linspace(0, 1, 24, endpoint=False):
            t2, t3 = t * t, t * t * t
            dens.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                               (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    dens.append(P[-2])
    dens = np.array(dens)
    seg = np.linalg.norm(np.diff(dens, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    alvo = np.linspace(0, s[-1], n)
    return np.stack([np.interp(alvo, s, dens[:, j]) for j in range(3)], axis=1)


def srgb(hexa):
    h = hexa.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def linear(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def normalizar(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-9)


def smooth(a, b, x):
    t = np.clip((np.asarray(x, float) - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# ====================================================================== cena, materiais, objetos
def limpar():
    bpy.ops.wm.read_factory_settings(use_empty=True)


MATS = {}


def material(nome, cor, alfa=1.0, cores_vertice=False, metal=0.0, rugosidade=0.55, **extras):
    """Material do Blender com a cor (sRGB) e, se pedido, as cores dos vértices ("Cor").
    Os extras (sombra, contorno...) vão para as propriedades do material e para o glb."""
    m = bpy.data.materials.new(nome)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*linear(srgb(cor)), 1.0)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rugosidade
    if alfa < 1.0 or cores_vertice == "alfa":
        b.inputs["Alpha"].default_value = alfa
        m.surface_render_method = "BLENDED"
    if cores_vertice:
        n = nt.nodes.new("ShaderNodeVertexColor")
        n.layer_name = "Cor"
        nt.links.new(n.outputs["Color"], b.inputs["Base Color"])
        if cores_vertice == "alfa":
            nt.links.new(n.outputs["Alpha"], b.inputs["Alpha"])
    m.diffuse_color = (*linear(srgb(cor)), alfa)
    for k, v in extras.items():
        m[k] = v
    MATS[nome] = m
    return m


def objeto(nome, V, F, mats, fmat=None, normais=None, cores=None, pai=None, facetado=False, para_fora=True):
    V = np.asarray(V, float)
    F = [list(map(int, f)) for f in F]
    me = bpy.data.meshes.new(nome)
    me.from_pydata(V.tolist(), [], F)
    me.validate(clean_customdata=False)
    if para_fora:            # todas as faces viradas para fora (o contorno de anime depende disso)
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
    for m in mats:
        me.materials.append(MATS[m])
    if fmat is not None:
        me.polygons.foreach_set("material_index", np.asarray(fmat, np.int32))
    me.polygons.foreach_set("use_smooth", np.full(len(me.polygons), not facetado))
    if cores is not None:
        cores = np.asarray(cores, float)
        if cores.shape[1] == 3:
            cores = np.hstack([cores, np.ones((len(cores), 1))])
        ca = me.color_attributes.new("Cor", "FLOAT_COLOR", "POINT")
        rgb = linear(cores[:, :3])
        ca.data.foreach_set("color", np.hstack([rgb, cores[:, 3:4]]).ravel())
        me.color_attributes.active_color = ca
    if normais is not None:
        me.normals_split_custom_set_from_vertices(normalizar(normais).tolist())
    me.update()
    ob = bpy.data.objects.new(nome, me)
    bpy.context.scene.collection.objects.link(ob)
    if pai is not None:
        ob.parent = pai
    return ob


def chaves(ob, alvos):
    """Shape keys: {nome: posições (N,3)}."""
    ob.shape_key_add(name="Basis", from_mix=False)
    for nome, V in alvos.items():
        k = ob.shape_key_add(name=nome, from_mix=False)
        k.data.foreach_set("co", np.asarray(V, float).ravel())
        k.value = 0.0


def vazio(nome, pos, pai=None):
    ob = bpy.data.objects.new(nome, None)
    ob.location = pos
    ob.empty_display_size = 0.2
    bpy.context.scene.collection.objects.link(ob)
    if pai is not None:
        ob.parent = pai
    return ob


class Juntar:
    """Junta várias partes (vértices, faces, material de cada face, cores) num objeto só."""

    def __init__(self, mats):
        self.mats = list(mats)
        self.V, self.F, self.M, self.C = [], [], [], []
        self.n = 0

    def add(self, V, F, mat, cor=None):
        V = np.asarray(V, float)
        self.V.append(V)
        self.F += [[i + self.n for i in f] for f in F]
        self.M += [self.mats.index(mat)] * len(F)
        if cor is None:
            cor = np.ones((len(V), 4))
        cor = np.asarray(cor, float)
        if cor.ndim == 1:
            cor = np.tile(cor, (len(V), 1))
        if cor.shape[1] == 3:
            cor = np.hstack([cor, np.ones((len(cor), 1))])
        self.C.append(cor)
        ini = self.n
        self.n += len(V)
        return ini

    @property
    def verts(self):
        return np.vstack(self.V)

    def criar(self, nome, pai=None, normais=None, com_cor=False, facetado=False):
        return objeto(nome, self.verts, self.F, self.mats, self.M, normais=normais,
                      cores=np.vstack(self.C) if com_cor else None, pai=pai, facetado=facetado)


# ====================================================================== a cabeça (loft de seções horizontais)
# z: meia-largura (a), frente (y da frente, negativo), trás (y de trás), expoente da seção (frente mais "chapada")
PERFIL = np.array([
    # z      a      frente   trás    n
    [1.02, 0.00, -0.02, 0.10, 2.0],
    [0.97, 0.32, -0.30, 0.40, 2.0],
    [0.86, 0.56, -0.54, 0.66, 2.0],
    [0.68, 0.77, -0.76, 0.86, 2.1],
    [0.45, 0.90, -0.90, 0.97, 2.3],
    [0.20, 0.95, -0.96, 1.00, 2.5],
    [-0.05, 0.94, -0.985, 0.99, 2.6],
    [-0.28, 0.90, -0.99, 0.93, 2.6],
    [-0.46, 0.83, -0.975, 0.82, 2.5],
    [-0.64, 0.71, -0.955, 0.60, 2.4],
    [-0.80, 0.56, -0.935, 0.28, 2.3],
    [-0.94, 0.41, -0.915, -0.12, 2.2],
    [-1.05, 0.27, -0.897, -0.48, 2.1],
    [-1.13, 0.14, -0.88, -0.68, 2.0],
    [-1.175, 0.0, -0.868, -0.77, 2.0],
])
_z = PERFIL[:, 0]
LARG, FRENTE, TRAS, EXPO = (pchip(_z, PERFIL[:, i]) for i in (1, 2, 3, 4))
Z_TOPO, Z_QUEIXO = PERFIL[0, 0], PERFIL[-1, 0]
NARIZ = (0.0, -0.44)            # ponta do nariz (x, z)
CENTRO_NORMAIS = np.array([0.0, 0.18, -0.12])   # normais "de anime": vindas de uma esfera, sombra limpa


def secao(z):
    a, fF, fB, n = LARG(z), FRENTE(z), TRAS(z), EXPO(z)
    yc = min(0.0, (fF + fB) / 2)
    return a, yc, yc - fF, fB - yc, n


def nariz_y(x, z):
    """Quanto o nariz sai da frente do rosto (negativo = para fora)."""
    dz = (z - NARIZ[1])
    forma = np.exp(-((x / 0.055) ** 2) - (np.maximum(dz, 0) / 0.2) ** 2 - (np.minimum(dz, 0) / 0.04) ** 2)
    return -0.07 * forma


def frente(x, z):
    """y da superfície da frente do rosto no ponto (x, z) visto de frente."""
    x, z = np.asarray(x, float), np.asarray(z, float)
    a, yc, dF, dB, n = np.vectorize(secao)(z)
    r = np.clip(np.abs(x) / np.maximum(a, 1e-6), 0, 1)
    return yc - dF * (1 - r ** n) ** (1 / n) + nariz_y(x, z)


def na_pele(x, z, fora=0.004):
    """Ponto (x, z) projetado na frente do rosto, um tiquinho para fora (para os "desenhos" do rosto)."""
    x, z = np.asarray(x, float), np.asarray(z, float)
    return np.stack([x, frente(x, z) - fora, z], axis=-1)


def cabeca_malha(aneis=44, voltas=48):
    zs = Z_TOPO + (Z_QUEIXO - Z_TOPO) * (0.5 - 0.5 * np.cos(np.linspace(0, math.pi, aneis)))
    V = [[0.0, FRENTE(Z_TOPO) * 0 + 0.04, Z_TOPO]]
    for z in zs[1:-1]:
        a, yc, dF, dB, n = secao(z)
        for j in range(voltas):
            psi = 2 * math.pi * j / voltas              # 0 = frente, cresce para +X (lado esquerdo dela)
            s, c = math.sin(psi), math.cos(psi)
            x = a * math.copysign(abs(s) ** (2 / n), s)
            if c >= 0:
                y = yc - dF * abs(c) ** (2 / n)
            else:
                y = yc + dB * abs(c) ** (2 / 2.0)
            y += float(nariz_y(x, z))
            V.append([x, y, z])
    V.append([0.0, FRENTE(Z_QUEIXO), Z_QUEIXO])
    V = np.array(V)
    F = []
    for j in range(voltas):
        F.append([0, 1 + (j + 1) % voltas, 1 + j])
    for i in range(aneis - 3):
        b0, b1 = 1 + i * voltas, 1 + (i + 1) * voltas
        for j in range(voltas):
            j2 = (j + 1) % voltas
            F.append([b0 + j, b0 + j2, b1 + j2, b1 + j])
    ult = len(V) - 1
    b0 = 1 + (aneis - 3) * voltas
    for j in range(voltas):
        F.append([b0 + j, b0 + (j + 1) % voltas, ult])
    return V, F


# ====================================================================== olhos
OLHO_Z, OLHO_X, OLHO_W, OLHO_H = -0.12, 0.37, 0.205, 0.155


def bezier(p0, p1, p2, p3, n=200):
    t = np.linspace(0, 1, n)[:, None]
    return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3


def curva_u(p0, p1, p2, p3):
    b = bezier(*(np.array(p, float) for p in (p0, p1, p2, p3)))
    return lambda u: np.interp(u, b[:, 0], b[:, 1])


PALP_CIMA = curva_u((-1.0, -0.14), (-0.62, 0.66), (0.52, 0.84), (1.0, 0.20))
PALP_BAIXO = curva_u((-1.0, -0.14), (-0.5, -0.66), (0.52, -0.62), (1.0, 0.20))


def olho(lado, pai):
    """lado -1: olho direito dela (à esquerda na tela, atrás do monóculo); +1: esquerdo."""
    cx = OLHO_X * lado
    W, H = OLHO_W, OLHO_H
    mats = ["sombra_olho", "vinco", "olho_branco", "iris", "iris_estrela", "pupila", "brilho_olho",
            "cilios_baixo", "cilios"]
    J = Juntar(mats)
    nu = 18
    us = -np.cos(np.linspace(0, math.pi, nu))                  # mais pontos perto dos cantos

    def pos(u, v, fora):
        return na_pele(cx + lado * np.asarray(u) * W, OLHO_Z + np.asarray(v) * H, fora)

    def faixa(u, v0, v1, fora):
        """Faixa entre as curvas v0(u) e v1(u) (duas fileiras)."""
        A, B = pos(u, v0, fora), pos(u, v1, fora)
        V = np.vstack([A, B])
        n = len(u)
        F = [[i, i + 1, n + i + 1, n + i] for i in range(n - 1)]
        return V, F

    def montar(cima, baixo, fechar_cilios=None, espessura=1.0, iris_dx=0.0, iris_dy=0.0, pupila=1.0,
               baixo_some=False, vinco_desce=0.0):
        """Todas as partes do olho para um formato de pálpebras (a base e cada shape key)."""
        out = []
        # sombra rosa acima dos cílios
        u = np.linspace(-0.75, 1.08, 14)
        lash = cima(u) if fechar_cilios is None else fechar_cilios(u)
        V, F = faixa(u, lash, lash + 0.5 * espessura, 0.0035)
        out.append(("sombra_olho", V, F, None))
        # vinco da pálpebra
        u = np.linspace(-0.45, 0.85, 10)
        base = (cima(u) if fechar_cilios is None else fechar_cilios(u)) + 0.30 - vinco_desce
        V, F = faixa(u, base, base + 0.055 * (1 - u ** 2) ** 0.5 * espessura, 0.0045)
        out.append(("vinco", V, F, None))
        # branco do olho (a máscara: íris, pupila e brilhos só aparecem dentro dele)
        linhas = 6
        V = np.vstack([pos(us, baixo(us) + (cima(us) - baixo(us)) * t, 0.006) for t in np.linspace(0, 1, linhas)])
        F = [[r * nu + i, r * nu + i + 1, (r + 1) * nu + i + 1, (r + 1) * nu + i]
             for r in range(linhas - 1) for i in range(nu - 1)]
        out.append(("olho_branco", V, F, None))
        # íris
        icx, icz = 0.06 + iris_dx, -0.04 + iris_dy
        riu, riv = 0.56, 0.9
        seg, raios = 30, [0.0, 0.3, 0.55, 0.75, 0.88, 1.0]
        Vi, Ci = [], []
        topo, meio, fundo = srgb("#1e2466"), srgb("#3f62cf"), srgb("#93d8ff")
        borda = srgb("#221f5c")
        for r in raios:
            for k in range(seg):
                ang = 2 * math.pi * k / seg
                su, sv = math.cos(ang) * r, math.sin(ang) * r
                Vi.append((icx + su * riu, icz + sv * riv))
                t = (1 - sv) / 2                                     # 0 em cima, 1 embaixo
                c = np.where(t < 0.45, topo + (meio - topo) * smooth(0.0, 0.45, t),
                             meio + (fundo - meio) * smooth(0.45, 1.0, t))
                c = c + (borda - c) * smooth(0.8, 1.0, r) * 0.85
                Ci.append(c)
        Vi = np.array(Vi)
        V = pos(Vi[:, 0], Vi[:, 1], 0.0075)
        F = [[a * seg + k, a * seg + (k + 1) % seg, (a + 1) * seg + (k + 1) % seg, (a + 1) * seg + k]
             for a in range(len(raios) - 1) for k in range(seg)]
        out.append(("iris", V, F, np.array(Ci)))
        # estrela de cristal na íris
        pts = [(icx, icz - 0.08)]
        for k in range(16):
            ang = math.pi / 2 + 2 * math.pi * k / 16
            r = 0.66 if k % 2 == 0 else 0.3
            pts.append((icx + math.cos(ang) * r * riu, icz - 0.08 + math.sin(ang) * r * riv * 0.9))
        pts = np.array(pts)
        V = pos(pts[:, 0], pts[:, 1], 0.0085)
        F = [[0, 1 + k, 1 + (k + 1) % 16] for k in range(16)]
        out.append(("iris_estrela", V, F, None))
        # pupila
        pts = [(icx, icz - 0.05)] + [(icx + math.cos(2 * math.pi * k / 20) * 0.26 * riu * pupila,
                                        icz - 0.05 + math.sin(2 * math.pi * k / 20) * 0.34 * riv * pupila)
                                       for k in range(20)]
        pts = np.array(pts)
        V = pos(pts[:, 0], pts[:, 1], 0.0095)
        F = [[0, 1 + k, 1 + (k + 1) % 20] for k in range(20)]
        out.append(("pupila", V, F, None))
        # brilhos (o grande em cima, do lado da luz, e dois pequenos)
        Vb, Fb = [], []
        luz = -lado                                                   # a luz vem da esquerda da tela
        for (bx, bz, ru_, rv_, rot) in ((0.34 * luz, 0.42, 0.26, 0.19, 0.5), (-0.36 * luz, -0.5, 0.11, 0.09, 0.0),
                                        (-0.05 * luz, -0.62, 0.06, 0.05, 0.0)):
            ini = len(Vb)
            Vb.append((icx + bx * riu, icz + bz * riv))
            for k in range(14):
                ang = 2 * math.pi * k / 14
                ex, ez = math.cos(ang) * ru_, math.sin(ang) * rv_
                Vb.append((icx + (bx + ex * math.cos(rot) - ez * math.sin(rot)) * riu,
                           icz + (bz + ex * math.sin(rot) + ez * math.cos(rot)) * riv))
            Fb += [[ini, ini + 1 + k, ini + 1 + (k + 1) % 14] for k in range(14)]
        Vb = np.array(Vb)
        out.append(("brilho_olho", pos(Vb[:, 0], Vb[:, 1], 0.0105), Fb, None))
        # cílios de baixo (fininhos, na metade de fora)
        u = np.linspace(0.05, 0.98, 10)
        vb = baixo(u) if not baixo_some else (fechar_cilios(u) if fechar_cilios else baixo(u))
        th = (0.0 if baixo_some else 0.075) * smooth(0.0, 0.5, u) * (1 - 0.4 * smooth(0.85, 1, u))
        V, F = faixa(u, vb - th * 0.4, vb + th * 0.6, 0.011)
        out.append(("cilios_baixo", V, F, None))
        # cílios de cima: a linha grossa, mais o "rabinho" do canto de fora
        u = np.concatenate([np.linspace(-0.93, 1.0, 20), [1.08, 1.16]])
        linha = cima if fechar_cilios is None else fechar_cilios
        v = np.concatenate([linha(u[:20]), linha(np.array([1.0]))[0] + np.array([0.08, 0.17]) * espessura])
        th = (0.16 + 0.34 * smooth(-0.85, 0.55, u)) * espessura
        th[-2:] = np.array([0.2, 0.04]) * espessura
        V, F = faixa(u, v - th * 0.25, v + th * 0.75, 0.013)
        # três pontinhas de cílio para fora
        extra_v, extra_f = [], []
        base_n = len(V)
        for k, (uu, du, dv) in enumerate(((0.62, 0.10, 0.34), (0.8, 0.16, 0.3), (0.95, 0.22, 0.2))):
            vv = float(linha(np.array([uu]))[0]) + 0.2 * espessura
            tri = pos(np.array([uu - 0.05, uu + 0.05, uu + du]),
                      np.array([vv, vv, vv + dv * espessura]), 0.013)
            extra_v.append(tri)
            extra_f.append([base_n + 3 * k, base_n + 3 * k + 1, base_n + 3 * k + 2])
        V = np.vstack([V] + extra_v)
        out.append(("cilios", V, F + extra_f, None))
        return out

    base = montar(PALP_CIMA, PALP_BAIXO)
    for mat, V, F, cor in base:
        J.add(V, F, mat, cor)

    def posicoes(partes_):
        return np.vstack([V for _, V, _, _ in partes_])

    fechado = lambda u: PALP_BAIXO(u) + 0.14 * (1 - np.asarray(u) ** 2)           # ︶ olho fechado calmo
    feliz = lambda u: -0.02 + 0.5 * (1 - np.asarray(u) ** 2) ** 0.8                 # ^ olho sorrindo
    alvos = {}
    nome_piscar = "piscar_direito" if lado < 0 else "piscar_esquerdo"
    alvos[nome_piscar] = posicoes(montar(fechado, fechado, fechar_cilios=fechado,
                                         espessura=0.62, vinco_desce=0.2))
    alvos["olhos_felizes"] = posicoes(montar(feliz, feliz, fechar_cilios=feliz,
                                             espessura=0.78, baixo_some=True, vinco_desce=0.25))
    alvos["arregalar"] = posicoes(montar(lambda u: PALP_CIMA(u) + 0.14 * (1 - np.asarray(u) ** 2) ** 0.5,
                                         lambda u: PALP_BAIXO(u) - 0.1 * (1 - np.asarray(u) ** 2) ** 0.5,
                                         pupila=0.72))
    # olhar: na tela, os dois olhos para o mesmo lado (o u cresce para fora de cada olho)
    for nome, dx, dy in (("olhar_esquerda", -1, 0), ("olhar_direita", 1, 0), ("olhar_cima", 0, 1),
                         ("olhar_baixo", 0, -1)):
        alvos[nome] = posicoes(montar(PALP_CIMA, PALP_BAIXO, iris_dx=0.34 * dx * lado, iris_dy=0.3 * dy))
    ob = J.criar("Olho_direito" if lado < 0 else "Olho_esquerdo", pai=pai, com_cor=True)
    chaves(ob, alvos)
    return ob


# ====================================================================== sobrancelhas
def sobrancelhas(pai):
    J = Juntar(["sobrancelha"])
    formatos = {"base": {}, "sobrancelhas_cima": {}, "sobrancelhas_bravas": {}, "sobrancelhas_tristes": {},
                "sobrancelha_pensativa": {}}
    u = np.linspace(-1, 1, 12)                     # -1 = ponta de dentro (perto do nariz)
    for lado in (-1, 1):
        cx = OLHO_X * lado + 0.01 * lado
        def banda(dz_fn):
            z = 0.135 + 0.045 * (1 - u ** 2) - 0.035 * u + dz_fn(u)
            x = cx + lado * u * 0.21
            th = 0.026 - 0.015 * (u + 1) / 2
            A = na_pele(x, z - th * 0.5, 0.009)
            B = na_pele(x, z + th * 0.5, 0.009)
            return np.vstack([A, B])
        formatos["base"][lado] = banda(lambda u: 0 * u)
        formatos["sobrancelhas_cima"][lado] = banda(lambda u: 0.075 + 0.015 * (1 - u ** 2))
        formatos["sobrancelhas_bravas"][lado] = banda(lambda u: -0.065 * (1 - u) / 2 + 0.012 * (1 + u) / 2)
        formatos["sobrancelhas_tristes"][lado] = banda(lambda u: 0.06 * (1 - u) / 2 - 0.02 * (1 + u) / 2)
        formatos["sobrancelha_pensativa"][lado] = banda(
            (lambda u: 0.07 + 0.02 * (1 - u ** 2)) if lado > 0 else (lambda u: -0.02 * (1 - u) / 2))
    n = len(u)
    for lado in (-1, 1):
        J.add(formatos["base"][lado], [[i, i + 1, n + i + 1, n + i] for i in range(n - 1)], "sobrancelha")
    ob = J.criar("Sobrancelhas", pai=pai)
    chaves(ob, {k: np.vstack([formatos[k][-1], formatos[k][1]]) for k in formatos if k != "base"})
    return ob


# ====================================================================== boca
BOCA_Z, BOCA_M = -0.695, 0.07


def boca(pai):
    mats = ["labio", "boca_dentro", "dentes", "lingua", "linha_boca"]
    J = Juntar(mats)
    nu = 15
    u = np.linspace(-1, 1, nu)

    def forma(w=1.0, cima=0.0, baixo=0.0, cantos=-0.004, redonda=0.5):
        x = u * BOCA_M * w
        env = (1 - u ** 2) ** redonda
        top = BOCA_Z + cima * env + cantos * u ** 2
        bot = BOCA_Z - baixo * (1 - u ** 2) ** 0.62 + cantos * u ** 2
        partes = []
        # lábio de baixo (brilho rosado, bem de leve)
        ul = np.linspace(-0.55, 0.55, 8)
        xl = ul * BOCA_M * w * 0.9
        bl = np.interp(ul, u, bot)
        A, B = na_pele(xl, bl - 0.012, 0.004), na_pele(xl, bl - 0.03 + 0.008 * ul ** 2, 0.004)
        partes.append(("labio", np.vstack([A, B]), [[i, i + 1, 8 + i + 1, 8 + i] for i in range(7)]))
        # o escuro da boca (a máscara dos dentes e da língua)
        linhas = 4
        V = np.vstack([na_pele(x, top + (bot - top) * t, 0.006) for t in np.linspace(0, 1, linhas)])
        F = [[r * nu + i, r * nu + i + 1, (r + 1) * nu + i + 1, (r + 1) * nu + i]
             for r in range(linhas - 1) for i in range(nu - 1)]
        partes.append(("boca_dentro", V, F))
        # dentes de cima
        dent = np.minimum(0.022, (top - bot) * 0.45) * env + 0.0005
        V = np.vstack([na_pele(x, top + 0.002, 0.007), na_pele(x, top - dent, 0.007)])
        partes.append(("dentes", V, [[i, i + 1, nu + i + 1, nu + i] for i in range(nu - 1)]))
        # língua
        lc = bot[nu // 2] + 0.02
        pts = [(0.0, lc)] + [(math.cos(2 * math.pi * k / 16) * 0.045 * w * (BOCA_M / 0.062),
                               lc + math.sin(2 * math.pi * k / 16) * 0.022) for k in range(16)]
        pts = np.array(pts)
        partes.append(("lingua", na_pele(pts[:, 0], pts[:, 1], 0.0072), [[0, 1 + k, 1 + (k + 1) % 16] for k in range(16)]))
        # a linha da boca (é ela que aparece com a boca fechada)
        th = 0.0045 * (1 - u ** 2) ** 0.35 + 0.0012
        V = np.vstack([na_pele(x, top - th * 0.6, 0.009), na_pele(x, top + th * 0.4, 0.009)])
        partes.append(("linha_boca", V, [[i, i + 1, nu + i + 1, nu + i] for i in range(nu - 1)]))
        return partes

    for mat, V, F in forma():
        J.add(V, F, mat)
    pos = lambda p: np.vstack([V for _, V, _ in p])
    alvos = {
        "boca_a": pos(forma(w=1.05, cima=0.014, baixo=0.13, cantos=0.0)),
        "boca_e": pos(forma(w=1.2, cima=0.013, baixo=0.075, cantos=0.004)),
        "boca_i": pos(forma(w=1.32, cima=0.007, baixo=0.04, cantos=0.01)),
        "boca_o": pos(forma(w=0.7, cima=0.034, baixo=0.1, cantos=0.0, redonda=0.5)),
        "boca_u": pos(forma(w=0.48, cima=0.025, baixo=0.058, cantos=0.0)),
        "sorriso": pos(forma(w=1.25, cantos=0.05)),
        "triste": pos(forma(w=0.95, cantos=-0.032)),
        "bravo": pos(forma(w=1.1, cima=0.004, baixo=0.022, cantos=-0.024)),
    }
    ob = J.criar("Boca", pai=pai)
    chaves(ob, alvos)
    return ob


# ====================================================================== detalhes do rosto
def detalhes_rosto(pai):
    J = Juntar(["nariz", "blush", "pele_sombra"])
    # nariz: um toque de sombra do lado direito da tela (a luz vem da esquerda)
    pts = np.array([(0.012, -0.36), (0.034, -0.41), (0.03, -0.455), (0.008, -0.462), (0.022, -0.43)])
    J.add(na_pele(pts[:, 0], pts[:, 1], 0.004), [[0, 1, 4], [1, 2, 4], [2, 3, 4]], "nariz")
    # blush com os risquinhos de anime
    for lado in (-1, 1):
        c = (0.52 * lado, -0.33)
        pts = [c] + [(c[0] + math.cos(2 * math.pi * k / 20) * 0.15, c[1] + math.sin(2 * math.pi * k / 20) * 0.065)
                     for k in range(20)]
        pts = np.array(pts)
        J.add(na_pele(pts[:, 0], pts[:, 1], 0.003), [[0, 1 + k, 1 + (k + 1) % 20] for k in range(20)], "blush",
              cor=np.array([[1, 1, 1, 0.9]] + [[1, 1, 1, 0.0]] * 20))
    # sombra do pescoço sob o queixo
    xs = np.linspace(-0.285, 0.285, 11)
    cima = np.array([[x, -0.19 + 0.3 * (x / 0.285) ** 2 * 0.1, -1.0] for x in xs])
    baixo = np.array([[x, -0.195 + 0.3 * (x / 0.285) ** 2 * 0.1, -1.33 + 0.12 * (x / 0.285) ** 2] for x in xs])
    J.add(np.vstack([cima, baixo]), [[i, i + 1, 11 + i + 1, 11 + i] for i in range(10)], "pele_sombra")
    return J.criar("Detalhes_rosto", pai=pai, com_cor=True)


# ====================================================================== cabelo
CENTRO_CABECA = np.array([0.0, 0.03, 0.02])


def esfera(r, teta, fi, centro=CENTRO_CABECA):
    """Ponto numa esfera: teta = ângulo a partir do topo; fi = 0 na frente, cresce para o lado esquerdo dela."""
    return centro + r * np.array([math.sin(teta) * math.sin(fi), -math.sin(teta) * math.cos(fi), math.cos(teta)])


def mecha(pontos, largura, espessura, curva=0.35, secoes=13, afina=0.9, bojo=0.12, torcao=0.0, fora=None,
          ponta_larga=0.0):
    """Uma mecha de anime: fita curvada que afina até a ponta. Devolve (V, F)."""
    P = catmull(pontos, secoes)
    T = normalizar(np.gradient(P, axis=0))
    if fora is None:
        N = P - CENTRO_CABECA
    else:
        N = np.tile(np.asarray(fora, float), (len(P), 1))
    N = normalizar(N - (N * T).sum(1, keepdims=True) * T)
    B = normalizar(np.cross(T, N))
    V, F = [], []
    ns = 5
    s_fora = np.linspace(-1, 1, ns)
    s_dentro = np.linspace(1, -1, ns)[1:-1]
    per = ns + len(s_dentro)
    for i, t in enumerate(np.linspace(0, 1, secoes)):
        if i == secoes - 1:
            V.append(P[i])
            continue
        w = largura * ((1 - t) ** afina * (1 - ponta_larga) + ponta_larga) * (1 + bojo * math.sin(math.pi * t))
        th = espessura * (1 - t) ** 0.6 + 0.004
        ang = torcao * t
        b = B[i] * math.cos(ang) + N[i] * math.sin(ang)
        n = N[i] * math.cos(ang) - B[i] * math.sin(ang)
        for s in s_fora:
            V.append(P[i] + b * s * w / 2 + n * (curva * w * (1 - s * s) * 0.5 + th / 2))
        for s in s_dentro:
            V.append(P[i] + b * s * w / 2 * 0.92 + n * (curva * w * (1 - s * s) * 0.42 - th / 2))
    for i in range(secoes - 2):
        a0, a1 = i * per, (i + 1) * per
        for k in range(per):
            k2 = (k + 1) % per
            F.append([a0 + k, a0 + k2, a1 + k2, a1 + k])
    ponta = len(V) - 1
    a0 = (secoes - 2) * per
    for k in range(per):
        F.append([a0 + k, a0 + (k + 1) % per, ponta])
    # tampa da raiz
    F.append(list(range(per))[::-1])
    return np.array(V), F


def cabelo(pai):
    J = Juntar(["cabelo", "cristal"])
    # --- a touca (o couro cabeludo coberto), sem a janela do rosto e sem as orelhas
    R = 1.075
    nt, nf = 24, 48
    V = []
    for i in range(nt + 1):
        teta = math.pi * i / nt
        for j in range(nf):
            V.append(esfera(R, teta, 2 * math.pi * j / nf, CENTRO_CABECA + [0, 0.03, 0.0]))
    V = np.array(V)
    F = []
    for i in range(nt):
        for j in range(nf):
            q = [i * nf + j, i * nf + (j + 1) % nf, (i + 1) * nf + (j + 1) % nf, (i + 1) * nf + j]
            c = normalizar(V[q].mean(0) - CENTRO_CABECA)
            rosto = c[1] < -0.25 and c[2] < 0.55
            if rosto or c[2] < -0.62:
                continue
            F.append(q)
    usados = sorted({i for f in F for i in f})
    remap = {v: k for k, v in enumerate(usados)}
    J.add(V[usados], [[remap[i] for i in f] for f in F], "cabelo")

    pontas = []                                    # onde a franja termina (para a sombra na testa)
    # --- franja: mechas que saem do alto da cabeça e caem sobre a testa, pontas em alturas diferentes
    franja = [(-1.2, 0.36, 0.3), (-1.0, 0.24, 0.3), (-0.8, 0.3, 0.29), (-0.6, 0.18, 0.28), (-0.4, 0.27, 0.27),
              (-0.2, 0.12, 0.24), (0.0, 0.2, 0.22), (0.2, 0.1, 0.24), (0.41, 0.25, 0.27), (0.61, 0.16, 0.28),
              (0.81, 0.29, 0.29), (1.01, 0.22, 0.3), (1.21, 0.35, 0.3)]
    for k, (fi, zp, w) in enumerate(franja):
        x_testa = math.sin(fi) * 0.97
        z_meio = 0.46 + 0.1 * abs(math.sin(fi))
        p0 = esfera(1.11, math.radians(14), fi * 0.3)
        p1 = esfera(1.115, math.radians(36), fi * 0.7)
        p2 = esfera(1.12, math.radians(54), fi * 0.92)
        xm = x_testa * 0.97
        p3 = np.array([xm, float(frente(xm * 0.95, z_meio)) - 0.1, z_meio])
        curva_ponta = -0.06 * np.sign(fi) if 0.15 < abs(fi) < 0.95 else 0.0
        xt = float(np.clip(x_testa * 0.9 + curva_ponta, -0.92, 0.92))
        p4 = np.array([xt, float(frente(xt, zp)) - 0.075, zp])
        V, F = mecha([p0, p1, p2, p3, p4], w, 0.055, curva=0.3, afina=0.8, bojo=0.2,
                     torcao=0.12 * (k % 3 - 1))
        J.add(V, F, "cabelo")
        pontas.append((xt, zp))
    # duas mechas finas no meio, descendo entre os olhos
    for fi, xt, zt in ((-0.06, -0.06, -0.02), (0.09, 0.075, 0.04)):
        p0 = esfera(1.11, math.radians(18), fi)
        p2 = esfera(1.12, math.radians(54), fi)
        p3 = np.array([xt * 1.4, float(frente(xt, 0.36)) - 0.11, 0.36])
        p4 = np.array([xt, float(frente(xt, zt)) - 0.07, zt])
        V, F = mecha([p0, p2, p3, p4], 0.1, 0.035, curva=0.25, afina=0.9)
        J.add(V, F, "cabelo")
    # --- nas têmporas: mechas que descem na frente da orelha até a bochecha
    for lado in (-1, 1):
        for fi, zf, larg, dx in ((1.05, -0.36, 0.24, 0.0), (1.28, -0.62, 0.26, 0.05)):
            p0 = esfera(1.11, math.radians(30), lado * fi * 0.8)
            p1 = esfera(1.12, math.radians(62), lado * fi)
            p2 = np.array([lado * (0.99 + dx), -0.5 + dx, 0.12])
            p3 = np.array([lado * (0.93 + dx), -0.62 + dx, zf])
            V, F = mecha([p0, p1, p2, p3], larg, 0.06, curva=0.35, afina=0.85, bojo=0.22, torcao=-0.25 * lado)
            J.add(V, F, "cabelo")
    # --- mechas dos lados, emoldurando o rosto até os ombros
    for lado in (-1, 1):
        for fi, zf, larg, dy in ((1.45, -1.25, 0.27, -0.38), (1.7, -1.42, 0.32, -0.12), (1.95, -1.2, 0.32, 0.15)):
            p0 = esfera(1.1, math.radians(32), lado * fi * 0.9)
            p1 = esfera(1.11, math.radians(70), lado * fi)
            p2 = np.array([lado * 1.08, dy + 0.02, -0.28])
            p3 = np.array([lado * 1.02, dy - 0.03, -0.82])
            p4 = np.array([lado * 0.88, dy - 0.07, zf])
            V, F = mecha([p0, p1, p2, p3, p4], larg, 0.065, curva=0.38, afina=0.8, bojo=0.25,
                         torcao=-0.3 * lado)
            J.add(V, F, "cabelo")
    # --- atrás: mechas penteadas para cima, até o coque
    coque = esfera(1.08, math.radians(24), math.pi) + np.array([0, 0.02, 0.1])
    for k, fi in enumerate(np.linspace(math.pi - 1.3, math.pi + 1.3, 9)):
        p0 = esfera(1.08, math.radians(122), fi)
        p1 = esfera(1.1, math.radians(95), fi * 0.98 + math.pi * 0.02)
        p2 = esfera(1.11, math.radians(60), math.pi + (fi - math.pi) * 0.55)
        p3 = coque + np.array([(fi - math.pi) * 0.12, 0.05, -0.08])
        V, F = mecha([p0, p1, p2, p3], 0.36, 0.04, curva=0.25, afina=0.5, bojo=0.1, ponta_larga=0.35)
        J.add(V, F, "cabelo")
    # fios soltos na nuca (o coque é meio bagunçado)
    for lado in (-1, 1):
        p0 = esfera(1.08, math.radians(118), math.pi - lado * 0.55)
        V, F = mecha([p0, p0 + [lado * 0.06, 0.08, -0.35], p0 + [lado * 0.14, 0.02, -0.75]], 0.14, 0.03,
                     curva=0.3, afina=0.9, torcao=0.6 * lado)
        J.add(V, F, "cabelo")
    # --- o coque, alto e redondo
    cq = coque + np.array([0, 0.02, 0.16])
    n1, n2 = 14, 22
    V = []
    for i in range(n1 + 1):
        th = math.pi * i / n1
        for j in range(n2):
            ph = 2 * math.pi * j / n2
            V.append(cq + np.array([0.37 * math.sin(th) * math.cos(ph), 0.32 * math.sin(th) * math.sin(ph),
                                    0.3 * math.cos(th)]))
    V = np.array(V)
    F = [[i * n2 + j, i * n2 + (j + 1) % n2, (i + 1) * n2 + (j + 1) % n2, (i + 1) * n2 + j]
         for i in range(n1) for j in range(n2)]
    J.add(V, F, "cabelo")
    # voltas de cabelo em volta do coque
    for k in range(6):
        eixo = normalizar(rng.normal(size=3) * [1, 1, 0.5] + [0, 0, 0.9])
        a = normalizar(np.cross(eixo, [1, 0, 0]))
        b = np.cross(eixo, a)
        ang0 = rng.uniform(0, 2 * math.pi)
        pts = [cq + 0.34 * (a * math.cos(ang0 + t) + b * math.sin(ang0 + t)) * [1.05, 0.95, 0.9]
               for t in np.linspace(0, 4.0, 7)]
        V, F = mecha(pts, 0.19, 0.05, curva=0.4, afina=0.6, bojo=0.2, ponta_larga=0.1)
        J.add(V, F, "cabelo")
    # pontinhas soltas saindo do coque, curvas (bagunçado, sem virar espeto)
    for k, d in enumerate(([0.3, 0.1, 0.22], [-0.32, 0.12, 0.2], [0.1, 0.32, 0.26])):
        d = np.array(d)
        p0 = cq + normalizar(d) * 0.26
        lado = np.cross(normalizar(d), [0, 0, 1])
        V, F = mecha([p0, p0 + d * 0.35 + lado * 0.04, p0 + d * 0.55 + lado * 0.12 + [0, 0, -0.06]], 0.11, 0.03,
                     curva=0.3, afina=0.9, torcao=0.8)
        J.add(V, F, "cabelo")
    # a antena (ahoge)
    p0 = esfera(1.1, math.radians(8), 0.4)
    V, F = mecha([p0, p0 + [0.03, -0.05, 0.2], p0 + [0.08, -0.2, 0.3], p0 + [0.1, -0.3, 0.22]], 0.08, 0.025,
                 curva=0.2, afina=1.0, torcao=0.5)
    J.add(V, F, "cabelo")
    # --- estrelas de cristal no coque e cristais no cabelo
    for pos, tam, rot in ((cq + [0.33, -0.14, 0.12], 0.1, 0.3), (cq + [-0.32, -0.16, 0.14], 0.085, -0.2),
                          (cq + [0.06, -0.22, 0.26], 0.07, 0.9)):
        V, F = estrela(pos, normalizar(pos - cq + [0, -0.4, 0]), tam, rot)
        J.add(V, F, "cristal")
    for k in range(3):
        base = np.array([-1.0, -0.3, 0.42]) + [0.03 * k, -0.02 * k, -0.09 * k]
        V, F = gema(base, normalizar([-0.6 - 0.2 * k, -0.4, 0.7 - 0.25 * k]), 0.028 - 0.005 * k, 0.1 - 0.02 * k)
        J.add(V, F, "cristal")
    ob = J.criar("Cabelo", pai=pai)
    return ob, pontas


def estrela(centro, normal, tam, rot, pontas=5, grossura=0.035):
    """Estrela de cristal (prisma facetado)."""
    n = normalizar(normal)
    a = normalizar(np.cross(n, [0, 0, 1]) if abs(n[2]) < 0.9 else np.cross(n, [1, 0, 0]))
    b = np.cross(n, a)
    V = [centro + n * grossura, centro - n * grossura * 0.3]
    for k in range(pontas * 2):
        ang = rot + math.pi * k / pontas
        r = tam if k % 2 == 0 else tam * 0.45
        V.append(centro + (a * math.cos(ang) + b * math.sin(ang)) * r)
    F = []
    m = pontas * 2
    for k in range(m):
        F.append([0, 2 + k, 2 + (k + 1) % m])
        F.append([1, 2 + (k + 1) % m, 2 + k])
    return np.array(V), F


def gema(base, direcao, raio, altura, lados=6):
    """Cristal alongado (duas pirâmides), da base na direção dada."""
    d = normalizar(direcao)
    a = normalizar(np.cross(d, [0, 0, 1]) if abs(d[2]) < 0.9 else np.cross(d, [1, 0, 0]))
    b = np.cross(d, a)
    meio = base + d * altura * 0.3
    V = [base, base + d * altura]
    for k in range(lados):
        ang = 2 * math.pi * k / lados
        V.append(meio + (a * math.cos(ang) + b * math.sin(ang)) * raio)
    F = []
    for k in range(lados):
        F.append([0, 2 + (k + 1) % lados, 2 + k])
        F.append([1, 2 + k, 2 + (k + 1) % lados])
    return np.array(V), F


def tubo(pontos, raio, lados=6, n=None):
    P = catmull(pontos, n or max(8, len(pontos) * 6))
    T = normalizar(np.gradient(P, axis=0))
    ref = np.array([0, 0, 1.0])
    V, F = [], []
    for i, p in enumerate(P):
        a = normalizar(np.cross(T[i], ref if abs(T[i] @ ref) < 0.9 else [1, 0, 0]))
        b = np.cross(T[i], a)
        for k in range(lados):
            ang = 2 * math.pi * k / lados
            V.append(p + (a * math.cos(ang) + b * math.sin(ang)) * raio)
    for i in range(len(P) - 1):
        for k in range(lados):
            k2 = (k + 1) % lados
            F.append([i * lados + k, i * lados + k2, (i + 1) * lados + k2, (i + 1) * lados + k])
    return np.array(V), F


def toro(centro, normal, R, r, n1=40, n2=8):
    n = normalizar(normal)
    a = normalizar(np.cross(n, [0, 0, 1]) if abs(n[2]) < 0.9 else np.cross(n, [1, 0, 0]))
    b = np.cross(n, a)
    V, F = [], []
    for i in range(n1):
        u = 2 * math.pi * i / n1
        eixo = a * math.cos(u) + b * math.sin(u)
        for j in range(n2):
            v = 2 * math.pi * j / n2
            V.append(centro + eixo * (R + r * math.cos(v)) + n * r * math.sin(v))
    for i in range(n1):
        for j in range(n2):
            F.append([i * n2 + j, i * n2 + (j + 1) % n2, ((i + 1) % n1) * n2 + (j + 1) % n2, ((i + 1) % n1) * n2 + j])
    return np.array(V), F


def disco(centro, normal, R, n=32):
    nn = normalizar(normal)
    a = normalizar(np.cross(nn, [0, 0, 1]))
    b = np.cross(nn, a)
    V = [centro] + [centro + (a * math.cos(2 * math.pi * k / n) + b * math.sin(2 * math.pi * k / n)) * R
                    for k in range(n)]
    return np.array(V), [[0, 1 + k, 1 + (k + 1) % n] for k in range(n)]


# ====================================================================== joias
def joias(pai):
    J = Juntar(["metal", "cristal"])
    V_vidro = None
    # monóculo sobre o olho direito dela (esquerda da tela)
    cx, cz = -OLHO_X, OLHO_Z + 0.005
    y0 = float(frente(cx, cz)) - 0.055
    centro = np.array([cx, y0, cz])
    normal = normalizar([0.18, -1, 0.02])
    V, F = toro(centro, normal, 0.255, 0.016, 44, 8)
    J.add(V, F, "metal")
    V_vidro = disco(centro + normal * -0.002, normal, 0.252, 36)
    # corrente do monóculo até atrás da orelha
    a0 = centro + np.array([-0.2, 0.03, -0.12])
    pts = [a0, a0 + [-0.16, 0.1, -0.2], a0 + [-0.3, 0.3, -0.33], np.array([-1.0, 0.05, -0.52])]
    V, F = tubo(pts, 0.0055, 6, 36)
    J.add(V, F, "metal")
    # gotas penduradas no monóculo
    for k, (ang, comp) in enumerate(((-1.95, 0.09), (-1.6, 0.13), (-1.25, 0.08))):
        topo = centro + np.array([math.cos(ang) * 0.255, 0.0, math.sin(ang) * 0.255])
        V, F = tubo([topo, topo + [0, -0.01, -comp * 0.6]], 0.003, 5, 6)
        J.add(V, F, "metal")
        V, F = gema(topo + [0, -0.01, -comp * 0.6], [0, 0, -1], 0.018, 0.065)
        J.add(V, F, "cristal")
    # filigrana com gotinhas de cristal sob os olhos
    for lado in (-1, 1):
        cxo = OLHO_X * lado
        us = np.linspace(-0.2, 1.15, 10)
        zs = OLHO_Z + (PALP_BAIXO(us) - 0.55) * OLHO_H + 0.02 * us
        xs = cxo + lado * us * OLHO_W
        P = na_pele(xs, zs, 0.012)
        V, F = tubo(P, 0.004, 5, 30)
        J.add(V, F, "metal")
        for k in (3, 6, 8):
            topo = P[k]
            comp = 0.03 + 0.012 * (k % 3)
            V, F = tubo([topo, topo + [0, -0.004, -comp]], 0.0025, 4, 5)
            J.add(V, F, "metal")
            V, F = gema(topo + [0, -0.004, -comp], [0, 0, -1], 0.011, 0.038)
            J.add(V, F, "cristal")
    # brincos longos de cristal
    for lado in (-1, 1):
        topo = np.array([lado * 0.99, -0.08, -0.47])
        V, F = gema(topo + [0, 0, 0.02], [0, -0.3, 1], 0.02, 0.04)
        J.add(V, F, "cristal")
        V, F = tubo([topo, topo + [lado * 0.01, -0.02, -0.22], topo + [lado * 0.02, -0.03, -0.44]], 0.005, 5, 14)
        J.add(V, F, "metal")
        for z, r, h in ((-0.18, 0.018, 0.05), (-0.34, 0.02, 0.055)):
            V, F = gema(topo + [lado * 0.01, -0.02, z + 0.02], [0, 0, -1], r, h)
            J.add(V, F, "cristal")
        V, F = gema(topo + [lado * 0.02, -0.03, -0.44], [0, 0, -1], 0.032, 0.13)
        J.add(V, F, "cristal")
    ob = J.criar("Joias", pai=pai, facetado=False)
    vidro = objeto("Monoculo_vidro", V_vidro[0], V_vidro[1], ["vidro"], pai=pai)
    return ob, vidro


# ====================================================================== pescoço e roupa
def corpo(pai):
    J = Juntar(["pele", "roupa", "roupa_detalhe", "cristal"])
    # pescoço
    n, m = 12, 24
    V = []
    for i in range(n):
        z = -0.55 - 1.05 * i / (n - 1)
        r = 0.275 + 0.035 * (i / (n - 1)) ** 2
        for j in range(m):
            a = 2 * math.pi * j / m
            V.append([r * math.sin(a), 0.1 - r * math.cos(a), z])
    V = np.array(V)
    F = [[i * m + j, i * m + (j + 1) % m, (i + 1) * m + (j + 1) % m, (i + 1) * m + j] for i in range(n - 1)
         for j in range(m)]
    J.add(V, F, "pele")
    # tronco e ombros (loft)
    niveis = [(-1.5, 0.36, 0.33), (-1.62, 0.62, 0.42), (-1.76, 1.02, 0.5), (-1.92, 1.3, 0.56), (-2.22, 1.46, 0.6),
              (-2.72, 1.48, 0.6)]
    V = []
    for z, a, d in niveis:
        for j in range(m * 2):
            ang = 2 * math.pi * j / (m * 2)
            s, c = math.sin(ang), math.cos(ang)
            V.append([a * math.copysign(abs(s) ** (2 / 2.6), s), 0.12 - d * math.copysign(abs(c) ** (2 / 2.6), c), z])
    V = np.array(V)
    mm = m * 2
    F = [[i * mm + j, i * mm + (j + 1) % mm, (i + 1) * mm + (j + 1) % mm, (i + 1) * mm + j]
         for i in range(len(niveis) - 1) for j in range(mm)]
    J.add(V, F, "roupa")
    # gola lilás e o pingente de cristal
    V, F = toro(np.array([0, 0.12, -1.52]), [0, 0.12, 1], 0.36, 0.028, 40, 6)
    J.add(V, F, "roupa_detalhe")
    V, F = tubo([[-0.14, -0.24, -1.54], [0, -0.37, -1.72], [0.14, -0.24, -1.54]], 0.006, 5, 16)
    J.add(V, F, "roupa_detalhe")
    V, F = gema(np.array([0, -0.38, -1.73]), [0, -0.15, -1], 0.035, 0.11)
    J.add(V, F, "cristal")
    # normais: o pescoço à sombra do queixo fica com a normal para baixo (sombra de anime)
    return J.criar("Pescoco_e_roupa", pai=pai)


def sombra_franja(pontas, pai):
    """Sombra que a franja faz na testa: uma faixa recortada acompanhando as pontas."""
    pontas = sorted(pontas)
    xs = np.array([p[0] for p in pontas])
    zs = np.array([p[1] for p in pontas])
    x = np.linspace(-0.82, 0.82, 33)
    zt = np.interp(x, xs, zs)
    baixo = zt + 0.045
    cima = np.minimum(zt + 0.26, 0.62)
    V = np.vstack([na_pele(x, baixo, 0.0025), na_pele(x, cima, 0.0025)])
    F = [[i, i + 1, 33 + i + 1, 33 + i] for i in range(32)]
    return objeto("Sombra_franja", V, F, ["pele_sombra"], pai=pai)


# ====================================================================== tudo
def construir():
    limpar()
    # materiais (cores em sRGB; os extras dizem ao app como pintar)
    material("pele", "#fde9ee", sombra="#eab3c6", contorno="#b06f86")
    material("pele_sombra", "#eab0c4", cores_vertice=False)
    material("cabelo", "#f3f0fb", sombra="#bdb0e2", contorno="#8474b4", brilho="#ffffff", iridescente=0.35)
    material("roupa", "#3b2d61", sombra="#271c47", contorno="#150d2a")
    material("roupa_detalhe", "#cbb2f8", sombra="#9a82d6", contorno="#4c3a80")
    material("metal", "#f0d3b2", metal=1.0, rugosidade=0.25, sombra="#c49a86", contorno="#7a5a55", iridescente=0.8)
    material("cristal", "#e9e3ff", rugosidade=0.1, sombra="#a9b8f5", contorno="#6b6fb8", iridescente=1.0)
    material("vidro", "#dfe8ff", alfa=0.16, rugosidade=0.05, iridescente=1.0)
    material("olho_branco", "#fcfaff", sombra="#d8ccf0")
    material("iris", "#ffffff", cores_vertice=True)
    material("iris_estrela", "#a8e4ff")
    material("pupila", "#15163f")
    material("brilho_olho", "#ffffff")
    material("cilios", "#2a1d3a")
    material("cilios_baixo", "#7a5a8c")
    material("vinco", "#d9a2bd", alfa=0.8)
    material("sombra_olho", "#f5a3d6", alfa=0.4)
    material("sobrancelha", "#a092cc")
    material("nariz", "#e7a9bc", alfa=0.9)
    material("blush", "#f597bf", alfa=0.5, cores_vertice="alfa")
    material("labio", "#f09cbd", alfa=0.5)
    material("boca_dentro", "#5c1c3f")
    material("dentes", "#ffffff")
    material("lingua", "#e07a95")
    material("linha_boca", "#8c3c62")

    cena = bpy.context.scene
    corpo_ob = vazio("Ametista", (0, 0, 0))
    cab = vazio("Cabeca", (0, 0.05, -0.8), pai=None)
    # a cabeça: filhos são criados em coordenadas do mundo; o pai fica no pescoço
    rosto_V, rosto_F = cabeca_malha()
    normais = normalizar(rosto_V - CENTRO_NORMAIS)
    rosto = objeto("Rosto", rosto_V, rosto_F, ["pele"], normais=normais)
    partes = [rosto]
    partes.append(detalhes_rosto(None))
    partes.append(olho(-1, None))
    partes.append(olho(1, None))
    partes.append(sobrancelhas(None))
    partes.append(boca(None))
    cab_ob, pontas = cabelo(None)
    partes.append(cab_ob)
    partes.append(sombra_franja(pontas, None))
    j, vidro = joias(None)
    partes += [j, vidro]
    cab.parent = corpo_ob
    bpy.context.view_layer.update()
    for p in partes:            # filhos da cabeça sem sair do lugar (o pivô fica no pescoço)
        p.parent = cab
        p.matrix_parent_inverse = cab.matrix_world.inverted()
    c = corpo(None)
    c.parent = corpo_ob
    cena.frame_set(1)
    bpy.context.view_layer.update()
    return partes + [c]


def exportar():
    blend = os.path.join(AQUI, "ametista.blend")
    glb = os.path.join(RAIZ, "web", "ametista.glb")
    bpy.context.preferences.filepaths.save_version = 0      # sem o backup .blend1
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", export_yup=True, export_apply=False,
                              export_texcoords=False, export_normals=True, export_morph=True,
                              export_morph_normal=False, export_try_sparse_sk=True, export_extras=True,
                              export_vertex_color="MATERIAL", export_animations=False, export_cameras=False,
                              export_lights=False, export_materials="EXPORT")
    sys.path.insert(0, AQUI)
    from compactar_glb import compactar
    compactar(glb)                   # bem mais leve para o app (16 bits), sem mudar nada do que aparece
    shutil.copyfile(glb, os.path.join(RAIZ, "celular", "public", "ametista.glb"))
    try:                             # o celular baixa a versão nova (a impressão digital da casca muda)
        sys.path.insert(0, RAIZ)
        from ametista import publicar_celular
        publicar_celular.atualizar_sw()
    except Exception as e:
        print(f"(atualize o celular/public/sw.js com o python da Ametista: {e})")
    return blend, glb


if __name__ == "__main__":
    objs = construir()
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs if o.type == "MESH")
    verts = sum(len(o.data.vertices) for o in objs if o.type == "MESH")
    blend, glb = exportar()
    print(f"Ametista em malha: {len(objs)} objetos, {verts} vértices, {tris} triângulos")
    print(f"  {blend} ({os.path.getsize(blend) // 1024} KB)")
    print(f"  {glb} ({os.path.getsize(glb) // 1024} KB)")
    sys.stdout.flush()
