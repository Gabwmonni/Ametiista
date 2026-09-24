"""Foco nos estudos: a Ametista percebe quando você troca os estudos por distração e chama você de volta.

- Sessão de foco: "Ametista, vou estudar cálculo por uma hora" (ou sozinha, nos horários do painel > Foco).
  A cada 15 segundos ela vê qual janela está na frente e separa em estudo, distração ou neutro. Alguns minutos
  seguidos em distração (YouTube que não é aula, Instagram, um jogo...) e ela chama você de volta, com calma, sem
  repetir antes de 8 minutos. "Pausa de 10 minutos" suspende tudo e ela avisa quando a pausa acaba.
- Fora das sessões (se ligado no painel): se você estava estudando e caiu numa distração por 15 minutos, ela
  comenta uma vez (e segue as regras de proatividade).
- No fim, um resumo falado: quanto estudou, quanto se distraiu e com o quê. O histórico fica em dados/ametista.db
  ("como foram meus estudos essa semana?").

Privacidade: o histórico guarda só o nome da distração ("YouTube", o nome do jogo), nunca o título da janela.
No modo privado ela não olha nada.
"""
import json
import re
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from datetime import time as hora

from . import acoes, avisos, config, estado

TICK_S = 15
AUSENTE_S = 300              # 5 min sem mexer no mouse ou teclado = saiu do PC
LEITURA_S = 1200             # lendo um PDF ou vendo uma aula parado: ainda é estudo (até 20 min)
REPETIR_S = 8 * 60           # intervalo mínimo entre dois chamados na mesma sessão
VOLTOU_S = 60                # 1 min estudando zera a contagem da distração
MAX_SESSAO_MIN = 240         # sessão "sem hora para acabar" termina sozinha depois de 4 horas
ESPONTANEO_MIN = 15          # fora das sessões: distração seguida que faz ela comentar
ESTUDOU_MIN = 10             # ... desde que você tenha estudado pelo menos isso
ESTUDO_RECENTE_S = 45 * 60   # ... nos últimos 45 minutos
_trava = threading.RLock()


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower())
                   if unicodedata.category(c) != "Mn")


# ====================================================================== o que é estudo e o que é distração
# (palavra no título da janela, sem acento; "*" no fim = começo de palavra). Rótulo e preposição para a frase
# ("no YouTube", "na Netflix", "jogando Valorant").
DISTRACOES = [
    ("youtube", "YouTube", "no"), ("netflix", "Netflix", "na"), ("twitch", "Twitch", "na"),
    ("instagram", "Instagram", "no"), ("tiktok", "TikTok", "no"), ("facebook", "Facebook", "no"),
    ("twitter", "Twitter", "no"), ("reddit", "Reddit", "no"), ("prime video", "Prime Video", "no"),
    ("disney+", "Disney+", "no"), ("disney plus", "Disney+", "no"), ("globoplay", "Globoplay", "no"),
    ("crunchyroll", "Crunchyroll", "no"), ("hbo max", "HBO Max", "na"), ("kwai", "Kwai", "no"),
    ("pinterest", "Pinterest", "no"), ("9gag", "9GAG", "no"), ("shopee", "Shopee", "na"),
    ("mercado livre", "Mercado Livre", "no"), ("aliexpress", "AliExpress", "no"), ("shein", "Shein", "na"),
    ("whatsapp", "WhatsApp", "no"), ("telegram", "Telegram", "no"), ("discord", "Discord", "no"),
    ("tinder", "Tinder", "no"), ("roblox", "Roblox", "jogando"), ("minecraft", "Minecraft", "jogando"),
    ("league of legends", "League of Legends", "jogando"), ("valorant", "Valorant", "jogando"),
    ("fortnite", "Fortnite", "jogando"), ("counter-strike", "Counter-Strike", "jogando"),
    ("free fire", "Free Fire", "jogando"), ("chess.com", "Chess.com", "no"), ("lichess", "Lichess", "no"),
]
DISTRACAO_EXE = {
    "steam.exe": ("Steam", "na"), "steamwebhelper.exe": ("Steam", "na"),
    "epicgameslauncher.exe": ("Epic Games", "na"), "riotclientux.exe": ("Riot", "no"),
    "riotclientservices.exe": ("Riot", "no"), "leagueclientux.exe": ("League of Legends", "jogando"),
    "league of legends.exe": ("League of Legends", "jogando"),
    "valorant-win64-shipping.exe": ("Valorant", "jogando"), "robloxplayerbeta.exe": ("Roblox", "jogando"),
    "minecraft.exe": ("Minecraft", "jogando"), "battle.net.exe": ("Battle.net", "no"),
    "eadesktop.exe": ("EA App", "no"), "xboxpcapp.exe": ("Xbox", "no"), "discord.exe": ("Discord", "no"),
    "whatsapp.exe": ("WhatsApp", "no"), "telegram.exe": ("Telegram", "no"), "netflix.exe": ("Netflix", "na"),
}
PASTAS_DE_JOGO = ("steamapps", "\\epic games\\", "\\riot games\\", "\\xboxgames\\", "\\ea games\\",
                  "\\gog galaxy\\games\\", "\\ubisoft game launcher\\games\\")
ESTUDO = [
    "aula*", "curso*", "estud*", "exercic*", "lista de", "prova*", "simulado*", "apostila*", "resumo*", "revis*",
    "materia*", "disciplina*", "faculdade", "universidade", "vestibular", "enem", "concurso*", "questoes",
    "tcc", "artigo*", "livro*", "capitulo*", "lecture*", "tutorial*", "course*", "study", "homework",
    "khan academy", "coursera", "udemy", "alura", "duolingo", "moodle", "classroom", "sala de aula", "notion",
    "obsidian", "anki", "wikipedia", "stack overflow", "brainly", "passei direto", "descomplica", "stoodi",
    "me salva", "qconcursos", "tec concursos", "gran cursos", "estrategia concursos", "scielo",
    "google academico", "scholar", "geogebra", "wolfram", "symbolab", "overleaf", "portal do aluno", "ava",
    "canvas", "blackboard", ".pdf",
]
ESTUDO_EXE = {
    "winword.exe", "excel.exe", "powerpnt.exe", "onenote.exe", "acad.exe", "acrobat.exe", "acrord32.exe",
    "sumatrapdf.exe", "foxitpdfreader.exe", "code.exe", "pycharm64.exe", "idea64.exe", "devenv.exe",
    "obsidian.exe", "notion.exe", "anki.exe", "matlab.exe", "revit.exe", "sketchup.exe", "geogebra.exe",
    "zotero.exe", "rstudio.exe", "spyder.exe", "texstudio.exe", "texmaker.exe", "xmind.exe", "soffice.bin",
    "swriter.exe", "scalc.exe", "simpress.exe", "wps.exe", "et.exe", "wpp.exe", "sldworks.exe", "inventor.exe",
    "archicad.exe", "qgis-bin.exe", "arcgispro.exe", "mathcad.exe", "goodnotes.exe", "xournalpp.exe",
}
NEUTRO_EXE = {"explorer.exe", "python.exe", "pythonw.exe", "ametista.exe", "taskmgr.exe", "systemsettings.exe",
              "searchhost.exe", "shellexperiencehost.exe", "lockapp.exe", "startmenuexperiencehost.exe",
              "spotify.exe", "applicationframehost.exe"}
NAVEGADORES = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "opera_gx.exe",
               "vivaldi.exe", "arc.exe"}


def _padrao(palavra: str) -> re.Pattern:
    p = _sem_acento(palavra).strip()
    if p.endswith("*"):
        return re.compile(r"(?<![a-z0-9])" + re.escape(p[:-1]))
    return re.compile(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])")


_ESTUDO_RE = [_padrao(p) for p in ESTUDO]
_DISTRACAO_RE = [(_padrao(p), r, prep) for p, r, prep in DISTRACOES]
_X_RE = re.compile(r"/ x(?: -|$)")         # "Página inicial / X - Google Chrome"


def _lista(texto: str) -> list[str]:
    return [p.strip() for p in re.split(r"[;,\n]+", texto or "") if p.strip()]


def _palavras_materia(materia: str) -> list[re.Pattern]:
    return [_padrao(p + "*") for p in re.findall(r"[a-z0-9]{4,}", _sem_acento(materia))]


def classificar(titulo: str, programa: str, caminho: str = "", tela_cheia: bool = False,
                materia: str = "") -> tuple[str, str, str]:
    """(classe, rótulo, preposição). classe: estudo | distracao | neutro."""
    t, prog, cam = _sem_acento(titulo), (programa or "").lower(), _sem_acento(caminho).replace("/", "\\")
    if not t and not prog:
        return "neutro", "", ""
    if prog.startswith("python") or prog == "ametista.exe":       # a própria Ametista
        return "neutro", "", ""
    # o que você configurou vale mais que as listas prontas
    if any(p.search(t) for p in [_padrao(x) for x in _lista(config.FOCO_ESTUDO)] + _palavras_materia(materia)):
        return "estudo", "", ""
    for x in _lista(config.FOCO_DISTRACOES):
        if _padrao(x).search(t) or _sem_acento(x) in (prog, prog.removesuffix(".exe")):
            return "distracao", x, "em"
    # jogos: pela pasta onde estão instalados
    if cam and any(m in cam for m in PASTAS_DE_JOGO):
        nome = (titulo or "").strip()[:40] or prog.removesuffix(".exe")
        return "distracao", nome, "jogando"
    if prog in DISTRACAO_EXE and DISTRACAO_EXE[prog][1] == "jogando":
        return "distracao", *DISTRACAO_EXE[prog]
    if any(p.search(t) for p in _ESTUDO_RE) or prog in ESTUDO_EXE:
        return "estudo", "", ""
    if prog in DISTRACAO_EXE:
        return "distracao", *DISTRACAO_EXE[prog]
    for p, rotulo, prep in _DISTRACAO_RE:
        if p.search(t):
            return "distracao", rotulo, prep
    if _X_RE.search(t):
        return "distracao", "X", "no"
    if tela_cheia and prog not in NAVEGADORES and prog not in NEUTRO_EXE:
        nome = (titulo or "").strip()[:40] or prog.removesuffix(".exe")
        return "distracao", nome, "jogando"
    return "neutro", "", ""


# ====================================================================== horários de estudo
_DIAS = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")
_DIA_RE = r"(seg|ter|qua|qui|sex|sab|dom)"


def _dias(spec: str) -> set[int]:
    spec = spec.strip()
    if not spec or re.search(r"todo|diari|sempre", spec):
        return set(range(7))
    dias: set[int] = set()
    if "uteis" in spec:
        dias |= set(range(5))
    if "fim de semana" in spec or "fds" in spec:
        dias |= {5, 6}
    for a, b in re.findall(_DIA_RE + r"[a-z]*\s*(?:-|a|ate)\s*" + _DIA_RE, spec):
        i, f = _DIAS.index(a), _DIAS.index(b)
        dias |= {(i + k) % 7 for k in range((f - i) % 7 + 1)}
    dias |= {_DIAS.index(d) for d in re.findall(_DIA_RE, spec)}
    return dias or set(range(7))


_HORAS_RE = re.compile(r"(\d{1,2})(?:[:h](\d{2}))?h?\s*(?:-|as|a|ate)\s*(\d{1,2})(?:[:h](\d{2}))?h?")


def horarios(texto: str | None = None) -> list[tuple[set[int], hora, hora]]:
    """'seg-sex 19:00-22:00; sab 9h-12h' -> [({0..4}, 19:00, 22:00), ({5}, 9:00, 12:00)]. Partes inválidas somem."""
    saida = []
    for parte in re.split(r"[;\n]+", _sem_acento(config.FOCO_HORARIOS if texto is None else texto)):
        m = _HORAS_RE.search(parte)
        if not m:
            continue
        try:
            ini = hora(int(m.group(1)), int(m.group(2) or 0))
            fim = hora(int(m.group(3)) % 24, int(m.group(4) or 0))
        except ValueError:
            continue
        if ini != fim:
            saida.append((_dias(parte[:m.start()]), ini, fim))
    return saida


def janela_de_estudo(agora: datetime, texto: str | None = None) -> tuple[datetime, datetime] | None:
    """O horário de estudo em que 'agora' está (inclusive os que passam da meia-noite), ou None."""
    for dia in (agora.date(), agora.date() - timedelta(days=1)):
        for dias, ini, fim in horarios(texto):
            if dia.weekday() not in dias:
                continue
            a = datetime.combine(dia, ini)
            b = datetime.combine(dia, fim)
            if b <= a:
                b += timedelta(days=1)
            if a <= agora < b:
                return a, b
    return None


# ====================================================================== falas
def _duracao(seg: float) -> str:
    m = round(seg / 60)
    if m < 1:
        return "menos de um minuto"
    h, m = divmod(m, 60)
    partes = ([f"{h} hora{'s' if h > 1 else ''}"] if h else []) + ([f"{m} minuto{'s' if m > 1 else ''}"] if m else [])
    return " e ".join(partes)


def _onde(rotulo: str, prep: str) -> str:
    return f"{prep} {rotulo}".strip()


# ====================================================================== sessão
@dataclass
class Sessao:
    inicio: float
    materia: str = ""
    fim: float | None = None                 # hora planejada para acabar (None = até pedir, no máximo 4 h)
    origem: str = "pedido"                   # pedido | horario
    tempos: dict = field(default_factory=lambda: {"estudo": 0.0, "distracao": 0.0, "neutro": 0.0,
                                                  "ausente": 0.0, "pausa": 0.0})
    distracoes: dict = field(default_factory=dict)      # rótulo -> segundos
    preps: dict = field(default_factory=dict)           # rótulo -> "no" / "na" / "jogando"
    avisos: int = 0
    seq_distracao: float = 0.0
    seq_estudo: float = 0.0
    ultimo_aviso: float = 0.0
    pausa_ate: float = 0.0
    anunciar: bool = False                   # sessão do horário que começou com você longe do PC
    salvo: float = 0.0

    def principal(self) -> tuple[str, str] | None:
        if not self.distracoes:
            return None
        r = max(self.distracoes, key=self.distracoes.get)
        return r, self.preps.get(r, "no")


def _resumo(s: Sessao, agora: float) -> str:
    total, est, dis = agora - s.inicio, s.tempos["estudo"], s.tempos["distracao"]
    de = f" de {s.materia}" if s.materia else ""
    if total < 60:
        return f"Sessão{de} encerrada (durou menos de um minuto)."
    base = f"Sessão{de} encerrada: {_duracao(total)} no total, {_duracao(est)} estudando"
    top = s.principal()
    if dis < 60 or not top:
        return base + ". Nenhuma distração. Mandou muito bem!"
    pct = est / max(1.0, est + dis)
    if pct >= 0.8:
        return base + f" e só {_duracao(dis)} de distração. Mandou bem!"
    if pct >= 0.5:
        return base + f" e {_duracao(dis)} em distrações, mais {_onde(*top)}. Dá para melhorar na próxima."
    return (base + f". As distrações levaram {_duracao(dis)}, mais {_onde(*top)}. Na próxima a gente tenta com "
                   "pausas curtas combinadas?")


def _texto_chamado(s: Sessao, agora: float, rotulo: str, prep: str) -> str:
    dono, onde = config.DONO, _onde(rotulo, prep)
    materia = s.materia or "os estudos"
    minutos = max(1, round(s.seq_distracao / 60))
    if s.avisos == 0:
        return f"Ei, {dono}. Faz {minutos} minutos que você está {onde}. Bora voltar para {materia}?"
    if s.avisos == 1:
        resta = round((s.fim - agora) / 60) if s.fim else 0
        falta = f" Faltam {resta} minutos para terminar a sessão." if resta >= 2 else ""
        return f"{dono}, você voltou a ficar {onde}.{falta} Você consegue, vamos lá!"
    return (f"{dono}, {onde} de novo. Se precisar descansar, me pede uma pausa de dez minutos, que eu seguro as "
            f"pontas. Senão, bora voltar para {materia}.")


def _tolerancia() -> float:
    return max(1.0, float(config.FOCO_TOLERANCIA_MIN or 3))


def _pode_chamar() -> bool:
    """Chamado dentro de uma sessão pedida por você: respeita o modo privado e o não perturbe, não o resto."""
    return not estado.privado() and not estado.nao_perturbe_ate() and not estado.ocupado and not estado.falando


_fila_fala: list[tuple[str, str, str]] = []


def _falar(texto: str, emocao: str = "neutra", chave: str = "foco") -> None:
    """Guarda a fala: ela sai depois que o vigia solta a trava (gerar a voz pode levar alguns segundos, e um
    "terminei de estudar" não pode ficar esperando por isso)."""
    _fila_fala.append((texto, emocao, chave))


def _soltar_falas() -> None:
    from . import proatividade

    with _trava:
        falas = list(_fila_fala)
        _fila_fala.clear()
    for texto, emocao, chave in falas:
        proatividade.marcar(chave)
        avisos.proativo(texto, emocao)


# ====================================================================== banco (histórico)
def _db():
    from . import memoria

    con = memoria.db()
    with memoria._trava:
        con.execute("""CREATE TABLE IF NOT EXISTS foco_sessoes(id INTEGER PRIMARY KEY, inicio TEXT, fim TEXT,
            materia TEXT, origem TEXT, estudo REAL, distracao REAL, neutro REAL, ausente REAL, pausa REAL,
            avisos INTEGER, distracoes TEXT)""")
    return con, memoria._trava


def _guardar(s: Sessao, agora: float) -> None:
    if agora - s.inicio < 60:
        return
    con, trava = _db()
    with trava:
        con.execute("INSERT INTO foco_sessoes(inicio, fim, materia, origem, estudo, distracao, neutro, ausente, "
                    "pausa, avisos, distracoes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (datetime.fromtimestamp(s.inicio).isoformat(timespec="seconds"),
                     datetime.fromtimestamp(agora).isoformat(timespec="seconds"), s.materia, s.origem,
                     s.tempos["estudo"], s.tempos["distracao"], s.tempos["neutro"], s.tempos["ausente"],
                     s.tempos["pausa"], s.avisos, json.dumps(s.distracoes, ensure_ascii=False)))
        con.commit()


def sessoes_do_periodo(inicio: datetime, fim: datetime) -> list[dict]:
    con, trava = _db()
    with trava:
        linhas = con.execute("SELECT * FROM foco_sessoes WHERE inicio >= ? AND inicio < ? ORDER BY inicio",
                             (inicio.isoformat(timespec="seconds"), fim.isoformat(timespec="seconds"))).fetchall()
    saida = []
    for l in linhas:
        d = dict(l)
        try:
            d["distracoes"] = json.loads(d.get("distracoes") or "{}")
        except ValueError:
            d["distracoes"] = {}
        saida.append(d)
    return saida


# ====================================================================== o vigia
class Monitor:
    def __init__(self):
        self.sessao: Sessao | None = None
        self.ultimo = 0.0
        self.ligado = False
        # fora das sessões
        self.estudo_recente = 0.0
        self.ultimo_estudo = 0.0
        self.seq_distracao = 0.0
        self.seq_estudo = 0.0
        self._restaurar()

    # ---------------------------------------------------------------- ciclo
    def ligar(self) -> None:
        with _trava:
            if self.ligado:
                return
            self.ligado = True
        threading.Thread(target=self._loop, daemon=True, name="foco").start()

    def _loop(self) -> None:
        while True:
            try:
                self.rodada()
            except Exception as e:
                print(f"[foco] erro: {e}")
            time.sleep(TICK_S)

    def rodada(self, agora: float | None = None, janela: tuple[str, str, str] | None = None,
               ocioso: float | None = None, tela_cheia: bool | None = None) -> None:
        from . import pc

        agora = agora or time.time()
        try:
            self._rodada(agora, janela, ocioso, tela_cheia)
        finally:
            _soltar_falas()

    def _rodada(self, agora: float, janela, ocioso, tela_cheia) -> None:
        from . import pc

        with _trava:
            dt = max(0.0, min(agora - self.ultimo, 2 * TICK_S)) if self.ultimo else 0.0   # relógio acertado
            self.ultimo = agora
            if estado.privado():                     # modo privado: não olha nada
                return
            self._horario(agora)
            s = self.sessao
            if s is None and not (config.FOCO_PERCEBER and config.PROATIVIDADE >= 2):
                return
            titulo, prog, caminho = janela if janela is not None else pc.janela_ativa_info(caminho=True)
            ocioso = pc.tempo_ocioso() if ocioso is None else ocioso
            if tela_cheia is None:
                tela_cheia = pc.tela_cheia() if prog.lower() not in NAVEGADORES else False
            classe, rotulo, prep = classificar(titulo, prog, caminho, tela_cheia, s.materia if s else "")
            if ocioso is not None and ocioso > AUSENTE_S and not (classe == "estudo" and ocioso < LEITURA_S):
                classe = "ausente"
            if s is not None:
                self._na_sessao(s, agora, dt, classe, rotulo, prep)
            else:
                self._fora_da_sessao(agora, dt, classe, rotulo, prep)

    # ---------------------------------------------------------------- dentro da sessão
    def _na_sessao(self, s: Sessao, agora: float, dt: float, classe: str, rotulo: str, prep: str) -> None:
        if s.anunciar and classe != "ausente" and _pode_chamar():
            s.anunciar = False
            ate = f" até as {datetime.fromtimestamp(s.fim):%H:%M}" if s.fim else ""
            _falar(f"Hora de estudar, {config.DONO}! Eu fico de olho nas distrações{ate}.", "feliz")
        if s.pausa_ate:
            if agora < s.pausa_ate:
                s.tempos["pausa"] += dt
                return self._salvar_ativa(agora)
            s.pausa_ate = 0.0
            s.seq_distracao = 0.0
            if _pode_chamar():
                _falar(f"A pausa acabou, {config.DONO}. Bora voltar para {s.materia or 'os estudos'}?", "feliz")
        s.tempos[classe] = s.tempos.get(classe, 0.0) + dt
        if classe == "distracao":
            s.distracoes[rotulo] = s.distracoes.get(rotulo, 0.0) + dt
            s.preps[rotulo] = prep
            s.seq_distracao += dt
            s.seq_estudo = 0.0
        elif classe == "estudo":
            s.seq_estudo += dt
            if s.seq_estudo >= VOLTOU_S:
                s.seq_distracao = 0.0
        elif classe == "ausente":
            s.seq_distracao = s.seq_estudo = 0.0
        # neutro (Explorer, um site qualquer): a contagem fica parada, sem zerar
        if classe == "distracao" and s.seq_distracao >= _tolerancia() * 60 and \
                agora - s.ultimo_aviso >= REPETIR_S and _pode_chamar():
            _falar(_texto_chamado(s, agora, rotulo, prep), "pensativa")
            s.avisos += 1
            s.ultimo_aviso = agora
        limite = s.fim if s.fim else s.inicio + MAX_SESSAO_MIN * 60
        if agora >= limite:
            texto = self.encerrar(agora)
            if texto and not estado.privado():
                _falar(texto, "feliz")
            return
        self._salvar_ativa(agora)

    # ---------------------------------------------------------------- fora da sessão
    def _fora_da_sessao(self, agora: float, dt: float, classe: str, rotulo: str, prep: str) -> None:
        from . import proatividade

        if agora - self.ultimo_estudo > ESTUDO_RECENTE_S:
            self.estudo_recente = 0.0
        if classe == "estudo":
            self.estudo_recente += dt
            self.ultimo_estudo = agora
            self.seq_estudo += dt
            if self.seq_estudo >= VOLTOU_S:
                self.seq_distracao = 0.0
        elif classe == "distracao":
            self.seq_distracao += dt
            self.seq_estudo = 0.0
        elif classe == "ausente":
            self.seq_distracao = self.seq_estudo = self.estudo_recente = 0.0
        if classe == "distracao" and self.estudo_recente >= ESTUDOU_MIN * 60 and \
                self.seq_distracao >= ESPONTANEO_MIN * 60:
            if proatividade.pode_falar(proatividade.NORMAL, 2, "foco_espontaneo", 1, tela_cheia=False):
                proatividade.marcar("foco_espontaneo")
                _falar(f"{config.DONO}, você estava estudando e já faz {round(self.seq_distracao / 60)} minutos "
                       f"{_onde(rotulo, prep)}. Quer voltar? Se quiser, eu marco uma sessão de foco com você.",
                       "pensativa", "foco_espontaneo")
                self.seq_distracao = self.estudo_recente = 0.0

    # ---------------------------------------------------------------- horários
    def _horario(self, agora: float) -> None:
        if not config.FOCO_HORARIOS.strip():
            return
        j = janela_de_estudo(datetime.fromtimestamp(agora))
        if j is None:
            return
        chave = f"{j[0]:%Y-%m-%d %H:%M}"
        if estado.obter("foco_horario") == chave:
            return
        estado.lembrar("foco_horario", chave)     # parou antes do fim? não recomeça no mesmo horário
        if self.sessao is None:
            self.sessao = Sessao(inicio=agora, fim=j[1].timestamp(), origem="horario", anunciar=True)
            self._salvar_ativa(agora, forcar=True)

    # ---------------------------------------------------------------- comandos
    def iniciar(self, minutos: float = 0, materia: str = "", agora: float | None = None) -> str:
        agora = agora or time.time()
        minutos = max(0.0, min(float(minutos or 0), MAX_SESSAO_MIN))
        materia = str(materia or "").strip()[:60]
        with _trava:
            s = self.sessao
            if s is not None:
                if materia:
                    s.materia = materia
                if minutos:
                    s.fim = agora + minutos * 60
                s.pausa_ate = 0.0
                self._salvar_ativa(agora, forcar=True)
                return ("A sessão de foco continua" + (f" ({s.materia})" if s.materia else "") +
                        (f", agora até as {datetime.fromtimestamp(s.fim):%H:%M}" if s.fim else "") + ".")
            self.sessao = Sessao(inicio=agora, materia=materia, fim=agora + minutos * 60 if minutos else None)
            self.seq_distracao = 0.0
            self._salvar_ativa(agora, forcar=True)
        self.ligar()
        quanto = (f"por {_duracao(minutos * 60)} (até as {datetime.fromtimestamp(agora + minutos * 60):%H:%M})"
                  if minutos else "sem hora para acabar (diga 'terminei de estudar' para encerrar)")
        de = f" de {materia}" if materia else ""
        return (f"Sessão de foco{de} começou, {quanto}. Se você ficar mais de {_duracao(_tolerancia() * 60)} "
                "seguidos numa distração, eu te chamo de volta.")

    def encerrar(self, agora: float | None = None) -> str:
        agora = agora or time.time()
        with _trava:
            s, self.sessao = self.sessao, None
            estado.lembrar("foco_sessao", None)
        if s is None:
            return ""
        _guardar(s, agora)
        return _resumo(s, agora)

    def pausar(self, minutos: float = 5, agora: float | None = None) -> str:
        agora = agora or time.time()
        minutos = max(1.0, min(float(minutos or 5), 60))
        with _trava:
            if self.sessao is None:
                return "Não há sessão de foco agora. Aproveite a pausa!"
            self.sessao.pausa_ate = agora + minutos * 60
            self.sessao.seq_distracao = 0.0
            self._salvar_ativa(agora, forcar=True)
        return f"Pausa de {_duracao(minutos * 60)}. Eu te chamo quando acabar."

    # ---------------------------------------------------------------- sobrevive a reinícios (atualização)
    def _salvar_ativa(self, agora: float, forcar: bool = False) -> None:
        s = self.sessao
        if s is None or (not forcar and agora - s.salvo < 60):
            return
        s.salvo = agora
        estado.lembrar("foco_sessao", asdict(s))

    def _restaurar(self) -> None:
        dados = estado.obter("foco_sessao")
        if not isinstance(dados, dict):
            return
        try:
            s = Sessao(**dados)
        except TypeError:
            estado.lembrar("foco_sessao", None)
            return
        agora = time.time()
        limite = s.fim if s.fim else s.inicio + MAX_SESSAO_MIN * 60
        if agora - s.salvo > 30 * 60 or agora >= limite:       # ficou desligada muito tempo: fecha a sessão
            _guardar(s, min(agora, max(s.salvo, s.inicio)))
            estado.lembrar("foco_sessao", None)
            return
        self.sessao = s


_monitor: Monitor | None = None


def monitor() -> Monitor:
    global _monitor
    with _trava:
        if _monitor is None:
            _monitor = Monitor()
        return _monitor


def ligar() -> Monitor:
    """Começa a olhar (o servidor chama ao iniciar)."""
    m = monitor()
    m.ligar()
    return m


def resumo_contexto() -> str:
    """Uma linha para o contexto do cérebro quando há sessão de foco."""
    s = monitor().sessao if _monitor else None
    if s is None:
        return ""
    agora = time.time()
    txt = f"Sessão de foco nos estudos em andamento{' (' + s.materia + ')' if s.materia else ''}: há " \
          f"{_duracao(agora - s.inicio)}"
    if s.fim:
        txt += f", até as {datetime.fromtimestamp(s.fim):%H:%M}"
    if s.pausa_ate > agora:
        txt += f", em pausa até as {datetime.fromtimestamp(s.pausa_ate):%H:%M}"
    return txt + ". Se ele disser que terminou de estudar, use foco_parar."


# ====================================================================== ferramentas
def iniciar(minutos: float = 0, materia: str = "") -> str:
    return monitor().iniciar(minutos, materia)


def parar() -> str:
    return monitor().encerrar() or "Não havia sessão de foco em andamento."


def pausar(minutos: float = 5) -> str:
    return monitor().pausar(minutos)


def _periodo(periodo: str) -> tuple[datetime, datetime, str]:
    hoje = datetime.combine(date.today(), hora())
    p = _sem_acento(periodo or "semana")
    if p == "hoje":
        return hoje, hoje + timedelta(days=1), "Hoje"
    if p == "ontem":
        return hoje - timedelta(days=1), hoje, "Ontem"
    if p.startswith(("mes", "30")):
        return hoje - timedelta(days=29), hoje + timedelta(days=1), "Nos últimos 30 dias"
    if p in ("tudo", "sempre"):
        return datetime(2000, 1, 1), hoje + timedelta(days=1), "Desde o começo"
    return hoje - timedelta(days=6), hoje + timedelta(days=1), "Nos últimos 7 dias"


def relatorio(periodo: str = "semana") -> str:
    ini, fim, rotulo = _periodo(periodo)
    sessoes = sessoes_do_periodo(ini, fim)
    s = monitor().sessao
    agora_txt = ""
    if s is not None:
        agora_txt = (f" Agora: sessão{' de ' + s.materia if s.materia else ''} em andamento há "
                     f"{_duracao(time.time() - s.inicio)}, {_duracao(s.tempos['estudo'])} estudando até aqui.")
    if not sessoes:
        return (f"{rotulo}: nenhuma sessão de foco terminada. Para começar, diga algo como 'vou estudar cálculo "
                f"por uma hora'.{agora_txt}")
    est = sum(x["estudo"] for x in sessoes)
    dis = sum(x["distracao"] for x in sessoes)
    distracoes: dict[str, float] = {}
    materias: dict[str, float] = {}
    dias: dict[str, float] = {}
    for x in sessoes:
        for r, v in x["distracoes"].items():
            distracoes[r] = distracoes.get(r, 0.0) + v
        if x["materia"]:
            materias[x["materia"]] = materias.get(x["materia"], 0.0) + x["estudo"]
        d = x["inicio"][:10]
        dias[d] = dias.get(d, 0.0) + x["estudo"]
    n = len(sessoes)
    partes = [f"{rotulo}: {n} sessão{'ões' if n > 1 else ''} de foco, {_duracao(est)} estudando e "
              f"{_duracao(dis)} em distrações ({round(100 * est / max(1.0, est + dis))}% de foco)."]
    tops = sorted(((r, v) for r, v in distracoes.items() if v >= 60), key=lambda i: -i[1])[:3]
    if tops:
        partes.append("O que mais te distraiu: " + ", ".join(f"{r} ({_duracao(v)})" for r, v in tops) + ".")
    if materias:
        partes.append("Por matéria: " + ", ".join(f"{m} ({_duracao(v)})"
                                                  for m, v in sorted(materias.items(), key=lambda i: -i[1])[:5]) + ".")
    if len(dias) > 1:
        melhor = max(dias, key=dias.get)
        dia = datetime.fromisoformat(melhor)
        nomes = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
        partes.append(f"O dia mais produtivo foi {nomes[dia.weekday()]} ({dia:%d/%m}), com {_duracao(dias[melhor])}.")
    return " ".join(partes) + agora_txt


DEFINICOES = [
    {"name": "foco_iniciar",
     "description": "Começa (ou ajusta) uma sessão de foco nos estudos: você passa a perceber quando o usuário troca "
                    "o estudo por distrações (YouTube, redes sociais, jogos) e chama ele de volta. Use quando ele "
                    "disser que vai estudar ou focar ('vou estudar cálculo por uma hora', 'me ajuda a focar', "
                    "'me vigia enquanto eu estudo').",
     "input_schema": {"type": "object", "properties": {
         "minutos": {"type": "number", "description": "duração; 0 = até ele dizer que terminou (no máximo 4 h)"},
         "materia": {"type": "string", "description": "a matéria ou o assunto, se ele disser"}}}},
    {"name": "foco_pausar", "description": "Pausa a sessão de foco por alguns minutos ('vou fazer uma pausa de 10 "
                                           "minutos'). Você avisa quando a pausa acabar.",
     "input_schema": {"type": "object", "properties": {"minutos": {"type": "number"}}}},
    {"name": "foco_parar", "description": "Encerra a sessão de foco ('terminei de estudar') e devolve o resumo: "
                                          "tempo estudando, tempo em distrações e com o quê. Fale o resumo.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "foco_relatorio",
     "description": "Como foram os estudos: sessões, tempo estudando, principais distrações, matérias e o melhor dia "
                    "('como foram meus estudos essa semana?', 'quanto eu estudei hoje?').",
     "input_schema": {"type": "object", "properties": {
         "periodo": {"type": "string", "description": "hoje, ontem, semana (padrão), mes ou tudo"}}}},
]
FUNCOES = {"foco_iniciar": iniciar, "foco_pausar": pausar, "foco_parar": parar, "foco_relatorio": relatorio}

acoes.registrar_ferramenta(
    "foco_iniciar", descrever=lambda a: "Começou uma sessão de foco" + (
        f" ({a['materia']})" if a.get("materia") else "") + (f", {int(a['minutos'])} min" if a.get("minutos") else ""))
acoes.registrar_ferramenta("foco_pausar", descrever=lambda a: f"Pausou o foco por {int(a.get('minutos') or 5)} min")
acoes.registrar_ferramenta("foco_parar", descrever=lambda a: "Encerrou a sessão de foco")
acoes.registrar_ferramenta("foco_relatorio", leitura=True)
