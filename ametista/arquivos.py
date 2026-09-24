"""Achar arquivos pelo nome falado ("abre a planta de Jundiaí", "cadê a planilha de orçamento?").

Mantém um índice dos nomes dos arquivos das suas pastas (Área de Trabalho, Documentos, Downloads,
Imagens, OneDrive e as pastas extras do painel) em dados/arquivos.db. Só nomes e datas: o conteúdo dos
arquivos não é lido. O índice é refeito em segundo plano a cada 6 horas.
"""
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from . import config

ARQUIVO = config.DADOS / "arquivos.db"
MAX_ARQUIVOS = 300_000
MAX_PROFUNDIDADE = 9
IGNORAR = {"node_modules", "__pycache__", "appdata", "$recycle.bin", "system volume information", ".git",
           ".venv", "venv", "site-packages", "cache", "caches", "temp", "tmp"}
EXECUTAVEIS = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".msi", ".msp", ".scr",
               ".com", ".cpl", ".hta", ".reg", ".jar", ".py", ".pyw"}
TIPOS = {
    "planilha": {".xlsx", ".xls", ".xlsm", ".csv", ".ods"},
    "documento": {".docx", ".doc", ".pdf", ".odt", ".rtf", ".txt", ".md"},
    "pdf": {".pdf"},
    "apresentacao": {".pptx", ".ppt", ".odp", ".key"},
    "imagem": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp", ".tif", ".tiff"},
    "desenho": {".dwg", ".dxf", ".rvt", ".skp", ".ifc", ".pdf"},
    "video": {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".webm"},
    "audio": {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"},
    "compactado": {".zip", ".rar", ".7z", ".tar", ".gz"},
}
_DICAS_TIPO = {
    "planilha": "planilha", "tabela": "planilha", "excel": "planilha", "documento": "documento",
    "word": "documento", "texto": "documento", "pdf": "pdf", "apresentacao": "apresentacao",
    "slides": "apresentacao", "powerpoint": "apresentacao", "foto": "imagem", "fotos": "imagem",
    "imagem": "imagem", "print": "imagem", "planta": "desenho", "desenho": "desenho", "projeto": "desenho",
    "dwg": "desenho", "autocad": "desenho", "video": "video", "musica": "audio", "audio": "audio",
    "zip": "compactado", "rar": "compactado",
}
_VAZIAS = {"o", "a", "os", "as", "de", "do", "da", "dos", "das", "e", "em", "no", "na", "arquivo", "arquivos",
           "meu", "minha", "aquele", "aquela", "esse", "essa", "um", "uma", "pasta", "que", "com", "pra", "para"}

_trava = threading.Lock()
_indexando = threading.Event()


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


def pastas() -> list[Path]:
    casa = Path.home()
    candidatas = [casa / n for n in ("Desktop", "Área de Trabalho", "Documents", "Documentos", "Downloads",
                                     "Pictures", "Imagens", "Videos", "Vídeos")]
    for od in [casa / "OneDrive"] + sorted(casa.glob("OneDrive - *")):
        candidatas.append(od)
    candidatas += [Path(p.strip().strip('"')) for p in config.PASTAS_INDICE.split(";") if p.strip()]
    vistas, saida = set(), []
    for p in candidatas:
        try:
            r = p.resolve()
        except OSError:
            continue
        if r.is_dir() and r not in vistas and not any(r.is_relative_to(v) for v in vistas):
            vistas.add(r)
            saida.append(r)
    return saida


def _conectar() -> sqlite3.Connection:
    con = sqlite3.connect(ARQUIVO, check_same_thread=False, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE IF NOT EXISTS arquivos(caminho TEXT PRIMARY KEY, nome TEXT, busca TEXT, "
                "ext TEXT, tamanho INTEGER, modificado REAL)")
    con.execute("CREATE TABLE IF NOT EXISTS info(chave TEXT PRIMARY KEY, valor TEXT)")
    return con


def _varrer(raiz: Path, saida: list, profundidade: int = 0) -> None:
    if profundidade > MAX_PROFUNDIDADE or len(saida) >= MAX_ARQUIVOS:
        return
    try:
        itens = list(os.scandir(raiz))
    except OSError:
        return
    for e in itens:
        nome = e.name
        if nome.startswith((".", "~$")):
            continue
        try:
            if e.is_dir(follow_symlinks=False):
                if nome.lower() not in IGNORAR:
                    _varrer(Path(e.path), saida, profundidade + 1)
            elif e.is_file(follow_symlinks=False):
                st = e.stat(follow_symlinks=False)
                ext = os.path.splitext(nome)[1].lower()
                saida.append((e.path, nome, _norm(os.path.splitext(nome)[0]) + " " + _norm(Path(e.path).parent.name),
                              ext, st.st_size, st.st_mtime))
        except OSError:
            continue
        if len(saida) >= MAX_ARQUIVOS:
            return


def indexar() -> int:
    """Refaz o índice (demora de segundos a poucos minutos, em segundo plano)."""
    if _indexando.is_set():
        return -1
    _indexando.set()
    try:
        linhas: list = []
        for p in pastas():
            _varrer(p, linhas)
        with _trava:
            con = _conectar()
            con.execute("DELETE FROM arquivos")
            con.executemany("INSERT OR REPLACE INTO arquivos VALUES (?,?,?,?,?,?)", linhas)
            con.execute("INSERT OR REPLACE INTO info VALUES ('atualizado', ?)", (str(time.time()),))
            con.commit()
            con.close()
        print(f"[arquivos] índice pronto: {len(linhas)} arquivos")
        return len(linhas)
    finally:
        _indexando.clear()


def iniciar_vigia() -> None:
    def loop():
        time.sleep(60)
        while True:
            try:
                indexar()
            except Exception as e:
                print(f"[arquivos] falha ao indexar: {e}")
            time.sleep(6 * 3600)
    threading.Thread(target=loop, daemon=True, name="indice-arquivos").start()


def total() -> int:
    if not ARQUIVO.exists():
        return 0
    with _trava:
        con = _conectar()
        n = con.execute("SELECT COUNT(*) FROM arquivos").fetchone()[0]
        con.close()
    return n


def buscar(consulta: str, tipo: str = "", limite: int = 8) -> list[dict]:
    palavras = [p for p in _norm(consulta).split() if p not in _VAZIAS]
    tipo = _norm(tipo)
    exts = TIPOS.get(_DICAS_TIPO.get(tipo, tipo), set())
    if not exts:
        for p in palavras:
            if p in _DICAS_TIPO:
                exts = TIPOS[_DICAS_TIPO[p]]
                break
    termos = [p for p in palavras if p not in _DICAS_TIPO or len(palavras) == 1] or palavras
    if not termos and not exts:
        return []
    if not ARQUIVO.exists():
        return []
    filtros, params = [], []
    for p in termos[:6]:
        raiz = p[:-1] if len(p) > 4 and p.endswith("s") else p  # plural simples
        filtros.append("busca LIKE ?")
        params.append(f"%{raiz}%")
    sql = "SELECT * FROM arquivos"
    if filtros:
        sql += " WHERE (" + " OR ".join(filtros) + ")"
    with _trava:
        con = _conectar()
        linhas = [dict(r) for r in con.execute(sql + " LIMIT 5000", params)]
        con.close()
    agora = time.time()
    notas = []
    for r in linhas:
        acertos = sum(1 for p in termos if (p[:-1] if len(p) > 4 and p.endswith("s") else p) in r["busca"])
        nota = acertos / max(1, len(termos))
        if exts:
            nota += 0.35 if r["ext"] in exts else -0.3
        if r["ext"] in EXECUTAVEIS or r["ext"] in (".lnk", ".tmp", ".ini", ".log", ".dll"):
            nota -= 0.2
        dias = (agora - (r["modificado"] or 0)) / 86400
        nota += 0.15 / (1 + dias / 30)  # mais recente, um pouco melhor
        notas.append((nota, r))
    notas.sort(key=lambda x: x[0], reverse=True)
    return [r for n, r in notas[:limite] if n > 0.3]


def descrever(r: dict) -> str:
    quando = datetime.fromtimestamp(r["modificado"]).strftime("%d/%m/%Y")
    tam = r["tamanho"] / 1e6
    return f"{r['nome']} (em {Path(r['caminho']).parent.name}, modificado em {quando}, {tam:.1f} MB) -> {r['caminho']}"


# ---------------------------------------------------------------- ferramentas
def ferramenta_buscar(consulta: str, tipo: str = "") -> str:
    achados = buscar(consulta, tipo)
    if not achados:
        n = total()
        if not n:
            return "O índice de arquivos ainda está sendo montado. Tente de novo em alguns minutos."
        return f"Não achei arquivos parecidos com '{consulta}' ({n} arquivos no índice)."
    return "Arquivos encontrados (o primeiro é o mais provável):\n" + "\n".join(
        f"{i + 1}. {descrever(r)}" for i, r in enumerate(achados))


def _dentro_das_pastas(caminho: Path) -> bool:
    try:
        r = caminho.resolve()
    except OSError:
        return False
    return any(r.is_relative_to(p) for p in pastas())


def abrir(caminho: str) -> str:
    p = Path(caminho.strip().strip('"'))
    if not p.exists():
        achados = buscar(caminho)
        if not achados:
            return f"Não achei o arquivo {caminho}."
        p = Path(achados[0]["caminho"])
    if not _dentro_das_pastas(p):
        return "Só abro arquivos das suas pastas pessoais (Documentos, Downloads, Área de Trabalho...)."
    if sys.platform == "win32":
        os.startfile(str(p))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return f"Abrindo {p.name}."


def mostrar_na_pasta(caminho: str) -> str:
    p = Path(caminho.strip().strip('"'))
    if not p.exists():
        return f"Não achei o arquivo {caminho}."
    if sys.platform == "win32":
        subprocess.Popen(["explorer.exe", "/select,", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p.parent)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return f"Mostrando {p.name} na pasta."


DEFINICOES = [
    {"name": "arquivos_buscar",
     "description": "Procura arquivos do usuário pelo nome (planilhas, plantas, PDFs, fotos...). Devolve os mais "
                    "prováveis com o caminho completo. Use antes de abrir um arquivo pedido pelo nome.",
     "input_schema": {"type": "object", "properties": {
         "consulta": {"type": "string", "description": "Palavras do nome, ex.: 'planta jundiai'"},
         "tipo": {"type": "string", "enum": ["", *TIPOS]}}, "required": ["consulta"]}},
    {"name": "arquivo_abrir", "description": "Abre um arquivo (caminho completo do arquivos_buscar).",
     "input_schema": {"type": "object", "properties": {"caminho": {"type": "string"}}, "required": ["caminho"]}},
    {"name": "arquivo_mostrar_na_pasta", "description": "Abre a pasta do arquivo com ele selecionado.",
     "input_schema": {"type": "object", "properties": {"caminho": {"type": "string"}}, "required": ["caminho"]}},
]
FUNCOES = {"arquivos_buscar": ferramenta_buscar, "arquivo_abrir": abrir, "arquivo_mostrar_na_pasta": mostrar_na_pasta}
