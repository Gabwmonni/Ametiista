"""Blocos de notas de verdade: arquivos .txt em Documentos\\Ametista\\Notas, que abrem no Bloco de Notas.

Criar, acrescentar, ler e listar notas, e salvar o histórico de conversas numa nota ("me manda a conversa de hoje
num bloco de notas"). Quando o pedido vem do PC, a nota abre na tela; pelo celular, ela pode ser enviada para lá.
"""
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import acoes, arquivos_io, memoria


def pasta() -> Path:
    return arquivos_io.pasta_ametista() / "Notas"


def _nome_arquivo(titulo: str) -> str:
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", str(titulo or "").strip())
    t = re.sub(r"\s+", " ", t).strip(" .")[:80]
    return t or f"Nota {datetime.now():%d-%m-%Y %Hh%M}"


def _achar(titulo: str) -> Path | None:
    alvo = pasta() / f"{_nome_arquivo(titulo)}.txt"
    if alvo.exists():
        return alvo
    chave = arquivos_io._sem_acento(_nome_arquivo(titulo))
    candidatos = [p for p in pasta().glob("*.txt") if chave in arquivos_io._sem_acento(p.stem)] if pasta().exists() else []
    return max(candidatos, key=lambda p: p.stat().st_mtime) if candidatos else None


def _no_pc() -> bool:
    from .ferramentas import CONTEXTO

    return CONTEXTO.get().get("origem", "pc") not in ("celular", "rotina", "agente")


def abrir_no_bloco(p: Path) -> None:
    if sys.platform == "win32":
        subprocess.Popen(["notepad.exe", str(p)])


def criar(titulo: str, texto: str = "", abrir: bool | None = None) -> str:
    pasta().mkdir(parents=True, exist_ok=True)
    p = arquivos_io._nome_livre(pasta() / f"{_nome_arquivo(titulo)}.txt")
    p.write_text(str(texto or ""), encoding="utf-8")
    if abrir if abrir is not None else _no_pc():
        abrir_no_bloco(p)
        return f"Criei a nota {p.stem} e abri no Bloco de Notas ({p})."
    return f"Criei a nota {p.stem} ({p})."


def acrescentar(titulo: str, texto: str) -> str:
    p = _achar(titulo)
    if not p:
        return criar(titulo, texto)
    atual = p.read_text(encoding="utf-8", errors="replace")
    p.write_text(atual + ("" if not atual or atual.endswith("\n") else "\n") + str(texto), encoding="utf-8")
    return f"Acrescentei na nota {p.stem}."


def ler(titulo: str) -> str:
    p = _achar(titulo)
    if not p:
        return f"Não achei a nota '{titulo}'. Notas que existem: {listar()}"
    texto = p.read_text(encoding="utf-8", errors="replace")
    return f"Nota {p.stem} ({p}):\n{texto[:arquivos_io.MAX_LEITURA]}"


def listar() -> str:
    if not pasta().exists():
        return "Nenhuma nota ainda."
    notas = sorted(pasta().glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not notas:
        return "Nenhuma nota ainda."
    return "; ".join(f"{p.stem} ({datetime.fromtimestamp(p.stat().st_mtime):%d/%m %H:%M})" for p in notas[:40])


def abrir(titulo: str) -> str:
    p = _achar(titulo)
    if not p:
        return f"Não achei a nota '{titulo}'."
    abrir_no_bloco(p)
    return f"Abri a nota {p.stem}."


# ------------------------------------------------------------------ histórico de conversas
def _periodo(periodo: str) -> tuple[datetime, datetime, str]:
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    p = arquivos_io._sem_acento(periodo or "hoje")
    if p in ("ontem",):
        return hoje - timedelta(days=1), hoje, f"de {hoje - timedelta(days=1):%d-%m-%Y}"
    if p in ("semana", "esta semana", "ultimos 7 dias", "7 dias"):
        return hoje - timedelta(days=6), hoje + timedelta(days=1), f"de {hoje - timedelta(days=6):%d-%m} a {hoje:%d-%m-%Y}"
    if p in ("tudo", "todas", "sempre"):
        return datetime(2000, 1, 1), hoje + timedelta(days=1), "completa"
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", p)
    if m:
        ano = int(m.group(3) or hoje.year)
        dia = datetime(ano + 2000 if ano < 100 else ano, int(m.group(2)), int(m.group(1)))
        return dia, dia + timedelta(days=1), f"de {dia:%d-%m-%Y}"
    return hoje, hoje + timedelta(days=1), f"de {hoje:%d-%m-%Y}"


def exportar_conversa(periodo: str = "hoje", abrir: bool | None = None) -> str:
    """Salva as conversas do período numa nota (e abre no Bloco de Notas se o pedido veio do PC)."""
    inicio, fim, rotulo = _periodo(periodo)
    linhas = memoria.conversas_do_periodo(inicio, fim, limite=2000)
    if not linhas:
        return f"Não há conversas guardadas {rotulo.replace('de ', 'em ', 1) if rotulo != 'completa' else ''}".strip() + "."
    from . import config

    texto = [f"Conversa com a {config.NOME} {rotulo}", ""]
    dia = None
    for l in linhas:
        quando = datetime.fromisoformat(l["quando"])
        if quando.date() != dia:
            dia = quando.date()
            texto += ["", f"— {quando:%d/%m/%Y} —"]
        quem = config.NOME if l["papel"] == "assistant" else (l.get("quem") or config.DONO)
        origem = " (pelo celular)" if l.get("origem") == "celular" and l["papel"] == "user" else ""
        texto.append(f"[{quando:%H:%M}] {quem}{origem}: {l['texto']}")
    return criar(f"Conversa {rotulo}", "\n".join(texto).strip() + "\n", abrir)


# ------------------------------------------------------------------ definições
DEFINICOES = [
    {"name": "nota_criar",
     "description": "Cria um bloco de notas (.txt em Documentos\\Ametista\\Notas) com um título e um texto, e abre "
                    "no Bloco de Notas quando o pedido é no PC. Use para anotações, listas, resumos, rascunhos.",
     "input_schema": {"type": "object", "properties": {
         "titulo": {"type": "string"}, "texto": {"type": "string"},
         "abrir": {"type": "boolean", "description": "abrir na tela (padrão: sim no PC, não pelo celular)"}},
         "required": ["titulo"]}},
    {"name": "nota_acrescentar", "description": "Acrescenta um texto no fim de uma nota (cria se não existir).",
     "input_schema": {"type": "object", "properties": {
         "titulo": {"type": "string"}, "texto": {"type": "string"}}, "required": ["titulo", "texto"]}},
    {"name": "nota_ler", "description": "Lê uma nota pelo título (ou parte dele).",
     "input_schema": {"type": "object", "properties": {"titulo": {"type": "string"}}, "required": ["titulo"]}},
    {"name": "notas_listar", "description": "Lista as notas (das mais recentes para as mais antigas).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "nota_abrir", "description": "Abre uma nota no Bloco de Notas.",
     "input_schema": {"type": "object", "properties": {"titulo": {"type": "string"}}, "required": ["titulo"]}},
    {"name": "conversa_exportar",
     "description": "Salva o histórico de conversas com você num bloco de notas (hoje, ontem, semana, tudo ou uma "
                    "data dd/mm) e abre no PC. Para mandar ao celular, depois use arquivo_enviar_celular.",
     "input_schema": {"type": "object", "properties": {
         "periodo": {"type": "string", "description": "hoje, ontem, semana, tudo ou dd/mm"},
         "abrir": {"type": "boolean"}}}},
]
FUNCOES = {"nota_criar": criar, "nota_acrescentar": acrescentar, "nota_ler": ler, "notas_listar": listar,
           "nota_abrir": abrir, "conversa_exportar": exportar_conversa}


def _preparar_acrescentar(a: dict) -> dict | None:
    p = _achar(a.get("titulo", ""))
    if p is None:
        return None
    return {"copia": str(arquivos_io._copia_de_seguranca(p)), "caminho": str(p)}


acoes.registrar_ferramenta(
    "nota_criar", descrever=lambda a: f"Criou a nota {a.get('titulo', '')}".strip(),
    preparar=lambda a: {"criado": str(arquivos_io._nome_livre(pasta() / f"{_nome_arquivo(a.get('titulo', ''))}.txt"))},
    desfazer=arquivos_io._desfazer_escrever)
acoes.registrar_ferramenta("nota_acrescentar", preparar=_preparar_acrescentar,
                           desfazer=arquivos_io._desfazer_escrever,
                           descrever=lambda a: f"Acrescentou na nota {a.get('titulo', '')}")
acoes.registrar_ferramenta("nota_ler", leitura=True)
acoes.registrar_ferramenta("notas_listar", leitura=True)
acoes.registrar_ferramenta("nota_abrir", descrever=lambda a: f"Abriu a nota {a.get('titulo', '')}")
acoes.registrar_ferramenta("conversa_exportar",
                           descrever=lambda a: f"Salvou a conversa ({a.get('periodo', 'hoje')}) num bloco de notas")
