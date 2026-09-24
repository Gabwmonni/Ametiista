"""Agenda: Google Agenda e Outlook (Microsoft 365 / conta pessoal) ao mesmo tempo.

Conectar (uma vez cada, passo a passo no LEIA-ME):
  Google : salve o arquivo de credenciais OAuth como dados/google_credenciais.json
           e clique em "Conectar Google Agenda" na bandeja.
  Outlook: coloque o MS_CLIENT_ID no .env e clique em "Conectar Outlook" na bandeja.

Os ids dos eventos têm prefixo: g:... (Google) e m:... (Microsoft).
"""
import threading
from datetime import date, datetime, timedelta

import httpx

from . import config

GOOGLE_CRED = config.DADOS / "google_credenciais.json"
GOOGLE_TOKEN = config.DADOS / "google_token.json"
MS_CACHE = config.DADOS / "microsoft_token.json"
GOOGLE_ESCOPOS = ["https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/calendar.readonly"]
MS_ESCOPOS = ["Calendars.ReadWrite"]
GRAPH = "https://graph.microsoft.com/v1.0"
GCAL = "https://www.googleapis.com/calendar/v3"

INSTRUCOES = """Agenda (Google e Outlook): para mudar ou cancelar um compromisso, primeiro use agenda_listar
para achar o id. Cancelar pede confirmação (o sistema cuida disso). Ao criar sem dizer qual agenda, use a
padrão. Leia horários de forma falada ("às duas da tarde")."""


def _tz():
    return datetime.now().astimezone().tzinfo


def google_conectado() -> bool:
    return GOOGLE_TOKEN.exists()


def outlook_conectado() -> bool:
    return bool(config.MS_CLIENT_ID) and MS_CACHE.exists()


def configurada() -> bool:
    return GOOGLE_CRED.exists() or GOOGLE_TOKEN.exists() or bool(config.MS_CLIENT_ID)


# ================================================================== Google
_google_creds = None
_trava_g = threading.Lock()


def conectar_google() -> str:
    """Abre o navegador para autorizar (bloqueante)."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not GOOGLE_CRED.exists():
        return f"Falta o arquivo {GOOGLE_CRED.name} na pasta dados (veja o LEIA-ME)."
    flow = InstalledAppFlow.from_client_secrets_file(str(GOOGLE_CRED), GOOGLE_ESCOPOS)
    creds = flow.run_local_server(port=0, prompt="consent", success_message="Google Agenda conectada! Pode fechar.")
    GOOGLE_TOKEN.write_text(creds.to_json(), encoding="utf-8")
    global _google_creds
    _google_creds = creds
    return "Google Agenda conectada."


def _google_token() -> str:
    global _google_creds
    with _trava_g:
        if _google_creds is None:
            if not GOOGLE_TOKEN.exists():
                raise RuntimeError("Google Agenda não conectada (bandeja > Conectar Google Agenda).")
            from google.oauth2.credentials import Credentials

            _google_creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN), GOOGLE_ESCOPOS)
        if not _google_creds.valid:
            from google.auth.transport.requests import Request

            _google_creds.refresh(Request())
            GOOGLE_TOKEN.write_text(_google_creds.to_json(), encoding="utf-8")
        return _google_creds.token


def _g(metodo: str, caminho: str, **kw) -> dict:
    r = httpx.request(metodo, GCAL + caminho, headers={"Authorization": f"Bearer {_google_token()}"},
                      timeout=15, **kw)
    r.raise_for_status()
    return r.json() if r.content else {}


def _g_listar(inicio: datetime, fim: datetime) -> list[dict]:
    dados = _g("GET", "/calendars/primary/events", params={
        "timeMin": inicio.isoformat(), "timeMax": fim.isoformat(), "singleEvents": "true",
        "orderBy": "startTime", "maxResults": 100})
    eventos = []
    for e in dados.get("items", []):
        if e.get("status") == "cancelled":
            continue
        ini, fi = e.get("start", {}), e.get("end", {})
        eventos.append({
            "id": "g:" + e["id"], "titulo": e.get("summary", "(sem título)"), "local": e.get("location", ""),
            "inicio": _parse(ini.get("dateTime") or ini.get("date")),
            "fim": _parse(fi.get("dateTime") or fi.get("date")),
            "dia_inteiro": "date" in ini, "agenda": "Google"})
    return eventos


def _g_corpo(titulo, inicio, fim, dia_inteiro, local, descricao) -> dict:
    corpo: dict = {}
    if titulo is not None:
        corpo["summary"] = titulo
    if local is not None:
        corpo["location"] = local
    if descricao is not None:
        corpo["description"] = descricao
    if inicio is not None:
        if dia_inteiro:
            corpo["start"] = {"date": inicio.date().isoformat()}
            corpo["end"] = {"date": (fim or inicio + timedelta(days=1)).date().isoformat()}
        else:
            corpo["start"] = {"dateTime": inicio.isoformat()}
            corpo["end"] = {"dateTime": fim.isoformat()}
    return corpo


# ================================================================== Microsoft (Outlook)
_msal_app = None
_ms_cache = None


def _ms():
    global _msal_app, _ms_cache
    if _msal_app is None:
        import msal

        _ms_cache = msal.SerializableTokenCache()
        if MS_CACHE.exists():
            _ms_cache.deserialize(MS_CACHE.read_text(encoding="utf-8"))
        _msal_app = msal.PublicClientApplication(config.MS_CLIENT_ID, token_cache=_ms_cache,
                                                 authority="https://login.microsoftonline.com/common")
    return _msal_app


def _ms_salvar_cache() -> None:
    if _ms_cache is not None and _ms_cache.has_state_changed:
        MS_CACHE.write_text(_ms_cache.serialize(), encoding="utf-8")


def conectar_outlook() -> str:
    if not config.MS_CLIENT_ID:
        return "Falta o MS_CLIENT_ID no .env (veja o LEIA-ME)."
    r = _ms().acquire_token_interactive(scopes=MS_ESCOPOS, prompt="select_account")
    if "access_token" not in r:
        return f"Não conectou: {r.get('error_description', r)}"
    _ms_salvar_cache()
    return "Outlook conectado."


def _ms_token() -> str:
    app = _ms()
    contas = app.get_accounts()
    if not contas:
        raise RuntimeError("Outlook não conectado (bandeja > Conectar Outlook).")
    r = app.acquire_token_silent(MS_ESCOPOS, account=contas[0])
    _ms_salvar_cache()
    if not r or "access_token" not in r:
        raise RuntimeError("A conexão com o Outlook expirou: conecte de novo pela bandeja.")
    return r["access_token"]


def _m(metodo: str, caminho: str, **kw) -> dict:
    cab = {"Authorization": f"Bearer {_ms_token()}", "Prefer": 'outlook.timezone="UTC"'}
    r = httpx.request(metodo, GRAPH + caminho, headers=cab, timeout=15, **kw)
    r.raise_for_status()
    return r.json() if r.content else {}


def _ms_data(d: dict) -> datetime:
    # Graph devolve "2026-09-24T17:00:00.0000000" no fuso pedido (UTC)
    from datetime import timezone

    return datetime.fromisoformat(d["dateTime"][:19]).replace(tzinfo=timezone.utc).astimezone(_tz())


def _m_listar(inicio: datetime, fim: datetime) -> list[dict]:
    dados = _m("GET", "/me/calendarView", params={
        "startDateTime": inicio.isoformat(), "endDateTime": fim.isoformat(), "$top": 100,
        "$orderby": "start/dateTime", "$select": "id,subject,start,end,location,isAllDay,isCancelled"})
    return [{
        "id": "m:" + e["id"], "titulo": e.get("subject") or "(sem título)",
        "local": (e.get("location") or {}).get("displayName", ""),
        "inicio": _ms_data(e["start"]), "fim": _ms_data(e["end"]),
        "dia_inteiro": e.get("isAllDay", False), "agenda": "Outlook",
    } for e in dados.get("value", []) if not e.get("isCancelled")]


def _m_corpo(titulo, inicio, fim, dia_inteiro, local, descricao) -> dict:
    corpo: dict = {}
    if titulo is not None:
        corpo["subject"] = titulo
    if local is not None:
        corpo["location"] = {"displayName": local}
    if descricao is not None:
        corpo["body"] = {"contentType": "text", "content": descricao}
    if inicio is not None:
        fmt = "%Y-%m-%dT00:00:00" if dia_inteiro else "%Y-%m-%dT%H:%M:%S"
        fim = fim or (inicio + timedelta(days=1))
        corpo["start"] = {"dateTime": inicio.strftime(fmt), "timeZone": config.FUSO_WINDOWS}
        corpo["end"] = {"dateTime": fim.strftime(fmt), "timeZone": config.FUSO_WINDOWS}
        corpo["isAllDay"] = bool(dia_inteiro)
    return corpo


# ================================================================== comum
def _parse(texto: str) -> datetime:
    if len(texto) == 10:  # dia inteiro
        return datetime.fromisoformat(texto).replace(tzinfo=_tz())
    d = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=_tz())).astimezone(_tz())


def _data_hora(texto: str) -> datetime:
    d = datetime.fromisoformat(texto.strip())
    return d if d.tzinfo else d.replace(tzinfo=_tz())


def todos_eventos(inicio: datetime, fim: datetime) -> tuple[list[dict], list[str]]:
    eventos, erros = [], []
    for nome, ok, func in (("Google", google_conectado, _g_listar), ("Outlook", outlook_conectado, _m_listar)):
        if ok():
            try:
                eventos += func(inicio, fim)
            except Exception as e:
                erros.append(f"{nome}: {e}")
    eventos.sort(key=lambda e: e["inicio"])
    return eventos, erros


def listar(data_inicio: str = "", dias: int = 1, busca: str = "") -> str:
    base = date.fromisoformat(data_inicio) if data_inicio else date.today()
    inicio = datetime.combine(base, datetime.min.time(), _tz())
    fim = inicio + timedelta(days=max(1, min(int(dias), 60)))
    if not (google_conectado() or outlook_conectado()):
        return "Nenhuma agenda conectada ainda (bandeja > Conectar Google Agenda / Conectar Outlook)."
    eventos, erros = todos_eventos(inicio, fim)
    if busca:
        eventos = [e for e in eventos if busca.lower() in (e["titulo"] + " " + e["local"]).lower()]
    linhas = []
    for e in eventos:
        quando = e["inicio"].strftime("%d/%m") + (" dia inteiro" if e["dia_inteiro"] else
                                                   f" {e['inicio']:%H:%M}-{e['fim']:%H:%M}")
        linhas.append(f"[{e['id']}] {quando} {e['titulo']}" + (f" @ {e['local']}" if e["local"] else "")
                      + f" ({e['agenda']})")
    texto = "\n".join(linhas) or "Nenhum compromisso nesse período."
    if erros:
        texto += "\nAvisos: " + "; ".join(erros)
    return texto


def criar(titulo: str, inicio: str, fim: str = "", duracao_min: int = 60, agenda: str = "",
          local: str = "", descricao: str = "", dia_inteiro: bool = False) -> str:
    ini = _data_hora(inicio)
    fi = _data_hora(fim) if fim else ini + timedelta(minutes=int(duracao_min or 60))
    qual = (agenda or config.AGENDA_PADRAO).lower()
    if qual.startswith("out") or qual.startswith("micro"):
        e = _m("POST", "/me/events", json=_m_corpo(titulo, ini, fi, dia_inteiro, local or None, descricao or None))
        return f"Criado no Outlook: {titulo} em {ini:%d/%m às %H:%M} [m:{e.get('id', '?')}]."
    e = _g("POST", "/calendars/primary/events", json=_g_corpo(titulo, ini, fi, dia_inteiro, local or None,
                                                               descricao or None))
    return f"Criado no Google Agenda: {titulo} em {ini:%d/%m às %H:%M} [g:{e.get('id', '?')}]."


def alterar(id: str, titulo: str = None, inicio: str = None, fim: str = None, local: str = None) -> str:
    prov, eid = id.split(":", 1)
    novo_ini = _data_hora(inicio) if inicio else None
    novo_fim = _data_hora(fim) if fim else None
    if novo_ini and not novo_fim:  # mantém a duração original
        atual = _obter(prov, eid)
        novo_fim = novo_ini + (atual["fim"] - atual["inicio"])
    if prov == "g":
        _g("PATCH", f"/calendars/primary/events/{eid}", json=_g_corpo(titulo, novo_ini, novo_fim, False, local, None))
    else:
        _m("PATCH", f"/me/events/{eid}", json=_m_corpo(titulo, novo_ini, novo_fim, False, local, None))
    return "Compromisso atualizado" + (f" para {novo_ini:%d/%m às %H:%M}." if novo_ini else ".")


def _obter(prov: str, eid: str) -> dict:
    if prov == "g":
        e = _g("GET", f"/calendars/primary/events/{eid}")
        return {"inicio": _parse(e["start"].get("dateTime") or e["start"]["date"]),
                "fim": _parse(e["end"].get("dateTime") or e["end"]["date"])}
    e = _m("GET", f"/me/events/{eid}", params={"$select": "start,end"})
    return {"inicio": _ms_data(e["start"]), "fim": _ms_data(e["end"])}


def obter(id: str) -> dict:
    """Dados completos de um compromisso (usado para desfazer alterações e cancelamentos)."""
    prov, eid = id.split(":", 1)
    if prov == "g":
        e = _g("GET", f"/calendars/primary/events/{eid}")
        ini, fi = e.get("start", {}), e.get("end", {})
        return {"titulo": e.get("summary", ""), "local": e.get("location", ""), "agenda": "google",
                "inicio": _parse(ini.get("dateTime") or ini.get("date")).isoformat(timespec="minutes"),
                "fim": _parse(fi.get("dateTime") or fi.get("date")).isoformat(timespec="minutes"),
                "dia_inteiro": "date" in ini}
    e = _m("GET", f"/me/events/{eid}", params={"$select": "subject,start,end,location,isAllDay"})
    return {"titulo": e.get("subject") or "", "local": (e.get("location") or {}).get("displayName", ""),
            "agenda": "outlook", "inicio": _ms_data(e["start"]).isoformat(timespec="minutes"),
            "fim": _ms_data(e["end"]).isoformat(timespec="minutes"), "dia_inteiro": e.get("isAllDay", False)}


def cancelar(id: str) -> str:
    prov, eid = id.split(":", 1)
    if prov == "g":
        _g("DELETE", f"/calendars/primary/events/{eid}")
    else:
        _m("DELETE", f"/me/events/{eid}")
    return "Compromisso cancelado."


# ================================================================== avisos antes dos compromissos
_avisados: set[str] = set()


def proximos_para_avisar() -> list[str]:
    """Chamado a cada minuto: compromissos que começam daqui a AVISO_AGENDA_MIN minutos."""
    if not (google_conectado() or outlook_conectado()) or config.AVISO_AGENDA_MIN <= 0:
        return []
    agora = datetime.now(_tz())
    eventos, _ = todos_eventos(agora, agora + timedelta(minutes=config.AVISO_AGENDA_MIN + 1))
    avisos = []
    for e in eventos:
        if e["dia_inteiro"] or e["id"] in _avisados or e["inicio"] < agora:
            continue
        _avisados.add(e["id"])
        minutos = max(1, round((e["inicio"] - agora).total_seconds() / 60))
        avisos.append(f"Daqui a {minutos} minutos: {e['titulo']}" + (f", em {e['local']}" if e["local"] else "") + ".")
    return avisos


DEFINICOES = [
    {"name": "agenda_listar",
     "description": "Compromissos do Google Agenda e do Outlook juntos, com id de cada um.",
     "input_schema": {"type": "object", "properties": {
         "data_inicio": {"type": "string", "description": "AAAA-MM-DD (padrão: hoje)"},
         "dias": {"type": "integer", "description": "Quantos dias a partir da data (padrão 1)"},
         "busca": {"type": "string", "description": "Filtra por texto no título/local"}}}},
    {"name": "agenda_criar", "description": "Cria um compromisso.",
     "input_schema": {"type": "object", "properties": {
         "titulo": {"type": "string"}, "inicio": {"type": "string", "description": "AAAA-MM-DDTHH:MM"},
         "fim": {"type": "string"}, "duracao_min": {"type": "integer"},
         "agenda": {"type": "string", "enum": ["google", "outlook"]}, "local": {"type": "string"},
         "descricao": {"type": "string"}, "dia_inteiro": {"type": "boolean"}},
         "required": ["titulo", "inicio"]}},
    {"name": "agenda_alterar",
     "description": "Muda título, horário ou local de um compromisso (id do agenda_listar). "
                    "Se mudar só o início, a duração é mantida.",
     "input_schema": {"type": "object", "properties": {
         "id": {"type": "string"}, "titulo": {"type": "string"}, "inicio": {"type": "string"},
         "fim": {"type": "string"}, "local": {"type": "string"}}, "required": ["id"]}},
    {"name": "agenda_cancelar", "description": "Apaga um compromisso (confirme antes).",
     "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
]
FUNCOES = {"agenda_listar": listar, "agenda_criar": criar, "agenda_alterar": alterar, "agenda_cancelar": cancelar}
