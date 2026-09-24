"""Estado de funcionamento da Ametista (o que vale para o programa inteiro).

- modo privado: microfone, memória e iniciativa desligados de uma vez;
- não perturbe: ela não puxa assunto até um horário;
- pedido em andamento: pode ser cancelado a qualquer momento ("para tudo");
- offline: sem internet, usa o cérebro local.
"""
import json
import threading
import time
from datetime import datetime

from . import config, eventos

ARQUIVO = config.DADOS / "estado.json"
_trava = threading.RLock()


class Cancelado(Exception):
    """O pedido foi interrompido (parar tudo, interrupção por voz ou um pedido novo)."""


class Ficha:
    """Identifica um pedido em andamento e permite cancelá-lo de outra thread."""

    def __init__(self, texto: str = "", origem: str = "pc"):
        self.texto = texto
        self.origem = origem
        self.criado = time.time()
        self._cancelado = threading.Event()

    def cancelar(self) -> None:
        self._cancelado.set()

    @property
    def cancelado(self) -> bool:
        return self._cancelado.is_set()

    def conferir(self) -> None:
        if self._cancelado.is_set():
            raise Cancelado()

    def esperar(self, segundos: float) -> bool:
        """Dorme até `segundos` ou até ser cancelado. Devolve True se foi cancelado."""
        return self._cancelado.wait(segundos)


def _carregar() -> dict:
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_persistente = _carregar()
_fichas: set[Ficha] = set()
offline = False
ocupado = False              # atendendo um pedido agora
falando = False              # a sobreposição está tocando a voz dela
inicio_processo = time.time()
_fim_da_fala = 0.0           # quando ela parou de falar pela última vez (relógio monotônico)


def definir_falando(valor: bool) -> None:
    global falando, _fim_da_fala
    if falando and not valor:
        _fim_da_fala = time.monotonic()
    falando = valor


def segundos_desde_que_falou() -> float:
    """0 enquanto ela fala; infinito se ainda não falou nada desde que ligou."""
    if falando:
        return 0.0
    return time.monotonic() - _fim_da_fala if _fim_da_fala else float("inf")


def _salvar() -> None:
    try:
        ARQUIVO.write_text(json.dumps(_persistente, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as e:
        print(f"[estado] não consegui salvar: {e}")


def _publicar() -> None:
    eventos.publicar({"tipo": "estado", **resumo()})


def resumo() -> dict:
    return {"privado": privado(), "nao_perturbe": nao_perturbe_ate(), "offline": offline}


# ---------------------------------------------------------------- modo privado
def privado() -> bool:
    return bool(_persistente.get("privado"))


def definir_privado(ligado: bool) -> None:
    with _trava:
        if privado() == bool(ligado):
            return
        _persistente["privado"] = bool(ligado)
        _salvar()
    eventos.publicar({"tipo": "privado", "valor": bool(ligado), "interno": True})
    _publicar()


# ---------------------------------------------------------------- não perturbe
def nao_perturbe_ate() -> str | None:
    ate = _persistente.get("nao_perturbe_ate")
    if not ate:
        return None
    try:
        if datetime.fromisoformat(ate) <= datetime.now():
            return None
    except ValueError:
        return None
    return ate


def definir_nao_perturbe(ate: datetime | None) -> None:
    with _trava:
        _persistente["nao_perturbe_ate"] = ate.isoformat(timespec="minutes") if ate else None
        _salvar()
    _publicar()


def silencio_agora(agora: datetime | None = None) -> bool:
    """Horário de silêncio configurado (ex.: 22:00-07:00) ou não perturbe ligado."""
    if nao_perturbe_ate():
        return True
    agora = agora or datetime.now()
    try:
        ini, fim = [datetime.strptime(p.strip(), "%H:%M").time() for p in config.HORARIO_SILENCIO.split("-")]
    except ValueError:
        return False
    t = agora.time()
    return (ini <= t < fim) if ini <= fim else (t >= ini or t < fim)


# ---------------------------------------------------------------- memória persistente simples
def lembrar(chave: str, valor) -> None:
    with _trava:
        _persistente[chave] = valor
        _salvar()


def obter(chave: str, padrao=None):
    return _persistente.get(chave, padrao)


# ---------------------------------------------------------------- pedidos em andamento
def nova_ficha(texto: str = "", origem: str = "pc") -> Ficha:
    f = Ficha(texto, origem)
    with _trava:
        _fichas.add(f)
    return f


def encerrar_ficha(f: Ficha) -> None:
    with _trava:
        _fichas.discard(f)


def cancelar_pedidos(origem: str | None = None) -> int:
    """Cancela os pedidos em andamento (todos, ou só os de uma origem)."""
    with _trava:
        alvo = [f for f in _fichas if origem is None or f.origem == origem]
    for f in alvo:
        f.cancelar()
    return len(alvo)


def definir_offline(valor: bool) -> None:
    global offline
    if offline != valor:
        offline = valor
        _publicar()
