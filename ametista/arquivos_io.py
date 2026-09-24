"""Ler, criar, editar, listar, mover, copiar e apagar arquivos do PC — de perto ou pelo celular.

Segurança:
- Pastas do Windows, dos programas instalados e da própria Ametista nunca são alteradas (só lidas).
- Mudar um arquivo que já existe, mover por cima de outro e apagar pedem confirmação. Criar um arquivo novo e
  mexer nas notas dela (Documentos\\Ametista) não precisam.
- Antes de mudar um arquivo, ela guarda uma cópia em dados/copias: "desfaz" devolve como estava.
- Apagar manda para a Lixeira do Windows (dá para restaurar por lá).
"""
import html
import io
import os
import re
import shutil
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

from . import acoes, config

COPIAS = config.DADOS / "copias"
MAX_LEITURA = 12_000          # letras devolvidas por vez (o resto vem com "inicio")
MAX_ESCRITA = 2_000_000
TEXTO = {".txt", ".md", ".csv", ".tsv", ".json", ".log", ".ini", ".cfg", ".conf", ".xml", ".html", ".htm",
         ".css", ".js", ".ts", ".py", ".java", ".c", ".cpp", ".h", ".cs", ".sql", ".yaml", ".yml", ".toml",
         ".bat", ".cmd", ".ps1", ".sh", ".env", ".srt", ".tex", ".rtf", ".properties", ".reg", ""}
IMAGENS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
ESCREVIVEIS = TEXTO


# ====================================================================== pastas
def _pasta_conhecida(guid: str) -> Path | None:
    """Pasta do Windows pelo identificador (Documentos, Área de Trabalho...), mesmo movida para o OneDrive."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                        ("Data4", ctypes.c_ubyte * 8)]

        g = GUID()
        ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(guid), ctypes.byref(g))
        ptr = ctypes.c_wchar_p()
        ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(ptr))
        caminho = ptr.value
        ctypes.windll.ole32.CoTaskMemFree(ptr)
        return Path(caminho) if caminho else None
    except Exception:
        return None


def _primeira(*candidatas: Path) -> Path:
    for c in candidatas:
        if c and c.exists():
            return c
    return candidatas[0]


def pasta_documentos() -> Path:
    casa = Path.home()
    return _pasta_conhecida("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}") or _primeira(casa / "Documents",
                                                                                   casa / "Documentos", casa)


def pasta_ametista() -> Path:
    """Onde ficam as notas e arquivos que ela cria: Documentos\\Ametista (ou "Ametista - arquivos", se o
    próprio programa estiver instalado em Documentos\\Ametista)."""
    p = pasta_documentos() / "Ametista"
    if _dentro(p, config.RAIZ) or _dentro(config.RAIZ, p):
        p = pasta_documentos() / "Ametista - arquivos"
    return p


def _apelidos() -> dict[str, Path]:
    casa = Path.home()
    desktop = _pasta_conhecida("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}") or _primeira(casa / "Desktop",
                                                                                     casa / "Área de Trabalho")
    downloads = _pasta_conhecida("{374DE290-123F-4565-9164-39C4925E467B}") or casa / "Downloads"
    imagens = _pasta_conhecida("{33E28130-4E1E-4676-835A-98395C3BC3BB}") or _primeira(casa / "Pictures",
                                                                                     casa / "Imagens")
    return {"documentos": pasta_documentos(), "documents": pasta_documentos(), "meus documentos": pasta_documentos(),
            "downloads": downloads, "area de trabalho": desktop, "desktop": desktop, "imagens": imagens,
            "fotos": imagens, "pictures": imagens, "musicas": _primeira(casa / "Music", casa / "Músicas"),
            "videos": _primeira(casa / "Videos", casa / "Vídeos"), "ametista": pasta_ametista(),
            "notas": pasta_ametista() / "Notas", "pasta pessoal": casa, "usuario": casa}


def _sem_acento(t: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


def resolver(caminho: str, para_criar: bool = False) -> Path:
    """Caminho completo a partir do que a pessoa (ou a IA) disse: aceita "Documentos/estudos/resumo.txt",
    "%USERPROFILE%\\Desktop\\x", "~/x" e caminhos completos. Sem pasta: arquivo novo vai para Documentos\\Ametista;
    arquivo existente é procurado pelo nome no índice de arquivos."""
    t = str(caminho or "").strip().strip('"').strip("'")
    if not t:
        raise ValueError("faltou o caminho do arquivo")
    t = os.path.expandvars(os.path.expanduser(t))
    p = Path(t)
    if p.is_absolute():
        return p
    partes = re.split(r"[\\/]", t, maxsplit=1)
    base = _apelidos().get(_sem_acento(partes[0]))
    if base is not None:
        return base / partes[1] if len(partes) > 1 and partes[1] else base
    if len(partes) == 1 and not para_criar:
        from . import arquivos

        achados = arquivos.buscar(t, limite=3)
        exatos = [a for a in achados if a["nome"].lower() == t.lower()]
        if exatos or len(achados) == 1:
            return Path((exatos or achados)[0]["caminho"])
    return pasta_ametista() / t


def _protegidas() -> list[Path]:
    env = os.environ
    lista = [env.get("SystemRoot") or r"C:\Windows", env.get("ProgramFiles") or r"C:\Program Files",
             env.get("ProgramFiles(x86)") or r"C:\Program Files (x86)", env.get("ProgramData") or r"C:\ProgramData",
             r"C:\$Recycle.Bin", r"C:\System Volume Information", r"C:\Recovery", str(config.RAIZ)]
    if sys.platform != "win32":
        lista += ["/bin", "/boot", "/etc", "/lib", "/sbin", "/usr", "/var", "/sys", "/proc"]
    return [Path(x) for x in lista]


def _dentro(p: Path, pasta: Path) -> bool:
    try:
        a, b = os.path.normcase(os.path.abspath(p)), os.path.normcase(os.path.abspath(pasta))
        return a == b or a.startswith(b.rstrip("\\/") + os.sep)
    except (OSError, ValueError):
        return False


def protegido(p: Path) -> bool:
    """Pastas que ela nunca altera: Windows, programas, a raiz do disco e a própria Ametista."""
    try:
        absoluto = Path(os.path.abspath(p))
    except (OSError, ValueError):
        return True
    if absoluto == Path(absoluto.anchor) or absoluto.parent == Path(absoluto.anchor) and absoluto.is_dir():
        return True                      # o disco inteiro ou uma pasta de primeiro nível (C:\Users, D:\Jogos)
    return any(_dentro(absoluto, x) for x in _protegidas())


def _nas_notas(p: Path) -> bool:
    return _dentro(p, pasta_ametista())


def _legivel(n: float) -> str:
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unidade == "TB":
            return f"{n:.0f} {unidade}" if unidade == "B" else f"{n:.1f} {unidade}".replace(".", ",")
        n /= 1024
    return str(n)


# ====================================================================== leitura
def _texto_de_bytes(b: bytes) -> str:
    for cod in ("utf-8-sig", "utf-16") if b[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return b.decode(cod)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace")


def _sem_tags(xml: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


def _ler_docx(p: Path) -> str:
    with zipfile.ZipFile(p) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"<w:tab/>", "\t", xml)
    return "\n".join(t for t in (_sem_tags(par) for par in re.split(r"</w:p>", xml)) if t.strip())


def _ler_pptx(p: Path) -> str:
    with zipfile.ZipFile(p) as z:
        slides = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)))
        partes = []
        for i, n in enumerate(slides, 1):
            textos = re.findall(r"<a:t>([^<]*)</a:t>", z.read(n).decode("utf-8", "replace"))
            partes.append(f"--- slide {i}\n" + html.unescape(" ".join(textos)))
    return "\n".join(partes)


def _ler_xlsx(p: Path, max_linhas: int = 300) -> str:
    with zipfile.ZipFile(p) as z:
        nomes = z.namelist()
        compartilhadas = []
        if "xl/sharedStrings.xml" in nomes:
            xml = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
            compartilhadas = [_sem_tags(si) for si in re.findall(r"<si>(.*?)</si>", xml, re.S)]
        livro = z.read("xl/workbook.xml").decode("utf-8", "replace") if "xl/workbook.xml" in nomes else ""
        titulos = [html.unescape(t) for t in re.findall(r'<sheet [^>]*name="([^"]*)"', livro)]
        planilhas = sorted((n for n in nomes if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)),
                           key=lambda n: int(re.search(r"(\d+)\.xml", n).group(1)))
        saida = []
        for i, n in enumerate(planilhas):
            saida.append(f"--- planilha {titulos[i] if i < len(titulos) else i + 1}")
            xml = z.read(n).decode("utf-8", "replace")
            for linha in re.findall(r"<row[^>]*>(.*?)</row>", xml, re.S)[:max_linhas]:
                valores = []
                for atributos, corpo in re.findall(r"<c([^>]*?)(?:/>|>(.*?)</c>)", linha, re.S):
                    v = re.search(r"<v>(.*?)</v>", corpo or "", re.S)
                    texto_inline = re.search(r"<is>(.*?)</is>", corpo or "", re.S)
                    if 't="s"' in atributos and v:
                        idx = int(v.group(1))
                        valores.append(compartilhadas[idx] if idx < len(compartilhadas) else "")
                    elif texto_inline:
                        valores.append(_sem_tags(texto_inline.group(1)))
                    else:
                        valores.append(html.unescape(v.group(1)) if v else "")
                saida.append(" | ".join(valores))
    return "\n".join(saida)


def _ler_pdf(p: Path, max_paginas: int = 80) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "(Para ler PDFs, rode o instalar.bat de novo: falta a biblioteca pypdf.)"
    leitor = PdfReader(str(p))
    partes = []
    for i, pag in enumerate(leitor.pages[:max_paginas], 1):
        partes.append(f"--- página {i}\n{(pag.extract_text() or '').strip()}")
    if len(leitor.pages) > max_paginas:
        partes.append(f"(... mais {len(leitor.pages) - max_paginas} páginas)")
    return "\n".join(partes)


def conteudo_texto(p: Path) -> str:
    """Todo o texto de um arquivo (txt, código, csv, json, Word, PowerPoint, Excel, PDF)."""
    ext = p.suffix.lower()
    if ext == ".docx":
        return _ler_docx(p)
    if ext == ".pptx":
        return _ler_pptx(p)
    if ext in (".xlsx", ".xlsm"):
        return _ler_xlsx(p)
    if ext == ".pdf":
        return _ler_pdf(p)
    if ext in TEXTO or p.stat().st_size < 400_000:
        dados = p.read_bytes()[:5_000_000]
        if b"\x00" in dados[:4000] and not dados.startswith((b"\xff\xfe", b"\xfe\xff")):
            raise ValueError(f"{p.name} não é um arquivo de texto ({ext or 'sem extensão'}).")
        return _texto_de_bytes(dados)
    raise ValueError(f"Não sei ler arquivos {ext} por dentro. Posso abrir no programa dele ou mandar para o celular.")


def ler(caminho: str, inicio: int = 0) -> str | dict:
    """Lê um arquivo e devolve o texto (em partes de até MAX_LEITURA letras). Imagens voltam como imagem."""
    try:
        p = resolver(caminho)
    except ValueError as e:
        return f"Erro: {e}"
    if not p.exists():
        return f"Não achei o arquivo {caminho}. Use arquivos_buscar para achar o caminho certo."
    if p.is_dir():
        return listar(str(p))
    if p.suffix.lower() in IMAGENS:
        import base64

        from PIL import Image

        img = Image.open(p)
        img.thumbnail((1280, 1280))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=80)
        return {"imagem_b64": base64.b64encode(buf.getvalue()).decode(), "texto": f"Imagem {p.name} ({p})."}
    try:
        texto = conteudo_texto(p)
    except (ValueError, zipfile.BadZipFile, KeyError) as e:
        return f"Não consegui ler {p.name}: {e}"
    inicio = max(0, int(inicio or 0))
    parte = texto[inicio:inicio + MAX_LEITURA]
    cabecalho = f"{p} ({len(texto)} letras"
    if inicio or len(texto) > inicio + MAX_LEITURA:
        cabecalho += f"; trecho {inicio}-{inicio + len(parte)}"
        if len(texto) > inicio + MAX_LEITURA:
            cabecalho += f"; para continuar use inicio={inicio + len(parte)}"
    return cabecalho + "):\n" + parte


def listar(caminho: str = "", ordenar: str = "nome", limite: int = 60) -> str:
    """O que tem numa pasta: subpastas e arquivos com tamanho e data."""
    try:
        p = resolver(caminho or "documentos", para_criar=True)
    except ValueError as e:
        return f"Erro: {e}"
    if not p.exists() or not p.is_dir():
        return f"Não achei a pasta {caminho}."
    itens = []
    try:
        for e in os.scandir(p):
            if e.name.startswith((".", "~$")) or e.name.lower() in ("desktop.ini", "thumbs.db"):
                continue
            try:
                st = e.stat()
            except OSError:
                continue
            itens.append((e.is_dir(), e.name, st.st_size, st.st_mtime))
    except PermissionError:
        return f"Sem permissão para ver a pasta {p}."
    chave = {"data": lambda i: -i[3], "tamanho": lambda i: -i[2]}.get(ordenar, lambda i: i[1].lower())
    pastas = sorted((i for i in itens if i[0]), key=chave)
    arquivos_ = sorted((i for i in itens if not i[0]), key=chave)
    linhas = [f"Pasta {p}: {len(pastas)} pastas e {len(arquivos_)} arquivos."]
    for _, nome, _, mod in pastas[:limite]:
        linhas.append(f"[pasta] {nome}  ({datetime.fromtimestamp(mod):%d/%m/%Y})")
    for _, nome, tam, mod in arquivos_[:max(0, limite - len(pastas[:limite]))]:
        linhas.append(f"{nome}  {_legivel(tam)}  {datetime.fromtimestamp(mod):%d/%m/%Y %H:%M}")
    if len(itens) > limite:
        linhas.append(f"(... e mais {len(itens) - limite} itens)")
    return "\n".join(linhas)


# ====================================================================== escrita
def _nome_livre(p: Path) -> Path:
    if not p.exists():
        return p
    for i in range(2, 1000):
        c = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not c.exists():
            return c
    raise ValueError("pasta cheia de arquivos com esse nome")


def _alvo_escrita(caminho: str, modo: str) -> Path:
    p = resolver(caminho, para_criar=True)
    if not p.suffix:
        p = p.with_suffix(".txt")
    return p


def escrever(caminho: str, conteudo: str = "", modo: str = "criar", procurar: str = "", trocar_por: str = "") -> str:
    """modo: criar (arquivo novo; se já existir, cria "nome (2)"), substituir (troca todo o conteúdo), acrescentar
    (no fim) ou trocar (troca o trecho `procurar` por `trocar_por`)."""
    try:
        p = _alvo_escrita(caminho, modo)
    except ValueError as e:
        return f"Erro: {e}"
    if protegido(p):
        return f"NEGADO: não mexo em {p.parent} (pasta do Windows, dos programas ou da própria Ametista)."
    if p.suffix.lower() not in ESCREVIVEIS:
        return f"Não consigo escrever arquivos {p.suffix} (só texto: .txt, .md, .csv, .json, código...)."
    conteudo = str(conteudo or "")
    if len(conteudo) > MAX_ESCRITA:
        return "Erro: texto grande demais para um arquivo de uma vez."
    p.parent.mkdir(parents=True, exist_ok=True)
    if modo == "criar":
        p = _nome_livre(p)
        p.write_text(conteudo, encoding="utf-8")
        return f"Criei {p} ({len(conteudo)} letras)."
    if not p.exists():
        if modo == "trocar":
            return f"Não achei o arquivo {p}."
        p.write_text(conteudo, encoding="utf-8")
        return f"Criei {p} ({len(conteudo)} letras)."
    atual = _texto_de_bytes(p.read_bytes())
    if modo == "substituir":
        novo = conteudo
    elif modo == "acrescentar":
        novo = atual + ("" if not atual or atual.endswith("\n") else "\n") + conteudo
    elif modo == "trocar":
        if not procurar:
            return "Erro: diga o trecho a procurar."
        vezes = atual.count(procurar)
        if not vezes:
            return f"Não encontrei esse trecho em {p.name}. Leia o arquivo antes (arquivo_ler) e copie o trecho igual."
        novo = atual.replace(procurar, trocar_por)
    else:
        return f"Erro: modo desconhecido '{modo}' (use criar, substituir, acrescentar ou trocar)."
    p.write_text(novo, encoding="utf-8")
    feito = {"substituir": "Substituí o conteúdo de", "acrescentar": "Acrescentei no fim de",
             "trocar": "Troquei o trecho em"}[modo]
    return f"{feito} {p}."


def _risco_escrever(a: dict) -> str:
    try:
        p = _alvo_escrita(a.get("caminho", ""), a.get("modo", "criar"))
    except ValueError:
        return acoes.LIVRE
    if a.get("modo", "criar") == "criar" or not p.exists() or _nas_notas(p):
        return acoes.LIVRE
    return acoes.CONFIRMAR


def _pergunta_escrever(a: dict) -> str:
    p = _alvo_escrita(a.get("caminho", ""), a.get("modo", "criar"))
    verbo = {"substituir": "trocar todo o conteúdo de", "acrescentar": "acrescentar um texto no fim de",
             "trocar": "trocar um trecho de"}.get(a.get("modo"), "mudar")
    return f"Posso {verbo} {p.name}, em {p.parent}? Eu guardo uma cópia para desfazer."


def _copia_de_seguranca(p: Path) -> Path:
    COPIAS.mkdir(parents=True, exist_ok=True)
    destino = COPIAS / f"{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}-{p.name}"
    shutil.copy2(p, destino)
    return destino


def _preparar_escrever(a: dict) -> dict | None:
    p = _alvo_escrita(a.get("caminho", ""), a.get("modo", "criar"))
    if a.get("modo", "criar") == "criar":
        return {"criado": str(_nome_livre(p))}
    if p.exists():
        return {"copia": str(_copia_de_seguranca(p)), "caminho": str(p)}
    return {"criado": str(p)}


def _desfazer_escrever(a: dict, antes: dict, resultado: str) -> str:
    if antes.get("copia"):
        shutil.copy2(antes["copia"], antes["caminho"])
        return f"{Path(antes['caminho']).name} voltou a ser como era."
    criado = Path(antes.get("criado", ""))
    if criado.exists():
        criado.unlink()
        return f"Apaguei {criado.name}, que eu tinha criado."
    return "Esse arquivo já não existe."


# ====================================================================== mover, copiar, apagar
def _destino_final(origem: Path, destino: str) -> Path:
    d = resolver(destino, para_criar=True)
    if d.is_dir() or str(destino).rstrip().endswith(("\\", "/")):
        return d / origem.name
    if not d.exists() and not d.suffix and origem.is_file():
        return d / origem.name           # "move para Documentos/Estudos": uma pasta (criada se não existir)
    return d


def _mover_ou_copiar(origem: str, destino: str, copiar: bool) -> str:
    try:
        o = resolver(origem)
        d = _destino_final(o, destino)
    except ValueError as e:
        return f"Erro: {e}"
    if not o.exists():
        return f"Não achei {origem}."
    if protegido(d) or (not copiar and protegido(o)):
        return "NEGADO: não mexo em pastas do Windows, dos programas ou da própria Ametista."
    d.parent.mkdir(parents=True, exist_ok=True)
    if d.exists() and d.is_file() and o.is_file():
        d.unlink()
    if copiar:
        if o.is_dir():
            shutil.copytree(o, d, dirs_exist_ok=True)
        else:
            shutil.copy2(o, d)
        return f"Copiei {o.name} para {d.parent}."
    shutil.move(str(o), str(d))
    return f"Movi {o.name} para {d}." if o.parent != d.parent else f"Renomeei para {d.name}."


def mover(origem: str, destino: str) -> str:
    return _mover_ou_copiar(origem, destino, copiar=False)


def copiar(origem: str, destino: str) -> str:
    return _mover_ou_copiar(origem, destino, copiar=True)


def _risco_mover(a: dict) -> str:
    try:
        o = resolver(a.get("origem", ""))
        d = _destino_final(o, a.get("destino", ""))
    except ValueError:
        return acoes.LIVRE
    return acoes.CONFIRMAR if d.exists() else acoes.LIVRE


def _preparar_mover(a: dict) -> dict | None:
    o = resolver(a.get("origem", ""))
    d = _destino_final(o, a.get("destino", ""))
    antes = {"origem": str(o), "destino": str(d)}
    if d.exists() and d.is_file():
        antes["copia_destino"] = str(_copia_de_seguranca(d))
    return antes


def _desfazer_mover(a: dict, antes: dict, resultado: str) -> str:
    d, o = Path(antes["destino"]), Path(antes["origem"])
    if not d.exists():
        return "O arquivo já não está onde eu deixei."
    o.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(d), str(o))
    if antes.get("copia_destino"):
        shutil.copy2(antes["copia_destino"], d)
    return f"{o.name} voltou para {o.parent}."


def _desfazer_copiar(a: dict, antes: dict, resultado: str) -> str:
    d = Path(antes["destino"])
    if antes.get("copia_destino"):
        shutil.copy2(antes["copia_destino"], d)
        return f"{d.name} voltou a ser como era."
    if d.is_dir():
        shutil.rmtree(d)
    elif d.exists():
        d.unlink()
    return f"Tirei a cópia de {d.name}."


def para_lixeira(p: Path) -> None:
    """Manda para a Lixeira do Windows (dá para restaurar por lá)."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                        ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

        op = SHFILEOPSTRUCTW(None, 3, str(p) + "\0", None, 0x0040 | 0x0010 | 0x0004 | 0x0400, False, None, None)
        codigo = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))   # FO_DELETE + ALLOWUNDO, sem janelas
        if codigo != 0 or op.fAnyOperationsAborted:
            raise OSError(f"o Windows não deixou apagar (código {codigo})")
        return
    lixo = config.DADOS / "lixeira"
    lixo.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p), str(_nome_livre(lixo / p.name)))


def apagar(caminho: str) -> str:
    try:
        p = resolver(caminho)
    except ValueError as e:
        return f"Erro: {e}"
    if not p.exists():
        return f"Não achei {caminho}."
    if protegido(p):
        return "NEGADO: não apago nada das pastas do Windows, dos programas ou da própria Ametista."
    try:
        para_lixeira(p)
    except OSError as e:
        return f"Não consegui apagar {p.name}: {e}"
    return f"Mandei {p.name} para a Lixeira (dá para restaurar por lá)."


def _pergunta_apagar(a: dict) -> str:
    try:
        p = resolver(a.get("caminho", ""))
    except ValueError:
        return "Posso apagar esse arquivo?"
    if p.is_dir():
        n = sum(len(f) for _, _, f in os.walk(p))
        return f"Posso mandar a pasta {p.name}, com {n} arquivos, para a Lixeira?"
    return f"Posso mandar {p.name} para a Lixeira?"


# ====================================================================== definições
DEFINICOES = [
    {"name": "arquivo_ler",
     "description": "Lê o conteúdo de um arquivo do PC: texto, código, CSV, JSON, Word (.docx), PowerPoint (.pptx), "
                    "Excel (.xlsx) e PDF; imagens você vê. Aceita caminho completo, 'Documentos/pasta/arquivo.txt' ou "
                    "só o nome (procura no índice). Textos longos vêm em partes: use 'inicio' para continuar.",
     "input_schema": {"type": "object", "properties": {
         "caminho": {"type": "string"}, "inicio": {"type": "integer", "description": "letra onde começar"}},
         "required": ["caminho"]}},
    {"name": "arquivo_escrever",
     "description": "Cria ou altera um arquivo de texto (.txt, .md, .csv, .json, código...). modo: criar (novo), "
                    "substituir (todo o conteúdo), acrescentar (no fim) ou trocar (troca o trecho 'procurar' por "
                    "'trocar_por'; leia o arquivo antes). Sem pasta no caminho, cria em Documentos\\Ametista. O "
                    "sistema pede confirmação quando precisa e guarda uma cópia para desfazer.",
     "input_schema": {"type": "object", "properties": {
         "caminho": {"type": "string"}, "conteudo": {"type": "string"},
         "modo": {"type": "string", "enum": ["criar", "substituir", "acrescentar", "trocar"]},
         "procurar": {"type": "string"}, "trocar_por": {"type": "string"}}, "required": ["caminho"]}},
    {"name": "pasta_listar",
     "description": "Mostra o que tem numa pasta (subpastas e arquivos com tamanho e data). Aceita 'Downloads', "
                    "'Área de Trabalho', 'Documentos/estudos' ou caminho completo.",
     "input_schema": {"type": "object", "properties": {
         "caminho": {"type": "string"}, "ordenar": {"type": "string", "enum": ["nome", "data", "tamanho"]}}}},
    {"name": "arquivo_mover",
     "description": "Move ou renomeia um arquivo ou pasta (destino: pasta ou caminho com o novo nome).",
     "input_schema": {"type": "object", "properties": {
         "origem": {"type": "string"}, "destino": {"type": "string"}}, "required": ["origem", "destino"]}},
    {"name": "arquivo_copiar", "description": "Copia um arquivo ou pasta para outro lugar.",
     "input_schema": {"type": "object", "properties": {
         "origem": {"type": "string"}, "destino": {"type": "string"}}, "required": ["origem", "destino"]}},
    {"name": "arquivo_apagar",
     "description": "Manda um arquivo ou pasta para a Lixeira (o sistema pede confirmação).",
     "input_schema": {"type": "object", "properties": {"caminho": {"type": "string"}}, "required": ["caminho"]}},
]
FUNCOES = {"arquivo_ler": ler, "arquivo_escrever": escrever, "pasta_listar": listar, "arquivo_mover": mover,
           "arquivo_copiar": copiar, "arquivo_apagar": apagar}


def _nome(a: dict, chave: str = "caminho") -> str:
    return re.split(r"[\\/]", str(a.get(chave, "")).rstrip("\\/"))[-1] or str(a.get(chave, ""))


acoes.registrar_ferramenta("arquivo_ler", descrever=lambda a: f"Leu o arquivo {_nome(a)}")
acoes.registrar_ferramenta("pasta_listar", leitura=True)
acoes.registrar_ferramenta(
    "arquivo_escrever", risco=_risco_escrever, pergunta=_pergunta_escrever, preparar=_preparar_escrever,
    desfazer=_desfazer_escrever,
    descrever=lambda a: {"criar": "Criou", "substituir": "Reescreveu", "acrescentar": "Acrescentou texto em",
                         "trocar": "Editou"}.get(a.get("modo", "criar"), "Alterou") + f" o arquivo {_nome(a)}")
acoes.registrar_ferramenta(
    "arquivo_mover", risco=_risco_mover, preparar=_preparar_mover, desfazer=_desfazer_mover,
    pergunta=lambda a: f"Já existe um arquivo com esse nome no destino. Posso substituir por {_nome(a, 'origem')}?",
    descrever=lambda a: f"Moveu {_nome(a, 'origem')} para {a.get('destino')}")
acoes.registrar_ferramenta(
    "arquivo_copiar", risco=_risco_mover, preparar=_preparar_mover, desfazer=_desfazer_copiar,
    pergunta=lambda a: f"Já existe um arquivo com esse nome no destino. Posso substituir pela cópia de "
                       f"{_nome(a, 'origem')}?",
    descrever=lambda a: f"Copiou {_nome(a, 'origem')} para {a.get('destino')}")
acoes.registrar_ferramenta("arquivo_apagar", risco=acoes.CONFIRMAR, pergunta=_pergunta_apagar,
                           descrever=lambda a: f"Mandou {_nome(a)} para a Lixeira")
