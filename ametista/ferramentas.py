"""Ferramentas que a Ametista pode usar: clima, notícias, lembretes, memória e casa."""
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import httpx

from . import config, memoria

# Códigos de tempo do Open-Meteo -> descrição em português
_CODIGOS = {
    0: "céu limpo", 1: "predominantemente limpo", 2: "parcialmente nublado", 3: "nublado",
    45: "neblina", 48: "neblina com geada", 51: "garoa fraca", 53: "garoa", 55: "garoa forte",
    61: "chuva fraca", 63: "chuva", 65: "chuva forte", 66: "chuva congelante", 67: "chuva congelante forte",
    71: "neve fraca", 73: "neve", 75: "neve forte", 80: "pancadas de chuva fracas",
    81: "pancadas de chuva", 82: "pancadas de chuva fortes", 95: "trovoadas",
    96: "trovoadas com granizo", 99: "trovoadas fortes com granizo",
}


# ---------------- Clima ----------------
def clima(dias: int = 1) -> str:
    dias = max(1, min(int(dias), 7))
    r = httpx.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": config.LATITUDE, "longitude": config.LONGITUDE,
            "current": "temperature_2m,apparent_temperature,weather_code,relative_humidity_2m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            "timezone": "auto", "forecast_days": dias,
        },
        timeout=10,
    )
    r.raise_for_status()
    d = r.json()
    atual = d["current"]
    linhas = [
        f"Agora em {config.CIDADE}: {round(atual['temperature_2m'])}°C "
        f"(sensação {round(atual['apparent_temperature'])}°C), "
        f"{_CODIGOS.get(atual['weather_code'], 'tempo indefinido')}, umidade {atual['relative_humidity_2m']}%."
    ]
    dd = d["daily"]
    for i, dia in enumerate(dd["time"]):
        rotulo = "Hoje" if i == 0 else ("Amanhã" if i == 1 else dia)
        linhas.append(
            f"{rotulo}: mínima {round(dd['temperature_2m_min'][i])}°C, máxima {round(dd['temperature_2m_max'][i])}°C, "
            f"{_CODIGOS.get(dd['weather_code'][i], '')}, chance de chuva {dd['precipitation_probability_max'][i]}%."
        )
    return "\n".join(linhas)


# ---------------- Notícias ----------------
def noticias(quantidade: int = 5) -> str:
    r = httpx.get(config.NOTICIAS_RSS, timeout=10, follow_redirects=True,
                  headers={"User-Agent": "Mozilla/5.0 Ametista"})
    r.raise_for_status()
    raiz = ET.fromstring(r.content)
    titulos = [i.findtext("title", "").strip() for i in raiz.iter("item")]
    titulos = [t for t in titulos if t][: max(1, min(int(quantidade), 10))]
    return "\n".join(f"- {t}" for t in titulos) or "Não encontrei manchetes agora."


# ---------------- Lembretes, alarmes e timers ----------------
def criar_timer(minutos: float, descricao: str = "Timer") -> str:
    quando = datetime.now() + timedelta(minutes=float(minutos))
    memoria.criar_lembrete(descricao or "Timer", quando, "timer")
    return f"Timer de {_fmt_duracao(float(minutos))} criado; toca às {quando:%H:%M:%S}."


def criar_lembrete(texto: str, data_hora: str) -> str:
    try:
        quando = datetime.fromisoformat(data_hora)
    except ValueError:
        return "Erro: data_hora deve estar no formato AAAA-MM-DDTHH:MM."
    if quando.tzinfo:
        quando = quando.astimezone().replace(tzinfo=None)
    if quando <= datetime.now():
        return "Erro: esse horário já passou."
    memoria.criar_lembrete(texto, quando, "lembrete")
    return f"Lembrete '{texto}' marcado para {quando:%d/%m às %H:%M}."


def listar_lembretes() -> str:
    itens = memoria.lembretes_pendentes()
    if not itens:
        return "Nenhum lembrete, alarme ou timer pendente."
    return "\n".join(
        f"[{l['id']}] {l['tipo']}: {l['texto']} — {datetime.fromisoformat(l['quando']):%d/%m %H:%M}" for l in itens
    )


def cancelar_lembrete(id: str) -> str:
    return "Cancelado." if memoria.remover_lembrete(id) else "Não encontrei esse id."


def _fmt_duracao(minutos: float) -> str:
    seg = int(round(minutos * 60))
    h, resto = divmod(seg, 3600)
    m, s = divmod(resto, 60)
    partes = []
    if h:
        partes.append(f"{h} hora{'s' if h > 1 else ''}")
    if m:
        partes.append(f"{m} minuto{'s' if m > 1 else ''}")
    if s:
        partes.append(f"{s} segundo{'s' if s > 1 else ''}")
    return " e ".join(partes) or "0 segundos"


# ---------------- Home Assistant ----------------
def casa_configurada() -> bool:
    return bool(config.HA_URL and config.HA_TOKEN)


def _ha_headers() -> dict:
    return {"Authorization": f"Bearer {config.HA_TOKEN}", "Content-Type": "application/json"}


def casa_listar(filtro: str = "") -> str:
    if not casa_configurada():
        return "Home Assistant não configurado (preencha HA_URL e HA_TOKEN no .env)."
    r = httpx.get(f"{config.HA_URL}/api/states", headers=_ha_headers(), timeout=10)
    r.raise_for_status()
    dominios = ("light.", "switch.", "fan.", "climate.", "cover.", "media_player.", "scene.", "script.")
    linhas = []
    for e in r.json():
        eid = e["entity_id"]
        nome = e.get("attributes", {}).get("friendly_name", eid)
        if not eid.startswith(dominios):
            continue
        if filtro and filtro.lower() not in (eid + " " + nome).lower():
            continue
        linhas.append(f"{eid} | {nome} | {e['state']}")
    return "\n".join(linhas[:60]) or "Nenhum dispositivo encontrado."


def casa_controlar(entity_id: str, acao: str, brilho: int | None = None, temperatura: float | None = None) -> str:
    if not casa_configurada():
        return "Home Assistant não configurado (preencha HA_URL e HA_TOKEN no .env)."
    dominio = entity_id.split(".", 1)[0]
    servico = {"ligar": "turn_on", "desligar": "turn_off", "alternar": "toggle"}.get(acao, acao)
    if dominio in ("scene", "script"):
        servico = "turn_on"
    dados: dict = {"entity_id": entity_id}
    if brilho is not None and dominio == "light":
        dados["brightness_pct"] = int(brilho)
    if temperatura is not None and dominio == "climate":
        servico, dados["temperature"] = "set_temperature", temperatura
    r = httpx.post(f"{config.HA_URL}/api/services/{dominio}/{servico}", headers=_ha_headers(), json=dados, timeout=10)
    r.raise_for_status()
    return f"Feito: {servico} em {entity_id}."


# ---------------- Definições para o Claude ----------------
DEFINICOES = [
    {
        "name": "clima",
        "description": f"Tempo atual e previsão em {config.CIDADE}.",
        "input_schema": {"type": "object", "properties": {
            "dias": {"type": "integer", "description": "Dias de previsão (1 a 7)."}}},
    },
    {
        "name": "noticias",
        "description": "Principais manchetes do dia.",
        "input_schema": {"type": "object", "properties": {"quantidade": {"type": "integer"}}},
    },
    {
        "name": "criar_timer",
        "description": "Cria um timer/contagem regressiva.",
        "input_schema": {"type": "object", "properties": {
            "minutos": {"type": "number"}, "descricao": {"type": "string"}}, "required": ["minutos"]},
    },
    {
        "name": "criar_lembrete",
        "description": "Cria um lembrete ou alarme para uma data e hora (horário local).",
        "input_schema": {"type": "object", "properties": {
            "texto": {"type": "string"},
            "data_hora": {"type": "string", "description": "Formato AAAA-MM-DDTHH:MM"}},
            "required": ["texto", "data_hora"]},
    },
    {
        "name": "listar_lembretes",
        "description": "Lista lembretes, alarmes e timers pendentes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancelar_lembrete",
        "description": "Cancela um lembrete pelo id (use listar_lembretes antes).",
        "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },
    {
        "name": "lembrar_fato",
        "description": "Guarda na memória de longo prazo algo que o dono contou sobre si "
                       "(preferências, pessoas, rotina). Use quando ele pedir para lembrar ou disser algo duradouro.",
        "input_schema": {"type": "object", "properties": {"fato": {"type": "string"}}, "required": ["fato"]},
    },
    {
        "name": "esquecer_fato",
        "description": "Apaga da memória fatos que contenham o trecho informado.",
        "input_schema": {"type": "object", "properties": {"trecho": {"type": "string"}}, "required": ["trecho"]},
    },
    {
        "name": "casa_listar",
        "description": "Lista dispositivos da casa (luzes, tomadas, ar, etc.) com entity_id e estado.",
        "input_schema": {"type": "object", "properties": {
            "filtro": {"type": "string", "description": "Parte do nome, ex.: 'sala'"}}},
    },
    {
        "name": "casa_controlar",
        "description": "Liga, desliga ou ajusta um dispositivo da casa. Use casa_listar para descobrir o entity_id.",
        "input_schema": {"type": "object", "properties": {
            "entity_id": {"type": "string"},
            "acao": {"type": "string", "enum": ["ligar", "desligar", "alternar"]},
            "brilho": {"type": "integer", "description": "0-100, só para luzes"},
            "temperatura": {"type": "number", "description": "Só para ar-condicionado"}},
            "required": ["entity_id", "acao"]},
    },
]

FUNCOES = {
    "clima": clima, "noticias": noticias, "criar_timer": criar_timer, "criar_lembrete": criar_lembrete,
    "listar_lembretes": listar_lembretes, "cancelar_lembrete": cancelar_lembrete,
    "lembrar_fato": memoria.lembrar_fato, "esquecer_fato": memoria.esquecer_fato,
    "casa_listar": casa_listar, "casa_controlar": casa_controlar,
}


# Módulos extras
from . import agenda, identidade, pc, spotify, steam  # noqa: E402

for _m in (pc, identidade, steam):
    DEFINICOES += _m.DEFINICOES
    FUNCOES.update(_m.FUNCOES)
if spotify.configurado():
    DEFINICOES += spotify.DEFINICOES
    FUNCOES.update(spotify.FUNCOES)
if agenda.configurada():
    DEFINICOES += agenda.DEFINICOES
    FUNCOES.update(agenda.FUNCOES)


def definicoes_permitidas() -> list[dict]:
    """Só as ferramentas que a pessoa que está falando pode usar."""
    return [d for d in DEFINICOES if identidade.permitido(d["name"])]


def executar(nome: str, argumentos: dict) -> str | list:
    """Devolve texto, ou uma lista de blocos (texto + imagem) para o Claude."""
    funcao = FUNCOES.get(nome)
    if not funcao:
        return f"Ferramenta desconhecida: {nome}"
    if not identidade.permitido(nome):  # segunda barreira, além de nem oferecer a ferramenta
        quem = identidade.falante_atual.get()
        return f"NEGADO: {quem.nome or 'essa pessoa'} ({quem.nivel}) não tem permissão para isso."
    try:
        resultado = funcao(**argumentos)
    except Exception as e:  # devolve o erro para a IA explicar ao usuário
        return f"Erro ao executar {nome}: {e}"
    if isinstance(resultado, dict) and "imagem_b64" in resultado:
        return [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": resultado["imagem_b64"]}},
            {"type": "text", "text": resultado.get("texto", "")},
        ]
    return str(resultado)
