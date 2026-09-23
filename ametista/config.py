"""Configurações da Ametista, lidas do arquivo .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

DADOS = RAIZ / "dados"
DADOS.mkdir(exist_ok=True)


def _env(nome: str, padrao: str = "") -> str:
    return os.getenv(nome, padrao).strip()


# --- Identidade ---
NOME = _env("AMETISTA_NOME", "Ametista")
DONO = _env("AMETISTA_DONO", "Gabriel")

# --- Cérebro na nuvem (Claude) ---
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
CLAUDE_MODELO = _env("CLAUDE_MODELO", "claude-haiku-4-5")

# --- Cérebro local (Ollama) ---
OLLAMA_URL = _env("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODELO = _env("OLLAMA_MODELO", "qwen2.5:3b")

# --- Voz (fala) ---
VOZ_PROVEDOR = _env("VOZ_PROVEDOR", "edge")                # edge | elevenlabs | local
VOZ = _env("AMETISTA_VOZ", "pt-BR-FranciscaNeural")        # voz do edge (reserva)
ELEVENLABS_API_KEY = _env("ELEVENLABS_API_KEY")
ELEVENLABS_VOZ_ID = _env("ELEVENLABS_VOZ_ID")
ELEVENLABS_MODELO = _env("ELEVENLABS_MODELO", "eleven_flash_v2_5")  # flash = rápido; multilingual_v2 = mais expressivo
VOZ_REFERENCIAS = RAIZ / "voz" / "referencia"              # amostras para a voz local (XTTS)

# --- Ouvido (escuta offline) ---
OUVIDO_LIGADO = _env("OUVIDO_LIGADO", "1") == "1"
VOSK_MODELO = RAIZ / _env("VOSK_MODELO", "modelos/vosk-model-small-pt-0.3")
WHISPER_MODELO = _env("WHISPER_MODELO", "small")          # tiny, base, small, medium
WHISPER_DISPOSITIVO = _env("WHISPER_DISPOSITIVO", "cpu")   # cpu ou cuda (placa NVIDIA)
MICROFONE = _env("MICROFONE")                              # vazio = padrão do Windows
LIMIAR_MIN = float(_env("LIMIAR_MIN", "350"))              # sensibilidade: menor = mais sensível
TEMPO_SEGUIMENTO = float(_env("TEMPO_SEGUIMENTO", "6"))

# --- Quem pode falar com ela (reconhecimento de voz) ---
MODO_VOZ = _env("MODO_VOZ", "restrito")                    # restrito | misto | aberto
LIMIAR_VOZ = float(_env("LIMIAR_VOZ", "0.62"))             # maior = mais exigente
MODELO_VOZ_ID = RAIZ / _env("MODELO_VOZ_ID", "modelos/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx")

# --- Sobreposição ---
ATALHO = _env("ATALHO", "ctrl+shift+space")

# --- Clima ---
CIDADE = _env("CIDADE", "São Paulo")
LATITUDE = float(_env("LATITUDE", "-23.55"))
LONGITUDE = float(_env("LONGITUDE", "-46.63"))

# --- Notícias (RSS) ---
NOTICIAS_RSS = _env("NOTICIAS_RSS", "https://g1.globo.com/rss/g1/")

# --- Spotify ---
SPOTIFY_CLIENT_ID = _env("SPOTIFY_CLIENT_ID")

# --- Steam ---
STEAM_PASTA = _env("STEAM_PASTA")                          # vazio = descobre sozinha

# --- Agenda ---
MS_CLIENT_ID = _env("MS_CLIENT_ID")                        # app do Azure para o Outlook
AGENDA_PADRAO = _env("AGENDA_PADRAO", "google")            # google ou outlook
AVISO_AGENDA_MIN = int(_env("AVISO_AGENDA_MIN", "10"))     # avisa X minutos antes (0 = não avisa)
FUSO_WINDOWS = _env("FUSO_WINDOWS", "E. South America Standard Time")  # fuso de Brasília

# --- Celular (app + ponte na Cloudflare) ---
NUVEM_URL = _env("NUVEM_URL")                              # ex.: https://ametista.seu-usuario.workers.dev
NUVEM_CHAVE = _env("NUVEM_CHAVE")                          # segredo compartilhado com o Worker
NUVEM_MOSTRAR_JANELA = _env("NUVEM_MOSTRAR_JANELA", "1") == "1"  # mostra no celular a janela aberta no PC

# --- Home Assistant ---
HA_URL = _env("HA_URL").rstrip("/")
HA_TOKEN = _env("HA_TOKEN")

# --- Servidor ---
PORTA = int(_env("PORTA", "8765"))
