"""Iniciativa da Ametista, com limite: ela ajuda sem virar uma chata.

O que ela faz sozinha:
  - resumo do dia na primeira vez que você usa o PC no dia (clima, compromissos, lembretes, aniversários);
  - lembretes por condição: "quando eu chegar", "quando eu ligar o PC", "quando eu abrir o AutoCAD",
    "quando eu chegar em casa" (Home Assistant);
  - sugere uma pausa depois de muito tempo seguido no PC;
  - avisa de bateria fraca, disco quase cheio e chuva chegando.

Limites (painel > Proatividade): nível, máximo por hora, intervalo mínimo, horário de silêncio. Nunca fala no
modo privado, com um jogo/filme em tela cheia, enquanto você fala com ela ou se você não estiver no PC.
"""
import threading
import time
from datetime import date, datetime, timedelta

from . import avisos, config, estado, memoria

URGENTE, NORMAL = "urgente", "normal"
_historico: list[float] = []             # quando ela falou por iniciativa (última hora)
_por_chave: dict[str, float] = {}
_trava = threading.Lock()
AUSENTE_SEG = 600                        # 10 min sem mexer = saiu do PC


# ====================================================================== regras
def pode_falar(prioridade: str = NORMAL, nivel_min: int = 2, chave: str | None = None,
               intervalo_chave_h: float = 6, agora: float | None = None, ocioso: float | None = None,
               tela_cheia: bool | None = None) -> bool:
    from . import pc

    agora = agora or time.time()
    if estado.privado() or config.PROATIVIDADE < nivel_min or config.PROATIVIDADE <= 0:
        return False
    if chave and agora - _por_chave.get(chave, 0) < intervalo_chave_h * 3600:
        return False
    if estado.ocupado or estado.falando:
        return False
    if prioridade == URGENTE:
        return True
    if estado.silencio_agora():
        return False
    if (tela_cheia if tela_cheia is not None else pc.tela_cheia()):
        return False
    ocioso = pc.tempo_ocioso() if ocioso is None else ocioso
    if ocioso is not None and ocioso > AUSENTE_SEG:
        return False
    with _trava:
        recentes = [t for t in _historico if agora - t < 3600]
        if len(recentes) >= max(1, config.PROATIVO_MAX_HORA):
            return False
        if recentes and agora - max(recentes) < config.PROATIVO_INTERVALO_MIN * 60:
            return False
    return True


def marcar(chave: str | None = None, agora: float | None = None) -> None:
    agora = agora or time.time()
    with _trava:
        _historico.append(agora)
        del _historico[:-50]
        if chave:
            _por_chave[chave] = agora


def tentar(texto: str, chave: str, prioridade: str = NORMAL, nivel_min: int = 2, intervalo_chave_h: float = 6,
           emocao: str = "neutra", celular: bool = False) -> bool:
    if not pode_falar(prioridade, nivel_min, chave, intervalo_chave_h):
        return False
    marcar(chave)
    avisos.proativo(texto, emocao, celular=celular)
    return True


# ====================================================================== resumo do dia
DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def resumo_do_dia(agora: datetime | None = None) -> str:
    """Texto curto e falado: saudação, clima, compromissos, lembretes e aniversários de hoje."""
    from . import agenda, ferramentas

    agora = agora or datetime.now()
    saud = "Bom dia" if agora.hour < 12 else "Boa tarde" if agora.hour < 18 else "Boa noite"
    partes = [f"{saud}, {config.DONO}!"]
    try:
        linhas = ferramentas.clima(1).split("\n")
        atual = linhas[0].split(":", 1)[1].strip().split(",")[0] if linhas else ""
        hoje = next((l for l in linhas if l.startswith("Hoje")), "")
        if atual:
            partes.append(f"Agora faz {atual.split('(')[0].strip()}.")
        if "chance de chuva" in hoje:
            chance = int(hoje.rsplit("chance de chuva", 1)[1].strip(" .%"))
            if chance >= 50:
                partes.append(f"Tem {chance} por cento de chance de chuva hoje.")
    except Exception:
        pass
    try:
        if agenda.google_conectado() or agenda.outlook_conectado():
            fim = datetime.combine(agora.date() + timedelta(days=1), datetime.min.time()).astimezone()
            eventos_, _ = agenda.todos_eventos(agora.astimezone(), fim)
            if eventos_:
                itens = [f"{e['titulo']} às {e['inicio']:%H:%M}" if not e["dia_inteiro"] else e["titulo"]
                         for e in eventos_[:4]]
                qtd = len(eventos_)
                partes.append(f"Você tem {qtd} compromisso{'s' if qtd > 1 else ''} hoje: " + ", ".join(itens) + ".")
            else:
                partes.append("Sua agenda está livre hoje.")
    except Exception:
        pass
    hoje_fim = datetime.combine(agora.date(), datetime.max.time())
    lembretes, anivs = [], []
    for l in memoria.lembretes_pendentes():
        if not l.get("quando"):
            continue
        q = datetime.fromisoformat(l["quando"])
        if agora <= q <= hoje_fim:
            if l["tipo"] == "aniversario":
                anivs.append(l["texto"])
            elif l["tipo"] == "lembrete":
                lembretes.append(f"{l['texto']} às {q:%H:%M}")
    if anivs:
        partes.append("Hoje é " + " e ".join(anivs) + ".")
    if lembretes:
        partes.append("Lembretes de hoje: " + "; ".join(lembretes[:3]) + ".")
    return " ".join(partes)


# ====================================================================== vigia
class Vigia:
    def __init__(self):
        self.ausente = False
        self.sessao_desde = time.time()
        self.ultimo_disco = 0.0
        self.ultima_chuva = 0.0
        self.pessoa_casa = None
        self.ultimo_ha = 0.0
        self.iniciou_condicoes = False

    def iniciar(self) -> None:
        threading.Thread(target=self._loop, daemon=True, name="proatividade").start()

    def _loop(self) -> None:
        time.sleep(25)
        while True:
            try:
                self.rodada()
            except Exception as e:
                print(f"[proatividade] erro: {e}")
            time.sleep(20)

    def rodada(self, agora: float | None = None) -> None:
        from . import pc

        agora = agora or time.time()
        ocioso = pc.tempo_ocioso()
        # ---- condições "ao ligar o PC" (uma vez, logo depois de iniciar)
        if not self.iniciou_condicoes:
            self.iniciou_condicoes = True
            self._disparar("ao_ligar_pc", criado_antes=estado.inicio_processo)
            self._disparar("ao_chegar", criado_antes=estado.inicio_processo)
        # ---- saiu e voltou
        if ocioso is not None:
            if ocioso >= AUSENTE_SEG:
                self.ausente = True
            elif self.ausente and ocioso < 30:
                self.ausente = False
                self.sessao_desde = agora
                self._disparar("ao_voltar")
                self._disparar("ao_chegar")
        # ---- programa aberto
        titulo, prog = pc.janela_ativa()
        if titulo or prog:
            self._disparar(f"ao_abrir:{titulo} {prog}")
        # ---- chegou em casa (Home Assistant)
        if config.HA_PESSOA and agora - self.ultimo_ha > 60:
            self.ultimo_ha = agora
            self._checar_casa()
        # ---- resumo do dia
        self._resumo(ocioso)
        # ---- pausa
        if config.PAUSA_MINUTOS > 0 and ocioso is not None and not self.ausente and \
                agora - self.sessao_desde >= config.PAUSA_MINUTOS * 60:
            horas = config.PAUSA_MINUTOS // 60
            tempo = f"{horas} hora{'s' if horas > 1 else ''}" if horas else f"{config.PAUSA_MINUTOS} minutos"
            if tentar(f"{config.DONO}, você está há {tempo} direto no computador. Que tal uma pausa rápida?",
                      "pausa", intervalo_chave_h=config.PAUSA_MINUTOS / 60):
                self.sessao_desde = agora
        # ---- bateria
        self._bateria()
        # ---- disco (a cada 30 min)
        if agora - self.ultimo_disco > 1800:
            self.ultimo_disco = agora
            self._disco()
        # ---- chuva (a cada 30 min, de dia)
        hora = datetime.now().hour
        if 7 <= hora <= 20 and agora - self.ultima_chuva > 1800:
            self.ultima_chuva = agora
            self._chuva()

    def _disparar(self, condicao: str, criado_antes: float | None = None) -> None:
        from . import ferramentas

        for item in memoria.retirar_condicionais(condicao, criado_antes):
            avisos.alerta(ferramentas.texto_do_alerta(item), "surpresa")

    def _checar_casa(self) -> None:
        from . import ferramentas

        try:
            e = ferramentas.casa_estado(config.HA_PESSOA)
        except Exception:
            return
        agora_casa = (e or {}).get("estado") == "home"
        if self.pessoa_casa is False and agora_casa:
            self._disparar("ao_chegar_casa")
            self._disparar("ao_chegar")
        self.pessoa_casa = agora_casa

    def _resumo(self, ocioso: float | None) -> None:
        hoje = date.today().isoformat()
        if not config.RESUMO_DIARIO or estado.obter("resumo_dia") == hoje:
            return
        if not pode_falar(NORMAL, nivel_min=1, ocioso=ocioso):
            return
        estado.lembrar("resumo_dia", hoje)
        marcar("resumo")
        avisos.proativo(resumo_do_dia(), "feliz")

    def _bateria(self) -> None:
        try:
            import psutil

            b = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
        except Exception:
            b = None
        if b and not b.power_plugged and b.percent <= 15:
            tentar(f"A bateria está em {round(b.percent)} por cento. Melhor ligar o carregador.", "bateria",
                   URGENTE, nivel_min=1, intervalo_chave_h=1, emocao="surpresa", celular=True)

    def _disco(self) -> None:
        import shutil
        from pathlib import Path

        try:
            uso = shutil.disk_usage(Path.home().anchor or "/")
        except OSError:
            return
        livre_gb = uso.free / 1e9
        if livre_gb < 10 or uso.free / uso.total < 0.06:
            tentar(f"O disco principal está quase cheio: só {livre_gb:.0f} GB livres.", "disco", nivel_min=1,
                   intervalo_chave_h=24, emocao="pensativa")

    def _chuva(self) -> None:
        from . import ferramentas

        chave = f"chuva-{date.today().isoformat()}"
        if not pode_falar(NORMAL, 1, chave, 24):
            return
        try:
            chance = ferramentas.chuva_proximas_horas(2)
        except Exception:
            return
        if chance is not None and chance >= 70:
            tentar(f"Vai chover nas próximas horas em {config.CIDADE}. Se for sair, leva o guarda-chuva.", chave,
                   nivel_min=1, intervalo_chave_h=24)


def na_conversa() -> list[str]:
    """Lembretes "na próxima vez que eu falar com você" (o núcleo chama no começo de cada pedido)."""
    from . import ferramentas

    return [ferramentas.texto_do_alerta(i) for i in memoria.retirar_condicionais("proxima_conversa")]


_vigia: Vigia | None = None


def iniciar() -> Vigia:
    global _vigia
    if _vigia is None:
        _vigia = Vigia()
        _vigia.iniciar()
    return _vigia
