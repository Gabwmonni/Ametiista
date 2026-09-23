"""App de desktop: sobreposição transparente por cima do Windows + ícone na bandeja.

- Janela sem borda, sempre no topo, transparente, fora da barra de tarefas.
- Aparece sozinha quando ouve "Ametista", no atalho (Ctrl+Shift+Espaço) ou em alarmes.
- Não rouba o foco do programa que você está usando (a não ser pelo atalho, para poder digitar).
"""
import os
import socket
import sys
import time
import webbrowser

# Toca áudio sem precisar de clique (a janela nunca recebe clique antes de falar)
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--autoplay-policy=no-user-gesture-required")

from PySide6.QtCore import QObject, QPointF, Qt, QTimer, QUrl, Signal  # noqa: E402
from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon, QPainter, QPixmap, QPolygonF  # noqa: E402
from PySide6.QtWebEngineCore import QWebEngineSettings  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialog, QInputDialog, QLabel, QMenu, QMessageBox,  # noqa: E402
                               QSystemTrayIcon, QVBoxLayout, QWidget)

from . import agenda, autoinicio, config, eventos, identidade, nuvem, servidor, spotify  # noqa: E402

LARGURA, ALTURA = 760, 250


class Ponte(QObject):
    """Leva eventos de outras threads para a thread da interface."""
    evento = Signal(dict)


class Sobreposicao(QWidget):
    """Janela transparente que contém a página web da sobreposição."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(config.NOME)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet("background: transparent;")

        self.web = QWebEngineView(self)
        self.web.setAttribute(Qt.WA_TranslucentBackground)
        self.web.setStyleSheet("background: transparent;")
        self.web.page().setBackgroundColor(Qt.transparent)
        s = self.web.settings()
        s.setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, False)
        s.setAttribute(QWebEngineSettings.ShowScrollBars, False)
        self.web.setContextMenuPolicy(Qt.NoContextMenu)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web)
        self.web.load(QUrl(f"http://127.0.0.1:{config.PORTA}/?sobreposicao=1"))
        self.posicionar()
        self._protegida = False

    def posicionar(self):
        tela = QGuiApplication.primaryScreen().availableGeometry()  # já desconta a barra de tarefas
        self.setGeometry(tela.x() + (tela.width() - LARGURA) // 2, tela.bottom() - ALTURA - 4, LARGURA, ALTURA)

    def aparecer(self, focar: bool = False):
        self.posicionar()
        if not self.isVisible():
            self.show()
        self.raise_()
        if focar:
            self.activateWindow()
            self.web.setFocus()
        self._fora_dos_prints()

    def _fora_dos_prints(self):
        """Some dos prints (pc_ver_tela vê o que está atrás dela, não ela mesma)."""
        if self._protegida or sys.platform != "win32":
            return
        try:
            import ctypes

            WDA_EXCLUDEFROMCAPTURE = 0x11
            ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), WDA_EXCLUDEFROMCAPTURE)
            self._protegida = True
        except Exception as e:
            print(f"[desktop] não consegui ocultar dos prints: {e}")


def icone_gema(tamanho: int = 64, apagada: bool = False) -> QIcon:
    pix = QPixmap(tamanho, tamanho)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    t = tamanho
    cor1, cor2 = (QColor("#777"), QColor("#444")) if apagada else (QColor("#d9b8ff"), QColor("#7a3dff"))
    p.setPen(Qt.NoPen)
    p.setBrush(cor2)
    p.drawPolygon(QPolygonF([QPointF(t * .5, t * .04), QPointF(t * .92, t * .38), QPointF(t * .5, t * .96),
                             QPointF(t * .08, t * .38)]))
    p.setBrush(cor1)
    p.drawPolygon(QPolygonF([QPointF(t * .5, t * .04), QPointF(t * .92, t * .38), QPointF(t * .5, t * .5),
                             QPointF(t * .08, t * .38)]))
    p.end()
    return QIcon(pix)


class Bandeja(QSystemTrayIcon):
    def __init__(self, janela: Sobreposicao, app: QApplication):
        super().__init__(icone_gema())
        self.janela, self.app = janela, app
        self.setToolTip(f"{config.NOME} — diga \"{config.NOME}\" ou {config.ATALHO}")
        menu = QMenu()
        menu.addAction(f"Chamar ({config.ATALHO})", self.chamar)
        menu.addSeparator()
        self.acao_mic = QAction("Microfone ligado", menu, checkable=True, checked=True)
        self.acao_mic.toggled.connect(self.alternar_mic)
        menu.addAction(self.acao_mic)
        self.acao_auto = QAction("Iniciar com o Windows", menu, checkable=True, checked=autoinicio.ativo())
        self.acao_auto.toggled.connect(autoinicio.definir)
        menu.addAction(self.acao_auto)
        menu.addSeparator()
        vozes = menu.addMenu("Vozes")
        vozes.addAction("Cadastrar a minha voz", lambda: self.cadastrar(config.DONO, "dono"))
        vozes.addAction("Cadastrar outra pessoa…", self.cadastrar_outra)
        vozes.addAction("Ver quem está cadastrado", self.ver_pessoas)
        cel = menu.addMenu("Celular")
        cel.addAction("Parear celular (QR code)", self.parear)
        cel.addAction("Desconectar todos os celulares", self.revogar)
        cel.addAction("Publicar o app do celular…", lambda: self._console("publicar_celular"))
        contas = menu.addMenu("Conectar contas")
        contas.addAction("Spotify", spotify.abrir_login)
        contas.addAction("Google Agenda", lambda: self._em_segundo_plano(agenda.conectar_google))
        contas.addAction("Outlook", lambda: self._em_segundo_plano(agenda.conectar_outlook))
        menu.addAction("Abrir no navegador (teste)", lambda: webbrowser.open(f"http://127.0.0.1:{config.PORTA}"))
        menu.addAction("Abrir pasta da Ametista", lambda: os.startfile(str(config.RAIZ))
                       if sys.platform == "win32" else None)
        menu.addSeparator()
        menu.addAction("Sair", self.app.quit)
        self.setContextMenu(menu)
        self.activated.connect(lambda motivo: self.chamar() if motivo == QSystemTrayIcon.Trigger else None)
        self._menu = menu  # mantém referência viva

    def chamar(self):
        eventos.publicar({"tipo": "chamar", "interno": True})

    def alternar_mic(self, ligado: bool):
        eventos.publicar({"tipo": "mudo", "valor": not ligado, "interno": True})
        self.acao_mic.setText("Microfone ligado" if ligado else "Microfone DESLIGADO")
        self.setIcon(icone_gema(apagada=not ligado))

    # ---------------- vozes
    def cadastrar(self, nome: str, nivel: str):
        eventos.publicar({"tipo": "cadastrar", "nome": nome, "nivel": nivel, "interno": True})

    def cadastrar_outra(self):
        nome, ok = QInputDialog.getText(None, config.NOME, "Nome da pessoa:")
        if not ok or not nome.strip():
            return
        rotulos = {"Família (quase tudo)": "familia", "Visitante (conversa e música)": "visitante",
                   "Dono (tudo)": "dono"}
        nivel, ok = QInputDialog.getItem(None, config.NOME, f"O que {nome.strip()} pode fazer?",
                                         list(rotulos), 0, False)
        if ok:
            self.cadastrar(nome.strip(), rotulos[nivel])

    def ver_pessoas(self):
        lista = identidade.pessoas()
        texto = "\n".join(f"• {p['nome']} — {p['nivel']}" for p in lista) or \
            "Ninguém cadastrado: ela atende qualquer voz."
        QMessageBox.information(None, config.NOME, f"{texto}\n\nModo: {config.MODO_VOZ}\n"
                                "Para remover alguém, diga: \"Ametista, apaga a voz da Fulana\".")

    # ---------------- celular
    def parear(self):
        try:
            codigo, link = nuvem.instancia().novo_codigo()
        except Exception as e:
            QMessageBox.warning(None, config.NOME, f"{e}\n\nPublique o app do celular primeiro "
                                                   "(💎 > Celular > Publicar o app do celular).")
            return
        DialogoQR(codigo, link).exec()

    def revogar(self):
        if QMessageBox.question(None, config.NOME, "Desconectar todos os celulares pareados?") == QMessageBox.Yes:
            ok = nuvem.instancia().revogar_celulares()
            QMessageBox.information(None, config.NOME, "Celulares desconectados." if ok else
                                    "O PC está sem conexão com o serviço do celular.")

    # ---------------- utilidades
    def _em_segundo_plano(self, funcao):
        import threading

        def rodar():
            try:
                msg = funcao()
            except Exception as e:
                msg = f"Não deu certo: {e}"
            eventos.publicar({"tipo": "aviso", "texto": msg})
        threading.Thread(target=rodar, daemon=True).start()

    def _console(self, modulo: str):
        """Abre uma janela de comando rodando um módulo da Ametista (ex.: publicar o app do celular)."""
        import subprocess

        py = sys.executable.replace("pythonw.exe", "python.exe")
        if sys.platform == "win32":
            subprocess.Popen(f'start "Ametista" cmd /k ""{py}" -m ametista.{modulo}"', shell=True,
                             cwd=str(config.RAIZ))
        else:
            subprocess.Popen([py, "-m", f"ametista.{modulo}"], cwd=str(config.RAIZ))


class DialogoQR(QDialog):
    """Mostra o QR code para parear o celular."""

    def __init__(self, codigo: str, link: str):
        super().__init__()
        self.setWindowTitle(f"{config.NOME} — parear celular")
        self.setStyleSheet("QDialog{background:#0d0816;} QLabel{color:#f1eaff; font-size:14px;}")
        lay = QVBoxLayout(self)
        img = QLabel()
        img.setPixmap(self._qr(link))
        img.setAlignment(Qt.AlignCenter)
        lay.addWidget(img)
        cod = QLabel(f"<div style='font-size:30px; letter-spacing:6px; font-weight:700'>"
                     f"{codigo[:4]} {codigo[4:]}</div>")
        cod.setAlignment(Qt.AlignCenter)
        lay.addWidget(cod)
        dica = QLabel("Aponte a câmera do celular para o QR code<br>ou abra o app e digite o código.<br>"
                      "<span style='color:#a597c4'>Vale por 10 minutos e só uma vez.</span>")
        dica.setAlignment(Qt.AlignCenter)
        lay.addWidget(dica)

    @staticmethod
    def _qr(texto: str) -> QPixmap:
        import io

        import qrcode

        img = qrcode.make(texto, box_size=8, border=2)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        pix = QPixmap()
        pix.loadFromData(buf.getvalue(), "PNG")
        return pix


def _porta_ocupada() -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", config.PORTA)) == 0


def _esperar_servidor(limite: float = 20) -> None:
    fim = time.time() + limite
    while time.time() < fim and not _porta_ocupada():
        time.sleep(0.1)


def main() -> int:
    # Instância única: se já estiver rodando, só chama a que existe
    if _porta_ocupada():
        try:
            import httpx

            httpx.get(f"http://127.0.0.1:{config.PORTA}/api/chamar", timeout=2)
        except Exception:
            pass
        return 0

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(config.NOME)
    app.setWindowIcon(icone_gema())

    servidor.rodar_em_segundo_plano()
    _esperar_servidor()

    janela = Sobreposicao()
    bandeja = Bandeja(janela, app)
    bandeja.show()

    # Eventos de qualquer thread -> interface
    ponte = Ponte()
    esconder_timer = QTimer(singleShot=True)
    esconder_timer.timeout.connect(janela.hide)

    estado = {"ouvido": False}

    def tratar(msg: dict):
        tipo = msg.get("tipo")
        if tipo in ("acordou", "ouvindo", "transcricao", "pensando", "resposta", "alerta", "aviso", "cadastro"):
            esconder_timer.stop()
            janela.aparecer(focar=bool(msg.get("manual")))
        elif tipo == "esconder":
            esconder_timer.start(50)
        elif tipo == "chamar" and not estado["ouvido"]:  # sem microfone: abre só para digitar
            eventos.publicar({"tipo": "acordou", "manual": True})

    ponte.evento.connect(tratar)
    eventos.ouvir(lambda m: ponte.evento.emit(m) if m.get("tipo") != "mic" else None)

    # Ouvido (microfone offline)
    if config.OUVIDO_LIGADO:
        from .ouvido import Ouvido

        estado["ouvido"] = Ouvido().iniciar()
        if not estado["ouvido"]:
            QTimer.singleShot(4000, lambda: eventos.publicar({
                "tipo": "aviso", "texto": "Não achei o modelo de voz; rode o instalar.bat. Por enquanto, só digitando."}))

    # Celular (ponte na Cloudflare)
    nuvem.instancia().iniciar()

    # Atalho global
    try:
        import keyboard

        keyboard.add_hotkey(config.ATALHO, lambda: eventos.publicar({"tipo": "chamar", "interno": True}))
    except Exception as e:
        print(f"[desktop] atalho {config.ATALHO} indisponível: {e}")

    # Mostra uma vez ao iniciar, para você saber que ela está ativa
    def boas_vindas():
        eventos.publicar({"tipo": "aviso", "texto": f"{config.NOME} ativa. Diga \"{config.NOME}\" "
                                                    f"ou use {config.ATALHO.replace('+', ' + ')}."})
    QTimer.singleShot(2500, boas_vindas)
    return app.exec()
