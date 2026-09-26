"""Ouvido da Ametista: escuta o microfone o tempo todo, 100% no seu PC.

Etapas:
  1. ESPERA      Vosk (leve, offline) procura a palavra "Ametista".
  2. GRAVANDO    Ao ouvir o nome, grava o pedido até você parar de falar.
  3. PROCESSANDO faster-whisper transcreve e confere quem está falando (ao mesmo tempo). Para ser rápida, a
                 transcrição começa já na pausa do fim da fala (se você voltar a falar, ela é descartada), o
                 Whisper usa a placa NVIDIA quando dá (transcricao.py) e o que você diz enquanto ela processa
                 um "Ametista" sozinho não se perde.
  4. FALANDO     Enquanto ela responde, só presta atenção em "Ametista" e em "para" (interrupção por voz).
  5. SEGUIMENTO  Logo depois da resposta, ouve alguns segundos sem precisar do nome.
     CONVERSA    Depois disso, por alguns minutos, continua atenta: se você falar com ela sem o nome, ela
                 responde; se for conversa com outra pessoa ou a TV, ela ignora.
"""
import json
import re
import threading
import time
import unicodedata
from collections import deque

import numpy as np

from . import config, estado, eventos, identidade, transcricao

TAXA = 16000
AMOSTRAS = 1280                 # 80 ms por bloco
DUR = AMOSTRAS / TAXA
PREROLL = 20                    # 1,6 s de áudio antes do gatilho (inclui o próprio nome)
BLOCOS_ATE_DESCANSAR = 19       # 1,5 s de silêncio e o reconhecedor da palavra de ativação descansa
PREROLL_ACORDAR = 8             # ao acordar, ele recebe os 0,64 s anteriores ao primeiro som
SILENCIO_FIM = 0.8              # segundos de silêncio que encerram o pedido
SILENCIO_ADIANTAR = 0.4         # com esse silêncio a transcrição já começa (e é descartada se você continuar)
DURANTE_MAX = 75                # até 6 s do que você diz enquanto ela processa um "Ametista" sozinho
MAX_PEDIDO = 14
ESPERA_SEM_FALA = 5
SEGURANCA_FALA = 90             # se a tela não avisar que terminou de falar

NOME_VOSK = re.compile(r"\bametista\b")
NOME = re.compile(r"\b(?:o\s+|oi\s+|ei\s+|e\s+ai\s+)?(?:a\s?m[ei]t[ií]st?[ae]s?|ametist\w*|metista)\b[\s,.!?:]*", re.I)
PARAR_FALA = re.compile(r"^(para|pare|parar|chega|silencio|cala|cala a boca|cala boca|espera|ok para|"
                        r"pode parar|para de falar|para ai|tá bom para|ta bom para|stop)$")
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


def _nivel(bloco: bytes) -> float:
    amostras = np.frombuffer(bloco, np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(amostras ** 2))) if len(amostras) else 0.0


class _EmParalelo:
    """Roda uma função numa thread e entrega o resultado quando pedido (ou a exceção dela)."""

    def __init__(self, funcao, *args):
        self._valor, self._erro = None, None
        self._fim = threading.Event()

        def rodar():
            try:
                self._valor = funcao(*args)
            except Exception as e:
                self._erro = e
            self._fim.set()

        threading.Thread(target=rodar, daemon=True).start()

    def resultado(self):
        self._fim.wait()
        if self._erro:
            raise self._erro
        return self._valor


_instancia: "Ouvido | None" = None
_whisper_avulso = None
_trava_avulso = threading.Lock()


def instancia() -> "Ouvido | None":
    return _instancia


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
            _whisper_avulso = transcricao.abrir("cpu")
    return transcricao.texto(_whisper_avulso, audio)


class _Adiantada:
    """Transcrição começada na pausa do fim da fala, rodando enquanto o silêncio se confirma."""

    def __init__(self, ouvido: "Ouvido", pcm: bytes):
        self.pcm, self.texto, self.erro = pcm, "", None
        self._pronta = threading.Event()
        threading.Thread(target=self._rodar, args=(ouvido,), daemon=True, name="transcricao-adiantada").start()

    def _rodar(self, ouvido: "Ouvido") -> None:
        try:
            self.texto = ouvido.transcrever(self.pcm)
        except Exception as e:
            self.erro = e
        self._pronta.set()

    def resultado(self) -> str:
        self._pronta.wait()
        if self.erro:
            raise self.erro
        return self.texto


class Ouvido:
    def __init__(self, atender=None):
        global _instancia
        from . import nucleo

        _instancia = self
        self.atender = atender or nucleo.atender
        self.estado = "espera"
        self.mudo_manual = False
        self.mudo_privado = estado.privado()
        self.relogio = 0.0                      # tempo em segundos, contado pelo áudio
        self.pre: deque[bytes] = deque(maxlen=PREROLL)
        self.ruido = 150.0
        self._vosk = None
        self._quietos = 0                       # blocos seguidos em silêncio (o reconhecedor descansa)
        self._vosk_descansando = False
        self._whisper = None
        self._whisper_pronto = threading.Event()
        self.dispositivo = "cpu"                # onde o Whisper roda (cpu ou cuda)
        self._trava = threading.RLock()         # o microfone e o processamento mexem no mesmo estado
        self._adiantada: _Adiantada | None = None
        self._depois_adiantar = 0               # blocos com som (acima do ruído) depois que ela adiantou
        self._durante: list[bytes] = []         # o que chegou enquanto processava um "Ametista" sozinho
        self._apos_fala = "espera"
        self._falando_desde = 0.0
        self._texto_falando = ""
        self._ultimo_mic = 0.0
        self._seg_ate = 0.0
        self._conversa_ate = 0.0
        self._avisou_conversa = False
        self._seg_fala = 0
        self._cadastro: dict | None = None
        self._cadastro_pendente: dict | None = None
        self.ultimo_bloco = 0.0                 # time.time() do último áudio (diagnóstico)
        self.nivel = 0.0
        self.microfone_ok = False
        self._reset_gravacao("", [])
        eventos.ouvir(self._evento)

    @property
    def mudo(self) -> bool:
        return self.mudo_manual or self.mudo_privado

    def status(self) -> dict:
        return {"estado": self.estado, "mudo": self.mudo, "privado": self.mudo_privado,
                "vosk": self._vosk is not None, "whisper": self._whisper_pronto.is_set(), "dispositivo": self.dispositivo,
                "microfone": self.microfone_ok, "ultimo_audio_s": round(time.time() - self.ultimo_bloco, 1)
                if self.ultimo_bloco else None, "ruido": round(self.ruido), "nivel": round(self.nivel)}

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
        t = time.time()

        def trocar(modelo) -> None:            # a placa NVIDIA ficou pronta depois: passa a usar ela
            self._whisper, self.dispositivo = modelo, "cuda"

        carregador = transcricao.Carregador(ao_trocar=trocar)
        try:
            self._whisper = carregador.carregar()
        except Exception as e:
            print(f"[ouvido] Whisper não carregou: {e}")
            return
        self.dispositivo = carregador.dispositivo
        print(f"[ouvido] Whisper '{config.WHISPER_MODELO}' pronto ({self.dispositivo}) em {time.time() - t:.1f}s")
        self._whisper_pronto.set()
        try:  # a identificação de voz também já carregada: a primeira frase não espera por ela
            if config.MODO_VOZ != "aberto" and identidade.tem_cadastro():
                identidade.disponivel()
        except Exception:
            pass

    def transcrever(self, pcm: bytes) -> str:
        self._whisper_pronto.wait()
        audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
        return transcricao.texto(self._whisper, audio)

    # ------------------------------------------------------------ eventos externos
    def _evento(self, msg: dict) -> None:
        tipo = msg.get("tipo")
        if tipo == "fala_inicio":
            if self.estado == "gravando":
                return
            self._apos_fala = "seguimento" if self.estado in ("processando", "falando") else self._modo_de_espera()
            self.estado, self._falando_desde, self._texto_falando = "falando", self.relogio, ""
        elif tipo == "fala_trecho":
            if self.estado == "falando":
                self._texto_falando += " " + _sem_acento(msg.get("texto", "").lower())
        elif tipo == "alerta":
            if self.estado in ("gravando", "processando"):
                return
            if self.estado != "falando":  # aviso depois de uma resposta: mantém o seguimento da resposta
                self._apos_fala = self._modo_de_espera()
                self._texto_falando = ""
            self.estado, self._falando_desde = "falando", self.relogio
            self._texto_falando += " " + _sem_acento(msg.get("texto", "").lower())
        elif tipo == "fala_terminou" and self.estado == "falando":
            self._depois_de_falar()
        elif tipo == "chamar":
            self.ativar_manual()
        elif tipo in ("cancelar_escuta", "fim_conversa"):
            self._cadastro = None
            self._conversa_ate = self._seg_ate = 0.0
            if self.estado in ("gravando", "seguimento"):
                self.estado = "espera"
                if tipo == "fim_conversa":
                    eventos.publicar({"tipo": "ocioso"})
        elif tipo == "calar" and self.estado == "falando":
            self._depois_de_falar(forcar="seguimento")
        elif tipo == "ignorado":
            if self.estado in ("processando", "seguimento"):
                self.estado = "seguimento" if self.relogio < self._conversa_ate else "espera"
        elif tipo == "cadastrar":
            pedido = {"nome": msg["nome"], "nivel": msg.get("nivel", "familia")}
            if self.estado in ("espera", "seguimento"):
                self._iniciar_cadastro(pedido)
            else:  # está falando/processando: começa assim que terminar
                self._cadastro_pendente = pedido
        elif tipo == "mudo":
            self.mudo_manual = bool(msg.get("valor"))
            if self.mudo:
                self.estado = "espera"
        elif tipo == "privado":
            self.mudo_privado = bool(msg.get("valor"))
            if self.mudo:
                self.estado, self._conversa_ate = "espera", 0.0

    def _modo_de_espera(self) -> str:
        return "conversa" if self.relogio < self._conversa_ate else "espera"

    def _depois_de_falar(self, forcar: str | None = None) -> None:
        if self._vosk:
            self._vosk.Reset()
        self._texto_falando = ""
        if self._cadastro_pendente:
            pedido, self._cadastro_pendente = self._cadastro_pendente, None
            self._iniciar_cadastro(pedido)
            return
        modo = forcar or self._apos_fala
        if modo == "seguimento" and not self.mudo:
            self._seg_ate = self.relogio + config.TEMPO_SEGUIMENTO
            if config.CONVERSA_MINUTOS > 0:
                self._conversa_ate = self._seg_ate + config.CONVERSA_MINUTOS * 60
            self._avisou_conversa = False
            self.estado, self._seg_fala = "seguimento", 0
            eventos.publicar({"tipo": "ouvindo", "seguimento": True})
        elif modo == "conversa" and not self.mudo:
            self.estado, self._seg_fala = "seguimento", 0
        else:
            self.estado = "espera"
            eventos.publicar({"tipo": "ocioso"})

    def ativar_manual(self) -> None:
        if self.mudo:
            eventos.publicar({"tipo": "aviso", "texto": "O microfone está desligado (modo privado ou bandeja)."})
            eventos.publicar({"tipo": "acordou", "manual": True})
            return
        if self.estado in ("falando", "processando"):
            self._interromper(com_nome=False)
        self._iniciar_gravacao("manual", [])

    # ------------------------------------------------------------ interrupção por voz
    def _interromper(self, com_nome: bool) -> None:
        print(f"[ouvido] interrompida pela voz ({'nome' if com_nome else 'parar'})")
        estado.cancelar_pedidos("pc")
        self.estado = "espera"  # o "calar" abaixo não deve mexer no estado
        eventos.publicar({"tipo": "calar"})
        self._texto_falando = ""
        if self._vosk:
            self._vosk.Reset()
        if com_nome:
            self._iniciar_gravacao("nome", list(self.pre))
        else:
            self._depois_de_falar(forcar="seguimento")

    def _escutar_interrupcao(self, bloco: bytes) -> None:
        if not (config.INTERROMPER_POR_VOZ and self._vosk):
            return
        final = self._vosk.AcceptWaveform(bloco)
        texto = json.loads(self._vosk.Result() if final else self._vosk.PartialResult()).get(
            "text" if final else "partial", "")
        if not texto:
            return
        if NOME_VOSK.search(texto) and "ametista" not in self._texto_falando:
            self._interromper(com_nome=True)
        elif final and PARAR_FALA.match(texto.strip()) and self.estado == "falando":
            self._interromper(com_nome=False)

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
        self.estado = "processando"
        from . import fala

        fala.falar(f"Pronto, {c['nome']}! Agora eu reconheço a sua voz.", "feliz", origem="local")

    # ------------------------------------------------------------ fluxo de áudio
    def _reset_gravacao(self, origem: str, preroll: list[bytes]) -> None:
        self.origem = origem
        self.audio = list(preroll)
        self.duracao = 0.0
        self.silencio = 0.0
        self.falou = origem == "nome"  # o próprio nome já foi fala
        self._adiantada, self._depois_adiantar = None, 0

    def _iniciar_gravacao(self, origem: str, preroll: list[bytes]) -> None:
        self._reset_gravacao(origem, preroll)
        self.estado = "gravando"
        if origem in ("nome", "manual"):
            eventos.publicar({"tipo": "acordou", "manual": origem == "manual"})
        elif origem == "seguimento":
            eventos.publicar({"tipo": "ouvindo"})

    @property
    def limiar(self) -> float:
        return max(self.ruido * 3.0, config.LIMIAR_MIN)

    def alimentar(self, bloco: bytes) -> None:
        """Recebe 80 ms de áudio PCM 16 bits mono 16 kHz."""
        self.relogio += DUR
        self.ultimo_bloco = time.time()
        nivel = _nivel(bloco)
        self.nivel = nivel
        self.pre.append(bloco)
        if self.mudo:
            return
        with self._trava:
            self._alimentar(bloco, nivel)

    def _alimentar(self, bloco: bytes, nivel: float) -> None:
        e = self.estado

        if e == "espera":
            if nivel < self.ruido * 2.5:  # aprende o ruído ambiente
                self.ruido = 0.97 * self.ruido + 0.03 * max(nivel, 20.0)
            if self._vosk is None:
                return
            # Economia: em silêncio o reconhecedor descansa. No primeiro som acima do ruído ele acorda e
            # recebe também o meio segundo anterior, para não perder o começo do "Ametista".
            if nivel < max(self.ruido * 1.4, 40.0):
                self._quietos += 1
                if self._quietos > BLOCOS_ATE_DESCANSAR:
                    if not self._vosk_descansando:
                        self._vosk.Reset()
                        self._vosk_descansando = True
                    return
            else:
                self._quietos = 0
                if self._vosk_descansando:
                    self._vosk_descansando = False
                    for anterior in list(self.pre)[-(PREROLL_ACORDAR + 1):-1]:
                        self._vosk.AcceptWaveform(anterior)
            if self._vosk.AcceptWaveform(bloco):
                texto = json.loads(self._vosk.Result()).get("text", "")
            else:
                texto = json.loads(self._vosk.PartialResult()).get("partial", "")
            if NOME_VOSK.search(texto):
                self._vosk.Reset()
                self._iniciar_gravacao("nome", list(self.pre))

        elif e == "seguimento":
            curto = self.relogio <= self._seg_ate
            if curto:
                self._enviar_mic(nivel)
            elif self.relogio > self._conversa_ate:
                self.estado = "espera"
                eventos.publicar({"tipo": "ocioso"})
                return
            elif not self._avisou_conversa:
                self._avisou_conversa = True
                eventos.publicar({"tipo": "conversa", "ativa": True})
            self._seg_fala = self._seg_fala + 1 if nivel > self.limiar else 0
            if self._seg_fala >= 2:
                self._iniciar_gravacao("seguimento" if curto else "conversa", list(self.pre)[-6:])

        elif e == "gravando":
            if self.origem != "conversa":
                self._enviar_mic(nivel)
            self._gravar(bloco, nivel)

        elif e in ("falando", "processando"):
            if e == "processando" and self.origem == "nome" and len(self._durante) < DURANTE_MAX:
                self._durante.append(bloco)
            self._escutar_interrupcao(bloco)
            if self.estado == "falando" and self.relogio - self._falando_desde > SEGURANCA_FALA:
                self._depois_de_falar()

    def _gravar(self, bloco: bytes, nivel: float) -> None:
        self.audio.append(bloco)
        self.duracao += DUR
        if nivel > self.limiar:
            self.falou, self.silencio = True, 0.0
            self._adiantada = None                      # voltou a falar: a transcrição adiantada não vale
        else:
            self.silencio += DUR
            if self._adiantada is not None and nivel > max(self.ruido * 1.8, 60.0):
                self._depois_adiantar += 1              # som fraco depois de adiantar (uma última palavra baixa?)
        if self.origem == "cadastro":
            espera_max = 12
        else:
            espera_max = ESPERA_SEM_FALA
            if self.falou and self._adiantada is None and self.silencio >= SILENCIO_ADIANTAR and \
                    self._whisper_pronto.is_set() and self.duracao < MAX_PEDIDO:
                self._adiantada, self._depois_adiantar = _Adiantada(self, b"".join(self.audio)), 0
        if (self.falou and self.silencio >= SILENCIO_FIM) or self.duracao >= MAX_PEDIDO or \
                (not self.falou and self.duracao >= espera_max):
            self.estado = "processando"
            adiantada = self._adiantada if self._depois_adiantar < 2 and self.silencio >= SILENCIO_FIM else None
            pcm, origem, falou = b"".join(self.audio), self.origem, self.falou
            self._adiantada, self._durante = None, []
            threading.Thread(target=self._processar, args=(pcm, origem, falou, adiantada), daemon=True).start()

    def _enviar_mic(self, nivel: float) -> None:
        if self.relogio - self._ultimo_mic >= 0.08:
            self._ultimo_mic = self.relogio
            eventos.publicar({"tipo": "mic", "nivel": round(min(1.0, nivel / (self.limiar * 4)), 3)})

    def _voltar_a_ouvir(self, conversa: bool) -> None:
        if conversa and self.relogio < self._conversa_ate:
            self.estado = "seguimento"
        else:
            self.estado = "espera"
            eventos.publicar({"tipo": "ocioso"})

    def _processar(self, pcm: bytes, origem: str, falou: bool, adiantada: "_Adiantada | None" = None) -> None:
        conversa = origem == "conversa"
        try:
            if origem == "cadastro":
                self._processar_cadastro(pcm, falou)
                return
            if not falou:
                self._voltar_a_ouvir(conversa)
                return
            quem = _EmParalelo(identidade.identificar, pcm)      # quem fala, enquanto transcreve
            texto = adiantada.resultado() if adiantada else self.transcrever(pcm)
            pedido, achou = tirar_nome(texto)
            print(f"[ouvido] ({origem}) ouvi: {texto!r}")

            if origem == "nome" and not achou:  # Vosk se enganou: não era o nome
                self._voltar_a_ouvir(False)
                return
            if ALUCINACOES.match(pedido) or len(pedido) < 2:
                if origem == "nome":  # disse só "Ametista" e fez pausa: espera o pedido
                    self._continuar_depois_do_nome()
                else:
                    self._voltar_a_ouvir(conversa)
                return
            falante = quem.resultado()
            if falante.nivel == "desconhecido" or (conversa and not achou and identidade.tem_cadastro()
                                                   and not falante.conhecido):
                print(f"[ouvido] voz não reconhecida ({falante.confianca:.2f}); ignorando")
                if not conversa:
                    eventos.publicar({"tipo": "aviso", "texto": "Não reconheci essa voz."})
                self._voltar_a_ouvir(conversa)
                return
            r = self.atender(pedido, falante, sem_nome=conversa and not achou) or {}
            if self.estado == "processando":  # a resposta não gerou fala (ignorada, cancelada...)
                if r.get("ignorado"):
                    self._voltar_a_ouvir(True)
                elif r.get("cancelado"):
                    pass  # quem cancelou já mudou o estado
                else:
                    self._depois_de_falar(forcar="seguimento")
        except Exception as e:
            print(f"[ouvido] erro ao processar: {e}")
            self.estado = "espera"
            eventos.publicar({"tipo": "ocioso"})

    def _continuar_depois_do_nome(self) -> None:
        """Você disse só "Ametista" e fez uma pausa: grava o pedido, sem perder o que já disse enquanto ela
        transcrevia o nome."""
        with self._trava:
            if self.estado != "processando":
                return
            durante, self._durante = self._durante, []
            self._iniciar_gravacao("continuacao", [])
            for bloco in durante:
                if self.estado != "gravando":
                    break
                self._gravar(bloco, _nivel(bloco))

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
                if dispositivo and str(dispositivo).isdigit():
                    dispositivo = int(dispositivo)
                with sd.RawInputStream(samplerate=TAXA, blocksize=AMOSTRAS, dtype="int16",
                                       channels=1, device=dispositivo) as fluxo:
                    print("[ouvido] microfone aberto; diga 'Ametista'")
                    self.microfone_ok, avisou = True, False
                    while True:
                        dados, _ = fluxo.read(AMOSTRAS)
                        self.alimentar(bytes(dados))
            except Exception as e:
                self.microfone_ok = False
                if not avisou:
                    print(f"[ouvido] microfone indisponível: {e}")
                    eventos.publicar({"tipo": "aviso", "texto": "Não consegui abrir o microfone."})
                    avisou = True
                time.sleep(5)


def microfones() -> list[dict]:
    """Microfones disponíveis (para o painel)."""
    try:
        import sounddevice as sd

        padrao = sd.default.device[0] if sd.default.device else None
        saida = []
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0 and d.get("hostapi", 0) == 0:
                saida.append({"id": str(i), "nome": d["name"], "padrao": i == padrao})
        return saida
    except Exception:
        return []
