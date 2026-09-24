"""Memória da Ametista (arquivo dados/ametista.db, só no seu PC).

- fatos:      o que o dono pediu para lembrar ("meu café é sem açúcar");
- conversas:  histórico pesquisável ("o que eu te pedi ontem?"), por palavras e por significado;
- caderno:    banco pessoal de projetos, equipamentos, arquivos, pessoas e lugares;
- lembretes:  timers, alarmes, lembretes com data, recorrentes, por condição e aniversários.

Privacidade: trocas marcadas como privadas ("não guarde isso") e tudo o que acontece no modo privado
ficam só na memória RAM, para a conversa fazer sentido, e nunca vão para o disco.
"""
import calendar
import json
import sqlite3
import threading
import time
import unicodedata
import uuid
from collections import deque
from datetime import date, datetime, timedelta

import numpy as np

from . import config

ARQUIVO = config.DADOS / "ametista.db"
ARQUIVO_V1 = config.DADOS / "memoria.json"
JANELA_CONTEXTO = timedelta(hours=3)   # o que conta como "a conversa de agora"
MAX_CONTEXTO = 24                      # mensagens enviadas ao cérebro

_trava = threading.RLock()
_con: sqlite3.Connection | None = None
_fts = True


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


# ====================================================================== banco
def db() -> sqlite3.Connection:
    """Conexão única (protegida por trava); outros módulos usam para as próprias tabelas."""
    global _con, _fts
    with _trava:
        if _con is not None:
            return _con
        con = sqlite3.connect(ARQUIVO, check_same_thread=False, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.executescript("""
            CREATE TABLE IF NOT EXISTS meta(chave TEXT PRIMARY KEY, valor TEXT);
            CREATE TABLE IF NOT EXISTS fatos(id INTEGER PRIMARY KEY, texto TEXT UNIQUE, criado TEXT, troca INTEGER);
            CREATE TABLE IF NOT EXISTS conversas(id INTEGER PRIMARY KEY, troca INTEGER, quando TEXT, quem TEXT,
                papel TEXT, texto TEXT, origem TEXT);
            CREATE INDEX IF NOT EXISTS conversas_quando ON conversas(quando);
            CREATE INDEX IF NOT EXISTS conversas_troca ON conversas(troca);
            CREATE TABLE IF NOT EXISTS caderno(id INTEGER PRIMARY KEY, categoria TEXT, nome TEXT, detalhes TEXT,
                criado TEXT, atualizado TEXT, UNIQUE(categoria, nome));
            CREATE TABLE IF NOT EXISTS lembretes(id TEXT PRIMARY KEY, texto TEXT, tipo TEXT, quando TEXT,
                recorrencia TEXT, condicao TEXT, grupo TEXT, criado TEXT);
            CREATE TABLE IF NOT EXISTS vetores(tabela TEXT, ref INTEGER, vetor BLOB, PRIMARY KEY(tabela, ref));
        """)
        try:
            con.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS conversas_fts USING fts5(texto, content='conversas',
                    content_rowid='id', tokenize='unicode61 remove_diacritics 2');
                CREATE TRIGGER IF NOT EXISTS conversas_ai AFTER INSERT ON conversas BEGIN
                    INSERT INTO conversas_fts(rowid, texto) VALUES (new.id, new.texto); END;
                CREATE TRIGGER IF NOT EXISTS conversas_ad AFTER DELETE ON conversas BEGIN
                    INSERT INTO conversas_fts(conversas_fts, rowid, texto) VALUES ('delete', old.id, old.texto); END;
                CREATE VIRTUAL TABLE IF NOT EXISTS caderno_fts USING fts5(categoria, nome, detalhes,
                    content='caderno', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
                CREATE TRIGGER IF NOT EXISTS caderno_ai AFTER INSERT ON caderno BEGIN
                    INSERT INTO caderno_fts(rowid, categoria, nome, detalhes)
                    VALUES (new.id, new.categoria, new.nome, new.detalhes); END;
                CREATE TRIGGER IF NOT EXISTS caderno_ad AFTER DELETE ON caderno BEGIN
                    INSERT INTO caderno_fts(caderno_fts, rowid, categoria, nome, detalhes)
                    VALUES ('delete', old.id, old.categoria, old.nome, old.detalhes); END;
                CREATE TRIGGER IF NOT EXISTS caderno_au AFTER UPDATE ON caderno BEGIN
                    INSERT INTO caderno_fts(caderno_fts, rowid, categoria, nome, detalhes)
                    VALUES ('delete', old.id, old.categoria, old.nome, old.detalhes);
                    INSERT INTO caderno_fts(rowid, categoria, nome, detalhes)
                    VALUES (new.id, new.categoria, new.nome, new.detalhes); END;
            """)
        except sqlite3.OperationalError as e:  # SQLite sem FTS5: busca simples com LIKE
            print(f"[memoria] busca rápida indisponível ({e}); usando busca simples")
            _fts = False
        con.commit()
        _con = con
        _migrar_v1()
        _carregar_recente()
        return con


def _exec(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    with _trava:
        cur = db().execute(sql, params)
        db().commit()
        return cur


def _consulta(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with _trava:
        return db().execute(sql, params).fetchall()


def _migrar_v1() -> None:
    """Traz os fatos e lembretes da v1.0 (memoria.json) para o banco novo, uma vez."""
    if not ARQUIVO_V1.exists():
        return
    try:
        v1 = json.loads(ARQUIVO_V1.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    agora = datetime.now().isoformat(timespec="seconds")
    for f in v1.get("fatos", []):
        _con.execute("INSERT OR IGNORE INTO fatos(texto, criado) VALUES (?, ?)", (f, agora))
    for l in v1.get("lembretes", []):
        _con.execute("INSERT OR IGNORE INTO lembretes(id, texto, tipo, quando, criado) VALUES (?,?,?,?,?)",
                     (l.get("id") or uuid.uuid4().hex[:8], l.get("texto", ""), l.get("tipo", "lembrete"),
                      l.get("quando"), agora))
    _con.commit()
    try:
        ARQUIVO_V1.rename(ARQUIVO_V1.with_name("memoria_v1_migrada.json"))
    except OSError:
        pass
    print("[memoria] memória da v1.0 migrada")


def meta(chave: str, padrao: str | None = None) -> str | None:
    r = _consulta("SELECT valor FROM meta WHERE chave=?", (chave,))
    return r[0]["valor"] if r else padrao


def definir_meta(chave: str, valor: str) -> None:
    _exec("INSERT OR REPLACE INTO meta(chave, valor) VALUES (?, ?)", (chave, valor))


# ====================================================================== fatos
def lembrar_fato(fato: str, troca: int | None = None) -> str:
    fato = fato.strip()
    if not fato:
        return "Nada para guardar."
    from . import estado

    if estado.privado():
        return "Não guardei: o modo privado está ligado."
    if troca is not None and _trocas_privadas.get(troca):
        return "Não guardei: o usuário pediu para não guardar esta conversa."
    _exec("INSERT OR IGNORE INTO fatos(texto, criado, troca) VALUES (?, ?, ?)",
          (fato, datetime.now().isoformat(timespec="seconds"), troca))
    return f"Guardei: {fato}"


def esquecer_fato(trecho: str) -> str:
    trecho = trecho.strip()
    if not trecho:
        return "Esquecer o quê?"
    alvo = _sem_acento(trecho)
    ids = [r["id"] for r in _consulta("SELECT id, texto FROM fatos") if alvo in _sem_acento(r["texto"])]
    for i in ids:
        _exec("DELETE FROM fatos WHERE id=?", (i,))
    return f"Esqueci {len(ids)} item(ns)." if ids else "Não achei nada parecido na memória."


def esquecer_fato_exato(texto: str) -> bool:
    return _exec("DELETE FROM fatos WHERE texto=?", (texto,)).rowcount > 0


def fatos() -> list[str]:
    return [r["texto"] for r in _consulta("SELECT texto FROM fatos ORDER BY id")]


# ====================================================================== conversas
_recente: deque[dict] = deque(maxlen=200)       # contexto curto (inclui as trocas privadas)
_trocas_privadas: dict[int, bool] = {}
_fila_vetores: deque[int] = deque()
_evento_vetores = threading.Event()


def nova_troca() -> int:
    """Identificador de uma troca (pedido + resposta)."""
    return int(time.time() * 1000)


def marcar_privada(troca: int) -> None:
    _trocas_privadas[troca] = True


def troca_privada(troca: int) -> bool:
    return bool(_trocas_privadas.get(troca))


def registrar(troca: int, papel: str, texto: str, quem: str = "", origem: str = "pc",
              privado: bool = False) -> None:
    """Guarda uma fala na conversa. papel: user | assistant."""
    from . import estado

    texto = (texto or "").strip()
    if not texto:
        return
    agora = datetime.now()
    privado = privado or estado.privado() or troca_privada(troca)
    if privado:
        marcar_privada(troca)
    with _trava:
        _recente.append({"role": papel, "content": texto, "quando": agora, "troca": troca, "privado": privado})
    if privado or not config.GUARDAR_CONVERSAS:
        return
    _exec("INSERT INTO conversas(troca, quando, quem, papel, texto, origem) VALUES (?,?,?,?,?,?)",
          (troca, agora.isoformat(timespec="seconds"), quem or "", papel, texto, origem))
    if papel == "assistant" and config.BUSCA_SEMANTICA:
        _fila_vetores.append(troca)
        _evento_vetores.set()


def _carregar_recente() -> None:
    limite = (datetime.now() - JANELA_CONTEXTO).isoformat(timespec="seconds")
    linhas = _con.execute("SELECT troca, quando, papel, texto FROM conversas WHERE quando >= ? "
                          "ORDER BY id DESC LIMIT ?", (limite, MAX_CONTEXTO)).fetchall()
    for r in reversed(linhas):
        _recente.append({"role": r["papel"], "content": r["texto"], "troca": r["troca"], "privado": False,
                         "quando": datetime.fromisoformat(r["quando"])})


def historico() -> list[dict]:
    """Mensagens recentes no formato da API (a conversa começa sempre pelo usuário)."""
    db()
    limite = datetime.now() - JANELA_CONTEXTO
    with _trava:
        h = [{"role": m["role"], "content": m["content"]} for m in _recente if m["quando"] >= limite]
    h = h[-MAX_CONTEXTO:]
    while h and h[0]["role"] != "user":
        h.pop(0)
    # junta falas seguidas do mesmo papel (ex.: pedido cancelado sem resposta)
    juntas: list[dict] = []
    for m in h:
        if juntas and juntas[-1]["role"] == m["role"]:
            juntas[-1] = {"role": m["role"], "content": juntas[-1]["content"] + "\n" + m["content"]}
        else:
            juntas.append(dict(m))
    return juntas


def limpar_historico() -> None:
    """Começa uma conversa nova (não apaga o arquivo de conversas)."""
    with _trava:
        _recente.clear()


def trocas_recentes(n: int = 2) -> list[int]:
    with _trava:
        vistas = []
        for m in reversed(_recente):
            if m["troca"] not in vistas:
                vistas.append(m["troca"])
            if len(vistas) >= n:
                break
    return vistas


def apagar_troca(troca: int) -> None:
    """"Não guarde isso": some do disco, do contexto e dos fatos guardados naquela troca."""
    marcar_privada(troca)
    with _trava:
        for m in _recente:
            if m["troca"] == troca:
                m["privado"] = True
    _exec("DELETE FROM conversas WHERE troca=?", (troca,))
    _exec("DELETE FROM fatos WHERE troca=?", (troca,))
    _exec("DELETE FROM vetores WHERE tabela='troca' AND ref=?", (troca,))


def apagar_conversas() -> int:
    n = _exec("DELETE FROM conversas").rowcount
    _exec("DELETE FROM vetores WHERE tabela='troca'")
    if _fts:
        _exec("INSERT INTO conversas_fts(conversas_fts) VALUES ('rebuild')")
    limpar_historico()
    return n


def limpar_antigas() -> None:
    if config.DIAS_CONVERSAS <= 0:
        return
    limite = (datetime.now() - timedelta(days=config.DIAS_CONVERSAS)).isoformat(timespec="seconds")
    trocas = [r["troca"] for r in _consulta("SELECT DISTINCT troca FROM conversas WHERE quando < ?", (limite,))]
    for t in trocas:
        _exec("DELETE FROM conversas WHERE troca=?", (t,))
        _exec("DELETE FROM vetores WHERE tabela='troca' AND ref=?", (t,))


def conversas_do_periodo(inicio: datetime, fim: datetime, limite: int = 300) -> list[dict]:
    linhas = _consulta("SELECT troca, quando, quem, papel, texto, origem FROM conversas "
                       "WHERE quando >= ? AND quando < ? ORDER BY id LIMIT ?",
                       (inicio.isoformat(timespec="seconds"), fim.isoformat(timespec="seconds"), limite))
    return [dict(r) for r in linhas]


def _trocas(ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    marcas = ",".join("?" * len(ids))
    saida: dict[int, dict] = {}
    for r in _consulta(f"SELECT troca, quando, quem, papel, texto FROM conversas WHERE troca IN ({marcas}) "
                       "ORDER BY id", tuple(ids)):
        t = saida.setdefault(r["troca"], {"troca": r["troca"], "quando": r["quando"], "quem": r["quem"],
                                           "pedido": "", "resposta": ""})
        chave = "pedido" if r["papel"] == "user" else "resposta"
        t[chave] = (t[chave] + " " + r["texto"]).strip()
    return saida


def _fts_consulta(texto: str) -> str:
    """Transforma a pergunta numa consulta FTS tolerante (qualquer palavra, com prefixo)."""
    palavras = [p for p in "".join(c if c.isalnum() else " " for c in _sem_acento(texto)).split()
                if len(p) > 2 and p not in _PALAVRAS_VAZIAS]
    return " OR ".join(f'"{p}"*' for p in palavras[:12])


_PALAVRAS_VAZIAS = set("""que para com uma umas uns por mais como mas foi ser esta isso isto essa esse ela ele
voce tem ter nao sim sao dos das nos nas pelo pela meu minha seu sua qual quais quando onde ontem hoje
amanha pedi falei disse sobre algo alguma coisa""".split())


def buscar_conversas(consulta: str = "", inicio: datetime | None = None, fim: datetime | None = None,
                     limite: int = 8) -> list[dict]:
    """Trocas passadas mais relevantes (por palavras e por significado), da mais recente à mais antiga."""
    filtros, params = [], []
    if inicio:
        filtros.append("c.quando >= ?")
        params.append(inicio.isoformat(timespec="seconds"))
    if fim:
        filtros.append("c.quando < ?")
        params.append(fim.isoformat(timespec="seconds"))
    onde = (" AND " + " AND ".join(filtros)) if filtros else ""
    pontos: dict[int, float] = {}

    if not consulta.strip():  # "o que eu pedi ontem?": todas as trocas do período
        linhas = _consulta(f"SELECT DISTINCT c.troca FROM conversas c WHERE 1=1{onde} ORDER BY c.troca DESC "
                           f"LIMIT ?", (*params, max(limite, 30)))
        ids = [r["troca"] for r in linhas]
        return sorted(_trocas(ids).values(), key=lambda t: t["troca"])

    q = _fts_consulta(consulta)
    if q and _fts:
        linhas = _consulta(f"SELECT c.troca, bm25(conversas_fts) AS nota FROM conversas_fts "
                           f"JOIN conversas c ON c.id = conversas_fts.rowid WHERE conversas_fts MATCH ?{onde} "
                           f"ORDER BY nota LIMIT 60", (q, *params))
        for i, r in enumerate(linhas):
            pontos[r["troca"]] = max(pontos.get(r["troca"], 0), 1.0 - i / 80)
    elif q:
        for p in q.replace('"', "").replace("*", "").split(" OR "):
            for r in _consulta(f"SELECT c.troca FROM conversas c WHERE c.texto LIKE ?{onde} LIMIT 40",
                               (f"%{p}%", *params)):
                pontos[r["troca"]] = pontos.get(r["troca"], 0) + 0.3

    for troca, nota in _semelhantes("troca", consulta, 40):
        if nota >= 0.35:
            pontos[troca] = pontos.get(troca, 0) + nota
    if pontos and (inicio or fim):
        validas = _trocas(list(pontos))
        pontos = {t: n for t, n in pontos.items() if t in validas}
    melhores = sorted(pontos, key=pontos.get, reverse=True)[:limite]
    trocas = _trocas(melhores)
    return [trocas[t] for t in melhores if t in trocas]


# ====================================================================== vetores (busca por significado)
_cache_vetores: dict[str, tuple[int, np.ndarray, list[int]]] = {}


def _guardar_vetor(tabela: str, ref: int, texto: str) -> None:
    from . import semantica

    v = semantica.vetor(texto, esperar=True)   # sempre em segundo plano
    if v is not None:
        _exec("INSERT OR REPLACE INTO vetores(tabela, ref, vetor) VALUES (?,?,?)",
              (tabela, ref, v.astype(np.float32).tobytes()))
        _cache_vetores.pop(tabela, None)


def _semelhantes(tabela: str, texto: str, n: int) -> list[tuple[int, float]]:
    from . import semantica

    if not config.BUSCA_SEMANTICA:
        return []
    total = _consulta("SELECT COUNT(*) AS n FROM vetores WHERE tabela=?", (tabela,))[0]["n"]
    if not total:
        return []
    q = semantica.vetor(texto)
    if q is None:
        return []
    cache = _cache_vetores.get(tabela)
    if not cache or cache[0] != total:
        linhas = _consulta("SELECT ref, vetor FROM vetores WHERE tabela=?", (tabela,))
        matriz = np.stack([np.frombuffer(r["vetor"], dtype=np.float32) for r in linhas])
        cache = (total, matriz, [r["ref"] for r in linhas])
        _cache_vetores[tabela] = cache
    _, matriz, refs = cache
    if matriz.shape[1] != q.shape[0]:
        return []
    notas = matriz @ q
    ordem = np.argsort(-notas)[:n]
    return [(refs[i], float(notas[i])) for i in ordem]


def _trabalhador_vetores() -> None:
    while True:
        _evento_vetores.wait()
        _evento_vetores.clear()
        while _fila_vetores:
            troca = _fila_vetores.popleft()
            t = _trocas([troca]).get(troca)
            if t:
                try:
                    _guardar_vetor("troca", troca, f"{t['pedido']} | {t['resposta']}")
                except Exception as e:
                    print(f"[memoria] vetor falhou: {e}")


threading.Thread(target=_trabalhador_vetores, daemon=True, name="vetores").start()


def vetorizar_pendentes(limite: int = 3000) -> int:
    """Põe na fila as conversas e itens do caderno que ainda não têm vetor (ex.: guardados antes do
    modelo de significado ficar pronto). Roda em segundo plano, depois que o modelo carrega."""
    if not config.BUSCA_SEMANTICA:
        return 0
    trocas = [r["troca"] for r in _consulta(
        "SELECT DISTINCT troca FROM conversas WHERE papel='assistant' AND troca NOT IN "
        "(SELECT ref FROM vetores WHERE tabela='troca') ORDER BY troca DESC LIMIT ?", (limite,))]
    _fila_vetores.extend(trocas)
    if trocas:
        _evento_vetores.set()
    itens = _consulta("SELECT id, categoria, nome, detalhes FROM caderno WHERE id NOT IN "
                      "(SELECT ref FROM vetores WHERE tabela='caderno')")
    for i in itens:
        _guardar_vetor("caderno", i["id"], f"{i['categoria']}: {i['nome']}. {i['detalhes']}")
    return len(trocas) + len(itens)


# ====================================================================== caderno pessoal
CATEGORIAS = ("projeto", "equipamento", "arquivo", "pessoa", "lugar", "conta", "outro")


def caderno_guardar(nome: str, detalhes: str, categoria: str = "outro", acrescentar: bool = False) -> str:
    from . import estado

    if estado.privado():
        return "Não guardei: o modo privado está ligado."
    nome, detalhes = nome.strip(), detalhes.strip()
    categoria = (categoria or "outro").strip().lower()
    if categoria not in CATEGORIAS:
        categoria = "outro"
    if not nome:
        return "Faltou o nome do item."
    agora = datetime.now().isoformat(timespec="seconds")
    atual = _consulta("SELECT id, detalhes FROM caderno WHERE categoria=? AND nome=? COLLATE NOCASE",
                      (categoria, nome))
    if atual:
        novo = (atual[0]["detalhes"] + "\n" + detalhes).strip() if acrescentar else detalhes
        _exec("UPDATE caderno SET detalhes=?, atualizado=? WHERE id=?", (novo, agora, atual[0]["id"]))
        ref, texto = atual[0]["id"], f"Atualizei no caderno: {nome}."
    else:
        cur = _exec("INSERT INTO caderno(categoria, nome, detalhes, criado, atualizado) VALUES (?,?,?,?,?)",
                    (categoria, nome, detalhes, agora, agora))
        ref, texto = cur.lastrowid, f"Anotei no caderno ({categoria}): {nome}."
    item = _consulta("SELECT nome, detalhes, categoria FROM caderno WHERE id=?", (ref,))[0]
    threading.Thread(target=_guardar_vetor, args=("caderno", ref,
                     f"{item['categoria']}: {item['nome']}. {item['detalhes']}"), daemon=True).start()
    return texto


def caderno_buscar(consulta: str, limite: int = 6) -> list[dict]:
    pontos: dict[int, float] = {}
    q = _fts_consulta(consulta)
    if q and _fts:
        for i, r in enumerate(_consulta("SELECT rowid FROM caderno_fts WHERE caderno_fts MATCH ? "
                                        "ORDER BY bm25(caderno_fts) LIMIT 20", (q,))):
            pontos[r["rowid"]] = 1.0 - i / 25
    elif q:
        for p in q.replace('"', "").replace("*", "").split(" OR "):
            for r in _consulta("SELECT id FROM caderno WHERE nome LIKE ? OR detalhes LIKE ?", (f"%{p}%", f"%{p}%")):
                pontos[r["id"]] = pontos.get(r["id"], 0) + 0.3
    for ref, nota in _semelhantes("caderno", consulta, 20):
        if nota >= 0.3:
            pontos[ref] = pontos.get(ref, 0) + nota
    ids = sorted(pontos, key=pontos.get, reverse=True)[:limite]
    if not ids:
        return []
    marcas = ",".join("?" * len(ids))
    itens = {r["id"]: dict(r) for r in _consulta(f"SELECT * FROM caderno WHERE id IN ({marcas})", tuple(ids))}
    return [itens[i] for i in ids if i in itens]


def caderno_listar(categoria: str = "") -> list[dict]:
    if categoria:
        return [dict(r) for r in _consulta("SELECT * FROM caderno WHERE categoria=? ORDER BY nome", (categoria,))]
    return [dict(r) for r in _consulta("SELECT * FROM caderno ORDER BY categoria, nome")]


def caderno_apagar(nome: str) -> int:
    linhas = _consulta("SELECT id FROM caderno WHERE nome=? COLLATE NOCASE", (nome.strip(),))
    for r in linhas:
        _exec("DELETE FROM caderno WHERE id=?", (r["id"],))
        _exec("DELETE FROM vetores WHERE tabela='caderno' AND ref=?", (r["id"],))
    return len(linhas)


# ====================================================================== lembretes
def _item(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["recorrencia"] = json.loads(d["recorrencia"]) if d.get("recorrencia") else None
    return d


def criar_lembrete(texto: str, quando: datetime | None, tipo: str = "lembrete", recorrencia: dict | None = None,
                   condicao: str | None = None, grupo: str | None = None) -> dict:
    item = {"id": uuid.uuid4().hex[:8], "texto": texto, "tipo": tipo,
            "quando": quando.isoformat(timespec="seconds") if quando else None,
            "recorrencia": json.dumps(recorrencia, ensure_ascii=False) if recorrencia else None,
            "condicao": condicao, "grupo": grupo, "criado": datetime.now().isoformat(timespec="seconds")}
    _exec("INSERT INTO lembretes(id, texto, tipo, quando, recorrencia, condicao, grupo, criado) "
          "VALUES (:id, :texto, :tipo, :quando, :recorrencia, :condicao, :grupo, :criado)", item)
    return {**item, "recorrencia": recorrencia}


def lembretes_pendentes() -> list[dict]:
    return [_item(r) for r in _consulta("SELECT * FROM lembretes ORDER BY quando IS NULL, quando")]


def obter_lembrete(id_: str) -> dict | None:
    r = _consulta("SELECT * FROM lembretes WHERE id=?", (id_,))
    return _item(r[0]) if r else None


def remover_lembrete(id_: str) -> bool:
    item = obter_lembrete(id_)
    if not item:
        return False
    if item.get("grupo"):  # aniversário: some o aviso do dia e o da véspera
        _exec("DELETE FROM lembretes WHERE grupo=?", (item["grupo"],))
    else:
        _exec("DELETE FROM lembretes WHERE id=?", (id_,))
    return True


def _ultimo_dia(ano: int, mes: int) -> int:
    return calendar.monthrange(ano, mes)[1]


def proxima_ocorrencia(rec: dict, base: datetime, depois: datetime) -> datetime:
    """Próxima data da recorrência, no mesmo horário de `base`, estritamente depois de `depois`."""
    tipo = rec.get("tipo")
    hora = base.time()
    if tipo in ("diario", "semanal", "dias_uteis"):
        dias = set(range(7)) if tipo == "diario" else set(range(5)) if tipo == "dias_uteis" else \
            {int(d) % 7 for d in rec.get("dias", [])} or {base.weekday()}
        d = depois.date()
        for _ in range(9):
            cand = datetime.combine(d, hora)
            if cand > depois and cand.weekday() in dias:
                return cand
            d += timedelta(days=1)
    if tipo == "mensal":
        dia = int(rec.get("dia") or base.day)
        ano, mes = depois.year, depois.month
        for _ in range(14):
            cand = datetime.combine(date(ano, mes, min(dia, _ultimo_dia(ano, mes))), hora)
            if cand > depois:
                return cand
            ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    if tipo == "anual":  # antes_dias: aviso de véspera de aniversário
        mes, dia = int(rec.get("mes") or base.month), int(rec.get("dia") or base.day)
        antes = timedelta(days=int(rec.get("antes_dias") or 0))
        for ano in range(depois.year, depois.year + 3):
            cand = datetime.combine(date(ano, mes, min(dia, _ultimo_dia(ano, mes))), hora) - antes
            if cand > depois:
                return cand
    raise ValueError(f"recorrência inválida: {rec}")


def retirar_vencidos(agora: datetime) -> list[dict]:
    """Devolve os lembretes cuja hora chegou. Os únicos somem; os recorrentes vão para a próxima data.

    Um recorrente perdido há mais de 6 horas (PC desligado) é pulado em silêncio."""
    vencidos = []
    for item in [_item(r) for r in _consulta(
            "SELECT * FROM lembretes WHERE quando IS NOT NULL AND quando <= ?", (agora.isoformat(timespec="seconds"),))]:
        quando = datetime.fromisoformat(item["quando"])
        rec = item.get("recorrencia")
        if rec:
            try:
                proxima = proxima_ocorrencia(rec, quando, agora)
            except ValueError:
                _exec("DELETE FROM lembretes WHERE id=?", (item["id"],))
                continue
            _exec("UPDATE lembretes SET quando=? WHERE id=?", (proxima.isoformat(timespec="seconds"), item["id"]))
            if agora - quando <= timedelta(hours=6):
                vencidos.append({**item, "atraso_min": int((agora - quando).total_seconds() // 60)})
        else:
            _exec("DELETE FROM lembretes WHERE id=?", (item["id"],))
            vencidos.append({**item, "atraso_min": int((agora - quando).total_seconds() // 60)})
    return vencidos


def condicionais() -> list[dict]:
    return [_item(r) for r in _consulta("SELECT * FROM lembretes WHERE condicao IS NOT NULL")]


def retirar_condicionais(condicao: str, criado_antes: float | None = None) -> list[dict]:
    """Dispara (e apaga) os lembretes de uma condição. criado_antes: só os criados antes desse instante."""
    saida = []
    for item in condicionais():
        cond = item["condicao"] or ""
        if cond != condicao and not (condicao.startswith("ao_abrir:") and cond.startswith("ao_abrir:")
                                     and _sem_acento(cond[9:]) in _sem_acento(condicao[9:])):
            continue
        if criado_antes is not None and datetime.fromisoformat(item["criado"]).timestamp() >= criado_antes:
            continue
        _exec("DELETE FROM lembretes WHERE id=?", (item["id"],))
        saida.append(item)
    return saida


def fechar() -> None:
    global _con
    with _trava:
        if _con is not None:
            _con.close()
            _con = None
