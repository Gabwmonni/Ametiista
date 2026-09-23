"""Memória persistente: fatos sobre o dono, lembretes e histórico curto da conversa."""
import json
import threading
import uuid
from datetime import datetime

from .config import DADOS

ARQUIVO = DADOS / "memoria.json"
_trava = threading.Lock()


def _carregar() -> dict:
    if ARQUIVO.exists():
        try:
            return json.loads(ARQUIVO.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"fatos": [], "lembretes": [], "historico": []}


_estado = _carregar()


def _salvar() -> None:
    ARQUIVO.write_text(json.dumps(_estado, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- Fatos ----------
def lembrar_fato(fato: str) -> str:
    with _trava:
        if fato not in _estado["fatos"]:
            _estado["fatos"].append(fato)
            _salvar()
    return f"Guardei: {fato}"


def esquecer_fato(trecho: str) -> str:
    with _trava:
        antes = len(_estado["fatos"])
        _estado["fatos"] = [f for f in _estado["fatos"] if trecho.lower() not in f.lower()]
        _salvar()
        removidos = antes - len(_estado["fatos"])
    return f"Esqueci {removidos} item(ns)." if removidos else "Não achei nada parecido na memória."


def fatos() -> list[str]:
    return list(_estado["fatos"])


# ---------- Lembretes / alarmes / timers ----------
def criar_lembrete(texto: str, quando: datetime, tipo: str = "lembrete") -> dict:
    item = {
        "id": uuid.uuid4().hex[:8],
        "texto": texto,
        "quando": quando.isoformat(timespec="seconds"),
        "tipo": tipo,
    }
    with _trava:
        _estado["lembretes"].append(item)
        _estado["lembretes"].sort(key=lambda x: x["quando"])
        _salvar()
    return item


def lembretes_pendentes() -> list[dict]:
    return list(_estado["lembretes"])


def remover_lembrete(id_: str) -> bool:
    with _trava:
        antes = len(_estado["lembretes"])
        _estado["lembretes"] = [l for l in _estado["lembretes"] if l["id"] != id_]
        _salvar()
        return len(_estado["lembretes"]) < antes


def retirar_vencidos(agora: datetime) -> list[dict]:
    """Remove e devolve os lembretes cuja hora já chegou."""
    with _trava:
        vencidos = [l for l in _estado["lembretes"] if datetime.fromisoformat(l["quando"]) <= agora]
        if vencidos:
            ids = {l["id"] for l in vencidos}
            _estado["lembretes"] = [l for l in _estado["lembretes"] if l["id"] not in ids]
            _salvar()
    return vencidos


# ---------- Histórico da conversa ----------
MAX_HISTORICO = 20


def adicionar_historico(papel: str, texto: str) -> None:
    with _trava:
        _estado["historico"].append({"role": papel, "content": texto})
        _estado["historico"] = _estado["historico"][-MAX_HISTORICO:]
        _salvar()


def historico() -> list[dict]:
    h = list(_estado["historico"])
    # A API exige que a conversa comece pelo usuário.
    while h and h[0]["role"] != "user":
        h.pop(0)
    return h


def limpar_historico() -> None:
    with _trava:
        _estado["historico"] = []
        _salvar()
