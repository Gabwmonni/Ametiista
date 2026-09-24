"""Atualizar o app do celular pelo instalar.bat: só quando já estava publicado, sem perguntar e sem falhar."""
from ametista import config, diagnostico, publicar_celular as pc


def test_sem_celular_publicado_nao_faz_nada(monkeypatch):
    monkeypatch.setattr(config, "NUVEM_URL", "")
    chamou = []
    monkeypatch.setattr(pc, "_quieto", lambda *a: chamou.append(a))
    assert "não publicado" in pc.atualizar_publicado() and chamou == []


def test_publicado_atualiza_sem_abrir_o_navegador(monkeypatch):
    monkeypatch.setattr(config, "NUVEM_URL", "https://ametista.exemplo.workers.dev")
    monkeypatch.setattr(config, "NUVEM_CHAVE", "chave")
    monkeypatch.setattr(pc.shutil, "which", lambda n: "npx")
    monkeypatch.setattr(pc, "atualizar_sw", lambda: True)
    comandos = []

    def quieto(cmd, limite):
        comandos.append(cmd)
        return 0, "logado"

    monkeypatch.setattr(pc, "_quieto", quieto)
    assert "versão nova publicada" in pc.atualizar_publicado()
    assert comandos == ["npm install --no-audit --no-fund", "npx wrangler whoami", "npx wrangler deploy"]
    assert not any("login" in c or "secret" in c for c in comandos)


def test_sem_login_ou_sem_node_so_explica(monkeypatch):
    monkeypatch.setattr(config, "NUVEM_URL", "https://ametista.exemplo.workers.dev")
    monkeypatch.setattr(config, "NUVEM_CHAVE", "chave")
    monkeypatch.setattr(pc.shutil, "which", lambda n: None)
    assert "Node.js" in pc.atualizar_publicado()
    monkeypatch.setattr(pc.shutil, "which", lambda n: "npx")
    monkeypatch.setattr(pc, "_quieto", lambda cmd, limite: (0, "You are not authenticated") if "whoami" in cmd else (0, ""))
    assert "publicar_celular.bat" in pc.atualizar_publicado()


def test_diagnostico_percebe_app_do_celular_desatualizado(monkeypatch):
    monkeypatch.setattr(config, "NUVEM_URL", "https://ametista.exemplo.workers.dev")

    class R:
        def __init__(self, texto):
            self.text = texto

    atual = pc.impressao_casca()
    monkeypatch.setattr(diagnostico.httpx, "get", lambda *a, **k: R(f'const CACHE = "ametista-casca-{atual}";'))
    assert diagnostico.versao_do_celular_publicada() is True
    monkeypatch.setattr(diagnostico.httpx, "get", lambda *a, **k: R('const CACHE = "ametista-casca-0000000000";'))
    assert diagnostico.versao_do_celular_publicada() is False

    def sem_rede(*a, **k):
        raise OSError("sem rede")

    monkeypatch.setattr(diagnostico.httpx, "get", sem_rede)
    assert diagnostico.versao_do_celular_publicada() is None
