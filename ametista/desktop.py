"""App de desktop: sobreposição transparente por cima do Windows + ícone na bandeja.

- Janela sem borda, sempre no topo, transparente, fora da barra de tarefas e fora dos prints.
- Mora no canto esquerdo de baixo; arrastando pelo rosto ou pela barra de cima, fica onde você deixar.
- Aparece sozinha quando ouve "Ametista", no atalho (Ctrl+Shift+Espaço) ou em avisos.
- Três tamanhos: compacto (a barra), expandido (conversa, tarefas, avisos, histórico) e tarefa
  (um cartãozinho no canto enquanto o modo agente usa a tela; os cliques passam através dele).
- Apontador: um círculo piscando onde clicar ("Ametista, onde eu clico?").
- Atalho de emergência (Ctrl+Shift+Backspace): para tudo.
"""
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser

# Toca áudio sem precisar de clique (a janela nunca recebe clique antes de falar)
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--autoplay-policy=no-user-gesture-required")

from PySide6.QtCore import QObject, QPoint, QPointF, QRectF, Qt, QTimer, QUrl, Signal  # noqa: E402
from PySide6.QtGui import (QAction, QColor, QFont, QGuiApplication, QIcon, QPainter, QPen, QPixmap,  # noqa: E402
                           QPolygonF)
from PySide6.QtWebEngineCore import QWebEngineSettings  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialog, QInputDialog, QLabel, QMenu, QMessageBox,  # noqa: E402
                               QSystemTrayIcon, QVBoxLayout, QWidget)

from . import agenda, autoinicio, config, estado, eventos, identidade, nuvem, posicao, servidor, spotify  # noqa: E402

TAMANHOS = posicao.TAMANHOS


class Ponte(QObject):
    """Leva eventos de outras threads para a thread da interface."""
    evento = Signal(dict)


def _fora_dos_prints(widget: QWidget) -> None:
    """A janela some dos prints (a IA vê o que está atrás dela, não ela mesma)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        WDA_EXCLUDEFROMCAPTURE = 0x11
        ctypes.windll.user32.SetWindowDisplayAffinity(int(widget.winId()), WDA_EXCLUDEFROMCAPTURE)
    except Exception as e:
        print(f"[desktop] não consegui ocultar dos prints: {e}")


def ponto_logico(px: int, py: int) -> QPoint:
    """Pixel real da tela (o que o mss e o mouse usam) -> coordenada do Qt (que desconta a escala do Windows)."""
    for s in QGuiApplication.screens():
        g, dpr = s.geometry(), s.devicePixelRatio()
        if g.x() <= px < g.x() + g.width() * dpr and g.y() <= py < g.y() + g.height() * dpr:
            return QPoint(int(g.x() + (px - g.x()) / dpr), int(g.y() + (py - g.y()) / dpr))
    dpr = QGuiApplication.primaryScreen().devicePixelRatio()
    return QPoint(int(px / dpr), int(py / dpr))


class Sobreposicao(QWidget):
    """Janela transparente que contém a página web da sobreposição."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(config.NOME)
        self.modo = "compacto"
        self._aplicar_flags()
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
        self._alvo = QPoint()                 # onde o próprio app pôs a janela (mover para lá não é você arrastando)
        self._inicio_arrasto: QPoint | None = None
        self._arrasto_do_sistema = False
        self._guardar_depois = QTimer(self, singleShot=True)
        self._guardar_depois.timeout.connect(self._guardar_lugar)
        self.posicionar()

    def _aplicar_flags(self) -> None:
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        if self.modo == "tarefa":
            flags |= Qt.WindowTransparentForInput  # o modo agente clica através dela
        self.setWindowFlags(flags)

    def posicionar(self):
        """No lugar escolhido (ou no canto esquerdo de baixo), inteira dentro da tela onde ela está."""
        ancora = posicao.ancora()
        tela = QGuiApplication.screenAt(QPoint(ancora[0] + 40, ancora[1] - 40)) if ancora else None
        area = (tela or QGuiApplication.primaryScreen()).availableGeometry()  # já desconta a barra de tarefas
        x, y, largura, altura = posicao.geometria(self.modo, (area.x(), area.y(), area.width(), area.height()), ancora)
        self._alvo = QPoint(x, y)
        self.setGeometry(x, y, largura, altura)

    # ---- arrastar pelo rosto (a página avisa quando o mouse andou com o botão apertado)
    def comecar_arrasto(self):
        self._inicio_arrasto = self.pos()
        janela = self.windowHandle()
        try:  # o Windows move a janela junto com o mouse; se não der, seguimos os deslocamentos da página
            self._arrasto_do_sistema = bool(janela and janela.startSystemMove())
        except Exception:
            self._arrasto_do_sistema = False

    def arrastar(self, dx: int, dy: int):
        if self._inicio_arrasto is not None and not self._arrasto_do_sistema:
            self.move(self._inicio_arrasto + QPoint(dx, dy))

    def terminar_arrasto(self):
        if self._inicio_arrasto is not None:
            self._inicio_arrasto, self._arrasto_do_sistema = None, False
            self._guardar_lugar()

    def moveEvent(self, evento):
        super().moveEvent(evento)
        if self.isVisible() and self.pos() != self._alvo:   # foi você que moveu: lembra o lugar
            self._guardar_depois.start(500)

    def _guardar_lugar(self):
        g = self.geometry()
        if g.topLeft() != self._alvo:
            posicao.lembrar(g.x(), g.y(), g.height())
            self._alvo = g.topLeft()

    def voltar_ao_canto(self):
        posicao.esquecer()
        self.posicionar()

    def mudar_modo(self, modo: str):
        if modo not in TAMANHOS or modo == self.modo:
            return
        visivel = self.isVisible()
        antigo, self.modo = self.modo, modo
        if (antigo == "tarefa") != (modo == "tarefa"):
            self._aplicar_flags()  # trocar as flags esconde a janela
        self.posicionar()
        if visivel or modo in ("expandido", "tarefa"):
            self.aparecer(focar=modo == "expandido")

    def aparecer(self, focar: bool = False):
        self.posicionar()
        if not self.isVisible():
            self.show()
            _fora_dos_prints(self)
        self.raise_()
        if focar and self.modo != "tarefa":
            self.activateWindow()
            self.web.setFocus()


class Apontador(QWidget):
    """Círculo piscando num ponto da tela, com uma legenda ("clique aqui")."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.resize(260, 190)
        self.rotulo = ""
        self.fase = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animar)
        self.fim = 0.0

    def mostrar(self, px: int, py: int, rotulo: str = ""):
        p = ponto_logico(px, py)
        self.rotulo = rotulo
        self.move(p.x() - 130, p.y() - 70)
        self.fim = time.time() + 7
        if not self.isVisible():
            self.show()
            _fora_dos_prints(self)
        self.raise_()
        self.timer.start(33)

    def _animar(self):
        self.fase = (self.fase + 0.045) % 1.0
        if time.time() > self.fim:
            self.timer.stop()
            self.hide()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        centro = QPointF(130, 70)
        for i in range(2):
            f = (self.fase + i * 0.5) % 1.0
            r = 12 + f * 44
            cor = QColor(150, 128, 240, int(255 * (1 - f)))
            p.setPen(QPen(cor, 4))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(centro, r, r)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(150, 128, 240, 230))
        p.drawEllipse(centro, 7, 7)
        if self.rotulo:
            p.setFont(QFont("Segoe UI", 10, QFont.DemiBold))
            m = p.fontMetrics()
            largura = min(250, m.horizontalAdvance(self.rotulo) + 20)
            caixa = QRectF(130 - largura / 2, 128, largura, 26)
            p.setBrush(QColor(16, 10, 28, 235))
            p.setPen(QPen(QColor(203, 178, 248, 200), 1))
            p.drawRoundedRect(caixa, 12, 12)
            p.setPen(QColor(241, 234, 255))
            p.drawText(caixa, Qt.AlignCenter, m.elidedText(self.rotulo, Qt.ElideRight, int(largura - 16)))
        p.end()


def icone_gema(tamanho: int = 64, apagada: bool = False, cadeado: bool = False) -> QIcon:
    pix = QPixmap(tamanho, tamanho)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    t = tamanho
    cor1, cor2 = (QColor("#777"), QColor("#444")) if apagada else (QColor("#cbb2f8"), QColor("#6f5bd6"))
    p.setPen(Qt.NoPen)
    p.setBrush(cor2)
    p.drawPolygon(QPolygonF([QPointF(t * .5, t * .04), QPointF(t * .92, t * .38), QPointF(t * .5, t * .96),
                             QPointF(t * .08, t * .38)]))
    p.setBrush(cor1)
    p.drawPolygon(QPolygonF([QPointF(t * .5, t * .04), QPointF(t * .92, t * .38), QPointF(t * .5, t * .5),
                             QPointF(t * .08, t * .38)]))
    if cadeado:
        p.setBrush(QColor("#ffcf6b"))
        p.drawRoundedRect(QRectF(t * .56, t * .6, t * .38, t * .32), t * .05, t * .05)
        p.setPen(QPen(QColor("#ffcf6b"), t * .07))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(t * .62, t * .42, t * .26, t * .32), 0, 180 * 16)
    p.end()
    return QIcon(pix)


class Bandeja(QSystemTrayIcon):
    def __init__(self, janela: Sobreposicao, app: QApplication):
        super().__init__(icone_gema())
        self.janela, self.app = janela, app
        self.mic_ligado = True
        self.setToolTip(f"{config.NOME} — diga \"{config.NOME}\" ou {config.ATALHO}")
        menu = QMenu()
        menu.addAction(f"Chamar ({config.ATALHO})", self.chamar)
        menu.addAction(f"Parar tudo ({config.ATALHO_PARAR})", self.parar_tudo)
        menu.addSeparator()
        self.acao_privado = QAction("Modo privado", menu, checkable=True, checked=estado.privado())
        self.acao_privado.toggled.connect(lambda v: estado.definir_privado(v))
        menu.addAction(self.acao_privado)
        self.acao_silencio = QAction("Não perturbe (1 hora)", menu, checkable=True,
                                     checked=bool(estado.nao_perturbe_ate()))
        self.acao_silencio.toggled.connect(self.alternar_silencio)
        menu.addAction(self.acao_silencio)
        self.acao_mic = QAction("Microfone ligado", menu, checkable=True, checked=True)
        self.acao_mic.toggled.connect(self.alternar_mic)
        menu.addAction(self.acao_mic)
        menu.addSeparator()
        menu.addAction("Configurações…", abrir_painel)
        menu.addAction("Conversa, tarefas e histórico", lambda: self.janela.mudar_modo("expandido"))
        menu.addAction("Voltar a janela para o canto", self.janela.voltar_ao_canto)
        menu.addAction("Fazer um diagnóstico", self.diagnostico)
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
        self.acao_auto = QAction("Iniciar com o Windows", menu, checkable=True, checked=autoinicio.ativo())
        self.acao_auto.toggled.connect(autoinicio.definir)
        menu.addAction(self.acao_auto)
        menu.addAction("Abrir no navegador (teste)", lambda: webbrowser.open(f"http://127.0.0.1:{config.PORTA}"))
        menu.addAction("Abrir pasta da Ametista", lambda: os.startfile(str(config.RAIZ))
                       if sys.platform == "win32" else None)
        menu.addSeparator()
        menu.addAction("Sair", self.app.quit)
        self.setContextMenu(menu)
        self.activated.connect(lambda motivo: self.chamar() if motivo == QSystemTrayIcon.Trigger else None)
        self._menu = menu  # mantém referência viva
        self.pintar()

    def pintar(self):
        privado = estado.privado()
        self.setIcon(icone_gema(apagada=privado or not self.mic_ligado or estado.offline, cadeado=privado))
        dica = f"{config.NOME} — " + ("modo privado" if privado else "microfone desligado" if not self.mic_ligado
                                       else "sem internet" if estado.offline else f"diga \"{config.NOME}\"")
        self.setToolTip(dica)
        if self.acao_privado.isChecked() != privado:
            self.acao_privado.blockSignals(True)
            self.acao_privado.setChecked(privado)
            self.acao_privado.blockSignals(False)
        silencio = bool(estado.nao_perturbe_ate())
        if self.acao_silencio.isChecked() != silencio:
            self.acao_silencio.blockSignals(True)
            self.acao_silencio.setChecked(silencio)
            self.acao_silencio.blockSignals(False)

    def chamar(self):
        eventos.publicar({"tipo": "chamar", "interno": True})

    def parar_tudo(self):
        from . import nucleo

        threading.Thread(target=nucleo.parar_tudo, daemon=True).start()

    def alternar_mic(self, ligado: bool):
        self.mic_ligado = ligado
        eventos.publicar({"tipo": "mudo", "valor": not ligado, "interno": True})
        self.acao_mic.setText("Microfone ligado" if ligado else "Microfone DESLIGADO")
        self.pintar()

    def alternar_silencio(self, ligado: bool):
        from . import ferramentas

        ferramentas.nao_perturbe(60 if ligado else 0)

    def diagnostico(self):
        from . import nucleo

        nucleo.atender_em_segundo_plano("faça um diagnóstico")

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
                                "Para mudar, use o painel de configurações (Pessoas).")

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
        def rodar():
            try:
                msg = funcao()
            except Exception as e:
                msg = f"Não deu certo: {e}"
            eventos.publicar({"tipo": "aviso", "texto": msg})
        threading.Thread(target=rodar, daemon=True).start()

    def _console(self, modulo: str):
        """Abre uma janela de comando rodando um módulo da Ametista (ex.: publicar o app do celular)."""
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


def abrir_painel() -> None:
    webbrowser.open(f"http://127.0.0.1:{config.PORTA}/painel")


def _porta_ocupada() -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", config.PORTA)) == 0


def _esperar_servidor(limite: float = 20) -> None:
    fim = time.time() + limite
    while time.time() < fim and not _porta_ocupada():
        time.sleep(0.1)


def reiniciar_processo(app: QApplication) -> None:
    """Abre uma Ametista nova (que espera esta fechar) e fecha esta."""
    principal = sys.modules.get("__main__")
    if getattr(principal, "__spec__", None) is not None:  # python -m ametista
        cmd = [sys.executable, "-m", "ametista"] + sys.argv[1:]
    else:                                                # ametista.pyw
        cmd = [sys.executable] + sys.argv
    env = {**os.environ, "AMETISTA_REINICIO": "1"}
    flags = 0x00000008 if sys.platform == "win32" else 0  # DETACHED_PROCESS
    subprocess.Popen(cmd, cwd=str(config.RAIZ), env=env, creationflags=flags)
    app.quit()


def main() -> int:
    if os.environ.pop("AMETISTA_REINICIO", None):  # reinício pelo painel: espera a anterior sair
        fim = time.time() + 20
        while _porta_ocupada() and time.time() < fim:
            time.sleep(0.3)
    # Instância única: se já estiver rodando, só chama a que existe
    if _porta_ocupada():
        try:
            import httpx

            httpx.get(f"http://127.0.0.1:{config.PORTA}/api/chamar", timeout=2)
        except Exception:
            pass
        return 0

    try:
        mudou = config.migrar_env()           # padrões novos para quem atualizou (ex.: voz mais calma)
        if mudou:
            print(f"[config] atualizadas para o padrão novo: {', '.join(mudou)}")
    except OSError as e:
        print(f"[config] não consegui atualizar o .env: {e}")

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(config.NOME)
    app.setWindowIcon(icone_gema())

    servidor.rodar_em_segundo_plano()
    _esperar_servidor()

    janela = Sobreposicao()
    apontador = Apontador()
    bandeja = Bandeja(janela, app)
    bandeja.show()

    # Eventos de qualquer thread -> interface
    ponte = Ponte()
    esconder_timer = QTimer(singleShot=True)
    esconder_timer.timeout.connect(lambda: janela.hide() if janela.modo == "compacto" else None)
    estado_ui = {"ouvido": False}

    def tratar(msg: dict):
        tipo = msg.get("tipo")
        if tipo in ("acordou", "ouvindo", "transcricao", "pensando", "fala_inicio", "alerta", "aviso", "cadastro",
                    "aguardando"):
            esconder_timer.stop()
            janela.aparecer(focar=bool(msg.get("manual")))
        elif tipo == "esconder":
            esconder_timer.start(50)
        elif tipo == "tamanho":
            janela.mudar_modo(msg.get("modo", "compacto"))
        elif tipo == "mover_inicio":
            janela.comecar_arrasto()
        elif tipo == "mover":
            janela.arrastar(int(msg.get("dx", 0)), int(msg.get("dy", 0)))
        elif tipo == "mover_fim":
            janela.terminar_arrasto()
        elif tipo == "agente_tela":
            janela.mudar_modo("tarefa" if msg.get("ativo") else "compacto")
        elif tipo == "apontar":
            apontador.mostrar(int(msg["x"]), int(msg["y"]), msg.get("rotulo", ""))
        elif tipo == "abrir_painel":
            abrir_painel()
        elif tipo in ("privado", "estado"):
            bandeja.pintar()
        elif tipo == "reiniciar":
            reiniciar_processo(app)
        elif tipo == "chamar" and not estado_ui["ouvido"]:  # sem microfone: abre só para digitar
            eventos.publicar({"tipo": "acordou", "manual": True})

    ponte.evento.connect(tratar)
    eventos.ouvir(lambda m: ponte.evento.emit(m) if m.get("tipo") not in ("mic", "fala_trecho") else None)

    # Ouvido (microfone offline)
    if config.OUVIDO_LIGADO:
        from .ouvido import Ouvido

        estado_ui["ouvido"] = Ouvido().iniciar()
        if not estado_ui["ouvido"]:
            QTimer.singleShot(4000, lambda: eventos.publicar({
                "tipo": "aviso", "texto": "Não achei o modelo de voz; rode o instalar.bat. Por enquanto, só digitando."}))

    # Celular (ponte na Cloudflare)
    nuvem.instancia().iniciar()

    # Atalhos globais
    try:
        import keyboard

        keyboard.add_hotkey(config.ATALHO, lambda: eventos.publicar({"tipo": "chamar", "interno": True}))
        keyboard.add_hotkey(config.ATALHO_PARAR, bandeja.parar_tudo)
    except Exception as e:
        print(f"[desktop] atalhos indisponíveis: {e}")

    # Mostra uma vez ao iniciar, para você saber que ela está ativa
    def boas_vindas():
        extra = " Modo privado ligado." if estado.privado() else ""
        eventos.publicar({"tipo": "aviso", "texto": f"{config.NOME} ativa. Diga \"{config.NOME}\" "
                                                    f"ou use {config.ATALHO.replace('+', ' + ')}.{extra}"})
    QTimer.singleShot(2500, boas_vindas)

    # Primeira vez (sem a chave do Claude): abre o painel para configurar
    if not config.ANTHROPIC_API_KEY and not os.environ.get("AMETISTA_SEM_PAINEL"):
        QTimer.singleShot(3500, abrir_painel)
    return app.exec()
