"""Steam: acha o jogo, mostra as unidades com espaço livre, instala na unidade escolhida e avisa quando termina.

Como a instalação "na unidade escolhida" funciona:
  A Steam instala num lugar chamado "biblioteca" (uma pasta SteamLibrary em cada disco).
  Se o disco escolhido já tem biblioteca, a Ametista cria o arquivo de instalação do jogo nela
  (appmanifest) e reinicia a Steam, que começa a baixar lá sozinha.
  Se o disco não tem biblioteca, ela abre a janela oficial de instalação da Steam, onde dá para
  escolher o disco ou criar a biblioteca.
"""
import html
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path

import httpx

from . import config, eventos

WINDOWS = sys.platform == "win32"
_SEM_JANELA = 0x08000000 if WINDOWS else 0

INSTRUCOES = """Steam: para instalar um jogo siga SEMPRE esta ordem:
1) steam_buscar_jogo para identificar o jogo certo (confirme com a pessoa se houver mais de um parecido)
   e ver se ele já está instalado e quanto espaço precisa;
2) se não estiver instalado, steam_unidades e diga quanto espaço livre tem em cada disco e em qual cabe;
3) pergunte em qual unidade instalar e só então use steam_instalar.
Se a Steam precisar reiniciar, o sistema pede a confirmação. Se pedirem para avisar quando terminar,
use steam_avisar_quando_pronto. Para "já está instalado?" use steam_buscar_jogo ou steam_status."""


# ================================================================== arquivos da Steam
def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in t if unicodedata.category(c) != "Mn"))


def ler_vdf(texto: str) -> dict:
    """Lê o formato de texto da Valve (VDF/ACF): "chave" "valor" e blocos { }."""
    fichas = re.findall(r'"((?:[^"\\]|\\.)*)"|([{}])', texto)
    pilha: list[dict] = [{}]
    chave = None
    for texto_f, chave_bloco in fichas:
        if chave_bloco == "{":
            novo: dict = {}
            pilha[-1][chave] = novo
            pilha.append(novo)
            chave = None
        elif chave_bloco == "}":
            pilha.pop()
            chave = None
        elif chave is None:
            chave = texto_f
        else:
            pilha[-1][chave] = texto_f.replace("\\\\", "\\")
            chave = None
    return pilha[0]


def pasta_steam() -> Path | None:
    if config.STEAM_PASTA:
        p = Path(config.STEAM_PASTA)
        return p if p.exists() else None
    if not WINDOWS:
        p = Path.home() / ".steam/steam"
        return p if p.exists() else None
    import winreg

    for raiz, chave, valor in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                               (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")):
        try:
            with winreg.OpenKey(raiz, chave) as k:
                p = Path(winreg.QueryValueEx(k, valor)[0])
                if p.exists():
                    return p
        except OSError:
            pass
    return None


def disponivel() -> bool:
    return pasta_steam() is not None


def bibliotecas() -> list[Path]:
    raiz = pasta_steam()
    if not raiz:
        return []
    libs = [raiz]
    arq = raiz / "steamapps" / "libraryfolders.vdf"
    if arq.exists():
        dados = ler_vdf(arq.read_text(encoding="utf-8", errors="ignore")).get("libraryfolders", {})
        for item in dados.values():
            if isinstance(item, dict) and item.get("path"):
                p = Path(item["path"])
                if p.exists() and all(p.resolve() != l.resolve() for l in libs):
                    libs.append(p)
    return libs


def jogos_instalados() -> list[dict]:
    jogos = []
    for lib in bibliotecas():
        for acf in (lib / "steamapps").glob("appmanifest_*.acf"):
            try:
                st = ler_vdf(acf.read_text(encoding="utf-8", errors="ignore")).get("AppState", {})
            except OSError:
                continue
            flags = int(st.get("StateFlags", "0") or 0)
            total = int(st.get("BytesToDownload", "0") or 0)
            feito = int(st.get("BytesDownloaded", "0") or 0)
            jogos.append({
                "appid": int(st.get("appid", "0") or 0), "nome": st.get("name", "?"),
                "biblioteca": str(lib), "unidade": _unidade_de(lib),
                "tamanho_gb": round(int(st.get("SizeOnDisk", "0") or 0) / 1e9, 1),
                "instalado": bool(flags & 4) and not (flags & 2) and (total == 0 or feito >= total),
                "baixando": bool(flags & (2 | 1024)) or (0 < feito < total),
                "progresso": round(100 * feito / total) if total else None,
                "manifesto": str(acf),
            })
    return jogos


def _unidade_de(caminho: Path) -> str:
    d = Path(caminho).resolve().drive
    return d.upper() if d else str(Path(caminho).resolve().anchor or "/")


# ================================================================== loja
def _tamanho_requisito(appid: int) -> float | None:
    try:
        r = httpx.get("https://store.steampowered.com/api/appdetails",
                      params={"appids": appid, "l": "portuguese", "cc": "BR"}, timeout=10)
        dados = r.json()[str(appid)].get("data", {})
    except Exception:
        return None
    req = dados.get("pc_requirements") or {}
    texto = html.unescape(re.sub(r"<[^>]+>", " ", (req.get("recommended") or "") + " " + (req.get("minimum") or "")
                                 if isinstance(req, dict) else ""))
    tamanhos = []
    for m in re.finditer(r"(armazenamento|espa[çc]o|disco|storage|hard (?:drive|disk))[^0-9]{0,40}"
                         r"(\d+(?:[.,]\d+)?)\s*(gb|mb|tb)", texto, re.I):
        v = float(m.group(2).replace(",", "."))
        tamanhos.append(v / 1000 if m.group(3).lower() == "mb" else v * 1000 if m.group(3).lower() == "tb" else v)
    return max(tamanhos) if tamanhos else None


def buscar_jogo(nome: str) -> str:
    """Identifica o jogo na loja e diz se já está instalado."""
    instalados = jogos_instalados()
    alvo = _norm(nome)
    locais = [j for j in instalados if alvo and alvo in _norm(j["nome"])]
    try:
        r = httpx.get("https://store.steampowered.com/api/storesearch/",
                      params={"term": nome, "l": "portuguese", "cc": "BR"}, timeout=10)
        itens = [i for i in r.json().get("items", []) if i.get("type") == "app"][:5]
    except Exception as e:
        itens = []
        if not locais:
            return f"Não consegui consultar a loja da Steam ({e})."
    linhas = []
    for i, it in enumerate(itens):
        inst = next((j for j in instalados if j["appid"] == it["id"]), None)
        preco = it.get("price") or {}
        valor = f"R$ {preco['final'] / 100:.2f}".replace(".", ",") if preco.get("final") else "grátis ou sem preço"
        linha = f"[{it['id']}] {it['name']} ({valor})"
        if i == 0:
            tam = _tamanho_requisito(it["id"])
            if tam:
                linha += f", precisa de uns {tam:.0f} GB"
        if inst:
            linha += (f" | JÁ INSTALADO em {inst['unidade']} ({inst['tamanho_gb']} GB)" if inst["instalado"]
                      else f" | BAIXANDO em {inst['unidade']}"
                           + (f", {inst['progresso']}%" if inst["progresso"] is not None else ""))
        else:
            linha += " | não instalado"
        linhas.append(linha)
    for j in locais:  # instalados que a busca não trouxe
        if all(j["appid"] != it["id"] for it in itens):
            linhas.append(f"[{j['appid']}] {j['nome']} | JÁ INSTALADO em {j['unidade']}")
    if not linhas:
        return f"Não achei nenhum jogo chamado {nome} na Steam."
    if not disponivel():
        linhas.append("(Steam não encontrada neste PC.)")
    return "Resultados (o primeiro é o mais provável):\n" + "\n".join(linhas)


# ================================================================== unidades
def unidades(espaco_necessario_gb: float = 0) -> str:
    import psutil

    libs_por_unidade: dict[str, list[str]] = {}
    for lib in bibliotecas():
        libs_por_unidade.setdefault(_unidade_de(lib), []).append(str(lib))
    vistos, linhas = set(), []
    for part in psutil.disk_partitions(all=False):
        if WINDOWS and ("cdrom" in part.opts or not part.fstype):
            continue
        if not WINDOWS and not part.mountpoint.startswith(("/", )):
            continue
        uni = _unidade_de(Path(part.mountpoint))
        if uni in vistos:
            continue
        vistos.add(uni)
        try:
            uso = shutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        livre, total = uso.free / 1e9, uso.total / 1e9
        if total < 8:  # pen drives pequenos, partições de sistema
            continue
        linha = f"{uni} {livre:.0f} GB livres de {total:.0f} GB"
        linha += " | tem biblioteca Steam" if uni in libs_por_unidade else " | sem biblioteca Steam"
        if espaco_necessario_gb:
            linha += " | CABE" if livre >= espaco_necessario_gb * 1.1 else " | NÃO CABE"
        linhas.append(linha)
    return "\n".join(linhas) or "Não encontrei unidades de disco."


# ================================================================== instalar
def _steam_exe() -> Path | None:
    raiz = pasta_steam()
    if not raiz:
        return None
    for nome in ("steam.exe", "Steam.exe", "steam.sh", "steam"):
        if (raiz / nome).exists():
            return raiz / nome
    return None


def _steam_rodando() -> bool:
    import psutil

    return any((p.info["name"] or "").lower() in ("steam.exe", "steam") for p in psutil.process_iter(["name"]))


def _abrir_url(url: str) -> None:
    if WINDOWS:
        os.startfile(url)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _reiniciar_steam() -> None:
    exe = _steam_exe()
    if _steam_rodando() and exe:
        subprocess.Popen([str(exe), "-shutdown"], creationflags=_SEM_JANELA)
        for _ in range(60):
            time.sleep(1)
            if not _steam_rodando():
                break
    if exe:
        subprocess.Popen([str(exe)], creationflags=_SEM_JANELA)
    else:
        _abrir_url("steam://open/downloads")


def _normalizar_unidade(unidade: str) -> str:
    uni = unidade.strip().rstrip(":\\/").upper()
    return f"{uni}:" if len(uni) == 1 else uni


def precisa_reiniciar_para(unidade: str, appid: int) -> bool:
    """Instalar nessa unidade vai reiniciar a Steam? (usado para pedir confirmação antes)"""
    if not disponivel() or not _steam_rodando():
        return False
    if any(j["appid"] == int(appid) for j in jogos_instalados()):
        return False
    uni = _normalizar_unidade(unidade)
    return any(_unidade_de(l) == uni for l in bibliotecas())


def instalar(appid: int, unidade: str, confirmado_reiniciar: bool = False) -> str:
    appid = int(appid)
    if not disponivel():
        return "Não encontrei a Steam neste PC. Instale a Steam primeiro."
    ja = next((j for j in jogos_instalados() if j["appid"] == appid), None)
    if ja:
        if ja["instalado"]:
            return f"{ja['nome']} já está instalado em {ja['unidade']}."
        return f"{ja['nome']} já está baixando em {ja['unidade']}."

    uni = _normalizar_unidade(unidade)
    libs = [l for l in bibliotecas() if _unidade_de(l) == uni]
    if not libs:
        _abrir_url(f"steam://install/{appid}")
        return (f"A unidade {uni} ainda não tem biblioteca da Steam. Abri a janela de instalação: em "
                f"'Local de instalação' escolha {uni} ou 'Adicionar nova biblioteca' nela.")

    if _steam_rodando() and not confirmado_reiniciar:
        return ("PRECISA CONFIRMAR: para instalar direto em " + uni + " a Steam precisa reiniciar "
                "(downloads e jogos abertos na Steam vão fechar).")

    nome = _nome_loja(appid) or f"app{appid}"
    pasta_jogo = re.sub(r'[<>:"/\\|?*]', "", nome).strip() or f"app{appid}"
    manifesto = libs[0] / "steamapps" / f"appmanifest_{appid}.acf"
    manifesto.parent.mkdir(parents=True, exist_ok=True)
    manifesto.write_text(
        '"AppState"\n{\n'
        f'\t"appid"\t\t"{appid}"\n\t"Universe"\t\t"1"\n\t"name"\t\t"{nome}"\n'
        '\t"StateFlags"\t\t"1026"\n'
        f'\t"installdir"\t\t"{pasta_jogo}"\n'
        '}\n', encoding="utf-8")
    threading.Thread(target=_reiniciar_e_conferir, args=(appid, manifesto, nome), daemon=True).start()
    return (f"Preparei {nome} para instalar em {uni} ({libs[0]}). "
            "A Steam está reiniciando e o download começa sozinho em instantes.")


def _nome_loja(appid: int) -> str | None:
    try:
        r = httpx.get("https://store.steampowered.com/api/appdetails",
                      params={"appids": appid, "l": "portuguese", "filters": "basic"}, timeout=10)
        return r.json()[str(appid)]["data"]["name"]
    except Exception:
        return None


def _reiniciar_e_conferir(appid: int, manifesto: Path, nome: str) -> None:
    """Reinicia a Steam e confere se o download começou; se não, abre a janela oficial."""
    _reiniciar_steam()
    for _ in range(18):  # até 3 minutos
        time.sleep(10)
        j = next((x for x in jogos_instalados() if x["appid"] == appid), None)
        if j and (j["progresso"] or j["instalado"]):
            return
        if not manifesto.exists():
            return
    # Não começou (ex.: jogo não está na conta): desfaz e abre a instalação oficial
    try:
        texto = manifesto.read_text(encoding="utf-8")
        if '"StateFlags"\t\t"1026"' in texto and "BytesToDownload" not in texto:
            manifesto.unlink()
    except OSError:
        pass
    _abrir_url(f"steam://install/{appid}")
    eventos.publicar({"tipo": "aviso", "texto": f"A Steam não começou a baixar {nome} sozinha. "
                                                "Abri a janela de instalação para você confirmar."})


# ================================================================== status e aviso
_vigias: dict[int, threading.Thread] = {}


def status(appid: int) -> str:
    j = next((x for x in jogos_instalados() if x["appid"] == int(appid)), None)
    if not j:
        return "Não está instalado nem baixando."
    if j["instalado"]:
        return f"{j['nome']} está instalado em {j['unidade']} ({j['tamanho_gb']} GB)."
    prog = f", {j['progresso']}% baixado" if j["progresso"] is not None else ""
    return f"{j['nome']} está baixando em {j['unidade']}{prog}."


def avisar_quando_pronto(appid: int) -> str:
    appid = int(appid)
    j = next((x for x in jogos_instalados() if x["appid"] == appid), None)
    if j and j["instalado"]:
        return f"{j['nome']} já está instalado."
    if appid in _vigias and _vigias[appid].is_alive():
        return "Já estou de olho nesse download."

    def vigiar():
        for _ in range(60 * 24 * 3):  # até 3 dias, conferindo a cada minuto
            time.sleep(60)
            x = next((y for y in jogos_instalados() if y["appid"] == appid), None)
            if x and x["instalado"]:
                texto = f"{x['nome']} terminou de instalar e já pode ser jogado!"
                from . import voz
                import asyncio

                eventos.publicar({"tipo": "alerta", "texto": texto, "emocao": "feliz",
                                  "audio": asyncio.run(voz.sintetizar(texto))})
                eventos.publicar({"tipo": "notificar_celular", "titulo": "Instalação concluída",
                                  "texto": texto, "interno": True})
                return

    _vigias[appid] = threading.Thread(target=vigiar, daemon=True, name=f"steam-{appid}")
    _vigias[appid].start()
    return "Combinado: aviso aqui (e no celular) quando terminar."


def abrir_steam() -> str:
    _abrir_url("steam://open/main")
    return "Abrindo a Steam."


DEFINICOES = [
    {"name": "steam_buscar_jogo",
     "description": "Identifica um jogo na loja da Steam (id, preço, espaço necessário) e diz se já está "
                    "instalado ou baixando e em qual unidade.",
     "input_schema": {"type": "object", "properties": {"nome": {"type": "string"}}, "required": ["nome"]}},
    {"name": "steam_unidades",
     "description": "Lista os discos (C:, D:...) com espaço livre, se têm biblioteca Steam e se o jogo cabe.",
     "input_schema": {"type": "object", "properties": {
         "espaco_necessario_gb": {"type": "number"}}}},
    {"name": "steam_instalar",
     "description": "Instala um jogo (appid) na unidade escolhida pela pessoa. Só use depois de perguntar a unidade.",
     "input_schema": {"type": "object", "properties": {
         "appid": {"type": "integer"}, "unidade": {"type": "string", "description": "Ex.: D:"}},
         "required": ["appid", "unidade"]}},
    {"name": "steam_status", "description": "Diz se um jogo (appid) está instalado ou quanto falta baixar.",
     "input_schema": {"type": "object", "properties": {"appid": {"type": "integer"}}, "required": ["appid"]}},
    {"name": "steam_avisar_quando_pronto",
     "description": "Fica de olho no download e avisa (voz + celular) quando o jogo terminar de instalar.",
     "input_schema": {"type": "object", "properties": {"appid": {"type": "integer"}}, "required": ["appid"]}},
    {"name": "steam_abrir", "description": "Abre a Steam.", "input_schema": {"type": "object", "properties": {}}},
]
FUNCOES = {"steam_buscar_jogo": buscar_jogo, "steam_unidades": unidades, "steam_instalar": instalar,
           "steam_status": status, "steam_avisar_quando_pronto": avisar_quando_pronto, "steam_abrir": abrir_steam}
