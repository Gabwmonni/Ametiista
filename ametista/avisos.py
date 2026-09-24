"""Avisos: alarmes, lembretes, compromissos e o que a Ametista diz por iniciativa própria.

- alerta():   o que você pediu (timer, lembrete, "me avisa quando o jogo instalar"). Toca sempre,
              com o som de alarme, e vai também para o celular.
- proativo(): o que ela diz sozinha (pausa, chuva, bateria). Passa pelas regras de proatividade.py.
Tudo fica na lista de avisos (aba "Avisos" da sobreposição e do celular).
"""
import threading
import time
from collections import deque
from datetime import datetime

from . import eventos, voz

_lista: deque[dict] = deque(maxlen=100)
_trava = threading.Lock()
_ids = iter(range(1, 10**12))


def _guardar(tipo: str, texto: str, titulo: str) -> dict:
    item = {"id": next(_ids), "tipo": tipo, "titulo": titulo, "texto": texto,
            "quando": datetime.now().isoformat(timespec="seconds")}
    with _trava:
        _lista.append(item)
    eventos.publicar({"tipo": "aviso_novo", "aviso": item})
    return item


def lista() -> list[dict]:
    with _trava:
        return list(reversed(_lista))


def alerta(texto: str, emocao: str = "surpresa", titulo: str = "Ametista", celular: bool = True,
           tom: bool = True) -> None:
    """Fala um aviso pedido pelo usuário (com som de alarme) e manda para o celular."""
    item = _guardar("alerta", texto, titulo)
    audio = voz.sintetizar_sync(texto)
    eventos.publicar({"tipo": "alerta", "id": f"a{item['id']}", "texto": texto, "emocao": emocao, "audio": audio,
                      "mime": voz.mime_de(audio), "tom": tom})
    if celular:
        eventos.publicar({"tipo": "notificar_celular", "titulo": titulo, "texto": texto, "interno": True})


def proativo(texto: str, emocao: str = "neutra", celular: bool = False, titulo: str = "Ametista") -> None:
    """Fala algo por iniciativa própria (quem decide se pode é proatividade.pode_falar)."""
    item = _guardar("proativo", texto, titulo)
    audio = voz.sintetizar_sync(texto)
    eventos.publicar({"tipo": "alerta", "id": f"a{item['id']}", "texto": texto, "emocao": emocao, "audio": audio,
                      "mime": voz.mime_de(audio), "tom": False, "proativo": True})
    if celular:
        eventos.publicar({"tipo": "notificar_celular", "titulo": titulo, "texto": texto, "interno": True})


def registrar(texto: str, titulo: str = "Ametista", tipo: str = "info") -> None:
    """Só anota na lista (sem falar)."""
    _guardar(tipo, texto, titulo)


def agora_ms() -> int:
    return int(time.time() * 1000)
