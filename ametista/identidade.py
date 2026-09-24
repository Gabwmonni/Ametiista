"""Quem está falando? Reconhecimento de voz por "impressão vocal", 100% no seu PC.

Cada pessoa cadastrada tem um nível:
  dono      -> tudo
  familia   -> quase tudo (não desliga o PC, não instala jogos, não mexe na agenda nem vê a tela)
  visitante -> conversa, música, clima, timers

MODO_VOZ no .env:
  restrito -> só atende vozes cadastradas (padrão, depois que houver alguém cadastrado)
  misto    -> desconhecidos são tratados como visitantes
  aberto   -> não verifica voz
"""
import json
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass

import numpy as np

from . import config

ARQUIVO = config.DADOS / "pessoas.json"
NIVEIS = ("dono", "familia", "visitante")

# Ferramentas por nível. O dono pode tudo.
PROIBIDAS_FAMILIA = {
    "pc_sistema", "pc_fechar", "pc_digitar", "pc_ver_tela", "pc_area_transferencia", "pc_janela_ativa",
    "pc_clicar", "pc_teclas", "pc_rolar", "pc_apontar", "steam_instalar",
    "agenda_listar", "agenda_criar", "agenda_alterar", "agenda_cancelar",
    "pessoas_cadastrar", "pessoas_remover", "lembrar_fato", "esquecer_fato",
    "memoria_buscar", "memoria_apagar_conversas", "caderno_guardar", "caderno_buscar", "caderno_listar",
    "caderno_apagar", "arquivos_buscar", "arquivo_abrir", "arquivo_mostrar_na_pasta", "agente_iniciar",
    "tarefa_cancelar", "acoes_listar", "desfazer_acao", "modo_privado", "rotina_criar", "rotina_apagar",
}
PERMITIDAS_VISITANTE = {
    "clima", "noticias", "criar_timer", "web_search", "pc_midia", "pc_volume",
    "spotify_tocar", "spotify_controle", "spotify_volume", "spotify_tocando", "spotify_fila",
    "chamar_modelo_forte",
}

FRASES_CADASTRO = [
    "Ametista, que horas são agora?",
    "Toca uma música animada no Spotify, por favor.",
    "Qual é a previsão do tempo para amanhã de manhã?",
    "Abre o navegador e pesquisa receitas de bolo de cenoura.",
    "Me lembra de ligar para o escritório às três da tarde.",
    "O rato roeu a roupa do rei de Roma e a rainha ficou brava.",
    "Liga a luz da sala e aumenta um pouco o volume.",
]


@dataclass
class Falante:
    nome: str | None
    nivel: str          # dono | familia | visitante | desconhecido
    confianca: float = 1.0

    @property
    def conhecido(self) -> bool:
        return self.nome is not None


DONO_PADRAO = Falante(config.DONO, "dono", 1.0)
VISITANTE = Falante(None, "visitante", 0.0)
# Quem fez o pedido que está sendo atendido agora (vale só dentro da thread do pedido).
# Por segurança, o padrão é o nível mais baixo: quem esquecer de dizer quem é, vira visitante.
falante_atual: ContextVar[Falante] = ContextVar("falante_atual", default=VISITANTE)


def permitido(ferramenta: str, falante: Falante | None = None) -> bool:
    f = falante or falante_atual.get()
    if f.nivel == "dono":
        return True
    if f.nivel == "familia":
        return ferramenta not in PROIBIDAS_FAMILIA
    return ferramenta in PERMITIDAS_VISITANTE


# ------------------------------------------------------------------ cadastro em disco
_trava = threading.Lock()


def _carregar() -> list[dict]:
    if ARQUIVO.exists():
        try:
            return json.loads(ARQUIVO.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return []


def pessoas() -> list[dict]:
    return [{"nome": p["nome"], "nivel": p["nivel"], "amostras": len(p["amostras"])} for p in _carregar()]


def tem_cadastro() -> bool:
    return bool(_carregar())


def salvar_pessoa(nome: str, nivel: str, amostras: list[np.ndarray]) -> None:
    if nivel not in NIVEIS:
        raise ValueError(f"nível inválido: {nivel}")
    with _trava:
        lista = [p for p in _carregar() if p["nome"].lower() != nome.lower()]
        lista.append({"nome": nome, "nivel": nivel, "criado": time.strftime("%Y-%m-%d %H:%M"),
                      "amostras": [a.astype(float).round(6).tolist() for a in amostras]})
        ARQUIVO.write_text(json.dumps(lista, ensure_ascii=False), encoding="utf-8")
    _cache.clear()


def remover_pessoa(nome: str) -> bool:
    with _trava:
        lista = _carregar()
        nova = [p for p in lista if p["nome"].lower() != nome.lower()]
        ARQUIVO.write_text(json.dumps(nova, ensure_ascii=False), encoding="utf-8")
    _cache.clear()
    return len(nova) < len(lista)


def alterar_nivel(nome: str, nivel: str) -> bool:
    with _trava:
        lista = _carregar()
        achou = False
        for p in lista:
            if p["nome"].lower() == nome.lower():
                p["nivel"], achou = nivel, True
        ARQUIVO.write_text(json.dumps(lista, ensure_ascii=False), encoding="utf-8")
    _cache.clear()
    return achou


# ------------------------------------------------------------------ impressão vocal
_extrator = None
_cache: dict = {}


def _modelo():
    global _extrator
    if _extrator is None:
        import sherpa_onnx

        caminho = config.MODELO_VOZ_ID
        if not caminho.exists():
            raise FileNotFoundError(f"Modelo de identificação de voz não encontrado: {caminho}")
        _extrator = sherpa_onnx.SpeakerEmbeddingExtractor(
            sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(caminho), num_threads=2))
    return _extrator


def disponivel() -> bool:
    try:
        _modelo()
        return True
    except Exception:
        return False


def impressao(pcm: bytes) -> np.ndarray:
    """Vetor que representa a voz (normalizado)."""
    audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
    ext = _modelo()
    s = ext.create_stream()
    s.accept_waveform(16000, audio)
    s.input_finished()
    v = np.array(ext.compute(s), dtype=np.float32)
    return v / (np.linalg.norm(v) + 1e-9)


def _centroides() -> list[tuple[str, str, np.ndarray]]:
    if "c" not in _cache:
        lista = []
        for p in _carregar():
            m = np.mean(np.array(p["amostras"], dtype=np.float32), axis=0)
            lista.append((p["nome"], p["nivel"], m / (np.linalg.norm(m) + 1e-9)))
        _cache["c"] = lista
    return _cache["c"]


def identificar(pcm: bytes) -> Falante:
    """Compara a voz com as pessoas cadastradas."""
    modo = config.MODO_VOZ
    if modo == "aberto" or not tem_cadastro():
        return DONO_PADRAO
    try:
        v = impressao(pcm)
    except Exception as e:
        print(f"[identidade] não consegui analisar a voz: {e}")
        return DONO_PADRAO if modo != "restrito" else Falante(None, "desconhecido", 0.0)
    melhor, nota = None, -1.0
    for nome, nivel, c in _centroides():
        s = float(c @ v)
        if s > nota:
            melhor, nota = (nome, nivel), s
    print(f"[identidade] mais parecido: {melhor and melhor[0]} ({nota:.2f})")
    if melhor and nota >= config.LIMIAR_VOZ:
        return Falante(melhor[0], melhor[1], nota)
    if modo == "misto":
        return Falante(None, "visitante", nota)
    return Falante(None, "desconhecido", nota)


# ------------------------------------------------------------------ ferramentas (só o dono usa)
def _cadastrar(nome: str, nivel: str = "familia") -> str:
    from . import eventos

    if nivel not in NIVEIS:
        return f"Nível deve ser um de: {', '.join(NIVEIS)}."
    eventos.publicar({"tipo": "cadastrar", "nome": nome, "nivel": nivel, "interno": True})
    return (f"CADASTRO INICIADO: diga à pessoa ({nome}) que ela vai ler {len(FRASES_CADASTRO)} frases "
            "que vão aparecer na tela, uma de cada vez.")


def _listar() -> str:
    lista = pessoas()
    if not lista:
        return "Ninguém cadastrado ainda: estou atendendo qualquer voz."
    return "; ".join(f"{p['nome']} ({p['nivel']})" for p in lista) + f". Modo: {config.MODO_VOZ}."


def _remover(nome: str) -> str:
    return f"{nome} removido." if remover_pessoa(nome) else f"Não achei {nome}."


def _nivel(nome: str, nivel: str) -> str:
    if nivel not in NIVEIS:
        return f"Nível deve ser um de: {', '.join(NIVEIS)}."
    return f"{nome} agora é {nivel}." if alterar_nivel(nome, nivel) else f"Não achei {nome}."


DEFINICOES = [
    {"name": "pessoas_cadastrar",
     "description": "Começa o cadastro da voz de uma pessoa (ela lê frases na tela). Níveis: dono (tudo), "
                    "familia (quase tudo, sem desligar PC/instalar/agenda/ver tela) e visitante (conversa e música).",
     "input_schema": {"type": "object", "properties": {
         "nome": {"type": "string"}, "nivel": {"type": "string", "enum": list(NIVEIS)}},
         "required": ["nome", "nivel"]}},
    {"name": "pessoas_listar", "description": "Lista as pessoas cujas vozes a Ametista reconhece.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "pessoas_remover", "description": "Apaga a voz cadastrada de uma pessoa.",
     "input_schema": {"type": "object", "properties": {"nome": {"type": "string"}}, "required": ["nome"]}},
    {"name": "pessoas_nivel", "description": "Muda o nível de permissão de uma pessoa cadastrada.",
     "input_schema": {"type": "object", "properties": {
         "nome": {"type": "string"}, "nivel": {"type": "string", "enum": list(NIVEIS)}},
         "required": ["nome", "nivel"]}},
]
PROIBIDAS_FAMILIA |= {"pessoas_nivel"}
FUNCOES = {"pessoas_cadastrar": _cadastrar, "pessoas_listar": _listar,
           "pessoas_remover": _remover, "pessoas_nivel": _nivel}
