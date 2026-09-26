"""Prepara o rosto da Ametista (a foto de frente do modelo 3D, rosto/frente.png) para a máscara animada.

A máscara é uma malha colada no rosto do modelo 3D, com a cor desta foto: parada, é igual ao modelo. Para ela
poder piscar, olhar e falar, algumas partes precisam existir separadas, e o que fica por baixo delas precisa ser
preenchido:

  * os cílios de cima viram uma camada própria (na piscada eles giram para baixo junto com a pálpebra), e a
    pálpebra por baixo deles é preenchida com a pele em volta;
  * o globo de cada olho (o branco) ganha a parte que a pálpebra esconde, e a íris vira um disco inteiro (a parte
    de cima, escondida, é completada pela de baixo);
  * a boca por dentro (dentes de cima, o escuro e a língua) aparece quando ela abre a boca;
  * nos buracos da máscara (olhos e boca) a foto é preenchida com a cor da borda, para a borda da pálpebra e dos
    lábios não levar um fio de branco quando mexe;
  * a borda da máscara some aos poucos (transparência), então ela se funde com o modelo em volta.

Tudo vai para um atlas de 1024 x 1024 (modelo/rosto/atlas.png) e as posições de cada parte para
modelo/rosto/atlas.json. O construir_ametista.py usa os dois.

Uso:  python modelo/preparar_rosto.py        (precisa de numpy, pillow e opencv-python-headless)
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

AQUI = Path(__file__).resolve().parent
PASTA = AQUI / "rosto"
sys.path.insert(0, str(AQUI))
from rosto_comum import Eixos, curva  # noqa: E402
LADO = 1024
BORDA = 6            # pixels repetidos em volta de cada parte (o mipmap não puxa preto das vizinhas)
SUMIR = 16           # quantos pixels a borda da máscara leva para sumir


def carregar():
    marcas = json.loads((PASTA / "marcas.json").read_text(encoding="utf-8"))
    x0, y0, x1, y1 = marcas["recorte"]
    foto = Image.open(PASTA / "frente.png").convert("RGBA")
    fundo = Image.new("RGBA", foto.size, (226, 212, 236, 255))
    fundo.alpha_composite(foto)
    return marcas, np.asarray(fundo.convert("RGB").crop((x0, y0, x1, y1))).astype(np.float32)


def poligono(pontos, forma):
    m = np.zeros(forma, np.uint8)
    cv2.fillPoly(m, [np.round(np.asarray(pontos) * 16).astype(np.int32)], 255, lineType=cv2.LINE_AA, shift=4)
    return m.astype(np.float32) / 255


def preencher(img, buraco, raio=4):
    """Preenche onde buraco > 0 com a cor em volta (cv2.inpaint, Telea)."""
    m = (buraco > 0.02).astype(np.uint8) * 255
    out = cv2.inpaint(np.clip(img, 0, 255).astype(np.uint8), m, raio, cv2.INPAINT_TELEA)
    return out.astype(np.float32)


def grade(forma):
    yy, xx = np.mgrid[0:forma[0], 0:forma[1]].astype(np.float64)
    return np.stack([xx + 0.5, yy + 0.5], axis=-1)


def luminancia(img):
    return img[..., 0] * 0.299 + img[..., 1] * 0.587 + img[..., 2] * 0.114


# ----------------------------------------------------------------------------------- partes
def cilios(img, eixos, olho):
    """Máscara dos cílios de cima (escuros sobre a pele rosada) dentro da área marcada, acima da linha dos cílios."""
    forma = img.shape[:2]
    cima, _ = curva(eixos, olho["cima"])
    area = poligono(olho["cilios"] + olho["cima"][::-1], forma)
    area = cv2.dilate(area, np.ones((3, 3), np.uint8))
    ab = eixos.local(grade(forma))
    acima = cima(ab[..., 0]) - ab[..., 1]                   # quanto o pixel está acima da linha dos cílios
    # os cílios são quase pretos no vermelho (R < ~130); a sombra rosa, o vinco e a rede de cristal da pálpebra
    # são mais claros (R 140-200) e ficam na pele
    r = img[..., 0]
    fechado = cv2.morphologyEx(r, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    contraste = np.clip((fechado - r - 6) / 22, 0, 1)
    escuro = np.clip((146 - r) / 34, 0, 1)
    alfa = contraste * escuro * area * np.clip((acima + 1.5) / 1.5, 0, 1)
    alfa = cv2.GaussianBlur(alfa, (3, 3), 0.6)
    return np.clip(alfa * 1.15, 0, 1), acima


def abertura(olho, forma):
    return poligono(olho["cima"] + olho["baixo"][::-1], forma)


def globo(img, eixos, olho, caixa):
    """O branco do olho sem a íris e com a parte que a pálpebra esconde: a cor do branco que aparece na pintura,
    com a sombra dos cílios perto da pálpebra de cima. Onde ele aparece na pintura (fora da íris), fica a pintura."""
    x0, y0, x1, y1 = caixa
    parte = img[y0:y1, x0:x1].copy()
    forma = parte.shape[:2]
    desloc = np.array([x0, y0])
    g = grade(forma) + desloc
    ab = eixos.local(g)
    cima, _ = curva(eixos, olho["cima"])
    baixo, _ = curva(eixos, olho["baixo"])
    abre = abertura({"cima": [list(np.subtract(p, desloc)) for p in olho["cima"]],
                     "baixo": [list(np.subtract(p, desloc)) for p in olho["baixo"]]}, forma)
    cx, cy, r = olho["iris"]
    dist_iris = np.hypot(g[..., 0] - cx, g[..., 1] - cy)
    abaixo_cima = ab[..., 1] - cima(ab[..., 0])          # > 0: abaixo da linha dos cílios
    branco = (abre > 0.5) & (dist_iris > r + 2.5) & (dist_iris < r + 12) & (abaixo_cima > 3)
    branco = cv2.erode(branco.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    if branco.sum() > 8:                                   # os tons mais claros do branco que aparece
        px = parte[branco]
        cor = np.median(px[luminancia(px) >= np.percentile(luminancia(px), 70)], axis=0)
    else:
        cor = np.array([226, 214, 236], np.float32)
    print("  branco do olho:", np.round(cor).astype(int), "de", int(branco.sum()), "pixels")
    sombra = np.clip(abaixo_cima / 9, 0, 1) ** 0.8                # sob a pálpebra de cima: mais escuro
    fundo_baixo = np.clip((baixo(ab[..., 0]) - ab[..., 1]) / 4, 0, 1)
    tom = 0.8 + 0.2 * sombra * (0.94 + 0.06 * fundo_baixo)
    sint = cor[None, None, :] * tom[..., None]
    manter = (abre > 0.5) & (dist_iris > r + 1.2)
    manter = cv2.GaussianBlur(cv2.erode(manter.astype(np.float32), np.ones((2, 2), np.uint8)), (3, 3), 0.8)
    return parte * manter[..., None] + sint * (1 - manter[..., None])


def iris(img, eixos, olho):
    """A íris como um disco inteiro: onde a pálpebra esconde, completa com a mesma distância do centro, do lado que
    aparece (o desenho dela é em raios, como uma estrela)."""
    cx, cy, r = olho["iris"]
    meio = int(np.ceil(r + 4))
    x0, y0 = int(round(cx)) - meio, int(round(cy)) - meio
    lado = 2 * meio
    parte = img[y0:y0 + lado, x0:x0 + lado].copy()
    forma = img.shape[:2]
    visivel = cv2.erode(abertura(olho, forma), np.ones((5, 5), np.uint8))[y0:y0 + lado, x0:x0 + lado] > 0.5
    g = grade((lado, lado)) + np.array([x0, y0])
    dx, dy = g[..., 0] - cx, g[..., 1] - cy
    dist = np.hypot(dx, dy)
    ang = np.arctan2(dy, dx)
    dentro = dist < r + 1.5
    falta = dentro & ~visivel
    ys, xs = np.nonzero(visivel & dentro)
    ang_v, dist_v = ang[ys, xs], dist[ys, xs]
    for y, x in zip(*np.nonzero(falta)):
        # o pixel visível mais parecido: mesma distância do centro, o ângulo mais perto
        dang = np.abs(np.angle(np.exp(1j * (ang_v - ang[y, x]))))
        custo = dang * max(dist[y, x], 3) + np.abs(dist_v - dist[y, x]) * 3
        k = np.argmin(custo)
        parte[y, x] = parte[ys[k], xs[k]]
    parte = np.where(falta[..., None], cv2.GaussianBlur(parte, (3, 3), 0.7), parte)
    alfa = np.clip(r + 0.9 - dist, 0, 1)
    return parte, alfa, (x0, y0, x0 + lado, y0 + lado)


def boca_dentro(img, eixos, boca, caixa):
    """Por dentro da boca: na fresta, a pintura (os dentes de cima e o escuro); atrás do lábio de cima, os dentes
    continuam e viram gengiva; atrás do de baixo, o escuro e a língua (aparece quando ela abre a boca)."""
    x0, y0, x1, y1 = caixa
    parte = img[y0:y1, x0:x1].copy()
    forma = parte.shape[:2]
    g = grade(forma) + np.array([x0, y0])
    ab = eixos.local(g)
    top, _ = curva(eixos, boca["fresta_cima"])
    bot, (amin, amax) = curva(eixos, boca["fresta_baixo"])
    fresta = poligono([list(np.subtract(p, (x0, y0))) for p in boca["fresta_cima"] + boca["fresta_baixo"][::-1]], forma)
    lum = luminancia(parte)
    dentro = fresta > 0.5
    claros = dentro & (lum > np.percentile(lum[dentro], 55))
    dente = np.median(parte[claros], axis=0) if claros.any() else np.array([236, 226, 238], np.float32)
    a, b = ab[..., 0], ab[..., 1]
    meio = (amin + amax) / 2
    acima = top(a) - b                                   # > 0: atrás do lábio de cima
    abaixo = b - bot(a)                                  # > 0: atrás do lábio de baixo
    gengiva = np.array([206, 128, 146], np.float32)
    escuro = np.array([58, 22, 34], np.float32)
    lingua = np.array([200, 104, 124], np.float32)
    t = np.clip((acima - 6) / 6, 0, 1)[..., None]
    cima_cor = dente * (1 - t) + gengiva * t
    # os dentes ficam no meio; perto dos cantos, atrás dos lábios, é escuro
    hw = max((amax - amin) / 2, 1)
    lateral = np.clip((np.abs(a - meio) - 0.62 * hw) / (0.2 * hw), 0, 1)[..., None]
    cima_cor = cima_cor * (1 - lateral) + escuro * lateral
    # a língua: um oval embaixo, no meio da boca
    la = (a - meio) / max((amax - amin) * 0.34, 1)
    lb = (abaixo - 13) / 8
    oval = np.clip(1.25 - np.sqrt(la ** 2 + lb ** 2), 0, 1)[..., None]
    luz = np.clip(1 - (abaixo - 6) / 18, 0.55, 1)[..., None]
    baixo_cor = escuro * (1 - oval) + lingua * luz * oval
    sint = np.where((acima > 0)[..., None], cima_cor, baixo_cor)
    lado = np.clip((np.maximum(amin + 6 - a, a - amax + 6)) / 5, 0, 1)[..., None]
    sint = sint * (1 - lado) + escuro * 0.8 * lado
    sint = cv2.GaussianBlur(sint, (7, 7), 1.8)
    # na fresta, fica a pintura só nos dentes de cima; abaixo deles, o escuro (quando a boca abre, esta faixa
    # estica, e precisa ser lisa)
    gap = np.maximum(bot(a) - top(a), 1e-3)
    escuro_fresta = np.clip((b - top(a) - 0.55 * gap) / (0.2 * gap + 1e-3), 0, 1)
    # e nos cantos (onde a fresta é só a linha entre os lábios) também é escuro
    escuro_fresta = np.maximum(escuro_fresta, lateral[..., 0])[..., None]
    parte = parte * (1 - escuro_fresta) + (escuro * 0.9) * escuro_fresta
    manter = cv2.GaussianBlur(fresta, (3, 3), 0.7)[..., None]
    return parte * manter + sint * (1 - manter)


def pele(img, marcas, eixos, masc_cilios, acima_cilios):
    """A pintura da malha: sem os cílios de cima (a camada deles fica por cima) e com os buracos preenchidos."""
    base = img.copy()
    forma = img.shape[:2]
    for nome in ("olho_d", "olho_e"):
        tirar = (masc_cilios[nome] > 0.12) & (acima_cilios[nome] > 2.5)
        tirar = cv2.dilate(tirar.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        base = preencher(base, tirar, raio=3)
        # a pálpebra fica lisa (sombra rosa em degradê): fechada, ela estica, e restos de cílio virariam riscos
        o = marcas[nome]
        area = poligono(o["cilios"] + o["cima"][::-1], forma)
        area = area * np.clip((acima_cilios[nome] - 2.0) / 3.0, 0, 1)
        area = cv2.GaussianBlur(area, (0, 0), 2.0)[..., None]
        lisa = cv2.GaussianBlur(base, (0, 0), 4.5)
        base = base * (1 - area) + lisa * area
    for nome in ("olho_d", "olho_e"):
        base = preencher(base, abertura(marcas[nome], forma), raio=3)
    boca = marcas["boca"]
    base = preencher(base, poligono(boca["fresta_cima"] + boca["fresta_baixo"][::-1], forma), raio=3)
    return base


def camada_cilios(img, lisa, olho, acima):
    """Os cílios como camada: tudo o que, acima da linha dos cílios, é mais escuro que a pálpebra lisa. Cor e
    transparência escolhidas para que cílios + pálpebra lisa = a foto original (parada, nada muda)."""
    forma = img.shape[:2]
    area = poligono(olho["cilios"] + olho["cima"][::-1], forma)
    area = cv2.dilate(area, np.ones((3, 3), np.uint8)) * np.clip((acima + 1.0) / 1.5, 0, 1)
    escuro = 30.0
    lo, ls = luminancia(img), luminancia(lisa)
    alfa = np.clip((ls - lo) / np.maximum(ls - escuro, 1), 0, 1) * area
    alfa[alfa < 0.03] = 0
    a = np.maximum(alfa, 1e-3)[..., None]
    cor = np.clip((img - (1 - a) * lisa) / a, 0, 255)
    return cor, alfa


# ----------------------------------------------------------------------------------- atlas
class Atlas:
    def __init__(self):
        self.rgb = np.zeros((LADO, LADO, 3), np.float32)
        self.a = np.zeros((LADO, LADO), np.float32)
        self.partes = {}
        self.x, self.y, self.linha = 0, 0, 0
        self.inicio = 0

    def por(self, nome, rgb, alfa, caixa, origem=None):
        h, w = rgb.shape[:2]
        if origem is None:
            if self.x + w + 2 * BORDA > LADO:
                self.x, self.y, self.linha = self.inicio, self.y + self.linha, 0
            origem = (self.x + BORDA, self.y + BORDA)
            self.x += w + 2 * BORDA
            self.linha = max(self.linha, h + 2 * BORDA)
        ox, oy = origem
        assert ox + w <= LADO and oy + h <= LADO, nome
        if alfa is None:                       # opaco: repete a borda em volta
            pad = cv2.copyMakeBorder(rgb, BORDA, BORDA, BORDA, BORDA, cv2.BORDER_REPLICATE)
            x0, y0 = max(0, ox - BORDA), max(0, oy - BORDA)
            recorte = pad[y0 - (oy - BORDA):, x0 - (ox - BORDA):]
            x1, y1 = min(LADO, ox + w + BORDA), min(LADO, oy + h + BORDA)
            self.rgb[y0:y1, x0:x1] = recorte[:y1 - y0, :x1 - x0]
            self.a[y0:y1, x0:x1] = 1
        else:
            self.rgb[oy:oy + h, ox:ox + w] = rgb * (alfa[..., None] > 0.002)
            self.a[oy:oy + h, ox:ox + w] = alfa
        self.partes[nome] = {"origem": [int(ox), int(oy)], "caixa": [int(v) for v in caixa]}

    def salvar(self):
        rgba = np.dstack([np.clip(self.rgb, 0, 255), np.clip(self.a * 255, 0, 255)]).round().astype(np.uint8)
        Image.fromarray(rgba, "RGBA").save(PASTA / "atlas.png", optimize=True)
        (PASTA / "atlas.json").write_text(json.dumps({"lado": LADO, "partes": self.partes}, indent=1) + "\n",
                                          encoding="utf-8")


def caixa_de(pontos, margem, forma):
    p = np.asarray(pontos)
    x0, y0 = np.floor(p.min(axis=0) - margem).astype(int)
    x1, y1 = np.ceil(p.max(axis=0) + margem).astype(int)
    return max(0, x0), max(0, y0), min(forma[1], x1), min(forma[0], y1)


def main():
    marcas, img = carregar()
    eixos = Eixos(marcas)
    forma = img.shape[:2]
    masc, acima = {}, {}
    for nome in ("olho_d", "olho_e"):
        masc[nome], acima[nome] = cilios(img, eixos, marcas[nome])
    atlas = Atlas()
    # a máscara do rosto: a foto (sem os cílios, com os buracos preenchidos) com a borda sumindo aos poucos
    cx = caixa_de(marcas["contorno_rosto"], 2, forma)
    x0, y0, x1, y1 = cx
    dentro = (poligono(marcas["contorno_rosto"], forma) > 0.5).astype(np.uint8)
    dist = cv2.distanceTransform(dentro, cv2.DIST_L2, 5)
    alfa = np.clip(dist / SUMIR, 0, 1) ** 1.2
    lisa = pele(img, marcas, eixos, masc, acima)
    atlas.por("rosto", lisa[y0:y1, x0:x1], alfa[y0:y1, x0:x1], cx, origem=(BORDA, BORDA))
    atlas.inicio = x1 - x0 + 3 * BORDA
    atlas.x, atlas.y = atlas.inicio, 0
    for nome in ("olho_d", "olho_e"):
        o = marcas[nome]
        cx = caixa_de(o["cima"] + o["baixo"], 14, forma)
        atlas.por("globo_" + nome[5:], globo(img, eixos, o, cx), None, cx)
    for nome in ("olho_d", "olho_e"):
        rgb, alfa, cx = iris(img, eixos, marcas[nome])
        atlas.por("iris_" + nome[5:], rgb, alfa, cx)
    for nome in ("olho_d", "olho_e"):
        o = marcas[nome]
        cx = caixa_de(o["cilios"] + o["cima"], 3, forma)
        x0, y0, x1, y1 = cx
        cor, alfa = camada_cilios(img, lisa, o, acima[nome])
        atlas.por("cilios_" + nome[5:], cor[y0:y1, x0:x1], alfa[y0:y1, x0:x1], cx)
    b = marcas["boca"]
    cx = caixa_de(b["labio_cima"] + b["labio_baixo"], 16, forma)
    atlas.por("boca_dentro", boca_dentro(img, eixos, b, cx), None, cx)
    atlas.salvar()
    print("atlas:", ", ".join(f"{k} {v['caixa']}" for k, v in atlas.partes.items()))


if __name__ == "__main__":
    main()
