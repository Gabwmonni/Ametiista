"""Fala em trechos: a Ametista começa a falar antes de terminar de pensar.

O cérebro entrega o texto aos pedaços (streaming). O Locutor corta em trechos, manda gerar o áudio de
cada trecho assim que ele fica pronto (dois ao mesmo tempo) e publica na ordem certa para a sobreposição
tocar em sequência. O primeiro trecho é a primeira frase (para começar a falar logo); os seguintes
juntam duas ou três frases, porque a voz soa bem mais natural quando a entonação não recomeça a cada
frase:

    fala_inicio -> fala_trecho (seq 0) -> fala_trecho (seq 1) ... -> fala_fim
"""
import itertools
import re
import threading
from concurrent.futures import Future, ThreadPoolExecutor

from . import eventos, voz
from .personalidade import EMOCOES

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tts")
_ids = itertools.count(1)
_ABREVIACOES = {"sr", "sra", "dr", "dra", "prof", "profa", "etc", "ex", "obs", "n", "nº", "av", "eng", "arq", "pg"}
_EMOCAO = re.compile(r"\[\s*(%s)\s*\]" % "|".join(EMOCOES), re.I)
_FIM_FRASE = re.compile(r"[.!?…]+[\"')\]]*(?=\s)")
TRECHO_MIN = 100     # depois da primeira frase, junta frases até ter pelo menos isso...
TRECHO_MAX = 260     # ...sem passar disso (trecho grande demora mais para gerar)


def _limpar_markdown(t: str) -> str:
    t = re.sub(r"[*#_`]+", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    return t


class Locutor:
    def __init__(self, origem: str = "local", publicar: bool = True, ficha=None, falar: bool = True):
        self.id = f"r{next(_ids)}"
        self.origem = origem
        self.publicar = publicar
        self.falar = falar
        self.ficha = ficha
        self.emocao_atual = "neutra"
        self._buffer = ""
        self._partes: list[str] = []      # texto limpo já cortado
        self._futuros: list[tuple[str, str, Future | None]] = []
        self._iniciado = False
        self._seq = 0
        self._publicador: threading.Thread | None = None
        self._novo = threading.Condition()
        self._terminou = False

    # ------------------------------------------------------------ entrada
    def emocao(self, e: str) -> None:
        if e in EMOCOES:
            self.emocao_atual = e

    def texto(self, delta: str) -> None:
        if not delta:
            return
        self._buffer += delta
        self._cortar(final=False)

    def terminar(self) -> str:
        """Fala o que sobrou, espera tudo tocar na fila e devolve o texto completo (limpo)."""
        self._cortar(final=True)
        with self._novo:
            self._terminou = True
            self._novo.notify_all()
        if self._publicador:
            self._publicador.join(timeout=120)
        if self._iniciado and self.publicar and not self._cancelado():
            eventos.publicar({"tipo": "fala_fim", "id": self.id, "texto": self.texto_completo(),
                              "total": self._seq, "emocao": self.emocao_atual, "origem": self.origem})
        return self.texto_completo()

    def texto_completo(self) -> str:
        return voz.texto_para_mostrar(" ".join(p for p in self._partes if p)).strip()

    @property
    def falou_algo(self) -> bool:
        return self._iniciado

    # ------------------------------------------------------------ corte em frases
    def _cancelado(self) -> bool:
        return bool(self.ficha and self.ficha.cancelado)

    def _achar_corte(self, texto: str, final: bool) -> int:
        primeiro = not self._partes
        quebra = texto.find("\n")
        if quebra >= 0:  # quebra de linha sempre fecha um trecho (fim de parágrafo, antes de uma ferramenta)
            antes = texto[:quebra]
            fim_frase = _FIM_FRASE.search(antes + " ")
            if not fim_frase or fim_frase.end() >= len(antes.rstrip()):
                return quebra + 1
        fins = []
        for m in _FIM_FRASE.finditer(texto):
            fim = m.end()
            antes = re.findall(r"(\w+)[.]$", texto[:fim].rstrip("\"')]"))
            if antes and antes[-1].lower() in _ABREVIACOES:
                continue
            if len(texto[:fim].strip()) >= 2:
                if primeiro:
                    return fim
                fins.append(fim)
        if fins:
            cabem = [f for f in fins if f <= TRECHO_MAX]
            if not cabem:
                return fins[0]                       # uma frase só já passa do tamanho: vai sozinha
            if cabem[-1] >= TRECHO_MIN or len(texto) > TRECHO_MAX:
                return cabem[-1]                     # duas ou três frases juntas
            if not final:
                return -1                            # espera mais frases para juntar
        if primeiro and len(texto) > 70:  # primeira frase longa: corta na vírgula para começar logo
            m = list(re.finditer(r"[,;:](?=\s)", texto[:160]))
            if m and m[-1].end() >= 25:
                return m[-1].end()
        if len(texto) > 240:  # sem ponto há muito tempo: corta no último espaço
            corte = texto.rfind(" ", 0, 220)
            return corte if corte > 40 else 220
        return len(texto) if final else -1

    def _cortar(self, final: bool) -> None:
        while self._buffer:
            corte = self._achar_corte(self._buffer, final)
            if corte <= 0:
                return
            pedaco, self._buffer = self._buffer[:corte], self._buffer[corte:]
            self._emitir(pedaco)

    def _emitir(self, bruto: str) -> None:
        emocoes = _EMOCAO.findall(bruto)
        if emocoes:
            self.emocao(emocoes[0].lower())
        falado = _limpar_markdown(_EMOCAO.sub("", bruto)).strip()
        mostrado = voz.texto_para_mostrar(falado)
        if not re.search(r"\w", mostrado):
            return
        self._partes.append(mostrado)
        if not self.publicar or self._cancelado():
            return
        futuro = _executor.submit(voz.sintetizar_sync, falado) if self.falar else None
        with self._novo:
            self._futuros.append((mostrado, self.emocao_atual, futuro))
            self._novo.notify_all()
        if self._publicador is None:
            self._publicador = threading.Thread(target=self._publicar_em_ordem, daemon=True, name=f"fala-{self.id}")
            self._publicador.start()

    # ------------------------------------------------------------ saída na ordem
    def _publicar_em_ordem(self) -> None:
        i = 0
        while True:
            with self._novo:
                while i >= len(self._futuros) and not self._terminou:
                    self._novo.wait(0.5)
                if i >= len(self._futuros):
                    return
                mostrado, emocao, futuro = self._futuros[i]
            i += 1
            audio = None
            if futuro is not None:
                try:
                    audio = futuro.result(timeout=45)
                except Exception as e:
                    print(f"[fala] trecho sem áudio: {e}")
            if self._cancelado():
                continue
            if not self._iniciado:
                self._iniciado = True
                eventos.publicar({"tipo": "fala_inicio", "id": self.id, "emocao": emocao, "origem": self.origem})
            eventos.publicar({"tipo": "fala_trecho", "id": self.id, "seq": self._seq, "texto": mostrado,
                              "emocao": emocao, "audio": audio, "mime": voz.mime_de(audio)})
            self._seq += 1


def falar(texto: str, emocao: str = "neutra", origem: str = "local", ficha=None) -> str:
    """Fala um texto pronto (confirmações, avisos locais) pelo mesmo caminho dos trechos."""
    loc = Locutor(origem=origem, ficha=ficha)
    loc.emocao(emocao)
    loc.texto(texto)
    return loc.terminar()
