"""Ferramentas que a Ametista pode usar, e o caminho único para executá-las.

Toda ferramenta (pedida pela IA, pelo roteador local, por uma rotina ou pelo modo agente) passa por
acoes.executar: permissão de quem pediu, confirmação para ações de risco, registro e desfazer.
"""
import contextvars
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import httpx

from . import acoes, config, memoria

# Pedido em andamento (texto, troca, origem, ficha...) - vale só dentro da thread do pedido.
CONTEXTO: contextvars.ContextVar[dict] = contextvars.ContextVar("contexto_pedido", default={})

# Códigos de tempo do Open-Meteo -> descrição em português
_CODIGOS = {
    0: "céu limpo", 1: "predominantemente limpo", 2: "parcialmente nublado", 3: "nublado",
    45: "neblina", 48: "neblina com geada", 51: "garoa fraca", 53: "garoa", 55: "garoa forte",
    61: "chuva fraca", 63: "chuva", 65: "chuva forte", 66: "chuva congelante", 67: "chuva congelante forte",
    71: "neve fraca", 73: "neve", 75: "neve forte", 80: "pancadas de chuva fracas",
    81: "pancadas de chuva", 82: "pancadas de chuva fortes", 95: "trovoadas",
    96: "trovoadas com granizo", 99: "trovoadas fortes com granizo",
}
DIAS_SEMANA = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}


def falavel(texto: str) -> str:
    """Tira do resultado de uma ferramenta os códigos internos que não devem ser falados."""
    t = re.sub(r"\s*\(id [0-9a-f]{8}\)", "", texto or "")
    t = re.sub(r"\s*\[(?:g|m):[^\]]+\]", "", t)
    return t.strip()


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


def chuva_proximas_horas(horas: int = 2) -> int | None:
    """Maior chance de chuva (%) nas próximas horas (usado pela iniciativa)."""
    r = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=10, params={
        "latitude": config.LATITUDE, "longitude": config.LONGITUDE, "hourly": "precipitation_probability",
        "forecast_hours": max(1, horas), "timezone": "auto"})
    r.raise_for_status()
    valores = [v for v in r.json().get("hourly", {}).get("precipitation_probability", []) if v is not None]
    return max(valores) if valores else None


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


def criar_timer(minutos: float, descricao: str = "Timer") -> str:
    minutos = float(minutos)
    if minutos <= 0 or minutos > 24 * 60:
        return "Erro: o timer precisa ter entre 1 segundo e 24 horas."
    quando = datetime.now() + timedelta(minutes=minutos)
    item = memoria.criar_lembrete(descricao or "Timer", quando, "timer")
    hora = f"{quando:%H:%M:%S}" if minutos < 2 else f"{quando:%H:%M}"
    return f"Timer de {_fmt_duracao(minutos)} criado, toca às {hora}. (id {item['id']})"


def _data_hora(texto: str) -> datetime:
    quando = datetime.fromisoformat(texto.strip())
    if quando.tzinfo:
        quando = quando.astimezone().replace(tzinfo=None)
    return quando


def criar_lembrete(texto: str, data_hora: str) -> str:
    try:
        quando = _data_hora(data_hora)
    except ValueError:
        return "Erro: data_hora deve estar no formato AAAA-MM-DDTHH:MM."
    if quando <= datetime.now():
        return "Erro: esse horário já passou."
    item = memoria.criar_lembrete(texto, quando, "lembrete")
    return f"Lembrete '{texto}' marcado para {quando:%d/%m às %H:%M}. (id {item['id']})"


def _dias_semana(dias: list | str | None) -> list[int]:
    from .cerebro import normalizar

    if not dias:
        return []
    if isinstance(dias, str):
        dias = re.split(r"[,;e ]+", dias)
    saida = []
    for d in dias:
        if isinstance(d, int) or str(d).isdigit():
            saida.append(int(d) % 7)
            continue
        n = normalizar(str(d)).replace("-feira", "").replace(" feira", "").strip()
        for nome, i in DIAS_SEMANA.items():
            if n.startswith(nome[:3]):
                saida.append(i)
    return sorted(set(saida))


def lembrete_recorrente(texto: str, hora: str, frequencia: str, dias_semana: list | None = None,
                        dia_mes: int | None = None, mes: int | None = None) -> str:
    try:
        h = datetime.strptime(hora.strip(), "%H:%M").time()
    except ValueError:
        return "Erro: hora deve estar no formato HH:MM."
    rec: dict = {"tipo": frequencia}
    if frequencia == "semanal":
        rec["dias"] = _dias_semana(dias_semana) or [datetime.now().weekday()]
    elif frequencia == "mensal":
        rec["dia"] = int(dia_mes or datetime.now().day)
    elif frequencia == "anual":
        rec["dia"], rec["mes"] = int(dia_mes or datetime.now().day), int(mes or datetime.now().month)
    elif frequencia not in ("diario", "dias_uteis"):
        return "Erro: frequencia deve ser diario, dias_uteis, semanal, mensal ou anual."
    agora = datetime.now()
    base = datetime.combine(agora.date(), h)
    primeira = memoria.proxima_ocorrencia(rec, base, agora)
    item = memoria.criar_lembrete(texto, primeira, "lembrete", recorrencia=rec)
    return f"Lembrete recorrente criado: {texto}. O próximo é {primeira:%d/%m às %H:%M}. (id {item['id']})"


CONDICOES = {
    "ao_chegar": "quando você chegar (ligar o PC ou voltar para ele)",
    "ao_ligar_pc": "quando você ligar o PC",
    "ao_voltar": "quando você voltar para o PC",
    "proxima_conversa": "na próxima vez que você falar comigo",
    "ao_abrir_programa": "quando você abrir o programa",
    "ao_chegar_casa": "quando você chegar em casa",
}


def lembrete_condicao(texto: str, condicao: str, programa: str = "") -> str:
    if condicao not in CONDICOES:
        return f"Erro: condicao deve ser uma de {', '.join(CONDICOES)}."
    nota = ""
    if condicao == "ao_abrir_programa":
        if not programa.strip():
            return "Erro: diga qual programa."
        cond = f"ao_abrir:{programa.strip()}"
        descricao = f"quando você abrir o {programa.strip()}"
    elif condicao == "ao_chegar_casa" and not (casa_configurada() and config.HA_PESSOA):
        cond, descricao = "ao_chegar", CONDICOES["ao_chegar"]
        nota = " (Sem o Home Assistant com HA_PESSOA eu não sei quando você chega em casa; vou avisar quando " \
               "você ligar o PC ou voltar para ele.)"
    else:
        cond, descricao = condicao, CONDICOES[condicao]
    item = memoria.criar_lembrete(texto, None, "condicao", condicao=cond)
    return f"Combinado: vou te lembrar {descricao}: {texto}.{nota} (id {item['id']})"


def aniversario_adicionar(nome: str, dia: int, mes: int, ano: int | None = None) -> str:
    try:
        date(2000, int(mes), int(dia))
    except ValueError:
        return "Erro: data de aniversário inválida."
    try:
        h = datetime.strptime(config.ANIVERSARIO_HORA, "%H:%M").time()
    except ValueError:
        h = datetime.strptime("09:00", "%H:%M").time()
    agora = datetime.now()
    grupo = f"aniv-{int(agora.timestamp() * 1000)}"
    rec = {"tipo": "anual", "dia": int(dia), "mes": int(mes)}
    if ano:
        rec["ano"] = int(ano)
    base = datetime.combine(agora.date(), h)
    item = memoria.criar_lembrete(f"aniversário de {nome}", memoria.proxima_ocorrencia(rec, base, agora),
                                  "aniversario", recorrencia=rec, grupo=grupo)
    if config.ANIVERSARIO_VESPERA:
        vespera = {**rec, "antes_dias": 1}
        base_v = datetime.combine(agora.date(), datetime.strptime("18:00", "%H:%M").time())
        memoria.criar_lembrete(f"aniversário de {nome}", memoria.proxima_ocorrencia(vespera, base_v, agora),
                               "aniversario_vespera", recorrencia=vespera, grupo=grupo)
    return f"Anotei: o aniversário de {nome} é dia {int(dia)}/{int(mes)}. Aviso no dia" + \
        (" e na véspera." if config.ANIVERSARIO_VESPERA else ".") + f" (id {item['id']})"


def texto_do_alerta(item: dict) -> str:
    """O que ela fala quando um lembrete dispara."""
    tipo, texto = item.get("tipo"), item.get("texto", "")
    if tipo == "timer":
        return "Seu timer acabou!" if texto in ("Timer", "") else f"Tempo esgotado: {texto}"
    if tipo == "aniversario":
        fala = f"Hoje é {texto}!"
        ano = (item.get("recorrencia") or {}).get("ano")
        if ano:
            fala += f" Faz {datetime.now().year - int(ano)} anos."
        return fala
    if tipo == "aniversario_vespera":
        return f"Amanhã é {texto}."
    if tipo == "condicao":
        return f"Você me pediu para lembrar: {texto}"
    fala = f"Lembrete: {texto}"
    if item.get("atraso_min", 0) > 5 and item.get("quando"):
        fala += f" (era para as {datetime.fromisoformat(item['quando']):%H:%M})"
    return fala


def listar_lembretes() -> str:
    itens = memoria.lembretes_pendentes()
    if not itens:
        return "Nenhum lembrete, alarme ou timer pendente."
    linhas = []
    for l in itens:
        if l["tipo"] == "aniversario_vespera":
            continue
        quando = datetime.fromisoformat(l["quando"]).strftime("%d/%m %H:%M") if l.get("quando") else \
            CONDICOES.get((l.get("condicao") or "").split(":")[0], l.get("condicao") or "")
        rec = f" (repete: {l['recorrencia']['tipo']})" if l.get("recorrencia") and l["tipo"] != "aniversario" else ""
        linhas.append(f"[{l['id']}] {l['tipo']}: {l['texto']} — {quando}{rec}")
    return "\n".join(linhas)


def cancelar_lembrete(id: str) -> str:
    return "Cancelado." if memoria.remover_lembrete(id) else "Não encontrei esse id."


# ---------------- Memória ----------------
def memoria_buscar(consulta: str = "", data_inicio: str = "", data_fim: str = "") -> str:
    try:
        ini = datetime.combine(date.fromisoformat(data_inicio), datetime.min.time()) if data_inicio else None
        fim = datetime.combine(date.fromisoformat(data_fim), datetime.min.time()) + timedelta(days=1) \
            if data_fim else (ini + timedelta(days=1) if ini else None)
    except ValueError:
        return "Erro: datas no formato AAAA-MM-DD."
    achados = memoria.buscar_conversas(consulta, ini, fim, limite=12 if not consulta else 8)
    if not achados:
        return "Não achei nada parecido nas conversas guardadas."
    linhas = []
    for t in achados:
        quando = datetime.fromisoformat(t["quando"]).strftime("%d/%m %H:%M")
        linhas.append(f"{quando} {t['quem'] or 'alguém'}: {t['pedido'][:200]} -> {config.NOME}: {t['resposta'][:200]}")
    return "\n".join(linhas)


def caderno_buscar(consulta: str) -> str:
    itens = memoria.caderno_buscar(consulta)
    if not itens:
        return "Nada parecido no caderno."
    return "\n".join(f"[{i['categoria']}] {i['nome']}: {i['detalhes']}" for i in itens)


def caderno_listar(categoria: str = "") -> str:
    itens = memoria.caderno_listar(categoria)
    if not itens:
        return "O caderno está vazio." if not categoria else f"Nada na categoria {categoria}."
    return "\n".join(f"[{i['categoria']}] {i['nome']}: {i['detalhes'][:120]}" for i in itens[:60])


def caderno_apagar(nome: str) -> str:
    n = memoria.caderno_apagar(nome)
    return f"Apaguei {nome} do caderno." if n else f"Não achei {nome} no caderno."


def memoria_apagar_conversas() -> str:
    n = memoria.apagar_conversas()
    return f"Apaguei o histórico de conversas ({n} falas)."


# ---------------- Ações, modos ----------------
def desfazer_acao(id: int | None = None) -> str:
    return acoes.desfazer(int(id)) if id else acoes.desfazer_ultima()


def acoes_listar(quantidade: int = 15) -> str:
    itens = acoes.listar(max(1, min(int(quantidade), 50)))
    if not itens:
        return "Nenhuma ação registrada ainda."
    return "\n".join(f"[{i['id']}] {datetime.fromisoformat(i['quando']):%d/%m %H:%M} {i['descricao']} — "
                     f"{'ok' if i['ok'] else 'falhou'}{' (desfeita)' if i['desfeito'] else ''}"
                     f"{' | pedido: ' + i['motivo'][:80] if i['motivo'] else ''}" for i in itens)


def nao_perturbe(minutos: int = 60) -> str:
    from . import estado

    minutos = int(minutos)
    if minutos <= 0:
        estado.definir_nao_perturbe(None)
        return "Não perturbe desligado."
    ate = datetime.now() + timedelta(minutes=minutos)
    estado.definir_nao_perturbe(ate)
    return f"Não perturbe até as {ate:%H:%M}. Só toco os alarmes que você pediu."


def modo_privado(ligar: bool = True) -> str:
    from . import estado

    estado.definir_privado(bool(ligar))
    if ligar:
        return ("Modo privado ligado: microfone desligado, nada é guardado e eu não puxo assunto. "
                "Para sair, use o ícone perto do relógio ou digite.")
    return "Modo privado desligado."


def diagnostico_ferramenta() -> str:
    from . import diagnostico

    return diagnostico.executar_e_resumir()


def chamar_modelo_forte(motivo: str = "") -> str:
    return "ok"


# ---------------- Home Assistant ----------------
def casa_configurada() -> bool:
    return bool(config.HA_URL and config.HA_TOKEN)


def _ha_headers() -> dict:
    return {"Authorization": f"Bearer {config.HA_TOKEN}", "Content-Type": "application/json"}


def casa_listar(filtro: str = "") -> str:
    if not casa_configurada():
        return "Home Assistant não configurado (preencha HA_URL e HA_TOKEN no painel)."
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


def casa_estado(entity_id: str) -> dict | None:
    if not casa_configurada():
        return None
    r = httpx.get(f"{config.HA_URL}/api/states/{entity_id}", headers=_ha_headers(), timeout=8)
    if r.status_code != 200:
        return None
    e = r.json()
    brilho = e.get("attributes", {}).get("brightness")
    return {"estado": e.get("state"), "brilho": round(brilho * 100 / 255) if brilho else None}


def casa_controlar(entity_id: str, acao: str, brilho: int | None = None, temperatura: float | None = None) -> str:
    if not casa_configurada():
        return "Home Assistant não configurado (preencha HA_URL e HA_TOKEN no painel)."
    dominio = entity_id.split(".", 1)[0]
    servico = {"ligar": "turn_on", "desligar": "turn_off", "alternar": "toggle"}.get(acao, acao)
    if dominio in ("scene", "script"):
        servico = "turn_on"
    dados: dict = {"entity_id": "all" if entity_id.endswith(".all") else entity_id}  # light.all = todas as luzes
    if brilho is not None and dominio == "light" and servico == "turn_on":
        dados["brightness_pct"] = int(brilho)
    if temperatura is not None and dominio == "climate":
        servico, dados["temperature"] = "set_temperature", temperatura
    r = httpx.post(f"{config.HA_URL}/api/services/{dominio}/{servico}", headers=_ha_headers(), json=dados, timeout=10)
    r.raise_for_status()
    return f"Feito: {servico} em {entity_id}."


# ---------------- Definições para o Claude ----------------
def _obj(props: dict, obrig: list | None = None) -> dict:
    d = {"type": "object", "properties": props}
    if obrig:
        d["required"] = obrig
    return d


DEFINICOES = [
    {"name": "clima", "description": f"Tempo atual e previsão em {config.CIDADE}.",
     "input_schema": _obj({"dias": {"type": "integer", "description": "Dias de previsão (1 a 7)."}})},
    {"name": "noticias", "description": "Principais manchetes do dia.",
     "input_schema": _obj({"quantidade": {"type": "integer"}})},
    {"name": "criar_timer", "description": "Cria um timer/contagem regressiva.",
     "input_schema": _obj({"minutos": {"type": "number"}, "descricao": {"type": "string"}}, ["minutos"])},
    {"name": "criar_lembrete", "description": "Lembrete ou alarme para uma data e hora (horário local).",
     "input_schema": _obj({"texto": {"type": "string"},
                           "data_hora": {"type": "string", "description": "AAAA-MM-DDTHH:MM"}}, ["texto", "data_hora"])},
    {"name": "lembrete_recorrente",
     "description": "Lembrete que se repete: todo dia, dias úteis, toda semana (dias escolhidos), todo mês ou todo ano.",
     "input_schema": _obj({"texto": {"type": "string"}, "hora": {"type": "string", "description": "HH:MM"},
                           "frequencia": {"type": "string", "enum": ["diario", "dias_uteis", "semanal", "mensal", "anual"]},
                           "dias_semana": {"type": "array", "items": {"type": "string"},
                                           "description": "Para semanal, ex.: ['segunda', 'quarta']"},
                           "dia_mes": {"type": "integer"}, "mes": {"type": "integer"}},
                          ["texto", "hora", "frequencia"])},
    {"name": "lembrete_condicao",
     "description": "Lembrete que dispara numa situação e não num horário: ao_chegar (quando a pessoa chegar: ligar "
                    "o PC ou voltar para ele), ao_ligar_pc, ao_voltar, proxima_conversa, ao_abrir_programa, "
                    "ao_chegar_casa.",
     "input_schema": _obj({"texto": {"type": "string"},
                           "condicao": {"type": "string", "enum": list(CONDICOES)},
                           "programa": {"type": "string", "description": "Só para ao_abrir_programa"}},
                          ["texto", "condicao"])},
    {"name": "aniversario_adicionar", "description": "Anota um aniversário (avisa todo ano no dia e na véspera).",
     "input_schema": _obj({"nome": {"type": "string"}, "dia": {"type": "integer"}, "mes": {"type": "integer"},
                           "ano": {"type": "integer", "description": "Ano de nascimento, se souber"}},
                          ["nome", "dia", "mes"])},
    {"name": "listar_lembretes", "description": "Lista lembretes, alarmes, timers e aniversários pendentes.",
     "input_schema": _obj({})},
    {"name": "cancelar_lembrete", "description": "Cancela um lembrete pelo id (use listar_lembretes antes).",
     "input_schema": _obj({"id": {"type": "string"}}, ["id"])},
    {"name": "lembrar_fato",
     "description": "Guarda na memória de longo prazo algo duradouro que o dono contou sobre si (preferências, "
                    "pessoas, rotina). Use quando ele pedir para lembrar ou disser algo duradouro.",
     "input_schema": _obj({"fato": {"type": "string"}}, ["fato"])},
    {"name": "esquecer_fato", "description": "Apaga da memória fatos que contenham o trecho informado.",
     "input_schema": _obj({"trecho": {"type": "string"}}, ["trecho"])},
    {"name": "memoria_buscar",
     "description": "Procura nas conversas passadas guardadas. Sem consulta, lista o que foi conversado no período "
                    "(ex.: 'o que eu te pedi ontem?' -> data_inicio = ontem).",
     "input_schema": _obj({"consulta": {"type": "string"},
                           "data_inicio": {"type": "string", "description": "AAAA-MM-DD"},
                           "data_fim": {"type": "string", "description": "AAAA-MM-DD (padrão: o mesmo dia)"}})},
    {"name": "caderno_guardar",
     "description": "Anota no caderno pessoal um projeto, equipamento, arquivo, pessoa, lugar ou conta, com detalhes.",
     "input_schema": _obj({"nome": {"type": "string"}, "detalhes": {"type": "string"},
                           "categoria": {"type": "string", "enum": list(memoria.CATEGORIAS)},
                           "acrescentar": {"type": "boolean", "description": "true = soma aos detalhes que já existem"}},
                          ["nome", "detalhes"])},
    {"name": "caderno_buscar", "description": "Procura no caderno pessoal (por palavras e por significado).",
     "input_schema": _obj({"consulta": {"type": "string"}}, ["consulta"])},
    {"name": "caderno_listar", "description": "Lista o caderno pessoal (opcional: só uma categoria).",
     "input_schema": _obj({"categoria": {"type": "string"}})},
    {"name": "caderno_apagar", "description": "Apaga um item do caderno pelo nome.",
     "input_schema": _obj({"nome": {"type": "string"}}, ["nome"])},
    {"name": "memoria_apagar_conversas", "description": "Apaga TODO o histórico de conversas guardado.",
     "input_schema": _obj({})},
    {"name": "desfazer_acao", "description": "Desfaz uma ação sua (a última que dá para desfazer, ou pelo id).",
     "input_schema": _obj({"id": {"type": "integer"}})},
    {"name": "acoes_listar", "description": "O registro das suas últimas ações (o que fez, quando, por quê, resultado).",
     "input_schema": _obj({"quantidade": {"type": "integer"}})},
    {"name": "nao_perturbe", "description": "Liga o não perturbe por X minutos (0 desliga).",
     "input_schema": _obj({"minutos": {"type": "integer"}}, ["minutos"])},
    {"name": "modo_privado",
     "description": "Liga/desliga o modo privado (desliga microfone, memória e iniciativa de uma vez).",
     "input_schema": _obj({"ligar": {"type": "boolean"}}, ["ligar"])},
    {"name": "diagnostico", "description": "Faz um diagnóstico completo da Ametista (internet, IA, microfone, voz, "
                                           "contas, celular...) e resume o resultado.",
     "input_schema": _obj({})},
    {"name": "casa_listar", "description": "Lista dispositivos da casa (luzes, tomadas, ar...) com entity_id e estado.",
     "input_schema": _obj({"filtro": {"type": "string", "description": "Parte do nome, ex.: 'sala'"}})},
    {"name": "casa_controlar",
     "description": "Liga, desliga ou ajusta um dispositivo da casa. Use casa_listar para descobrir o entity_id.",
     "input_schema": _obj({"entity_id": {"type": "string"},
                           "acao": {"type": "string", "enum": ["ligar", "desligar", "alternar"]},
                           "brilho": {"type": "integer", "description": "0-100, só para luzes"},
                           "temperatura": {"type": "number", "description": "Só para ar-condicionado"}},
                          ["entity_id", "acao"])},
    {"name": "chamar_modelo_forte",
     "description": "Passa o pedido para o seu modo de raciocínio mais forte (pedidos difíceis).",
     "input_schema": _obj({"motivo": {"type": "string"}})},
]

FUNCOES = {
    "clima": clima, "noticias": noticias, "criar_timer": criar_timer, "criar_lembrete": criar_lembrete,
    "lembrete_recorrente": lembrete_recorrente, "lembrete_condicao": lembrete_condicao,
    "aniversario_adicionar": aniversario_adicionar, "listar_lembretes": listar_lembretes,
    "cancelar_lembrete": cancelar_lembrete, "memoria_buscar": memoria_buscar,
    "caderno_guardar": lambda nome, detalhes, categoria="outro", acrescentar=False: memoria.caderno_guardar(
        nome, detalhes, categoria, acrescentar),
    "caderno_buscar": caderno_buscar, "caderno_listar": caderno_listar, "caderno_apagar": caderno_apagar,
    "memoria_apagar_conversas": memoria_apagar_conversas, "desfazer_acao": desfazer_acao,
    "acoes_listar": acoes_listar, "nao_perturbe": nao_perturbe, "modo_privado": modo_privado,
    "diagnostico": diagnostico_ferramenta, "casa_listar": casa_listar, "casa_controlar": casa_controlar,
    "chamar_modelo_forte": chamar_modelo_forte,
}


def _lembrar_fato(fato: str) -> str:
    return memoria.lembrar_fato(fato, CONTEXTO.get().get("troca"))


FUNCOES["lembrar_fato"] = _lembrar_fato
FUNCOES["esquecer_fato"] = memoria.esquecer_fato

# Módulos extras
from . import (agenda, agente, arquivos, arquivos_io, controle, envio, foco, identidade, notas, pc,  # noqa: E402
               rotinas, sistema, spotify, steam)

_SEMPRE = (pc, controle, identidade, steam, arquivos, rotinas, agente, arquivos_io, notas, sistema, envio, foco)
for _m in _SEMPRE:
    DEFINICOES += _m.DEFINICOES
    FUNCOES.update(_m.FUNCOES)
DEFINICOES += spotify.DEFINICOES + agenda.DEFINICOES
FUNCOES.update(spotify.FUNCOES)
FUNCOES.update(agenda.FUNCOES)
_SPOTIFY = {d["name"] for d in spotify.DEFINICOES}
_AGENDA = {d["name"] for d in agenda.DEFINICOES}
_CASA = {"casa_listar", "casa_controlar"}
POR_NOME = {d["name"]: d for d in DEFINICOES}


def _disponivel(nome: str) -> bool:
    if nome in _SPOTIFY:
        return spotify.configurado()
    if nome in _AGENDA:
        return agenda.configurada()
    if nome in _CASA:
        return casa_configurada()
    if nome.startswith("steam_"):
        return steam.disponivel()
    if nome == "arquivo_enviar_celular":
        from . import nuvem

        return nuvem.configurada()
    return True


def definicoes_permitidas(falante=None, forte: bool = False) -> list[dict]:
    """Só as ferramentas que existem neste PC e que a pessoa que está falando pode usar (ordem fixa)."""
    falante = falante or identidade.falante_atual.get()
    saida = [d for d in DEFINICOES if _disponivel(d["name"]) and identidade.permitido(d["name"], falante)
             and not (forte and d["name"] == "chamar_modelo_forte")]
    return sorted(saida, key=lambda d: d["name"])


def executar(nome: str, argumentos: dict, **extra) -> str | list:
    """Devolve texto, ou uma lista de blocos (imagem + texto) para o Claude."""
    funcao = FUNCOES.get(nome)
    if not funcao or not _disponivel(nome):
        return f"Ferramenta desconhecida: {nome}"
    ctx = {**CONTEXTO.get(), **extra}
    resultado = acoes.executar(nome, argumentos or {}, funcao, origem=ctx.get("origem", "pc"),
                               motivo=ctx.get("texto", ""), troca=ctx.get("troca"), grupo=ctx.get("grupo"),
                               automatico=ctx.get("automatico", False),
                               registrar_falha=not ctx.get("sondagem", False))
    if isinstance(resultado, dict) and "imagem_b64" in resultado:
        return [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": resultado["imagem_b64"]}},
            {"type": "text", "text": resultado.get("texto", "")},
        ]
    return str(resultado)
