"""Configurações da Ametista, lidas do arquivo .env.

Cada configuração é descrita uma vez em CAMPOS: é daí que saem os valores usados pelo programa
e também o painel de configuração (web/painel.html), que lê e grava o .env sem você abrir o arquivo.
"""
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parent.parent
# AMETISTA_ENV / AMETISTA_DADOS: usados pelos testes automáticos para não mexer nos seus arquivos
ARQUIVO_ENV = Path(os.environ.get("AMETISTA_ENV") or RAIZ / ".env")
DADOS = Path(os.environ.get("AMETISTA_DADOS") or RAIZ / "dados")
DADOS.mkdir(parents=True, exist_ok=True)

VERDADE = ("1", "true", "sim", "s", "yes", "on")


@dataclass(frozen=True)
class Campo:
    chave: str                     # nome no .env
    padrao: str
    secao: str
    rotulo: str
    ajuda: str = ""
    tipo: str = "texto"            # texto | segredo | numero | bool | opcao | microfone | voz_edge | intervalo
    opcoes: tuple = ()             # para "opcao": ((valor, rótulo), ...)
    atributo: str = ""             # nome em config.X (padrão: igual à chave)
    reiniciar: bool = False        # só vale depois de reiniciar a Ametista
    oculto: bool = False           # não aparece no painel
    conversor: object = field(default=None, compare=False)

    @property
    def nome(self) -> str:
        return self.atributo or self.chave


def _bool(v: str) -> bool:
    return str(v).strip().lower() in VERDADE


def _float(padrao: float):
    def conv(v: str) -> float:
        try:
            return float(str(v).replace(",", "."))
        except ValueError:
            return padrao
    return conv


def _int(padrao: int):
    def conv(v: str) -> int:
        try:
            return int(float(str(v).replace(",", ".")))
        except ValueError:
            return padrao
    return conv


def _caminho(v: str) -> Path:
    p = Path(v)
    return p if p.is_absolute() else RAIZ / p


MODELOS_RAPIDOS = (("claude-haiku-4-5", "Claude Haiku 4.5 (rápido e barato, o melhor para voz)"),
                   ("claude-sonnet-5", "Claude Sonnet 5 (mais esperto, um pouco mais lento)"))
MODELOS_FORTES = (("claude-opus-5", "Claude Opus 5 (recomendado)"),
                  ("claude-sonnet-5", "Claude Sonnet 5 (mais barato)"),
                  ("claude-fable-5-1", "Claude Fable 5.1 (o mais capaz, o mais caro)"))

CAMPOS: list[Campo] = [
    # ------------------------------------------------------------------ Geral
    Campo("AMETISTA_NOME", "Ametista", "Geral", "Nome da assistente", atributo="NOME",
          ajuda="A palavra de ativação continua sendo \"Ametista\"."),
    Campo("AMETISTA_DONO", "Gabriel", "Geral", "Seu nome", atributo="DONO"),
    Campo("CIDADE", "São Paulo", "Geral", "Cidade (clima e notícias)"),
    Campo("LATITUDE", "-23.55", "Geral", "Latitude", tipo="numero", conversor=_float(-23.55)),
    Campo("LONGITUDE", "-46.63", "Geral", "Longitude", tipo="numero", conversor=_float(-46.63)),
    Campo("ATALHO", "ctrl+shift+space", "Geral", "Atalho para chamar", reiniciar=True),
    Campo("ATALHO_PARAR", "ctrl+shift+backspace", "Geral", "Atalho de emergência (parar tudo)",
          ajuda="Cala a Ametista, cancela o que ela estiver fazendo e pausa a música.", reiniciar=True),
    Campo("NOTICIAS_RSS", "https://g1.globo.com/rss/g1/", "Geral", "Feed de notícias (RSS)"),

    # ------------------------------------------------------------------ Cérebro
    Campo("ANTHROPIC_API_KEY", "", "Cérebro", "Chave da API da Anthropic", tipo="segredo",
          ajuda="Crie em console.anthropic.com."),
    Campo("CLAUDE_MODELO", "claude-haiku-4-5", "Cérebro", "Modelo do dia a dia", tipo="opcao",
          opcoes=MODELOS_RAPIDOS, ajuda="Usado na maioria dos pedidos. Tem que ser rápido para a voz."),
    Campo("CLAUDE_MODELO_FORTE", "claude-opus-5", "Cérebro", "Modelo para pedidos difíceis", tipo="opcao",
          opcoes=MODELOS_FORTES, ajuda="Entra em explicações, análises, a tela e o modo agente."),
    Campo("MODELO_AUTOMATICO", "1", "Cérebro", "Escolher o modelo pela dificuldade", tipo="bool",
          conversor=_bool, ajuda="Desligado: usa sempre o modelo do dia a dia."),
    Campo("AGENTE_MODELO", "claude-opus-5", "Cérebro", "Modelo do modo agente", tipo="opcao",
          opcoes=MODELOS_FORTES, ajuda="Faz tarefas grandes e controla o mouse e o teclado."),
    Campo("OLLAMA_URL", "http://localhost:11434", "Cérebro", "Endereço do Ollama (IA local de reserva)"),
    Campo("OLLAMA_MODELO", "qwen2.5:3b", "Cérebro", "Modelo do Ollama"),

    # ------------------------------------------------------------------ Voz
    Campo("VOZ_PROVEDOR", "edge", "Voz", "Voz da Ametista", tipo="opcao",
          opcoes=(("edge", "Vozes prontas da Microsoft (grátis)"), ("elevenlabs", "Voz clonada na ElevenLabs"),
                  ("local", "Voz clonada no próprio PC (XTTS)"))),
    Campo("AMETISTA_VOZ", "pt-BR-FranciscaNeural", "Voz", "Voz pronta", tipo="voz_edge", atributo="VOZ"),
    Campo("VOZ_VELOCIDADE", "+5%", "Voz", "Velocidade da voz pronta", tipo="opcao",
          opcoes=(("-10%", "Mais devagar"), ("+0%", "Normal"), ("+5%", "Um pouco rápida"), ("+15%", "Rápida"))),
    Campo("ELEVENLABS_API_KEY", "", "Voz", "Chave da ElevenLabs", tipo="segredo"),
    Campo("ELEVENLABS_VOZ_ID", "", "Voz", "ID da voz na ElevenLabs",
          ajuda="O clonar_voz.bat preenche sozinho."),
    Campo("ELEVENLABS_MODELO", "eleven_flash_v2_5", "Voz", "Modelo da ElevenLabs", tipo="opcao",
          opcoes=(("eleven_flash_v2_5", "Flash v2.5 (a mais rápida)"),
                  ("eleven_multilingual_v2", "Multilingual v2 (mais natural)"),
                  ("eleven_v3", "v3 (a mais expressiva: risadas, suspiros, pausas)"))),
    Campo("VOZ_EXPRESSIVA", "1", "Voz", "Risadas, suspiros e pausas", tipo="bool", conversor=_bool,
          ajuda="Só funciona com a ElevenLabs v3. Nas outras vozes as marcas são removidas."),

    # ------------------------------------------------------------------ Ouvido
    Campo("OUVIDO_LIGADO", "1", "Ouvido", "Usar o microfone", tipo="bool", conversor=_bool, reiniciar=True),
    Campo("MICROFONE", "", "Ouvido", "Microfone", tipo="microfone", reiniciar=True,
          ajuda="Vazio = o microfone padrão do Windows."),
    Campo("LIMIAR_MIN", "350", "Ouvido", "Sensibilidade", tipo="numero", conversor=_float(350),
          ajuda="Menor = percebe voz mais baixa. Maior = ignora mais barulho (200 a 600)."),
    Campo("WHISPER_MODELO", "small", "Ouvido", "Precisão da transcrição", tipo="opcao", reiniciar=True,
          opcoes=(("base", "Rápida"), ("small", "Equilibrada"), ("medium", "Precisa (precisa de PC forte)"))),
    Campo("WHISPER_DISPOSITIVO", "cpu", "Ouvido", "Transcrever com", tipo="opcao", reiniciar=True,
          opcoes=(("cpu", "Processador"), ("cuda", "Placa NVIDIA (CUDA)"))),
    Campo("TEMPO_SEGUIMENTO", "8", "Ouvido", "Segundos ouvindo depois de responder", tipo="numero",
          conversor=_float(8), ajuda="Nesse tempo você fala sem repetir o nome."),
    Campo("CONVERSA_MINUTOS", "3", "Ouvido", "Minutos de conversa contínua", tipo="numero",
          conversor=_float(3),
          ajuda="Depois disso ela continua atenta, mas só responde o que for claramente para ela. 0 desliga."),
    Campo("INTERROMPER_POR_VOZ", "1", "Ouvido", "Interromper a fala dela pela voz", tipo="bool",
          conversor=_bool, ajuda="Diga \"Ametista\" ou \"para\" enquanto ela fala."),
    Campo("VOSK_MODELO", "modelos/vosk-model-small-pt-0.3", "Ouvido", "Modelo da palavra de ativação",
          conversor=_caminho, oculto=True),

    # ------------------------------------------------------------------ Pessoas
    Campo("MODO_VOZ", "restrito", "Pessoas", "Quem pode falar com ela", tipo="opcao",
          opcoes=(("restrito", "Só vozes cadastradas"), ("misto", "Desconhecidos viram visitantes"),
                  ("aberto", "Qualquer pessoa"))),
    Campo("LIMIAR_VOZ", "0.62", "Pessoas", "Rigor no reconhecimento de voz", tipo="numero",
          conversor=_float(0.62), ajuda="0.55 = mais tolerante, 0.70 = mais exigente."),
    Campo("MODELO_VOZ_ID", "modelos/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx", "Pessoas",
          "Modelo de reconhecimento de voz", conversor=_caminho, oculto=True),

    # ------------------------------------------------------------------ Proatividade
    Campo("PROATIVIDADE", "2", "Proatividade", "Iniciativa da Ametista", tipo="opcao",
          opcoes=(("0", "Desligada: só fala quando chamada"), ("1", "Só o importante (bateria, disco, chuva)"),
                  ("2", "Normal (inclui pausas e resumo do dia)")), conversor=_int(2)),
    Campo("PROATIVO_MAX_HORA", "3", "Proatividade", "No máximo quantos avisos por hora", tipo="numero",
          conversor=_int(3)),
    Campo("PROATIVO_INTERVALO_MIN", "20", "Proatividade", "Minutos mínimos entre dois avisos", tipo="numero",
          conversor=_int(20)),
    Campo("HORARIO_SILENCIO", "22:00-07:00", "Proatividade", "Horário de silêncio", tipo="intervalo",
          ajuda="Nesse horário ela não puxa assunto. Alarmes e lembretes pedidos por você tocam normalmente."),
    Campo("RESUMO_DIARIO", "1", "Proatividade", "Resumo do dia ao ligar o PC", tipo="bool", conversor=_bool),
    Campo("PAUSA_MINUTOS", "120", "Proatividade", "Sugerir pausa depois de quantos minutos no PC",
          tipo="numero", conversor=_int(120), ajuda="0 desliga."),

    # ------------------------------------------------------------------ Memória
    Campo("GUARDAR_CONVERSAS", "1", "Memória", "Guardar o histórico das conversas", tipo="bool",
          conversor=_bool, ajuda="Permite perguntar \"o que eu te pedi ontem?\"."),
    Campo("DIAS_CONVERSAS", "365", "Memória", "Guardar conversas por quantos dias", tipo="numero",
          conversor=_int(365), ajuda="0 = para sempre."),
    Campo("BUSCA_SEMANTICA", "1", "Memória", "Busca por significado", tipo="bool", conversor=_bool,
          ajuda="Acha lembranças mesmo com outras palavras. Roda no PC (baixa uns 220 MB na primeira vez)."),
    Campo("PASTAS_INDICE", "", "Memória", "Pastas extras para ela achar arquivos",
          ajuda="Separe por ponto e vírgula. Área de Trabalho, Documentos e Downloads já entram."),

    # ------------------------------------------------------------------ Agenda e lembretes
    Campo("AGENDA_PADRAO", "google", "Agenda", "Agenda padrão", tipo="opcao",
          opcoes=(("google", "Google Agenda"), ("outlook", "Outlook"))),
    Campo("AVISO_AGENDA_MIN", "10", "Agenda", "Avisar quantos minutos antes", tipo="numero",
          conversor=_int(10), ajuda="0 desliga."),
    Campo("ANIVERSARIO_HORA", "09:00", "Agenda", "Hora do aviso de aniversário"),
    Campo("ANIVERSARIO_VESPERA", "1", "Agenda", "Avisar também na véspera", tipo="bool", conversor=_bool),
    Campo("MS_CLIENT_ID", "", "Agenda", "ID do app do Outlook (Azure)"),
    Campo("FUSO_WINDOWS", "E. South America Standard Time", "Agenda", "Fuso do Windows", oculto=True),

    # ------------------------------------------------------------------ Contas e casa
    Campo("SPOTIFY_CLIENT_ID", "", "Contas", "Client ID do Spotify"),
    Campo("STEAM_PASTA", "", "Contas", "Pasta da Steam", ajuda="Vazio = acha sozinha."),
    Campo("HA_URL", "", "Casa", "Endereço do Home Assistant", ajuda="Ex.: http://192.168.0.10:8123"),
    Campo("HA_TOKEN", "", "Casa", "Token do Home Assistant", tipo="segredo"),
    Campo("HA_PESSOA", "", "Casa", "Você no Home Assistant",
          ajuda="Ex.: person.gabriel. Serve para lembretes \"quando eu chegar em casa\"."),

    # ------------------------------------------------------------------ Celular
    Campo("NUVEM_URL", "", "Celular", "Endereço do app do celular", reiniciar=True,
          ajuda="O publicar_celular.bat preenche sozinho."),
    Campo("NUVEM_CHAVE", "", "Celular", "Chave secreta do PC", tipo="segredo", reiniciar=True),
    Campo("NUVEM_MOSTRAR_JANELA", "1", "Celular", "Mostrar no celular a janela aberta no PC", tipo="bool",
          conversor=_bool),

    # ------------------------------------------------------------------ Avançado
    Campo("PORTA", "8765", "Avançado", "Porta interna", tipo="numero", conversor=_int(8765), reiniciar=True,
          ajuda="Se mudar, atualize também o Redirect URI no painel do Spotify."),
]

POR_CHAVE = {c.chave: c for c in CAMPOS}
_trava = threading.Lock()


def _ler_env() -> dict[str, str]:
    if not ARQUIVO_ENV.exists():
        return {}
    return {k: (v or "") for k, v in dotenv_values(ARQUIVO_ENV).items()}


def _aplicar(valores: dict[str, str]) -> None:
    g = globals()
    for c in CAMPOS:
        # variável de ambiente do sistema tem prioridade (útil em testes e atalhos)
        bruto = os.environ.get(c.chave, valores.get(c.chave, c.padrao))
        bruto = (bruto if bruto is not None else c.padrao).strip()
        if bruto == "" and c.tipo in ("numero", "bool", "opcao") and c.padrao:
            bruto = c.padrao
        g[c.nome] = c.conversor(bruto) if c.conversor else bruto
    g["HA_URL"] = g["HA_URL"].rstrip("/")


def recarregar() -> None:
    """Relê o .env (o painel chama isto depois de salvar)."""
    with _trava:
        _aplicar(_ler_env())


def valor_texto(chave: str) -> str:
    """Valor como está no .env (ou o padrão)."""
    c = POR_CHAVE[chave]
    return os.environ.get(chave, _ler_env().get(chave, c.padrao)) or ""


def _formatar(valor: str) -> str:
    if valor == "" or re.fullmatch(r"[^\s#'\"\\]+(?: [^\s#'\"\\]+)*", valor):
        return valor
    return '"' + valor.replace("\\", "\\\\").replace('"', '\\"') + '"'


def salvar(novos: dict[str, str]) -> list[str]:
    """Grava valores no .env mantendo os comentários. Devolve as chaves que precisam de reinício."""
    reiniciar = []
    with _trava:
        linhas = ARQUIVO_ENV.read_text(encoding="utf-8").splitlines() if ARQUIVO_ENV.exists() else []
        atuais = _ler_env()
        pendentes = {}
        for chave, valor in novos.items():
            if chave not in POR_CHAVE:
                raise KeyError(f"configuração desconhecida: {chave}")
            valor = str(valor).replace("\r", "").replace("\n", " ").strip()
            if atuais.get(chave, POR_CHAVE[chave].padrao) != valor and POR_CHAVE[chave].reiniciar:
                reiniciar.append(chave)
            pendentes[chave] = valor
        for i, linha in enumerate(linhas):
            m = re.match(r"^\s*([A-Z0-9_]+)\s*=", linha)
            if m and m.group(1) in pendentes:
                linhas[i] = f"{m.group(1)}={_formatar(pendentes.pop(m.group(1)))}"
        if pendentes:
            if linhas and linhas[-1].strip():
                linhas.append("")
            linhas.append("# --- ajustado pelo painel de configuração")
            linhas += [f"{k}={_formatar(v)}" for k, v in pendentes.items()]
        ARQUIVO_ENV.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        for chave in novos:
            os.environ.pop(chave, None)  # o .env passa a valer
        _aplicar(_ler_env())
    return reiniciar


def texto_exemplo() -> str:
    """Conteúdo do .env.example, gerado a partir de CAMPOS (assim os dois nunca ficam diferentes)."""
    linhas = ["# ===== Projeto Ametista - configurações =====",
              "# Quase tudo aqui também muda pelo painel: botão direito no ícone da Ametista > Configurações.",
              "# Linhas começando com # são comentários. Chave vazia = usa o padrão.", ""]
    secao = None
    for c in CAMPOS:
        if c.oculto:
            continue
        if c.secao != secao:
            secao = c.secao
            if linhas[-1] != "":
                linhas.append("")
            linhas.append(f"# --- {secao}")
        linhas.append(f"# {c.rotulo}." + (f" {c.ajuda}" if c.ajuda else ""))
        if c.tipo == "bool":
            linhas.append("#   1 = sim, 0 = não")
        elif c.tipo == "opcao" and c.opcoes:
            linhas += [f"#   {valor} = {rotulo}" for valor, rotulo in c.opcoes]
        linhas.append(f"{c.chave}={_formatar(c.padrao)}")
    return "\n".join(linhas) + "\n"


_aplicar(_ler_env())

# ---------------------------------------------------------------- caminhos e constantes derivadas
VOZ_REFERENCIAS = RAIZ / "voz" / "referencia"      # amostras para a voz local (XTTS)
MODELOS = RAIZ / "modelos"
IDENTIDADE_DOC = RAIZ / "IDENTIDADE_DA_AMETISTA.md"
ROTINAS_ARQ = DADOS / "rotinas.json"
