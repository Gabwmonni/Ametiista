"""Constrói a Ametista em 3D, no Blender: o modelo 3D dela (modelo/fonte/ametista_3d.glb), animável.

O modelo (corpo, cabelo, joias, monóculo) vira a malha "Corpo", mais leve, com um esqueleto: a cabeça acena, nega,
inclina e olha em volta de verdade (em 3D), o peito respira. Por cima do rosto vai a "máscara" (malha "Rosto"),
colada na superfície do rosto e pintada com a foto de frente do próprio modelo (rosto/frente.png): parada, é igual
ao modelo; com as shape keys, as pálpebras descem (e os cílios giram junto), a boca abre e fala, as sobrancelhas
sobem e franzem. Atrás dela ficam o branco dos olhos, as íris (que se mexem para olhar) e a boca por dentro.

Gera:
  modelo/ametista.blend       o arquivo para abrir e editar no Blender
  web/ametista.glb            o que o app usa (e celular/public/ametista.glb, a mesma coisa)

Uso (qualquer um dos dois):
  blender --background --python modelo/construir_ametista.py
  python modelo/construir_ametista.py          (com o módulo bpy instalado: pip install bpy)

Se o modelo 3D ou as marcações do rosto mudarem, antes:
  python modelo/renderizar_rosto.py   (a foto de frente, com o bpy)  e  python modelo/preparar_rosto.py  (o atlas)

As peças:
  Corpo         o modelo 3D, com menos triângulos (o rosto guarda mais detalhe) e a cor em 1024 x 1024
  Rosto         a máscara do rosto, com buracos nos olhos e na boca, e a borda que some aos poucos
  Olho_*        o branco de cada olho (atrás das pálpebras)          Iris_*     a íris (mexe para olhar)
  Cilios_*      os cílios de cima (giram para baixo na piscada)     Boca_dentro  dentes, o escuro e a língua
  Blush         o rubor (quando ela fica feliz)
Os ossos (Esqueleto): raiz, peito (respira), pescoco e cabeca (acenar, negar, inclinar, olhar em volta).
Coordenadas: as do modelo (Blender: Z para cima, ela olha para -Y, a vista de frente do Blender).
"""
import json
import math
import os
import shutil
import sys

import bpy
import numpy as np
from mathutils import Quaternion, Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import delaunay_2d_cdt

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
from rosto_comum import (Eixos, carregar_atlas, carregar_marcas, curva, dentro, distancia,  # noqa: E402
                         distancia_com_sinal, reamostrar, suave)

FONTE = os.path.join(AQUI, "fonte", "ametista_3d.glb")
PASTA_ROSTO = os.path.join(AQUI, "rosto")
MARCAS = carregar_marcas()
ATLAS = carregar_atlas()
EIX = Eixos(MARCAS)
with open(os.path.join(PASTA_ROSTO, "frente.json"), encoding="utf-8") as _f:
    JANELA = json.load(_f)                        # que pedaço do modelo a foto do rosto mostra
PX = JANELA["pixels"] / (JANELA["x1"] - JANELA["x0"])        # pixels da foto por unidade do modelo
ESC = EIX.s / 81.0                # as medidas das expressões foram pensadas para ~81 px entre o meio do rosto e um olho
REDUZIR = 0.30                    # quanto do número de triângulos do modelo fica (o rosto fica com mais)
LADO_COR = 1024                   # a cor do corpo (o modelo vem com 4096; o rosto tem a textura própria, bem mais fina)
# quanto cada camada fica à frente da pele do modelo (unidades; ~1 mm)
# (negativo = atrás da pele: sob a máscara o modelo é aberto, e o branco dos olhos e a boca por dentro ficam no
# fundo, como de verdade)
AFASTA = {"rosto": 0.0012, "olho": -0.0012, "iris": -0.0006, "cilios": 0.0019, "boca": -0.0045, "blush": 0.0015}
SUMIR_MASCARA = 16                # a borda da máscara que some aos poucos (o mesmo do preparar_rosto.py), em pixels
OSSOS = ["raiz", "peito", "pescoco", "cabeca"]
PIVOS = {"raiz": ((0.0, 0.0, 0.0), None), "peito": ((0.0, 0.03, 0.30), "raiz"),
         "pescoco": ((0.0, 0.03, 0.47), "peito"), "cabeca": ((0.0, 0.02, 0.57), "pescoco")}


# ====================================================================== foto do rosto → modelo
def px_xz(P):
    P = np.asarray(P, float)
    return np.stack([JANELA["x0"] + P[:, 0] / PX, JANELA["z1"] - P[:, 1] / PX], axis=1)


class Superficie:
    """A pele do modelo (já reduzido): onde cada ponto da foto de frente cai nela."""

    def __init__(self, ob):
        self.bvh = BVHTree.FromObject(ob, bpy.context.evaluated_depsgraph_get())

    def projetar(self, P, afastar):
        xz = px_xz(P)
        V = np.zeros((len(P), 3))
        achou = np.zeros(len(P), bool)
        for i, (x, z) in enumerate(xz):
            loc, nor, _, _ = self.bvh.ray_cast(Vector((x, -3.0, z)), Vector((0.0, 1.0, 0.0)))
            if loc is None:
                V[i] = (x, 0.0, z)
                continue
            n = Vector(nor)
            if n.y > 0:
                n = -n
            V[i] = loc + n * afastar
            achou[i] = True
        if not achou.all() and achou.any():         # fora do modelo (não deve acontecer): a profundidade vizinha
            V[~achou, 1] = np.median(V[achou, 1])
        return V


def silhueta_queixo(sup):
    """A linha do queixo contra o pescoço, achada no próprio modelo: onde, descendo pela foto de frente, a pele
    salta para trás (do queixo para o pescoço). A máscara segue essa linha e o queixo desce até ela."""
    c = np.asarray(MARCAS["rosto"]["queixo"], float)
    pontos = []
    for x in np.arange(c[0] - 150 * ESC / 1.44, c[0] + 150 * ESC / 1.44, 2.0):
        ys = np.arange(c[1] - 60 * ESC / 1.44, c[1] + 50 * ESC / 1.44, 0.5)
        prof = sup.projetar(np.stack([np.full_like(ys, x), ys], 1), 0.0)[:, 1]
        salto = np.nonzero(np.diff(prof) > 0.01)[0]
        if len(salto):
            pontos.append((x, ys[salto[0]] + 0.25))
    P = np.array(pontos)
    # só a parte contínua em volta do queixo (sem pular para mechas de cabelo)
    meio = np.argmin(np.abs(P[:, 0] - c[0]))
    ok = [meio]
    for passo in (1, -1):
        k = meio
        while 0 <= k + passo < len(P) and abs(P[k + passo, 1] - P[k, 1]) < 6:
            k += passo
            ok.append(k)
    P = P[sorted(ok)]
    P[:, 1] = np.convolve(np.pad(P[:, 1], 2, mode="edge"), np.ones(5) / 5, mode="valid")
    return P.tolist()


class SuperficieLisa:
    """Uma superfície lisa (quadrática) ajustada à pele numa região (a abertura do olho, a boca): o branco dos
    olhos, a íris e a boca por dentro ficam nela, atrás da pele, sem seguir o relevo fino do modelo (que as faria
    atravessar a máscara nos vincos)."""

    def __init__(self, sup, amostras):
        A = np.asarray(amostras, float)
        prof = sup.projetar(A, 0.0)[:, 1]
        self.c = A.mean(axis=0)
        self.coef = np.linalg.lstsq(self._base(A), prof, rcond=None)[0]

    def _base(self, P):
        u, v = (np.asarray(P, float) - self.c).T / 100.0
        return np.stack([np.ones_like(u), u, v, u * u, u * v, v * v], axis=1)

    def projetar(self, P, afastar):
        xz = px_xz(P)
        y = self._base(P) @ self.coef - afastar
        return np.stack([xz[:, 0], y, xz[:, 1]], axis=1)


def pontos_dentro(poli, passo=2.0, encolher=0.0):
    q = np.asarray(poli, float)
    xs = np.arange(q[:, 0].min(), q[:, 0].max(), passo)
    ys = np.arange(q[:, 1].min(), q[:, 1].max(), passo)
    P = np.stack(np.meshgrid(xs, ys), -1).reshape(-1, 2)
    return P[distancia_com_sinal(P, poli) > encolher]


def recortar(P, F, poli, margem):
    """Só os triângulos perto do polígono (dentro dele, ou até 'margem' pixels fora)."""
    cent = np.array([P[list(f)].mean(axis=0) for f in F])
    return [f for f, ok in zip(F, distancia_com_sinal(cent, poli) > -margem) if ok]


def uv_de(P, parte):
    """Onde cada ponto pega a cor no atlas do rosto (a parte da foto correspondente)."""
    info = ATLAS["partes"][parte]
    (ox, oy), (x0, y0) = info["origem"], info["caixa"][:2]
    lado = ATLAS["lado"]
    P = np.asarray(P, float)
    return np.stack([(ox + P[:, 0] - x0) / lado, 1 - (oy + P[:, 1] - y0) / lado], axis=1)


# ====================================================================== ossos: quanto cada ponto segue cada osso
def pesos_ossos(V):
    """A cabeça (com o queixo inteiro) segue o osso cabeca; o pescoço mistura; o resto é o peito."""
    V = np.asarray(V, float)
    x, y, z = V[:, 0], V[:, 1], V[:, 2]
    ref = 0.555 + 0.05 * np.clip((y + 0.13) / 0.28, 0, 1)        # a linha do queixo, subindo para a nuca
    cab = suave(ref - 0.035, ref, z)
    pesc = (1 - cab) * suave(0.44, 0.5, z)
    peito = (1 - cab - pesc) * suave(0.02, 0.1, z)
    w = np.stack([1 - cab - pesc - peito, peito, pesc, cab], axis=1)
    w = np.clip(w, 0, 1)
    w[w < 0.004] = 0
    return w / w.sum(axis=1, keepdims=True)


# ====================================================================== a máscara do rosto
def poligono_olho(o):
    return o["cima"] + o["baixo"][::-1][1:-1]


def poligono_boca():
    b = MARCAS["boca"]
    return b["fresta_cima"] + b["fresta_baixo"][::-1][1:-1]


def buracos():
    return [poligono_olho(MARCAS["olho_d"]), poligono_olho(MARCAS["olho_e"]), poligono_boca()]


def espacamento(P):
    """O tamanho dos triângulos: bem pequenos em volta dos olhos e da boca, médios no resto do rosto."""
    d = np.full(len(P), 1e9)
    for poli in buracos():
        d = np.minimum(d, distancia(P, poli, fechada=True)[0])
    ds = np.minimum(distancia(P, MARCAS["sobrancelha_d"])[0], distancia(P, MARCAS["sobrancelha_e"])[0])
    dm = distancia(P, MARCAS["mandibula"])[0]
    return np.minimum.reduce([2.6 + 0.3 * d, 4.5 + 0.3 * ds, 2.6 + 0.3 * dm, np.full(len(P), 9.0)])


def _mais_perto(C, A, bloco=1500):
    if not len(A):
        return np.full(len(C), 1e9)
    out = np.empty(len(C))
    for i in range(0, len(C), bloco):
        c = C[i:i + bloco]
        out[i:i + bloco] = np.sqrt(((c[:, None, :] - A[None, :, :]) ** 2).sum(-1)).min(axis=1)
    return out


def pontos_soltos(x0, y0, x1, y1, espaco, niveis=(2.8, 4.0, 5.6, 8.0, 11.3, 16.0)):
    """Pontos bem distribuídos (redes hexagonais de vários tamanhos, cada uma onde o espaçamento pede)."""
    aceitos = np.zeros((0, 2))
    for k, r in enumerate(niveis):
        linhas = []
        for i, y in enumerate(np.arange(y0 + r * 0.5, y1 - r * 0.3, r * 0.866)):
            xs = np.arange(x0 + (r * 0.5 if i % 2 == 0 else r), x1 - r * 0.3, r)
            linhas.append(np.stack([xs, np.full_like(xs, y)], 1))
        C = np.vstack(linhas)
        e = espaco(C)
        prox = niveis[k + 1] if k + 1 < len(niveis) else 1e9
        C = C[(e < prox * 0.93) & ((e >= r * 0.93) | (k == 0))]
        C = C[_mais_perto(C, aceitos) >= 0.72 * r]
        aceitos = np.vstack([aceitos, C])
    return aceitos


def triangular(pontos, restricoes, tirar):
    """Delaunay com as linhas marcadas (contornos dos olhos, da boca, a mandíbula, a borda) como arestas da
    malha; tira os triângulos dentro dos polígonos em 'tirar'."""
    verts, arestas = [], []
    for linha, fechada in restricoes:
        ini = len(verts)
        verts += [tuple(p) for p in linha]
        n = len(linha)
        arestas += [(ini + i, ini + (i + 1) % n) for i in range(n if fechada else n - 1)]
    verts += [tuple(p) for p in pontos]
    res = delaunay_2d_cdt([Vector(p) for p in verts], arestas, [], 0, 1e-5)
    V = np.array([tuple(v) for v in res[0]])
    F = [f for f in res[2] if len(f) == 3]
    cent = np.array([V[list(f)].mean(axis=0) for f in F])
    fora = np.zeros(len(F), bool)
    for poli in tirar:
        fora |= dentro(cent, poli)
    return V, [f for f, x in zip(F, fora) if not x]


def malha_rosto():
    borda = reamostrar(MARCAS["contorno_rosto"], 6.0, fechada=True)
    restr = [(borda, True)]
    for poli in buracos():
        restr.append((reamostrar(poli, 1.6, fechada=True), True))
    mand = np.asarray(MARCAS["mandibula"], float)
    mand = mand[dentro(mand, MARCAS["contorno_rosto"])]
    restr.append((reamostrar(mand, 2.4), False))
    fixos = np.vstack([r[0] for r in restr])
    c = np.asarray(MARCAS["contorno_rosto"], float)
    P = pontos_soltos(c[:, 0].min(), c[:, 1].min(), c[:, 0].max(), c[:, 1].max(), espacamento,
                      niveis=(2.6, 3.7, 5.2, 7.4, 9.0))
    P = P[dentro(P, MARCAS["contorno_rosto"])]
    P = P[_mais_perto(P, fixos) >= 0.55 * espacamento(P)]
    for poli in buracos():
        P = P[~dentro(P, poli)]
    V, F = triangular(P, restr, buracos())
    cent = np.array([V[list(f)].mean(axis=0) for f in F])
    return V, [f for f, ok in zip(F, dentro(cent, MARCAS["contorno_rosto"])) if ok]


# ====================================================================== expressões (deslocamentos em pixels)
class Olho:
    def __init__(self, o):
        self.o = o
        self.cima, (self.a0, self.a1) = curva(EIX, o["cima"])
        self.baixo, _ = curva(EIX, o["baixo"])

    def partes(self, P):
        ab = EIX.local(P)
        a, b = ab[:, 0], ab[:, 1]
        ac = np.clip(a, self.a0, self.a1)
        U, L = self.cima(ac), self.baixo(ac)
        fora = np.maximum(np.maximum(self.a0 - a, a - self.a1), 0)
        lat = np.exp(-(fora / (5.0 * ESC)) ** 2)
        meio = np.sin(np.pi * np.clip((ac - self.a0) / (self.a1 - self.a0), 0, 1)) ** 0.6
        return a, b, U, L, lat, meio

    def pele(self, P):
        """Pálpebras na malha da pintura: a de cima desce até a de baixo (a pele entre o vinco e os cílios estica),
        a de baixo sobe um pouco."""
        a, b, U, L, lat, meio = self.partes(P)
        K = U - self.o["vinco"]
        Mb = L + self.o["prega_baixo"]
        C = L + 0.12 * (U - L)
        cima = np.clip((b - K) / np.maximum(U - K, 1e-6), 0, 1) * (b <= U + 0.01) * lat
        baixo = np.clip((Mb - b) / np.maximum(Mb - L, 1e-6), 0, 1) * (b >= L - 0.01) * lat
        abertura = L - U
        Mf = L + 18 * ESC
        baixo_f = np.clip((Mf - b) / np.maximum(Mf - L, 1e-6), 0, 1) * (b >= L - 0.01) * lat
        z = np.zeros(len(P))
        return {
            "piscar": (EIX.vetor(0, cima * (C - U) + baixo * (C - L)), z + 1.5 * ESC * cima),
            "olhos_felizes": (EIX.vetor(0, cima * 0.12 * abertura - baixo_f * 0.5 * abertura), z),
            "arregalar": (EIX.vetor(0, (-cima * 4.5 * meio + baixo * 1.5 * meio) * ESC), z),
        }

    def cilios(self, P):
        """Os cílios de cima: na piscada giram em volta da linha da pálpebra e ficam apontando para baixo."""
        a, b, U, L, lat, meio = self.partes(P)
        C = L + 0.12 * (U - L)
        acima = U - b
        abertura = L - U
        z = np.zeros(len(P))
        return {
            "piscar": (EIX.vetor(0, (C - U) + 1.55 * acima), z + 1.5 * ESC),
            "olhos_felizes": (EIX.vetor(0, 0.12 * abertura), z),
            "arregalar": (EIX.vetor(0, -4.5 * ESC * meio), z),
        }


def olhar(P):
    z = np.zeros(len(P))
    um = np.ones(len(P)) * ESC
    return {"olhar_direita": (np.stack([6 * um, 0 * um], 1), z), "olhar_esquerda": (np.stack([-6 * um, 0 * um], 1), z),
            "olhar_cima": (np.stack([0 * um, -4 * um], 1), z), "olhar_baixo": (np.stack([0 * um, 4 * um], 1), z)}


class Boca:
    # abre (queixo), largura dos cantos, cantos para cima, lábio de cima sobe, lábio de baixo sobe, bico
    FORMAS = {
        "boca_a": (13.0, -2.0, 0.0, 1.5, 0.0, 0.0),
        "boca_e": (6.0, 4.0, 1.0, 1.5, 0.0, 0.0),
        "boca_i": (3.5, 6.0, 1.5, 2.0, 0.0, 0.0),
        "boca_o": (10.0, -9.0, 0.0, 1.5, 0.0, 1.0),
        "boca_u": (4.5, -13.0, 0.0, 0.5, 0.0, 1.4),
        "sorriso": (0.0, 4.0, 6.0, 0.5, 2.5, 0.0),
        "triste": (0.0, -1.0, -3.0, 0.0, 1.0, 0.0),
        "bravo": (0.0, -2.0, -1.5, 0.0, 5.5, 0.0),
    }

    def __init__(self):
        b = MARCAS["boca"]
        self.top, (self.am0, self.am1) = curva(EIX, b["fresta_cima"])
        self.bot, _ = curva(EIX, b["fresta_baixo"])
        self.T, _ = curva(EIX, b["labio_cima"])
        self.B, _ = curva(EIX, b["labio_baixo"])
        self.cantos = [np.array(b["fresta_cima"][0], float), np.array(b["fresta_cima"][-1], float)]
        self.meio = (self.am0 + self.am1) / 2
        self.hw = (self.am1 - self.am0) / 2
        self.queixo = np.array(MARCAS["rosto"]["queixo"], float)

    def campos(self, P):
        ab = EIX.local(P)
        a, b = ab[:, 0], ab[:, 1]
        ac = np.clip(a, self.am0, self.am1)
        top, bot, T, B = self.top(ac), self.bot(ac), self.T(ac), self.B(ac)
        gm = (top + bot) / 2
        fora = np.maximum(np.maximum(self.am0 - a, a - self.am1), 0)
        lat = np.exp(-(fora / (22.0 * ESC)) ** 2)
        baixo = b > gm
        dB = b - B
        # o lábio de baixo desce mais no meio e quase nada nos cantos (a boca abre em forma de lente)
        cantos = suave(-0.1 * self.hw, 0.55 * self.hw, np.minimum(a - self.am0, self.am1 - a))
        labio_b = np.where(dB <= 0, 1.0, np.exp(-(dB / (10.0 * ESC)) ** 2)) * baixo * lat * cantos
        labio_b_so = np.where(dB <= 0, 1.0, np.exp(-(dB / (6.0 * ESC)) ** 2)) * baixo * lat * cantos
        dq = np.linalg.norm(P - self.queixo, axis=1)
        # o queixo desce até a linha da mandíbula (o contorno do queixo contra o pescoço); o pescoço fica
        mand, (m0, m1) = curva(EIX, MARCAS["mandibula"])
        acima = suave(-1.5 * ESC, 1.5 * ESC, mand(np.clip(a, m0, m1)) - b)
        queixo = 0.62 * np.clip(1 - dq / (160.0 * ESC), 0, 1) * suave(-6 * ESC, 8 * ESC, b - gm) * acima
        wl = labio_b + (1 - labio_b) * queixo
        dT = T - b
        wu = (~baixo) * np.where(b >= T, 1.0, np.exp(-(dT / (7.0 * ESC)) ** 2)) * lat
        perto = np.minimum(np.abs(b - T), np.abs(b - B))
        labios = np.where((b >= T) & (b <= B), 1.0, np.exp(-(perto / (5.0 * ESC)) ** 2)) * lat
        rel = np.clip((a - self.meio) / self.hw, -1.25, 1.25)
        fresta = np.maximum(bot - top, 0)
        bochechas = np.zeros(len(P))
        for c, lado in zip(self.cantos, (-1, 1)):
            centro = EIX.tela(EIX.local(c) + np.array([lado * 20, -26]) * ESC)
            bochechas += np.exp(-(np.linalg.norm(P - centro, axis=1) / (28.0 * ESC)) ** 2)
        return dict(a=a, b=b, wl=wl, wu=wu, labios=labios, rel=rel, fresta=fresta, labio_b_so=labio_b_so,
                    bochechas=bochechas, bot=bot)

    def pele(self, P):
        c = self.campos(P)
        out = {}
        for nome, forma in self.FORMAS.items():
            D, dw, cu, uu, lu, bico = (v * ESC for v in forma)
            da = dw * c["rel"] * c["labios"]
            db = D * c["wl"] - uu * c["wu"] - cu * c["rel"] ** 2 * c["labios"] - 0.35 * cu * c["bochechas"]
            db -= np.minimum(lu, 0.85 * c["fresta"]) * c["labio_b_so"]
            out[nome] = (EIX.vetor(da, db), bico * 3.0 * c["labios"])
        return out

    def dentro(self, P):
        """Por dentro: os dentes de cima ficam; o que está atrás do lábio de baixo desce com o queixo (um pouco
        menos que o lábio, para a língua aparecer)."""
        c = self.campos(P)
        corte = c["bot"] - 1.5 * ESC
        desce = suave(corte - 1.0 * ESC, corte + 1.5 * ESC, c["b"])
        out = {}
        for nome, forma in self.FORMAS.items():
            D, dw, cu, uu, lu, bico = (v * ESC for v in forma)
            if D == 0:
                continue
            out[nome] = (EIX.vetor(0, 0.72 * D * desce), np.zeros(len(P)))
        return out


def sobrancelhas(P):
    """Sobrancelhas: sobem, franzem (a ponta de dentro desce e vem para o meio), ficam tristes (a de dentro sobe)."""
    out = {k: (np.zeros((len(P), 2)), np.zeros(len(P))) for k in
           ("sobrancelhas_cima", "sobrancelhas_bravas", "sobrancelhas_tristes", "sobrancelha_pensativa")}
    ab = EIX.local(P)
    for nome_s, nome_o, para_dentro, pensa in (("sobrancelha_d", "olho_d", -1, 1.0), ("sobrancelha_e", "olho_e", 1, -0.3)):
        linha = MARCAS[nome_s]
        d, t = distancia(P, linha)
        w = np.exp(-(d / (13.0 * ESC)) ** 2)
        # não mexe na pálpebra (abaixo do vinco do olho)
        o = Olho(MARCAS[nome_o])
        ac = np.clip(ab[:, 0], o.a0, o.a1)
        K = o.cima(ac) - o.o["vinco"]
        dentro_a = (ab[:, 0] > o.a0 - 6 * ESC) & (ab[:, 0] < o.a1 + 6 * ESC)
        protege = np.where(dentro_a, np.clip((K - ab[:, 1]) / (8.0 * ESC), 0, 1), 1.0)
        w *= protege * ESC
        dentro_ = 1 - t
        z = np.zeros(len(P))
        out["sobrancelhas_cima"] = (out["sobrancelhas_cima"][0] + EIX.vetor(0, -5 * w), z)
        out["sobrancelhas_bravas"] = (out["sobrancelhas_bravas"][0] + EIX.vetor(para_dentro * 2.5 * dentro_ * w,
                                      (4 * dentro_ - 1 * t) * w), z)
        out["sobrancelhas_tristes"] = (out["sobrancelhas_tristes"][0] + EIX.vetor(para_dentro * 1.0 * dentro_ * w,
                                       (-5 * dentro_ + 1.5 * t) * w), z)
        out["sobrancelha_pensativa"] = (out["sobrancelha_pensativa"][0] + EIX.vetor(0, -4 * pensa * w), z)
    return out


def aro_rigido(P):
    """O aro do monóculo é de metal: não entorta quando a pele em volta mexe."""
    a = MARCAS["aro"]
    (cx, cy), (rx, ry), hw = a["centro"], a["raios"], a["meia_largura"]
    el = np.sqrt(((P[:, 0] - cx) / rx) ** 2 + ((P[:, 1] - cy) / ry) ** 2)
    dr = np.abs(el - 1) * (rx + ry) / 2
    r = 1 - suave(hw, hw + 3 * ESC, dr)
    for poli in a["enfeites"]:
        r = np.maximum(r, suave(-2, 2, distancia_com_sinal(P, poli)))
    return r


def juntar(*dicts):
    out = {}
    for d in dicts:
        for k, (dxy, dz) in d.items():
            if k in out:
                out[k] = (out[k][0] + dxy, out[k][1] + dz)
            else:
                out[k] = (dxy, dz)
    return out


# ====================================================================== Blender
def limpar():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def material(nome, img=None, transparente=False, cor=None):
    """Sem luz (a cor do modelo já tem a luz dela): o Background do Blender vira KHR_materials_unlit no glb."""
    m = bpy.data.materials.new(nome)
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    saida = nt.nodes.new("ShaderNodeOutputMaterial")
    fundo = nt.nodes.new("ShaderNodeBackground")
    if img is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.interpolation = "Linear"
        nt.links.new(tex.outputs["Color"], fundo.inputs["Color"])
    else:
        fundo.inputs["Color"].default_value = (*cor, 1.0)
    if transparente:
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        if img is not None:
            nt.links.new(tex.outputs["Alpha"], mix.inputs["Fac"])
        else:
            mix.inputs["Fac"].default_value = 0.5
        nt.links.new(tr.outputs[0], mix.inputs[1])
        nt.links.new(fundo.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], saida.inputs["Surface"])
        m.surface_render_method = "BLENDED"
    else:
        nt.links.new(fundo.outputs[0], saida.inputs["Surface"])
    return m


def esqueleto(raiz):
    arm = bpy.data.armatures.new("Esqueleto")
    ob = bpy.data.objects.new("Esqueleto", arm)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = raiz
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    for nome in OSSOS:                          # todos em pé (sem giro de repouso: o app gira em volta do pivô)
        p, pai = PIVOS[nome]
        b = arm.edit_bones.new(nome)
        b.head = p
        b.tail = (p[0], p[1], p[2] + 0.05)
        b.roll = 0
        if pai:
            b.parent = arm.edit_bones[pai]
    bpy.ops.object.mode_set(mode="OBJECT")
    ob.show_in_front = True
    return ob


def ligar_ossos(ob, arm, W):
    grupos = [ob.vertex_groups.get(o) or ob.vertex_groups.new(name=o) for o in OSSOS]
    for j, g in enumerate(grupos):
        col = W[:, j]
        for valor in np.unique(np.round(col[col > 0.004], 3)):
            g.add(np.nonzero(np.abs(np.round(col, 3) - valor) < 1e-9)[0].tolist(), float(valor), "REPLACE")
    mod = ob.modifiers.new("Esqueleto", "ARMATURE")
    mod.object = arm
    ob.parent = arm


def objeto(nome, V, F, uv, mats, arm, chaves=None):
    """Uma peça: vértices já no lugar (V, coordenadas do Blender); chaves = {nome: posições (N, 3)}."""
    V = np.asarray(V, float)
    me = bpy.data.meshes.new(nome)
    me.from_pydata(V.tolist(), [], [list(map(int, f)) for f in F])
    me.validate(clean_customdata=False)
    for m in mats:
        me.materials.append(m)
    camada = me.uv_layers.new(name="UV")
    idx = np.zeros(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", idx)
    camada.data.foreach_set("uv", np.asarray(uv, np.float32)[idx].ravel())
    me.update()
    ob = bpy.data.objects.new(nome, me)
    bpy.context.scene.collection.objects.link(ob)
    ligar_ossos(ob, arm, pesos_ossos(V))
    if chaves:
        ob.shape_key_add(name="Basis", from_mix=False)
        for k, Vk in chaves.items():
            Vk = np.asarray(Vk, float)
            parado = np.abs(Vk - V).max(axis=1) < 2e-5                  # o resto do rosto não se mexe
            Vk = np.where(parado[:, None], V, Vk)
            if parado.all():
                continue
            sk = ob.shape_key_add(name=k, from_mix=False)
            sk.data.foreach_set("co", Vk.ravel())
            sk.value = 0.0
    return ob


def chaves_na_pele(sup, P, desloc, afastar, colar):
    """Deslocamentos em pixels da foto → posições no modelo. 'colar': as que escorregam pela pele (pálpebras,
    sobrancelhas, olhar) são projetadas de novo na superfície; as outras (a boca, o queixo) só andam."""
    V0 = sup.projetar(P, afastar)
    out = {}
    for nome, (dxy, dz) in desloc.items():
        if np.abs(dxy).max() < 0.05 and np.abs(dz).max() < 0.05:
            continue
        mexe = (np.abs(dxy).max(axis=1) > 0.02) | (np.abs(dz) > 0.02)
        Vk = V0.copy()
        if colar(nome):
            Vk[mexe] = sup.projetar(P[mexe] + dxy[mexe], afastar)
            Vk[mexe, 1] -= dz[mexe] / PX
        else:
            Vk[mexe, 0] += dxy[mexe, 0] / PX
            Vk[mexe, 2] -= dxy[mexe, 1] / PX
            Vk[mexe, 1] -= dz[mexe] / PX
        out[nome] = Vk
    return V0, out


def colar_na_pele(nome):
    return not (nome.startswith("boca_") or nome in ("sorriso", "triste", "bravo"))


def grade(x0, y0, x1, y1, passo):
    nx, ny = max(2, int(round((x1 - x0) / passo)) + 1), max(2, int(round((y1 - y0) / passo)) + 1)
    xs, ys = np.linspace(x0, x1, nx), np.linspace(y0, y1, ny)
    P = np.stack(np.meshgrid(xs, ys), -1).reshape(-1, 2)
    F = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            F += [(a, a + 1, a + nx + 1), (a, a + nx + 1, a + nx)]
    return P, F


def disco(c, r, aneis=7, voltas=28):
    P = [c]
    for k in range(1, aneis + 1):
        rr = r * k / aneis
        for i in range(voltas):
            t = 2 * math.pi * i / voltas
            P.append([c[0] + rr * math.cos(t), c[1] + rr * math.sin(t)])
    F = [(0, 1 + i, 1 + (i + 1) % voltas) for i in range(voltas)]
    for k in range(1, aneis):
        a0, a1 = 1 + (k - 1) * voltas, 1 + k * voltas
        for i in range(voltas):
            j = (i + 1) % voltas
            F += [(a0 + i, a1 + i, a1 + j), (a0 + i, a1 + j, a0 + j)]
    return np.array(P, float), F


def quadrado(c, w, h, ang=0.0):
    ca, sa = math.cos(ang), math.sin(ang)
    cant = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    P = np.array([[c[0] + x * ca - y * sa, c[1] + x * sa + y * ca] for x, y in cant])
    return P, [(0, 1, 2), (0, 2, 3)], np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)


def abrir_rosto(ob, sup):
    """Tira do modelo a pele do rosto que a máscara cobre por inteiro (fora a borda, onde as duas se misturam):
    ali a máscara é a pele. Sem isso, o relevo fino do modelo (cílios, vincos) atravessaria a máscara, e pelos
    buracos dela (olhos e boca) apareceria a pintura do modelo em vez do branco dos olhos e da boca por dentro."""
    import bmesh

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    faces = list(bm.faces)
    C = np.array([f.calc_center_median()[:] for f in faces])
    P = np.stack([(C[:, 0] - JANELA["x0"]) * PX, (JANELA["z1"] - C[:, 2]) * PX], axis=1)
    # a face inteira (todos os cantos) bem dentro da máscara, depois da borda que some aos poucos
    Vt = np.array([v.co[:] for v in bm.verts])
    for i, v in enumerate(bm.verts):
        v.index = i
    Pv = np.stack([(Vt[:, 0] - JANELA["x0"]) * PX, (JANELA["z1"] - Vt[:, 2]) * PX], axis=1)
    dv = distancia_com_sinal(Pv, MARCAS["contorno_rosto"])
    dentro_f = np.array([min(dv[v.index] for v in f.verts) for f in faces])
    cand = np.nonzero((C[:, 1] < 0.02) & (dentro_f > SUMIR_MASCARA + 3))[0]
    frente = sup.projetar(P[cand], 0.0)[:, 1]
    perto = np.abs(C[cand, 1] - frente) < 0.006            # só a camada da frente (não a nuca, nem o coque)
    b = MARCAS["boca"]
    fundo = np.zeros(len(cand), bool)                      # nas aberturas, também o fundo (vincos, cavidades)
    for poli in (poligono_olho(MARCAS["olho_d"]), poligono_olho(MARCAS["olho_e"]),
                 b["labio_cima"] + b["labio_baixo"][::-1][1:-1]):
        fundo |= (distancia_com_sinal(P[cand], poli) > -9 * ESC) & (C[cand, 1] - frente < 0.025)
    tirar = cand[perto | fundo]
    bmesh.ops.delete(bm, geom=[faces[i] for i in tirar], context="FACES")
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    return len(tirar)


def corpo_do_modelo():
    """O modelo 3D: menos triângulos (o rosto e o cabelo em volta dele guardam mais) e a cor em 2048."""
    bpy.ops.import_scene.gltf(filepath=FONTE)
    ob = next(o for o in bpy.context.scene.objects if o.type == "MESH")
    ob.name = ob.data.name = "Corpo"
    V = np.array([v.co[:] for v in ob.data.vertices])
    x, y, z = V[:, 0], V[:, 1], V[:, 2]
    frente = suave(-0.02, -0.07, y) * suave(0.54, 0.58, z) * suave(0.88, 0.84, z) * suave(0.16, 0.12, np.abs(x))
    g = ob.vertex_groups.new(name="reduzir")
    for valor in np.unique(np.round(1 - frente, 2)):
        g.add(np.nonzero(np.abs(np.round(1 - frente, 2) - valor) < 1e-9)[0].tolist(), float(valor), "REPLACE")
    mod = ob.modifiers.new("Reduzir", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = REDUZIR
    mod.vertex_group = "reduzir"
    mod.vertex_group_factor = 4.0
    mod.use_collapse_triangulate = True
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    ob.vertex_groups.remove(ob.vertex_groups["reduzir"])
    # a cor: 4096 → 2048, guardada ao lado (o .blend aponta para ela)
    img = next(n.image for n in ob.active_material.node_tree.nodes if n.type == "TEX_IMAGE")
    img.scale(LADO_COR, LADO_COR)
    cena = bpy.context.scene
    cena.view_settings.view_transform = "Standard"     # sem o AgX: a cor sai igual à do modelo
    cena.view_settings.look = "None"
    cena.view_settings.exposure = 0.0
    cena.view_settings.gamma = 1.0
    cena.render.image_settings.file_format = "WEBP"
    cena.render.image_settings.quality = 88
    cena.render.image_settings.color_mode = "RGB"
    caminho = os.path.join(AQUI, "fonte", "cor_corpo.webp")
    img.save_render(caminho, scene=cena)
    bpy.data.images.remove(img)
    cor = bpy.data.images.load(caminho)
    cor.name = "cor_corpo"
    antigo = ob.active_material
    ob.data.materials.clear()
    bpy.data.materials.remove(antigo)              # o do modelo importado (o nome "corpo" fica para o novo)
    ob.data.materials.append(material("corpo", cor))
    sup = Superficie(ob)                     # a pele inteira, antes de abrir o rosto
    abrir_rosto(ob, sup)
    return ob, sup


def construir():
    limpar()
    corpo, sup = corpo_do_modelo()
    atlas = bpy.data.images.load(os.path.join(PASTA_ROSTO, "atlas.png"))
    atlas.name = "rosto_ametista"
    atlas.alpha_mode = "STRAIGHT"
    m_rosto = material("rosto", atlas, transparente=True)
    m_olho = material("olho", atlas)
    m_iris = material("iris", atlas, transparente=True)
    m_cilios = material("cilios", atlas, transparente=True)
    m_boca = material("boca_dentro", atlas)
    m_blush = material("blush", cor=(1.0, 0.45, 0.6), transparente=True)

    MARCAS["mandibula"] = silhueta_queixo(sup)
    raiz = bpy.data.objects.new("Ametista", None)
    bpy.context.scene.collection.objects.link(raiz)
    # para o app enquadrar (coordenadas do glb: x, y para cima): o busto nas molduras altas, o rosto nas quadradas
    raiz["quadro_tudo"] = [0.0, 0.695, 0.55]            # centro x, centro y, altura
    raiz["quadro_rosto"] = [0.0, 0.705, 0.34]
    raiz["inclinacao_rosto"] = math.atan2(-EIX.ex[1], EIX.ex[0])
    arm = esqueleto(raiz)
    bpy.context.view_layer.update()
    ligar_ossos(corpo, arm, pesos_ossos([v.co[:] for v in corpo.data.vertices]))
    objs = [corpo]

    # a máscara do rosto
    P, F = malha_rosto()
    olhos = {"direito": Olho(MARCAS["olho_e"]), "esquerdo": Olho(MARCAS["olho_d"])}   # o direito dela = o da esquerda da tela
    boca = Boca()
    desloc = {}
    for lado, o in olhos.items():
        for k, v in o.pele(P).items():
            desloc = juntar(desloc, {f"piscar_{lado}" if k == "piscar" else k: v})
    desloc = juntar(desloc, boca.pele(P), sobrancelhas(P))
    rigido = aro_rigido(P)
    desloc = {k: (dxy * (1 - rigido)[:, None], dz * (1 - rigido)) for k, (dxy, dz) in desloc.items()}
    V0, ch = chaves_na_pele(sup, P, desloc, AFASTA["rosto"], colar_na_pele)
    objs.append(objeto("Rosto", V0, F, uv_de(P, "rosto"), [m_rosto], arm, ch))

    # os olhos: o branco, a íris e os cílios
    for lado, nome_o, sufixo in (("direito", "olho_e", "e"), ("esquerdo", "olho_d", "d")):
        o = MARCAS[nome_o]
        poli_o = poligono_olho(o)
        lisa = SuperficieLisa(sup, pontos_dentro(poli_o, 1.5, 1.5))
        x0, y0, x1, y1 = ATLAS["partes"]["globo_" + sufixo]["caixa"]
        Pg, Fg = grade(x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 0.5, 2.5 * ESC)
        Fg = recortar(Pg, Fg, poli_o, 10 * ESC)
        objs.append(objeto(f"Olho_{sufixo.upper()}", lisa.projetar(Pg, AFASTA["olho"]), Fg,
                           uv_de(Pg, "globo_" + sufixo), [m_olho], arm))
        cx, cy, r = o["iris"]
        Pi, Fi = disco([cx, cy], r + 2.5, aneis=10, voltas=40)
        Fi = recortar(Pi, Fi, poli_o, 9 * ESC)
        V0, ch = chaves_na_pele(lisa, Pi, olhar(Pi), AFASTA["iris"], lambda n: True)
        objs.append(objeto(f"Iris_{sufixo.upper()}", V0, Fi, uv_de(Pi, "iris_" + sufixo), [m_iris], arm, ch))
        poli = o["cilios"] + o["cima"][::-1]
        cont = reamostrar(poli, 2.0, fechada=True)
        xs, ys = np.array(poli)[:, 0], np.array(poli)[:, 1]
        dentro_ = pontos_soltos(xs.min(), ys.min(), xs.max(), ys.max(), lambda Q: np.full(len(Q), 2.8), niveis=(2.8,))
        dentro_ = dentro_[dentro(dentro_, poli)]
        dentro_ = dentro_[_mais_perto(dentro_, cont) > 1.4]
        Pc, Fc = triangular(dentro_, [(cont, True)], [])
        cent = np.array([Pc[list(f)].mean(axis=0) for f in Fc])
        Fc = [f for f, c in zip(Fc, dentro(cent, poli)) if c]
        desl = {(f"piscar_{lado}" if k == "piscar" else k): v for k, v in olhos[lado].cilios(Pc).items()}
        V0, ch = chaves_na_pele(sup, Pc, desl, AFASTA["cilios"], lambda n: True)
        objs.append(objeto(f"Cilios_{sufixo.upper()}", V0, Fc, uv_de(Pc, "cilios_" + sufixo), [m_cilios], arm, ch))

    # por dentro da boca
    x0, y0, x1, y1 = ATLAS["partes"]["boca_dentro"]["caixa"]
    b = MARCAS["boca"]
    labios = b["labio_cima"] + b["labio_baixo"][::-1][1:-1]
    lisa = SuperficieLisa(sup, pontos_dentro(labios, 2.0, 2.0))
    Pb, Fb = grade(x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 0.5, 2.5 * ESC)
    # só o que pode aparecer pela boca aberta: entre os lábios, até um pouco abaixo da fresta (o resto ficaria
    # atrás do lábio de baixo e do queixo, e poderia atravessar a pele no vinco abaixo do lábio)
    Fb = recortar(Pb, Fb, labios, 9 * ESC)
    bot, _ = curva(EIX, b["fresta_baixo"])
    cent = np.array([Pb[list(f)].mean(axis=0) for f in Fb])
    ab = EIX.local(cent)
    Fb = [f for f, ok in zip(Fb, ab[:, 1] < bot(ab[:, 0]) + 12 * ESC) if ok]
    V0, ch = chaves_na_pele(lisa, Pb, boca.dentro(Pb), AFASTA["boca"], lambda n: False)
    objs.append(objeto("Boca_dentro", V0, Fb, uv_de(Pb, "boca_dentro"), [m_boca], arm, ch))

    # o rubor nas bochechas
    Pr, Fr, Ur = [], [], []
    for c, (w, h) in ((EIX.tela(EIX.local(MARCAS["rosto"]["olho_d"]) + np.array([14, 70]) * ESC), (74, 40)),
                      (EIX.tela(EIX.local(MARCAS["rosto"]["olho_e"]) + np.array([-8, 76]) * ESC), (66, 36))):
        g, f = grade(c[0] - w * ESC / 2, c[1] - h * ESC / 2, c[0] + w * ESC / 2, c[1] + h * ESC / 2, 8.0)
        Fr += [[i + sum(len(p) for p in Pr) for i in t] for t in f]
        Ur.append(np.stack([(g[:, 0] - g[:, 0].min()) / np.ptp(g[:, 0]), (g[:, 1] - g[:, 1].min()) / np.ptp(g[:, 1])], 1))
        Pr.append(g)
    Pr = np.vstack(Pr)
    objs.append(objeto("Blush", sup.projetar(Pr, AFASTA["blush"]), Fr, np.vstack(Ur), [m_blush], arm))

    # pontos de brilho nos cristais (o app faz as estrelinhas cintilarem)
    m_brilho = material("brilho", cor=(1.0, 1.0, 1.0), transparente=True)
    Pq, Fq, Uq = [], [], []
    for c in MARCAS["brilhos"]:
        q, f, uvq = quadrado(c, 6, 6)
        Fq += [[i + len(Pq) * 4 for i in t] for t in f]
        Pq.append(q)
        Uq.append(uvq)
    Pq = np.vstack(Pq)
    objs.append(objeto("Brilhos", sup.projetar(Pq, 0.003), Fq, np.vstack(Uq), [m_brilho], arm))

    camera_e_vista()
    bpy.context.view_layer.update()
    return objs


def camera_e_vista():
    """Uma câmera de frente para o busto, e a vista 3D já mostrando ela (com o material)."""
    cena = bpy.context.scene
    cam = bpy.data.cameras.new("Camera")
    cam.lens = 85
    ob = bpy.data.objects.new("Camera", cam)
    cena.collection.objects.link(ob)
    ob.location = (0, -2.2, 0.66)
    ob.rotation_euler = (math.pi / 2, 0, 0)
    cena.camera = ob
    cena.render.resolution_x, cena.render.resolution_y = 720, 1080
    cena.view_settings.view_transform = "Standard"
    for tela in bpy.data.screens:
        for area in tela.areas:
            if area.type != "VIEW_3D":
                continue
            for esp in area.spaces:
                if esp.type == "VIEW_3D":
                    esp.shading.type = "MATERIAL"
                    r3d = esp.region_3d
                    r3d.view_perspective = "PERSP"
                    r3d.view_rotation = Quaternion((math.sqrt(0.5), math.sqrt(0.5), 0, 0))
                    r3d.view_location = (0, 0, 0.66)
                    r3d.view_distance = 1.3


def exportar():
    blend = os.path.join(AQUI, "ametista.blend")
    glb = os.path.join(RAIZ, "web", "ametista.glb")
    bpy.context.preferences.filepaths.save_version = 0      # sem o backup .blend1
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True, relative_remap=True)
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", export_yup=True, export_apply=False,
                              export_texcoords=True, export_normals=False, export_morph=True,
                              export_morph_normal=False, export_try_sparse_sk=True, export_extras=True,
                              export_skins=True, export_all_influences=False, export_def_bones=False,
                              export_image_format="WEBP", export_image_quality=84,
                              export_animations=False, export_cameras=False, export_lights=False,
                              export_materials="EXPORT")
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
    tris = sum(len(o.data.polygons) for o in objs)
    verts = sum(len(o.data.vertices) for o in objs)
    blend, glb = exportar()
    print(f"Ametista em 3D: {len(objs)} objetos, {verts} vértices, {tris} triângulos")
    print(f"  {blend} ({os.path.getsize(blend) // 1024} KB)")
    print(f"  {glb} ({os.path.getsize(glb) // 1024} KB)")
    sys.stdout.flush()
