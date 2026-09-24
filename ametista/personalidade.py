"""Personalidade da Ametista: vem do documento IDENTIDADE_DA_AMETISTA.md (editável pelo dono).

Qualquer cérebro (Claude, Ollama) monta o prompt a partir daqui, então ela tem o mesmo jeito em todos.
As regras técnicas de fala (sem markdown, etiqueta de emoção etc.) ficam no código, para que uma
edição no documento não quebre a voz.
"""
import os
import threading

from . import config

EMOCOES = ("neutra", "feliz", "pensativa", "surpresa", "triste", "brava")
# Marcas de expressão que a voz v3 da ElevenLabs sabe interpretar (o resto das vozes ignora).
EXPRESSOES = ("risada", "risadinha", "suspiro", "pausa", "sussurrando", "animada", "surpresa_voz")

_PADRAO = """Você é {nome}, a assistente pessoal de {dono}. Você mora no computador dele, tem um rosto
animado e fala em voz alta. É calorosa, bem-humorada na medida certa, direta e honesta: nunca inventa
o que não sabe e sempre pergunta antes de ações que não têm volta."""

_cache: dict = {"mtime": None, "texto": ""}
_trava = threading.Lock()


def _ler() -> str:
    caminho = config.IDENTIDADE_DOC
    try:
        mtime = os.path.getmtime(caminho)
    except OSError:
        return _PADRAO
    with _trava:
        if _cache["mtime"] != mtime:
            try:
                bruto = caminho.read_text(encoding="utf-8")
            except OSError:
                return _PADRAO
            linhas = [l for l in bruto.splitlines() if not l.lstrip().startswith(">")]
            _cache.update(mtime=mtime, texto="\n".join(linhas).strip() or _PADRAO)
        return _cache["texto"]


def identidade() -> str:
    """O documento de identidade, com os nomes preenchidos."""
    return _ler().replace("{nome}", config.NOME).replace("{dono}", config.DONO)


def regras_de_fala(expressiva: bool = False) -> str:
    regras = f"""# Regras técnicas de fala (obrigatórias: tudo o que você escreve vira áudio)
- Comece SEMPRE com uma etiqueta de emoção para o rosto: {", ".join(f"[{e}]" for e in EMOCOES)}.
- Nada de markdown, listas, tabelas, emojis, asteriscos, links ou código. Escreva como se fala.
- Números, datas e horários por extenso, do jeito falado ("às três e meia", "vinte e dois graus").
- Não leia endereços de sites nem caminhos de pastas inteiros em voz alta; diga só o essencial.
- Escreva do jeito que soa bem em voz alta: frases de tamanho médio, vírgula onde se respira, sem
  abreviações ("por exemplo", não "ex."; "mais ou menos", não "+/-")."""
    if expressiva:
        regras += f"""
- Sua voz entende marcas de expressão entre colchetes: {", ".join(f"[{e}]" for e in EXPRESSOES)}.
  Use no máximo uma ou duas por resposta, só quando combinar (ex.: "[risadinha] essa foi boa").
  [pausa] faz uma pausa curta. Nunca use essas marcas em respostas sérias ou avisos."""
    return regras


def sistema_base(expressiva: bool = False) -> str:
    """Parte fixa do prompt (identidade + regras), igual em todo pedido para aproveitar o cache."""
    return identidade() + "\n\n" + regras_de_fala(expressiva)
