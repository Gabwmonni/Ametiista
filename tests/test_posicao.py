"""Onde a janela fica: canto esquerdo de baixo, arrastável, lembra o lugar e nunca sai da tela."""
from ametista import posicao

TELA = (0, 0, 1920, 1040)          # área útil de uma tela Full HD (sem a barra de tarefas)


def test_comeca_no_canto_esquerdo_de_baixo():
    x, y, w, h = posicao.geometria("compacto", TELA)
    assert (x, y + h) == (0, 1040), "encostada no canto esquerdo, logo acima da barra de tarefas"
    assert x + w < 1920 / 2, "não chega ao meio da tela"


def test_mudar_de_tamanho_nao_tira_do_lugar():
    ancora = (300, 900)
    for modo in ("compacto", "expandido", "tarefa"):
        x, y, w, h = posicao.geometria(modo, TELA, ancora)
        assert (x, y + h) == ancora, modo


def test_sempre_inteira_dentro_da_tela():
    for ancora in ((-500, 2000), (1900, 100), (5000, -300), (100, 50)):
        for modo in ("compacto", "expandido", "tarefa"):
            x, y, w, h = posicao.geometria(modo, TELA, ancora)
            assert 0 <= x and x + w <= 1920 and 0 <= y and y + h <= 1040, (modo, ancora, (x, y, w, h))


def test_segunda_tela_e_tela_pequena():
    direita = (1920, 0, 1280, 984)          # monitor à direita
    x, y, w, h = posicao.geometria("compacto", direita, (2000, 700))
    assert (x, y + h) == (2000, 700)
    x, y, w, h = posicao.geometria("expandido", (0, 0, 700, 500))
    assert (x, y, w, h) == (0, 0, 700, 500), "tela menor que a janela: encolhe para caber"


def test_lembra_onde_voce_deixou_e_volta_ao_canto():
    assert posicao.ancora() is None
    assert posicao.lembrar(400, 610, 250) == (400, 860)
    assert posicao.ancora() == (400, 860)
    assert posicao.geometria("compacto", TELA, posicao.ancora())[:2] == (400, 610)
    posicao.esquecer()
    assert posicao.ancora() is None


def test_ancora_estragada_no_estado_volta_ao_padrao():
    from ametista import estado

    for ruim in ("canto", [1], [None, "x"], {"x": 1}):
        estado.lembrar(posicao.CHAVE, ruim)
        assert posicao.ancora() is None, ruim
