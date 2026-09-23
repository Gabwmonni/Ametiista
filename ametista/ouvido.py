"""Ouvido da Ametista: escuta o microfone o tempo todo, 100% no seu PC.

Etapas:
  1. ESPERA      Vosk (leve, offline) procura a palavra "Ametista".
  2. GRAVANDO    Ao ouvir o nome, grava o pedido até você parar de falar.
  3. PROCESSANDO faster-whisper transcreve com precisão e confirma que o nome foi dito.
  4. FALANDO     Enquanto ela responde, o microfone é ignorado (para não ouvir a si mesma).
  5. SEGUIMENTO  Depois da resposta, ouve por alguns segundos sem precisar do nome.
"""
import json
import re
import threading
import time
import unicodedata
from collections import deque

import numpy as np

from . import config, eventos, identidade

TAXA = 16000
AMOSTRAS = 1280                 # 80 ms por bloco
DUR = AMOSTRAS / TAXA
PREROLL = 20                    # 1,6 s de áudio antes do gatilho (inclui o próprio nome)
SILENCIO_FIM = 0.9              # segundos de silêncio que encerram o pedido
MAX_PEDIDO = 14
ESPERA_SEM_FALA = 5
SEGURANCA_FALA = 60             # se a tela não avisar que terminou de falar

NOME_VOSK = re.compile(r"\bametista\b")
NOME = re.compile(r"\b(?:o\s+|oi\s+|ei\s+|e\s+ai\s+)?(?:a\s?m[ei]t[ií]st?[ae]s?|ametist\w*|metista)\b[\s,.!?:]*", re.I)
ALUCINACOES = re.compile(
    r"^(obrigad[oa]\.?|tchau\.?|legendas?.*|.*amara\.org.*|inscreva-se.*|\.+|\s*)$", re.I)


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def tirar_nome(texto: str) -> tuple[str, bool]:
    """Remove "Ametista" do começo do pedido. Devolve (resto, achou_nome)."""
    m = NOME.search(_sem_acento(texto))
    if not m:
        return texto.strip(), False
    # só aceita o nome no começo da frase (até 2 palavras antes, ex.: "Ô Ametista")
    if len(texto[: m.start()].split()) > 2:
        return texto.strip(), True
    return texto[m.end():].strip(" ,.!?:"), True


_instancia: "Ouvido | None" = None
_whisper_avulso = None
_trava_avulso = threading.Lock()


def transcrever_bytes(dados: bytes) -> str:
    """Transcreve um arquivo de áudio qualquer (ex.: gravação do celular)."""
    import io

    from faster_whisper.audio import decode_audio

    audio = decode_audio(io.BytesIO(dados), sampling_rate=TAXA)
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
    if _instancia is not None and _instancia._whisper_pronto.is_set():
        return _instancia.transcrever(pcm)
    global _whisper_avulso
    with _trava_avulso:
        if _whisper_avulso is None:
            from faster_whisper import WhisperModel

            _whisper_avulso = WhisperModel(config.WHISPER_MODELO, device="cpu", compute_type="int8")
    segs, _ = _whisper_avulso.transcribe(audio, language="pt", beam_size=1,
                                         initial_prompt=f"{config.NOME}, abre a Steam, toca no Spotify.")
    return "".join(s.text for s in segs).strip()


class Ouvido:
    def __init__(self, atender=None):
        global _instancia
        from . import nucleo

        _instancia = self

        self.atender = atender or nucleo.atender
        self.estado = "espera"
        self.mudo = False
        self.relogio = 0.0                      # tempo em segundos, contado pelo áudio
        self.pre: deque[bytes] = deque(maxlen=PREROLL)
        self.ruido = 150.0
        self._vosk = None
        self._whisper = None
        self._whisper_pronto = threading.Event()
        self._apos_fala = "espera"
        self._falando_desde = 0.0
        self._ultimo_mic = 0.0
        self._cadastro: dict | None = None
        self._cadastro_pendente: dict | None = None
        self._reset_gravacao("", [])
        eventos.ouvir(self._evento)

    # ------------------------------------------------------------ modelos
    def carregar_modelos(self) -> None:
        import vosk

        vosk.SetLogLevel(-1)
        caminho = config.VOSK_MODELO
        if not caminho.exists():
            raise FileNotFoundError(f"Modelo Vosk não encontrado em {caminho}. Rode instalar.bat.")
        self._vosk = vosk.KaldiRecognizer(vosk.Model(str(caminho)), TAXA)
        threading.Thread(target=self._carregar_whisper, daemon=True).start()

    def _carregar_whisper(self) -> None:
        from faster_whisper import WhisperModel

        t = time.time()
        dispositivo = config.WHISPER_DISPOSITIVO
        try:
            self._whisper = WhisperModel(config.WHISPER_MODELO, device=dispositivo,
                                         compute_type="int8" if dispositivo == "cpu" else "default")
        except Exception as e:  # GPU sem CUDA etc.
            print(f"[ouvido] Whisper em {dispositivo} falhou ({e}); usando CPU")
            self._whisper = WhisperModel(config.WHISPER_MODELO, device="cpu", compute_type="int8")
        print(f"[ouvido] Whisper '{config.WHISPER_MODELO}' pronto em {time.time() - t:.1f}s")
        self._whisper_pronto.set()

    def transcrever(self, pcm: bytes) -> str:
        self._whisper_pronto.wait()
        audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
        segmentos, _ = self._whisper.transcribe(
            audio, language="pt", beam_size=1, condition_on_previous_text=False,
            initial_prompt=f"{config.NOME}, abre a Steam, toca no Spotify, abre o YouTube, "
                           "o que tem na minha agenda amanhã? Que horas são?",
        )
        return "".join(s.text for s in segmentos).strip()

    # ------------------------------------------------------------ eventos externos
    def _evento(self, msg: dict) -> None:
        tipo = msg.get("tipo")
        if tipo in ("resposta", "alerta"):
            self._apos_fala = "seguimento" if tipo == "resposta" else "espera"
            self.estado, self._falando_desde = "falando", self.relogio
        elif tipo == "fala_terminou" and self.estado == "falando":
            self._depois_de_falar()
        elif tipo == "chamar":
            self.ativar_manual()
        elif tipo == "cancelar_escuta":
            self._cadastro = None
            if self.estado in ("gravando", "seguimento"):
                self.estado = "espera"
        elif tipo == "cadastrar":
            pedido = {"nome": msg["nome"], "nivel": msg.get("nivel", "familia")}
            if self.estado in ("espera", "seguimento"):
                self._iniciar_cadastro(pedido)
            else:  # está falando/processando: começa assim que terminar
                self._cadastro_pendente = pedido
        elif tipo == "mudo":
            self.mudo = bool(msg.get("valor"))
            if self.mudo:
                self.estado = "espera"

    def _depois_de_falar(self) -> None:
        if self._vosk:
            self._vosk.Reset()
        if self._cadastro_pendente:
            pedido, self._cadastro_pendente = self._cadastro_pendente, None
            self._iniciar_cadastro(pedido)
            return
        if self._apos_fala == "seguimento":
            self.estado, self._seg_desde, self._seg_fala = "seguimento", self.relogio, 0
            eventos.publicar({"tipo": "ouvindo", "seguimento": True})
        else:
            self.estado = "espera"
            eventos.publicar({"tipo": "ocioso"})

    def ativar_manual(self) -> None:
        if self.mudo:
            eventos.publicar({"tipo": "aviso", "texto": "O microfone está desligado na bandeja."})
            return
        self._iniciar_gravacao("manual", [])

    # ------------------------------------------------------------ cadastro de voz
    def _iniciar_cadastro(self, pedido: dict) -> None:
        if not identidade.disponivel():
            eventos.publicar({"tipo": "aviso", "texto": "Modelo de identificação de voz não instalado (rode o instalar.bat)."})
            return
        self._cadastro = {**pedido, "amostras": [], "tentativas": 0}
        self._proxima_frase()

    def _proxima_frase(self) -> None:
        c = self._cadastro
        i = len(c["amostras"])
        total = len(identidade.FRASES_CADASTRO)
        eventos.publicar({"tipo": "cadastro", "nome": c["nome"], "passo": i + 1, "total": total,
                          "frase": identidade.FRASES_CADASTRO[i]})
        self._reset_gravacao("cadastro", [])
        self.estado = "gravando"

    def _processar_cadastro(self, pcm: bytes, falou: bool) -> None:
        c = self._cadastro
        if c is None:
            self.estado = "espera"
            return
        if not falou or len(pcm) < 16000 * 2 * 1.0:  # menos de 1 s de fala
            c["tentativas"] += 1
            if c["tentativas"] > 2:
                self._cadastro = None
                self.estado = "espera"
                eventos.publicar({"tipo": "aviso", "texto": "Cadastro de voz cancelado: não ouvi ninguém lendo."})
                return
            self._proxima_frase()
            return
        c["tentativas"] = 0
        c["amostras"].append(identidade.impressao(pcm))
        if len(c["amostras"]) < len(identidade.FRASES_CADASTRO):
            self._proxima_frase()
            return
        # Terminou: descarta amostras muito diferentes (tosse, barulho, outra pessoa falando junto)
        amostras = np.array(c["amostras"])
        centro = amostras.mean(0)
        centro /= np.linalg.norm(centro)
        boas = [a for a in amostras if float(a @ centro) >= 0.55] or list(amostras)
        identidade.salvar_pessoa(c["nome"], c["nivel"], boas)
        self._cadastro = None
        self._falar_aviso(f"Pronto, {c['nome']}! Agora eu reconheço a sua voz.", "feliz")

    def _falar_aviso(self, texto: str, emocao: str = "neutra") -> None:
        import asyncio

        from . import voz

        eventos.publicar({"tipo": "resposta", "texto": texto, "emocao": emocao, "origem": "local",
                          "audio": asyncio.run(voz.sintetizar(texto))})

    # ------------------------------------------------------------ fluxo de áudio
    def _reset_gravacao(self, origem: str, preroll: list[bytes]) -> None:
        self.origem = origem
        self.audio = list(preroll)
        self.duracao = 0.0
        self.silencio = 0.0
        self.falou = origem == "nome"  # o próprio nome já foi fala

    def _iniciar_gravacao(self, origem: str, preroll: list[bytes]) -> None:
        self._reset_gravacao(origem, preroll)
        self.estado = "gravando"
        if origem in ("nome", "manual"):
            eventos.publicar({"tipo": "acordou", "manual": origem == "manual"})
        else:
            eventos.publicar({"tipo": "ouvindo"})

    @property
    def limiar(self) -> float:
        return max(self.ruido * 3.0, config.LIMIAR_MIN)

    def alimentar(self, bloco: bytes) -> None:
        """Recebe 80 ms de áudio PCM 16 bits mono 16 kHz."""
        self.relogio += DUR
        amostras = np.frombuffer(bloco, np.int16).astype(np.float32)
        nivel = float(np.sqrt(np.mean(amostras ** 2))) if len(amostras) else 0.0
        self.pre.append(bloco)

        if self.mudo:
            return
        e = self.estado

        if e == "espera":
            if nivel < self.ruido * 2.5:  # aprende o ruído ambiente
                self.ruido = 0.97 * self.ruido + 0.03 * max(nivel, 20.0)
            if self._vosk is None:
                return
            if self._vosk.AcceptWaveform(bloco):
                texto = json.loads(self._vosk.Result()).get("text", "")
            else:
                texto = json.loads(self._vosk.PartialResult()).get("partial", "")
            if NOME_VOSK.search(texto):
                self._vosk.Reset()
                self._iniciar_gravacao("nome", list(self.pre))

        elif e == "seguimento":
            self._enviar_mic(nivel)
            self._seg_fala = self._seg_fala + 1 if nivel > self.limiar else 0
            if self._seg_fala >= 2:
                self._iniciar_gravacao("seguimento", list(self.pre)[-6:])
            elif self.relogio - self._seg_desde > config.TEMPO_SEGUIMENTO:
                self.estado = "espera"
                eventos.publicar({"tipo": "ocioso"})

        elif e == "gravando":
            self._enviar_mic(nivel)
            self.audio.append(bloco)
            self.duracao += DUR
            if nivel > self.limiar:
                self.falou, self.silencio = True, 0.0
            else:
                self.silencio += DUR
            espera_max = 12 if self.origem == "cadastro" else ESPERA_SEM_FALA
            if (self.falou and self.silencio >= SILENCIO_FIM) or self.duracao >= MAX_PEDIDO or \
                    (not self.falou and self.duracao >= espera_max):
                self.estado = "processando"
                pcm, origem, falou = b"".join(self.audio), self.origem, self.falou
                threading.Thread(target=self._processar, args=(pcm, origem, falou), daemon=True).start()

        elif e == "falando" and self.relogio - self._falando_desde > SEGURANCA_FALA:
            self._depois_de_falar()

    def _enviar_mic(self, nivel: float) -> None:
        if self.relogio - self._ultimo_mic >= 0.08:
            self._ultimo_mic = self.relogio
            eventos.publicar({"tipo": "mic", "nivel": round(min(1.0, nivel / (self.limiar * 4)), 3)})

    def _processar(self, pcm: bytes, origem: str, falou: bool) -> None:
        try:
            if origem == "cadastro":
                self._processar_cadastro(pcm, falou)
                return
            if not falou:
                self.estado = "espera"
                eventos.publicar({"tipo": "ocioso"})
                return
            texto = self.transcrever(pcm)
            pedido, achou = tirar_nome(texto)
            print(f"[ouvido] ({origem}) ouvi: {texto!r}")

            if origem == "nome" and not achou:  # Vosk se enganou: não era o nome
                self.estado = "espera"
                eventos.publicar({"tipo": "ocioso"})
                return
            if ALUCINACOES.match(pedido) or len(pedido) < 2:
                if origem == "nome":  # disse só "Ametista" e fez pausa: espera o pedido
                    self._iniciar_gravacao("continuacao", [])
                else:
                    self.estado = "espera"
                    eventos.publicar({"tipo": "ocioso"})
                return
            falante = identidade.identificar(pcm)
            if falante.nivel == "desconhecido":  # modo restrito: voz não cadastrada
                print(f"[ouvido] voz não reconhecida ({falante.confianca:.2f}); ignorando")
                self.estado = "espera"
                eventos.publicar({"tipo": "aviso", "texto": "Não reconheci essa voz."})
                return
            self.atender(pedido, falante)
            if self.estado == "processando":  # resposta não gerou fala
                self.estado = "espera"
        except Exception as e:
            print(f"[ouvido] erro ao processar: {e}")
            self.estado = "espera"
            eventos.publicar({"tipo": "ocioso"})

    # ------------------------------------------------------------ microfone
    def iniciar(self) -> bool:
        try:
            self.carregar_modelos()
        except Exception as e:
            print(f"[ouvido] desligado: {e}")
            eventos.remover(self._evento)
            return False
        threading.Thread(target=self._loop_microfone, daemon=True, name="microfone").start()
        return True

    def _loop_microfone(self) -> None:
        avisou = False
        while True:
            try:
                import sounddevice as sd

                dispositivo = config.MICROFONE or None
                if dispositivo and dispositivo.isdigit():
                    dispositivo = int(dispositivo)
                with sd.RawInputStream(samplerate=TAXA, blocksize=AMOSTRAS, dtype="int16",
                                       channels=1, device=dispositivo) as fluxo:
                    print("[ouvido] microfone aberto; diga 'Ametista'")
                    avisou = False
                    while True:
                        dados, _ = fluxo.read(AMOSTRAS)
                        self.alimentar(bytes(dados))
            except Exception as e:
                if not avisou:
                    print(f"[ouvido] microfone indisponível: {e}")
                    eventos.publicar({"tipo": "aviso", "texto": "Não consegui abrir o microfone."})
                    avisou = True
                time.sleep(5)
