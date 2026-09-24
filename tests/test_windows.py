"""Testes que só rodam no Windows (no GitHub Actions): API do Windows de verdade."""
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="só no Windows")


def test_captura_de_tela_e_coordenadas():
    from ametista import controle

    img, geo = controle.capturar("principal", "claude-opus-5")
    assert img.size == (geo["largura"], geo["altura"])
    assert max(img.size) <= 1920 and 0 < geo["escala"] <= 1
    x, y = controle.para_tela(geo["largura"] / 2, geo["altura"] / 2, geo)
    assert geo["x0"] <= x and geo["y0"] <= y


def test_janelas_mouse_e_teclas():
    from ametista import controle

    assert isinstance(controle.janelas(), list)
    controle.janela_alvo("")                    # não pode dar erro, mesmo sem janelas
    controle.mover(123, 145)
    time.sleep(0.05)
    assert controle.posicao_cursor() == (123, 145)
    assert "Nenhuma" in controle.janela_acao("listar") or controle.janela_acao("listar")
    destino = controle.janela_destino()
    assert destino is None or isinstance(destino, int)
    assert controle.janela_de_comando() in ("", "terminal", "caixa Executar")
    controle.devolver_foco()                    # sem janela da Ametista em foco: não faz nada


def test_terminal_de_verdade_e_reconhecido():
    import subprocess

    from ametista import controle

    p = subprocess.Popen(["cmd.exe", "/k", "title ametista-teste"], creationflags=subprocess.CREATE_NEW_CONSOLE)
    try:
        hwnd = None
        for _ in range(50):
            hwnd = next((j["hwnd"] for j in controle.janelas() if "ametista-teste" in j["titulo"]), None)
            if hwnd:
                break
            time.sleep(0.1)
        if not hwnd:
            pytest.skip("a janela do cmd não apareceu neste computador")
        controle._focar(hwnd)
        time.sleep(0.3)
        if controle.janela_destino() != hwnd:
            pytest.skip("o Windows não deixou trocar o foco aqui")
        assert controle.janela_de_comando() == "terminal"
    finally:
        p.kill()


def test_informacoes_do_pc():
    from ametista import pc

    assert pc.tempo_ocioso() is None or pc.tempo_ocioso() >= 0
    assert pc.tela_cheia() in (True, False)
    assert isinstance(pc.janela_ativa(), tuple)
    v = pc.volume_atual()
    assert v is None or 0 <= v <= 100
    assert "CPU" in pc.status()


def test_iniciar_com_o_windows():
    from ametista import autoinicio

    antes = autoinicio.ativo()
    autoinicio.definir(True)
    assert autoinicio.ativo()
    autoinicio.definir(False)
    assert not autoinicio.ativo()
    if antes:
        autoinicio.definir(True)


def test_microfones_e_steam():
    from ametista import ouvido, steam

    assert isinstance(ouvido.microfones(), list)
    assert steam.disponivel() in (True, False)
