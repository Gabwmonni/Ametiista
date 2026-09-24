"""Rotinas: vários passos com uma frase ("bom dia", "vou dormir", "modo filme").

Ficam em dados/rotinas.json (editáveis no painel ou por voz: "cria uma rotina modo jogo que abre a Steam e
o Discord e coloca o volume em 40"). Cada passo é um destes:
  {"ferramenta": "pc_volume", "args": {"acao": "definir", "valor": 20}}   qualquer ferramenta da Ametista
  {"falar": "Boa noite!"}                                                 uma frase
  {"resumo": true}                                                        clima, compromissos e lembretes do dia
  {"noticias": 3}                                                         manchetes
  {"amanha": true}                                                        o primeiro compromisso de amanhã
  {"pausar_musica": true}                                                 pausa o Spotify (se estiver tocando)
  {"luzes": "desligar"}                                                   todas as luzes (Home Assistant)
  {"nao_perturbe_ate": "07:00"} ou {"nao_perturbe_min": 180}
  {"esperar": 5}                                                          segundos

Uma rotina pode ter horário ("horario": "07:30", "dias": [0,1,2,3,4] = segunda a sexta). Rodando sozinha,
ela pula as ações críticas (como desligar o PC). Um passo que pede confirmação encerra a rotina com a
pergunta; se você disser "sim", ele é executado.
"""
import json
import re
import threading
import time
import unicodedata
from datetime import date, datetime, timedelta

from . import config

PADRAO = [
    {"nome": "bom dia", "frases": ["bom dia", "modo bom dia", "comecar o dia"],
     "passos": [{"resumo": True}, {"noticias": 3}], "horario": None, "dias": None, "ativa": True},
    {"nome": "vou dormir", "frases": ["vou dormir", "boa noite", "hora de dormir", "modo dormir"],
     "passos": [{"pausar_musica": True}, {"ferramenta": "pc_volume", "args": {"acao": "definir", "valor": 20}},
                {"luzes": "desligar"}, {"nao_perturbe_ate": "07:00"}, {"amanha": True},
                {"falar": "Boa noite, {dono}. Durma bem!"},
                {"ferramenta": "pc_sistema", "args": {"acao": "desligar"}}],
     "horario": None, "dias": None, "ativa": True},
    {"nome": "modo filme", "frases": ["modo filme", "modo cinema", "vamos ver um filme", "hora do filme"],
     "desfazer_com": ["acabou o filme", "fim do filme", "sai do modo filme", "desliga o modo filme"],
     "passos": [{"nao_perturbe_min": 180}, {"luzes": "desligar"},
                {"ferramenta": "pc_volume", "args": {"acao": "definir", "valor": 70}},
                {"falar": "Modo filme ligado. Bom filme!"}],
     "horario": None, "dias": None, "ativa": True},
]
TIPOS_PASSO = {"ferramenta", "falar", "resumo", "noticias", "amanha", "pausar_musica", "luzes", "nao_perturbe_ate",
               "nao_perturbe_min", "esperar"}
PROIBIDAS_EM_ROTINA = {"rotina_executar", "rotina_criar", "rotina_apagar", "agente_iniciar", "chamar_modelo_forte",
                       "memoria_apagar_conversas", "modo_privado"}
_trava = threading.Lock()
_ultimas: dict[str, str] = {}   # rotina agendada -> dia em que rodou


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", t)).strip()


def carregar() -> list[dict]:
    arq = config.ROTINAS_ARQ
    if not arq.exists():
        salvar(PADRAO)
        return json.loads(json.dumps(PADRAO))
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
        return dados if isinstance(dados, list) else PADRAO
    except (OSError, ValueError) as e:
        print(f"[rotinas] arquivo com problema ({e}); usando as rotinas padrão")
        return json.loads(json.dumps(PADRAO))


def salvar(lista: list[dict]) -> None:
    with _trava:
        config.ROTINAS_ARQ.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")


def obter(nome: str) -> dict | None:
    alvo = _norm(nome)
    return next((r for r in carregar() if _norm(r["nome"]) == alvo), None)


def _limpar_frase(t: str) -> str:
    t = _norm(t)
    t = re.sub(rf"\b({_norm(config.NOME)}|ametista|por favor|agora|ai)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def achar_por_frase(texto: str) -> str | None:
    t = _limpar_frase(texto)
    if not t:
        return None
    for r in carregar():
        if not r.get("ativa", True):
            continue
        nome = _norm(r["nome"])
        frases = {_norm(f) for f in r.get("frases", [])} | {nome}
        if t in frases or re.fullmatch(rf"(ativa|ative|roda|rode|executa|execute|liga|inicia)( a rotina| o)? {re.escape(nome)}", t):
            return r["nome"]
    return None


def achar_desfazer(texto: str) -> str | None:
    t = _limpar_frase(texto)
    for r in carregar():
        if t and t in {_norm(f) for f in r.get("desfazer_com", [])}:
            return r["nome"]
    return None


# ====================================================================== validação
def validar_passos(passos: list) -> list[dict]:
    from . import ferramentas

    if not isinstance(passos, list) or not passos:
        raise ValueError("a rotina precisa de pelo menos um passo")
    saida = []
    for p in passos:
        if not isinstance(p, dict):
            raise ValueError(f"passo inválido: {p}")
        chaves = set(p) - {"args"}
        if len(chaves) != 1 or not chaves <= TIPOS_PASSO:
            raise ValueError(f"passo inválido: {json.dumps(p, ensure_ascii=False)}")
        if "ferramenta" in p:
            nome = p["ferramenta"]
            if nome not in ferramentas.FUNCOES or nome in PROIBIDAS_EM_ROTINA:
                raise ValueError(f"ferramenta não permitida em rotina: {nome}")
            if not isinstance(p.get("args", {}), dict):
                raise ValueError(f"args de {nome} precisa ser um objeto")
        if "nao_perturbe_ate" in p:
            datetime.strptime(p["nao_perturbe_ate"], "%H:%M")
        saida.append(p)
    return saida


# ====================================================================== execução
def _passo(p: dict, falas: list[str], grupo: str | None, automatico: bool) -> str | None:
    """Executa um passo. Devolve a pergunta se ele precisar de confirmação."""
    from . import acoes, ferramentas, proatividade, spotify

    if "falar" in p:
        falas.append(str(p["falar"]).replace("{dono}", config.DONO).replace("{nome}", config.NOME))
    elif "resumo" in p:
        falas.append(proatividade.resumo_do_dia())
    elif "noticias" in p:
        try:
            titulos = ferramentas.noticias(int(p["noticias"] or 3)).split("\n")
            falas.append("As manchetes: " + "; ".join(t.lstrip("- ") for t in titulos) + ".")
        except Exception:
            pass
    elif "amanha" in p:
        falas.append(_amanha())
    elif "pausar_musica" in p:
        if spotify.conectado():
            try:
                atual = spotify.cliente().current_playback()
                if atual and atual.get("is_playing"):
                    ferramentas.executar("spotify_controle", {"acao": "pausar"}, grupo=grupo, automatico=automatico)
            except Exception as e:
                print(f"[rotinas] não pausei a música: {e}")
    elif "luzes" in p:
        if ferramentas.casa_configurada():
            ferramentas.executar("casa_controlar", {"entity_id": "light.all",
                                                    "acao": "ligar" if p["luzes"] == "ligar" else "desligar"},
                                 grupo=grupo, automatico=automatico)
    elif "nao_perturbe_ate" in p:
        h = datetime.strptime(p["nao_perturbe_ate"], "%H:%M").time()
        agora = datetime.now()
        alvo = datetime.combine(agora.date(), h)
        if alvo <= agora:
            alvo += timedelta(days=1)
        ferramentas.executar("nao_perturbe", {"minutos": int((alvo - agora).total_seconds() // 60) + 1},
                             grupo=grupo, automatico=automatico)
    elif "nao_perturbe_min" in p:
        ferramentas.executar("nao_perturbe", {"minutos": int(p["nao_perturbe_min"])}, grupo=grupo,
                             automatico=automatico)
    elif "esperar" in p:
        time.sleep(max(0, min(float(p["esperar"]), 60)))
    elif "ferramenta" in p:
        r = ferramentas.executar(p["ferramenta"], dict(p.get("args") or {}), grupo=grupo, automatico=automatico)
        if isinstance(r, str) and r.startswith("PRECISA CONFIRMAR"):
            pend = acoes.pendente()
            return pend["pergunta"] if pend else "Confirma?"
    return None


def _amanha() -> str:
    from . import agenda

    try:
        if not (agenda.google_conectado() or agenda.outlook_conectado()):
            return ""
        amanha = date.today() + timedelta(days=1)
        ini = datetime.combine(amanha, datetime.min.time()).astimezone()
        eventos_, _ = agenda.todos_eventos(ini, ini + timedelta(days=1))
        if not eventos_:
            return "Amanhã sua agenda está livre."
        e = eventos_[0]
        quando = "o dia inteiro" if e["dia_inteiro"] else f"às {e['inicio']:%H:%M}"
        return f"Amanhã o primeiro compromisso é {e['titulo']}, {quando}."
    except Exception:
        return ""


def executar(nome: str, _grupo: str | None = None, automatico: bool = False) -> str:
    from .ferramentas import CONTEXTO

    r = obter(nome)
    if not r:
        return f"Não achei a rotina {nome}."
    automatico = automatico or bool(CONTEXTO.get().get("automatico"))
    falas: list[str] = []
    for p in r.get("passos", []):
        try:
            pergunta = _passo(p, falas, _grupo, automatico)
        except Exception as e:
            print(f"[rotinas] passo falhou ({p}): {e}")
            continue
        if pergunta:
            falas.append(pergunta)
            break
    texto = " ".join(f for f in falas if f).strip()
    return texto or f"Rotina {r['nome']} pronta."


def iniciar_agendador() -> None:
    """Roda as rotinas com horário (sem ações críticas)."""
    def loop():
        while True:
            try:
                agendadas()
            except Exception as e:
                print(f"[rotinas] agendador: {e}")
            time.sleep(20)
    threading.Thread(target=loop, daemon=True, name="rotinas").start()


def agendadas(agora: datetime | None = None) -> list[str]:
    from . import avisos, estado, ferramentas

    agora = agora or datetime.now()
    rodadas = []
    for r in carregar():
        if not r.get("ativa", True) or not r.get("horario"):
            continue
        try:
            h = datetime.strptime(r["horario"], "%H:%M")
        except ValueError:
            continue
        dias = r.get("dias")
        if dias and agora.weekday() not in dias:
            continue
        chave = f"{r['nome']}|{agora.date().isoformat()}"
        if _ultimas.get(r["nome"]) == chave or estado.privado():
            continue
        if (agora.hour, agora.minute) == (h.hour, h.minute):
            _ultimas[r["nome"]] = chave
            from .identidade import DONO_PADRAO, falante_atual

            falante_atual.set(DONO_PADRAO)
            token = ferramentas.CONTEXTO.set({"texto": f"rotina agendada: {r['nome']}", "origem": "rotina",
                                               "automatico": True})
            try:
                fala = ferramentas.executar("rotina_executar", {"nome": r["nome"]})
            finally:
                ferramentas.CONTEXTO.reset(token)
            if isinstance(fala, str) and fala and not fala.startswith(("NEGADO", "Erro")):
                avisos.proativo(ferramentas.falavel(fala), "feliz")
            rodadas.append(r["nome"])
    return rodadas


# ====================================================================== ferramentas
def criar(nome: str, passos: list, frases: list | None = None, horario: str | None = None,
          dias: list | None = None) -> str:
    from .ferramentas import _dias_semana

    nome = nome.strip()
    if not nome:
        return "Erro: faltou o nome da rotina."
    try:
        passos = validar_passos(passos)
        if horario:
            datetime.strptime(horario, "%H:%M")
    except ValueError as e:
        return f"Erro: {e}"
    lista = [r for r in carregar() if _norm(r["nome"]) != _norm(nome)]
    lista.append({"nome": nome, "frases": [f for f in (frases or []) if f], "passos": passos,
                  "horario": horario or None, "dias": _dias_semana(dias) or None, "ativa": True})
    salvar(lista)
    quando = f" Ela roda sozinha às {horario}." if horario else ""
    return f"Rotina {nome} criada com {len(passos)} passos.{quando}"


def listar() -> str:
    lista = carregar()
    if not lista:
        return "Nenhuma rotina."
    linhas = []
    for r in lista:
        frases = ", ".join(r.get("frases", [])[:3])
        hor = f", às {r['horario']}" if r.get("horario") else ""
        linhas.append(f"{r['nome']} ({len(r.get('passos', []))} passos{hor}; frases: {frases})")
    return "\n".join(linhas)


def apagar(nome: str) -> str:
    lista = carregar()
    nova = [r for r in lista if _norm(r["nome"]) != _norm(nome)]
    if len(nova) == len(lista):
        return f"Não achei a rotina {nome}."
    salvar(nova)
    return f"Rotina {nome} apagada."


DEFINICOES = [
    {"name": "rotina_executar", "description": "Executa uma rotina pelo nome (ex.: 'bom dia', 'vou dormir').",
     "input_schema": {"type": "object", "properties": {"nome": {"type": "string"}}, "required": ["nome"]}},
    {"name": "rotina_criar",
     "description": "Cria ou substitui uma rotina. Passos possíveis: {\"ferramenta\": nome, \"args\": {...}} "
                    "(qualquer ferramenta sua), {\"falar\": texto}, {\"resumo\": true}, {\"noticias\": 3}, "
                    "{\"amanha\": true}, {\"pausar_musica\": true}, {\"luzes\": \"desligar\"}, "
                    "{\"nao_perturbe_min\": 60}, {\"nao_perturbe_ate\": \"07:00\"}, {\"esperar\": 5}.",
     "input_schema": {"type": "object", "properties": {
         "nome": {"type": "string"},
         "passos": {"type": "array", "items": {"type": "object"}},
         "frases": {"type": "array", "items": {"type": "string"}, "description": "Frases que disparam a rotina"},
         "horario": {"type": "string", "description": "HH:MM para rodar sozinha (opcional)"},
         "dias": {"type": "array", "items": {"type": "string"}, "description": "Dias da semana (opcional)"}},
         "required": ["nome", "passos"]}},
    {"name": "rotina_listar", "description": "Lista as rotinas.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "rotina_apagar", "description": "Apaga uma rotina.",
     "input_schema": {"type": "object", "properties": {"nome": {"type": "string"}}, "required": ["nome"]}},
]
FUNCOES = {"rotina_executar": executar, "rotina_criar": criar, "rotina_listar": listar, "rotina_apagar": apagar}
