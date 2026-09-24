"""Mandar arquivos do PC para o celular, pelo mesmo caminho seguro das mensagens (o relé na Cloudflare).

- O arquivo vai em pedaços (o relé aceita mensagens de até ~1 MB).
- App do celular fechado: o arquivo espera numa fila (dados/para_celular) e chega um aviso no celular. Quando o app
  abre, a entrega acontece sozinha. O arquivo só sai da fila quando o celular confirma que recebeu inteiro.
- Pastas viram um .zip. Limite de 25 MB por arquivo (pensando nos dados móveis).
"""
import base64
import json
import math
import mimetypes
import threading
import time
import uuid
import zipfile
from pathlib import Path

from . import acoes, arquivos_io, config, eventos

MAX_BYTES = 25 * 1024 * 1024
PEDACO = 384 * 1024                 # bytes por mensagem (~512 KB em base64: abaixo do limite do relé)
VALIDADE_DIAS = 7
REENVIO_S = 90                      # sem confirmação nesse tempo, manda de novo na próxima abertura do app
_trava = threading.Lock()
_entregando: set[str] = set()


def fila_pasta() -> Path:
    return config.DADOS / "para_celular"


def _meta(ident: str) -> Path:
    return fila_pasta() / f"{ident}.json"


def _salvar(item: dict) -> None:
    fila_pasta().mkdir(parents=True, exist_ok=True)
    _meta(item["id"]).write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")


def fila() -> list[dict]:
    itens = []
    for m in sorted(fila_pasta().glob("*.json")) if fila_pasta().exists() else []:
        try:
            itens.append(json.loads(m.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(itens, key=lambda i: i.get("criado", 0))


def _remover(item: dict) -> None:
    _meta(item["id"]).unlink(missing_ok=True)
    if item.get("temporario"):
        Path(item["caminho"]).unlink(missing_ok=True)


def _zipar(pasta: Path, destino: Path) -> Path:
    total = 0
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for arq in sorted(pasta.rglob("*")):
            if arq.is_file():
                total += arq.stat().st_size
                if total > MAX_BYTES * 3:          # não vale a pena compactar algo enorme
                    raise ValueError("a pasta é grande demais para mandar ao celular")
                z.write(arq, arq.relative_to(pasta.parent))
    return destino


def _legivel(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB".replace(".", ",") if n >= 1024 * 1024 else f"{max(1, n // 1024)} KB"


def _pode_entregar_agora() -> bool:
    from . import nuvem

    n = nuvem.instancia()
    return n.conectada and (n.celulares > 0 or not n.rele_novo)


def enviar(caminho: str) -> str:
    """Manda um arquivo (ou uma pasta, em .zip) para o app do celular."""
    from . import nuvem
    from .ferramentas import CONTEXTO

    if not nuvem.configurada():
        return "O app do celular ainda não foi publicado: veja 'App do celular' no LEIA-ME (publicar_celular.bat)."
    try:
        p = arquivos_io.resolver(caminho)
    except ValueError as e:
        return f"Erro: {e}"
    if not p.exists():
        return f"Não achei {caminho}. Use arquivos_buscar para achar o caminho."
    fila_pasta().mkdir(parents=True, exist_ok=True)
    ident = uuid.uuid4().hex[:12]
    temporario = False
    if p.is_dir():
        try:
            arquivo, nome, temporario = _zipar(p, fila_pasta() / f"{ident}.zip"), f"{p.name}.zip", True
        except ValueError as e:
            (fila_pasta() / f"{ident}.zip").unlink(missing_ok=True)
            return f"Não mandei: {e}."
    else:
        arquivo, nome = p, p.name
    tamanho = arquivo.stat().st_size
    if tamanho > MAX_BYTES:
        if temporario:
            arquivo.unlink(missing_ok=True)
        return f"{nome} tem {_legivel(tamanho)}: passa do limite de 25 MB para mandar ao celular."
    item = {"id": ident, "nome": nome, "caminho": str(arquivo), "tamanho": tamanho, "temporario": temporario,
            "mime": mimetypes.guess_type(nome)[0] or "application/octet-stream", "criado": time.time(),
            "para": CONTEXTO.get().get("celular")}
    _salvar(item)
    if _pode_entregar_agora():
        threading.Thread(target=entregar, args=(item,), daemon=True, name="envio").start()
        return f"Mandando {nome} ({_legivel(tamanho)}) para o celular."
    eventos.publicar({"tipo": "notificar_celular", "titulo": "Arquivo para você",
                      "texto": f"{nome} está pronto. Abra o app da Ametista para receber."})
    return (f"O app do celular está fechado: {nome} ficou esperando e mandei um aviso. Ele chega assim que você "
            "abrir o app.")


def entregar(item: dict) -> bool:
    """Manda os pedaços. Devolve False se a conexão caiu no meio (fica na fila para a próxima)."""
    from . import nuvem

    with _trava:
        if item["id"] in _entregando:
            return False
        _entregando.add(item["id"])
    try:
        caminho = Path(item["caminho"])
        if not caminho.exists():
            _remover(item)
            return False
        dados = caminho.read_bytes()
        total = max(1, math.ceil(len(dados) / PEDACO))
        n = nuvem.instancia()
        for i in range(total):
            msg = {"tipo": "arquivo", "id": item["id"], "nome": item["nome"], "mime": item["mime"],
                   "tamanho": item["tamanho"], "parte": i, "total": total,
                   "dados": base64.b64encode(dados[i * PEDACO:(i + 1) * PEDACO]).decode()}
            if item.get("para"):
                msg["para"] = item["para"]
            if not n.enviar(msg):
                return False
        item["enviado"] = time.time()
        _salvar(item)
        return True
    finally:
        with _trava:
            _entregando.discard(item["id"])


def confirmar(ident: str) -> None:
    """O celular recebeu o arquivo inteiro: sai da fila."""
    for item in fila():
        if item["id"] == ident:
            _remover(item)
            eventos.publicar({"tipo": "aviso", "texto": f"{item['nome']} chegou no celular.", "interno": True})


def entregar_fila() -> int:
    """Chamado quando um celular abre o app: entrega o que estava esperando (para qualquer celular pareado)."""
    agora, n = time.time(), 0
    for item in fila():
        if agora - item.get("criado", agora) > VALIDADE_DIAS * 86400:
            _remover(item)
            continue
        if item.get("enviado") and agora - item["enviado"] < REENVIO_S:
            continue
        item["para"] = None
        if entregar(item):
            n += 1
    return n


DEFINICOES = [
    {"name": "arquivo_enviar_celular",
     "description": "Manda um arquivo do PC (ou uma pasta, em .zip) para o app do celular do usuário: PDFs, fotos, "
                    "planilhas, notas, o que ele pedir ('me manda o PDF da aula', 'puxa aquela planilha'). Use o "
                    "caminho do arquivos_buscar. Se o app estiver fechado, o arquivo espera e chega quando abrir. "
                    "Limite de 25 MB.",
     "input_schema": {"type": "object", "properties": {"caminho": {"type": "string"}}, "required": ["caminho"]}},
]
FUNCOES = {"arquivo_enviar_celular": enviar}

acoes.registrar_ferramenta("arquivo_enviar_celular", descrever=lambda a: "Mandou para o celular: " + (
    str(a.get("caminho", "")).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]))
