"""Atende um pedido, venha ele da voz, do atalho, da caixa de texto, do celular ou de uma rotina.

Caminho de um pedido:
  1. "para tudo"          -> cala, cancela o que estiver em andamento e pausa a música (na hora, sem fila);
  2. confirmação pendente -> "sim"/"não" resolve a ação que estava esperando;
  3. "não guarde isso"    -> a troca (ou a anterior) não vai para o disco;
  4. cérebro              -> a resposta é falada em trechos enquanto é gerada;
  5. memória              -> a troca vai para o histórico (se não for privada).
"""
import re
import threading

from . import acoes, cerebro, estado, eventos, fala, ferramentas, memoria, voz
from .estado import Cancelado
from .identidade import DONO_PADRAO, Falante, falante_atual

_trava = threading.Lock()

PARAR = re.compile(r"^(?:(?:ametista|ei|ô|o)\s+)?(para|pare|parar|cancela|cancele|interrompe) (tudo|isso tudo)"
                   r"|^(emergencia|parada de emergencia|chega de tudo)$")
NAO_GUARDE = re.compile(
    r"\b(nao (guarde|guarda|grave|grava|salve|salva|anote|anota|memorize|registre|registra)( isso| essa| esse| nada|"
    r" essa conversa)?|nao (quero|precisa) que (voce )?(guarde|grave|lembre|anote)( isso)?|"
    r"isso (e|fica) (so )?entre (a gente|nos)|esquece (o que|que) eu (acabei de )?(disse|falei|contei))\b")
DESPEDIDA_RESPONDE_ATE = 30   # segundos depois da última fala dela
DESPEDIDA = re.compile(r"^(obrigad[oa]|muito obrigad[oa]|valeu|brigad[oa]|tchau|ate mais|ate logo|pode ir|"
                       r"era so isso|so isso|e so isso|nada nao|beleza obrigad[oa]|ok obrigad[oa])( ametista)?$")


def parar_tudo(origem: str = "pc") -> str:
    """Botão de emergência: cala, cancela pedidos, tarefas e confirmações, e pausa a música."""
    from . import agente, pc, spotify

    n = estado.cancelar_pedidos()
    tarefas = agente.cancelar_todas()
    acoes.cancelar_pendente()
    eventos.publicar({"tipo": "calar"})
    eventos.publicar({"tipo": "fim_conversa", "interno": True})
    if spotify.conectado():
        try:
            atual = spotify.cliente().current_playback()
            if atual and atual.get("is_playing"):
                spotify.controle("pausar")
        except Exception as e:
            print(f"[nucleo] não consegui pausar o Spotify: {e}")
    desligando = next((a for a in acoes.listar(10) if a["ferramenta"] == "pc_sistema" and a["ok"] and
                       a["args"].get("acao") in ("desligar", "reiniciar") and not a["desfeito"]), None)
    if desligando:
        try:
            pc.sistema("cancelar_desligamento")
        except Exception:
            pass
    acoes.registrar("parar_tudo", {}, f"{n} pedido(s) e {tarefas} tarefa(s) cancelados", True, None,
                    quem=falante_atual.get().nome or "", origem=origem, motivo="parar tudo")
    eventos.publicar({"tipo": "parou_tudo"})
    return "Parei tudo."


def _desfazer_troca_anterior() -> bool:
    """"Não guarde isso" dito depois: apaga a troca anterior e o que foi guardado nela."""
    trocas = memoria.trocas_recentes(1)
    if not trocas:
        return False
    t = trocas[0]
    for item in acoes.listar(30):
        if item.get("troca") == t and item["ferramenta"] in ("lembrar_fato", "caderno_guardar") \
                and item["desfazivel"] and not item["desfeito"]:
            acoes.desfazer(item["id"])
    memoria.apagar_troca(t)
    return True


def _falar_curto(texto: str, emocao: str, origem: str, ficha) -> str:
    if origem == "pc":
        fala.falar(texto, emocao, origem="local", ficha=ficha)
    return texto


def atender(texto: str, falante: Falante = DONO_PADRAO, mostrar_pedido: bool = True, origem: str = "pc",
            sem_nome: bool = False, com_voz: bool = True, celular: str | None = None) -> dict:
    """Bloqueante: roda numa thread de trabalho, nunca no loop do servidor.

    falante: quem pediu (a voz identificada). Texto digitado no PC e o celular pareado contam como o dono.
    origem: "pc" ou "celular" (a resposta do celular volta só para o celular, com o áudio inteiro).
    sem_nome: fala captada na conversa contínua, sem dizer "Ametista" (pode não ser para ela).
    com_voz: False = o celular está com a voz desligada (economiza a geração e os dados do áudio).
    celular: qual celular pediu (arquivos pedidos por ele voltam para ele).
    """
    texto = (texto or "").strip()
    if not texto:
        return {}
    norm = cerebro.normalizar(texto)
    norm_limpo = re.sub(r"[.,!?]+", "", norm).strip()
    if PARAR.match(norm_limpo):
        token = falante_atual.set(falante)
        try:
            msg = parar_tudo(origem)
        finally:
            falante_atual.reset(token)
        if origem == "pc":
            fala.falar(msg, "neutra", origem="local")
        return {"tipo": "resposta", "texto": msg, "emocao": "neutra", "origem": "local"}

    if origem == "pc":
        estado.cancelar_pedidos("pc")  # um pedido novo substitui o que ainda estava sendo respondido
    with _trava:
        ficha = estado.nova_ficha(texto, origem)
        estado.ocupado = True
        token_f = falante_atual.set(falante)
        troca = memoria.nova_troca()
        token_c = ferramentas.CONTEXTO.set({"texto": texto, "troca": troca, "origem": origem, "ficha": ficha,
                                            "celular": celular})
        try:
            return _atender(texto, norm_limpo, falante, mostrar_pedido, origem, sem_nome, ficha, troca, com_voz)
        except Cancelado:
            eventos.publicar({"tipo": "cancelado", "interno": origem != "pc"})
            return {"cancelado": True}
        finally:
            ferramentas.CONTEXTO.reset(token_c)
            falante_atual.reset(token_f)
            estado.encerrar_ficha(ficha)
            estado.ocupado = False


def _atender(texto, norm, falante, mostrar_pedido, origem, sem_nome, ficha, troca, com_voz=True) -> dict:
    from . import proatividade

    quem = falante.nome if falante.nome != DONO_PADRAO.nome else ""
    if origem == "pc" and mostrar_pedido and not sem_nome:
        eventos.publicar({"tipo": "transcricao", "texto": texto, "quem": quem})
    if origem == "pc" and not sem_nome:
        eventos.publicar({"tipo": "pensando"})

    def devolver(resposta: str, emocao: str = "neutra", privado: bool = False) -> dict:
        memoria.registrar(troca, "user", texto, falante.nome or "", origem, privado)
        memoria.registrar(troca, "assistant", resposta, "", origem, privado)
        r = {"tipo": "resposta", "texto": resposta, "emocao": emocao, "origem": "local"}
        if origem == "celular" and com_voz:
            r["audio"] = voz.sintetizar_sync(resposta)
        return r

    # 1) confirmação pendente ("sim, pode desligar")
    tratado, resp = acoes.resolver_pendente(texto, falante)
    if tratado:
        resp = ferramentas.falavel(resp or "Feito.")
        _falar_curto(resp, "feliz", origem, ficha)
        return devolver(resp, "feliz")

    # 2) "não guarde isso"
    privado_troca = False
    if NAO_GUARDE.search(norm):
        resto = NAO_GUARDE.sub(" ", norm)
        resto = re.sub(r"\b(ametista|por favor|ta|tá|ok|ai|entao)\b", " ", resto).strip(" ,.")
        if len(resto.split()) <= 2:  # só o pedido: vale para a conversa anterior
            _desfazer_troca_anterior()
            memoria.marcar_privada(troca)
            msg = "Tudo bem, não guardei."
            _falar_curto(msg, "feliz", origem, ficha)
            return devolver(msg, "feliz", privado=True)
        privado_troca = True
        memoria.marcar_privada(troca)

    # 3) despedida: encerra a conversa contínua. Sem o nome e muito depois da última fala dela, o "valeu"
    #    provavelmente era para outra pessoa da sala: encerra a conversa em silêncio.
    if DESPEDIDA.match(norm):
        if sem_nome and estado.segundos_desde_que_falou() > DESPEDIDA_RESPONDE_ATE:
            eventos.publicar({"tipo": "fim_conversa", "interno": True})
            return {"ignorado": True}
        msg = "De nada!" if re.match(r"^(obrigad|muito obrigad|valeu|brigad|beleza|ok obrigad)", norm) else "Até mais!"
        eventos.publicar({"tipo": "fim_conversa", "interno": True})
        _falar_curto(msg, "feliz", origem, ficha)
        return devolver(msg, "feliz", privado_troca)

    # 4) cérebro, com a fala em trechos
    locutor = fala.Locutor(origem="nuvem", publicar=origem == "pc", ficha=ficha)
    for lembrete in proatividade.na_conversa():
        locutor.texto(lembrete + " ")
    r = cerebro.pensar(texto, falante, locutor, ficha, sem_nome, origem, privado_troca)
    ficha.conferir()
    if r.get("ignorado"):
        eventos.publicar({"tipo": "ignorado", "interno": True})
        return {"ignorado": True}
    locutor.origem = r.get("origem", "nuvem")
    falado = locutor.terminar() or ferramentas.falavel(r.get("texto", ""))
    if origem == "pc" and not locutor.falou_algo:
        eventos.publicar({"tipo": "ocioso"})
    memoria.registrar(troca, "user", texto, falante.nome or "", origem, privado_troca)
    memoria.registrar(troca, "assistant", falado, "", origem, privado_troca)
    resultado = {"tipo": "resposta", "texto": falado, "emocao": locutor.emocao_atual or r.get("emocao", "neutra"),
                 "origem": r.get("origem", "local"), "aguardando": bool(acoes.pendente())}
    if origem == "celular" and com_voz:
        resultado["audio"] = voz.sintetizar_sync(falado)
    return resultado


def atender_em_segundo_plano(texto: str, falante: Falante = DONO_PADRAO, **kw) -> threading.Thread:
    t = threading.Thread(target=atender, args=(texto, falante), kwargs=kw, daemon=True, name="pedido")
    t.start()
    return t
