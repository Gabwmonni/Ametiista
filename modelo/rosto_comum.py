"""O que o preparar_rosto.py e o construir_ametista.py usam em comum: as marcações do rosto (na foto de frente
do modelo 3D) e a geometria em cima delas (só numpy, roda no Python normal e no do Blender)."""
import json
import os

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(AQUI, "rosto")


def carregar_marcas():
    with open(os.path.join(PASTA, "marcas.json"), encoding="utf-8") as f:
        return json.load(f)


def carregar_atlas():
    with open(os.path.join(PASTA, "atlas.json"), encoding="utf-8") as f:
        return json.load(f)


class Eixos:
    """Os eixos do rosto: 'a' vai do olho da esquerda ao da direita, 'b' desce (a cabeça está inclinada na
    pintura). Em pixels da pintura, com o zero entre os olhos."""

    def __init__(self, marcas):
        e, d = np.array(marcas["rosto"]["olho_e"], float), np.array(marcas["rosto"]["olho_d"], float)
        self.c = (e + d) / 2
        self.ex = (d - e) / np.linalg.norm(d - e)
        self.ey = np.array([-self.ex[1], self.ex[0]])
        self.s = np.linalg.norm(d - e) / 2               # meia distância entre os olhos

    def local(self, p):
        p = np.asarray(p, dtype=np.float64) - self.c
        return np.stack([p @ self.ex, p @ self.ey], axis=-1)

    def tela(self, ab):
        ab = np.asarray(ab, dtype=np.float64)
        return self.c + ab[..., :1] * self.ex + ab[..., 1:2] * self.ey

    def vetor(self, da, db):
        """Um deslocamento (da ao longo dos olhos, db para baixo no rosto) em pixels da pintura."""
        da, db = np.asarray(da, float), np.asarray(db, float)
        return da[..., None] * self.ex + db[..., None] * self.ey


def curva(eixos, pontos):
    """Uma linha marcada vira b(a) nos eixos do rosto; devolve a função e o intervalo de 'a'."""
    ab = eixos.local(pontos)
    ordem = np.argsort(ab[:, 0])
    a, b = ab[ordem, 0], ab[ordem, 1]
    return (lambda x: np.interp(x, a, b)), (float(a[0]), float(a[-1]))


def dentro(p, poligono):
    """Quais pontos estão dentro do polígono (par-ímpar)."""
    p = np.asarray(p, float)
    q = np.asarray(poligono, float)
    x, y = p[:, 0][:, None], p[:, 1][:, None]
    x1, y1 = q[:, 0][None, :], q[:, 1][None, :]
    x2, y2 = np.roll(q[:, 0], -1)[None, :], np.roll(q[:, 1], -1)[None, :]
    cruza = ((y1 > y) != (y2 > y)) & (x < (x2 - x1) * (y - y1) / np.where(y2 == y1, 1e-9, y2 - y1) + x1)
    return (np.count_nonzero(cruza, axis=1) % 2) == 1


def distancia(p, linha, fechada=False):
    """Distância de cada ponto até a linha (polilinha), e onde cai nela (0 no começo, 1 no fim)."""
    p = np.asarray(p, float)
    q = np.asarray(linha, float)
    if fechada:
        q = np.vstack([q, q[:1]])
    a, b = q[:-1], q[1:]
    ab = b - a
    comp = np.linalg.norm(ab, axis=1)
    acum = np.concatenate([[0], np.cumsum(comp)])
    ap = p[:, None, :] - a[None, :, :]
    t = np.clip((ap * ab[None]).sum(-1) / np.maximum((ab * ab).sum(-1), 1e-12)[None], 0, 1)
    perto = a[None] + t[..., None] * ab[None]
    d = np.linalg.norm(p[:, None, :] - perto, axis=-1)
    k = np.argmin(d, axis=1)
    i = np.arange(len(p))
    onde = (acum[k] + t[i, k] * comp[k]) / max(acum[-1], 1e-9)
    return d[i, k], onde


def distancia_com_sinal(p, poligono):
    """Positiva dentro do polígono, negativa fora."""
    d, _ = distancia(p, poligono, fechada=True)
    return np.where(dentro(p, poligono), d, -d)


def reamostrar(linha, passo, fechada=False):
    q = np.asarray(linha, float)
    if fechada:
        q = np.vstack([q, q[:1]])
    comp = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))])
    n = max(2, int(np.ceil(comp[-1] / passo)) + 1)
    t = np.linspace(0, comp[-1], n)
    out = np.stack([np.interp(t, comp, q[:, 0]), np.interp(t, comp, q[:, 1])], axis=1)
    return out[:-1] if fechada else out


def suave(a, b, x):
    t = np.clip((np.asarray(x, float) - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)
