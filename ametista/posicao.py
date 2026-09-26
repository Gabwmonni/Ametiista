"""Onde a janela da sobreposição fica na tela.

Ela mora no canto esquerdo de baixo (no meio da tela ela tapava o que você estava usando). Arrastando pelo rosto
ou pela barra de cima, vai para onde você quiser, e lembra: o canto de baixo à esquerda da janela fica preso ali
(a "âncora"), então crescer (conversa aberta) ou encolher (cartãozinho de tarefa) não a tira do lugar. Sempre
inteira dentro da tela, mesmo que a resolução mude ou o monitor onde ela estava tenha sido desligado.
"""
from . import estado

# largura e altura da janela (o painel tem 12 px de folga em volta, para o brilho)
TAMANHOS = {"compacto": (570, 250), "expandido": (800, 650), "tarefa": (430, 140)}
CHAVE = "janela_ancora"


def ancora() -> tuple[int, int] | None:
    """O canto de baixo à esquerda escolhido por você (ou None: o padrão, canto esquerdo de baixo da tela)."""
    a = estado.obter(CHAVE)
    if not isinstance(a, (list, tuple)) or len(a) != 2:
        return None
    try:
        return int(a[0]), int(a[1])
    except (TypeError, ValueError):
        return None


def lembrar(x: int, y: int, altura: int) -> tuple[int, int]:
    """Guarda onde a janela ficou (depois de arrastar): o canto de baixo à esquerda dela."""
    a = (int(x), int(y) + int(altura))
    estado.lembrar(CHAVE, list(a))
    return a


def esquecer() -> None:
    estado.lembrar(CHAVE, None)


def geometria(modo: str, area: tuple[int, int, int, int],
              ancora_: tuple[int, int] | None = None) -> tuple[int, int, int, int]:
    """(x, y, largura, altura) da janela no modo, dentro da área útil da tela (x, y, largura, altura, sem a
    barra de tarefas)."""
    ax, ay, aw, ah = area
    largura, altura = TAMANHOS.get(modo, TAMANHOS["compacto"])
    largura, altura = min(largura, aw), min(altura, ah)
    x, base = ancora_ if ancora_ else (ax, ay + ah)
    x = max(ax, min(int(x), ax + aw - largura))
    y = max(ay, min(int(base) - altura, ay + ah - altura))
    return x, y, largura, altura
