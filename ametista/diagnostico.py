"""Diagnóstico: "Ametista, faça um diagnóstico" (ou diagnostico.bat, ou o botão no painel).

Confere cada peça, fala um resumo curto e guarda o relatório completo em dados/diagnostico.txt.
"""
import platform
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import httpx

from . import __version__, config, eventos

OK, AVISO, ERRO = "ok", "aviso", "erro"


def _item(nome: str, situacao: str, detalhe: str) -> dict:
    return {"item": nome, "situacao": situacao, "detalhe": detalhe}


def _internet() -> dict:
    t = time.time()
    try:
        httpx.get("https://www.google.com/generate_204", timeout=6)
        return _item("Internet", OK, f"conectada ({(time.time() - t) * 1000:.0f} ms)")
    except Exception as e:
        return _item("Internet", ERRO, f"sem conexão ({type(e).__name__})")


def _claude() -> dict:
    if not config.ANTHROPIC_API_KEY:
        return _item("Cérebro na nuvem (Claude)", ERRO, "sem chave da API: cole no painel > Cérebro")
    try:
        import anthropic

        c = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=0, timeout=10)
        vistos = []
        for modelo in dict.fromkeys([config.CLAUDE_MODELO, config.CLAUDE_MODELO_FORTE, config.AGENTE_MODELO]):
            c.models.retrieve(modelo)
            vistos.append(modelo)
        return _item("Cérebro na nuvem (Claude)", OK, "chave válida; modelos: " + ", ".join(vistos))
    except anthropic.AuthenticationError:
        return _item("Cérebro na nuvem (Claude)", ERRO, "a chave da API foi recusada")
    except anthropic.NotFoundError as e:
        return _item("Cérebro na nuvem (Claude)", ERRO, f"modelo não encontrado: {e}")
    except Exception as e:
        return _item("Cérebro na nuvem (Claude)", ERRO, f"não respondeu: {type(e).__name__}")


def _ollama() -> dict:
    from . import cerebro_local

    nome = "Cérebro local (Ollama)"
    instalados = cerebro_local.modelos_instalados(forcar=True)
    try:
        aberto = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=2).status_code == 200
    except Exception:
        aberto = False
    if not aberto:
        if config.CEREBRO_PRINCIPAL == "ollama":
            return _item(nome, ERRO, "é o cérebro principal, mas o Ollama está fechado (abra o Ollama)")
        return _item(nome, AVISO, "desligado (opcional: é a reserva sem internet)")
    usado = cerebro_local.modelo()
    if not any(cerebro_local._mesmo(m, usado) for m in instalados):
        return _item(nome, AVISO, f"aberto, mas sem nenhum modelo (rode: ollama pull {config.OLLAMA_MODELO})")
    detalhe = f"pronto com {usado}"
    if not cerebro_local._mesmo(usado, config.OLLAMA_MODELO):
        detalhe += f" ({config.OLLAMA_MODELO} não está baixado: ollama pull {config.OLLAMA_MODELO})"
    if "tools" not in cerebro_local.capacidades(usado):
        return _item(nome, AVISO, detalhe + "; esse modelo não sabe usar ferramentas, então pelo Ollama ela só "
                                            "conversa (use o qwen2.5:7b)")
    return _item(nome, OK, detalhe + ", com ferramentas")


def _ouvido() -> list[dict]:
    from . import identidade, ouvido

    itens = []
    o = ouvido.instancia()
    if not config.OUVIDO_LIGADO:
        return [_item("Microfone", AVISO, "desligado nas configurações")]
    if o is None and FORA_DO_APP:  # diagnostico.bat: o ouvido roda no app, aqui só dá para ver as peças
        mics = ouvido.microfones()
        if not config.VOSK_MODELO.exists():
            itens.append(_item("Microfone", ERRO, "modelo da palavra de ativação faltando (rode o instalar.bat)"))
        elif not mics:
            itens.append(_item("Microfone", ERRO, "nenhum microfone encontrado no Windows"))
        else:
            padrao = next((m["nome"] for m in mics if m["padrao"]), mics[0]["nome"])
            itens.append(_item("Microfone", OK, f"{len(mics)} encontrado(s), padrão: {padrao}; modelos instalados"))
    elif o is None:
        itens.append(_item("Microfone", ERRO, "o ouvido não iniciou (modelos faltando? rode o instalar.bat)"))
    else:
        s = o.status()
        if s["privado"]:
            itens.append(_item("Microfone", AVISO, "desligado pelo modo privado"))
        elif s["mudo"]:
            itens.append(_item("Microfone", AVISO, "desligado na bandeja"))
        elif not s["microfone"]:
            itens.append(_item("Microfone", ERRO, "não consegui abrir o microfone"))
        elif s["ultimo_audio_s"] is not None and s["ultimo_audio_s"] > 5:
            itens.append(_item("Microfone", ERRO, "aberto, mas sem áudio chegando"))
        else:
            itens.append(_item("Microfone", OK, f"ouvindo (ruído ambiente {s['ruido']}, sensibilidade "
                                                f"{config.LIMIAR_MIN:.0f})"))
        itens.append(_item("Palavra de ativação e transcrição", OK if s["vosk"] and s["whisper"] else AVISO,
                           "Vosk e Whisper carregados" if s["vosk"] and s["whisper"] else "Whisper ainda carregando"))
    pessoas = identidade.pessoas()
    if not identidade.disponivel():
        itens.append(_item("Reconhecer quem fala", ERRO, "modelo não instalado (rode o instalar.bat)"))
    elif not pessoas:
        itens.append(_item("Reconhecer quem fala", AVISO, "ninguém cadastrado: atendo qualquer voz"))
    else:
        itens.append(_item("Reconhecer quem fala", OK, f"{len(pessoas)} voz(es) cadastrada(s), modo {config.MODO_VOZ}"))
    return itens


def _voz_local() -> dict:
    from . import voz_local

    r = voz_local.resumo()
    if not r["instalado"]:
        return _item("Voz", ERRO, "a voz clonada no PC foi escolhida, mas não está instalada: rode o "
                                  "instalar_voz_local.bat (enquanto isso ela usa a voz pronta)")
    if not r["referencias"]:
        return _item("Voz", ERRO, "a voz clonada no PC não tem amostras: rode o clonar_voz.bat (enquanto isso ela "
                                  "usa a voz pronta)")
    srv = voz_local.servidor()
    srv.iniciar()
    s = srv.esperar(150)
    if not s or not s.get("pronto"):
        motivo = (s or {}).get("erro") or (s or {}).get("etapa") or "não abriu"
        return _item("Voz", ERRO if (s or {}).get("erro") else AVISO,
                     f"voz clonada no PC: {motivo} (veja dados/voz_local.log)")
    t = time.time()
    try:
        srv.falar("Teste de voz.", espera=90)
    except Exception as e:
        return _item("Voz", ERRO, f"voz clonada no PC falhou: {e}")
    ms = (time.time() - t) * 1000
    onde = f"na placa de vídeo ({s.get('gpu')})" if s.get("dispositivo") == "cuda" else \
        "no processador (lenta: o ideal é uma placa NVIDIA)"
    return _item("Voz", OK if ms < 2500 else AVISO, f"voz clonada no PC, {onde}, respondeu em {ms:.0f} ms")


def _voz() -> dict:
    from . import voz

    if config.VOZ_PROVEDOR == "local":
        return _voz_local()
    t = time.time()
    audio = voz.sintetizar_sync("Teste de voz.", espera=20)
    ms = (time.time() - t) * 1000
    if not audio:
        return _item("Voz", ERRO, "não consegui gerar a voz (vai usar a voz do sistema)")
    nome = {"edge": f"voz pronta {config.VOZ}", "elevenlabs": f"ElevenLabs ({config.ELEVENLABS_MODELO})",
            "local": "voz clonada no PC"}.get(config.VOZ_PROVEDOR, config.VOZ_PROVEDOR)
    return _item("Voz", OK if ms < 4000 else AVISO, f"{nome}, respondeu em {ms:.0f} ms")


def _contas() -> list[dict]:
    from . import agenda, spotify, steam

    itens = []
    if spotify.configurado():
        try:
            spotify.cliente().devices()
            itens.append(_item("Spotify", OK, "conectado"))
        except Exception as e:
            itens.append(_item("Spotify", ERRO, f"{e}"[:120]))
    else:
        itens.append(_item("Spotify", AVISO, "não configurado (opcional)"))
    if agenda.google_conectado():
        try:
            agenda._google_token()
            itens.append(_item("Google Agenda", OK, "conectada"))
        except Exception as e:
            itens.append(_item("Google Agenda", ERRO, f"{e}"[:120]))
    if agenda.outlook_conectado():
        try:
            agenda._ms_token()
            itens.append(_item("Outlook", OK, "conectado"))
        except Exception as e:
            itens.append(_item("Outlook", ERRO, f"{e}"[:120]))
    if not (agenda.google_conectado() or agenda.outlook_conectado()):
        itens.append(_item("Agenda", AVISO, "nenhuma agenda conectada (opcional)"))
    itens.append(_item("Steam", OK if steam.disponivel() else AVISO,
                       f"{len(steam.bibliotecas())} biblioteca(s)" if steam.disponivel() else "não encontrada (opcional)"))
    return itens


def _casa() -> dict:
    from . import ferramentas

    if not ferramentas.casa_configurada():
        return _item("Casa (Home Assistant)", AVISO, "não configurada (opcional)")
    try:
        r = httpx.get(f"{config.HA_URL}/api/", headers={"Authorization": f"Bearer {config.HA_TOKEN}"}, timeout=6)
        if r.status_code == 200:
            return _item("Casa (Home Assistant)", OK, "conectada")
        return _item("Casa (Home Assistant)", ERRO, f"respondeu {r.status_code} (confira o token)")
    except Exception as e:
        return _item("Casa (Home Assistant)", ERRO, f"sem resposta ({type(e).__name__})")


def versao_do_celular_publicada() -> bool | None:
    """O app publicado na Cloudflare é o desta versão? (compara a impressão digital dos arquivos no sw.js)"""
    import re

    from .publicar_celular import impressao_casca

    try:
        sw = httpx.get(config.NUVEM_URL.rstrip("/") + "/sw.js", timeout=6).text
    except Exception:
        return None
    m = re.search(r'ametista-casca-([0-9a-f]+)', sw)
    return None if not m else m.group(1) == impressao_casca()


def _celular() -> dict:
    from . import nuvem

    if not nuvem.configurada():
        return _item("App do celular", AVISO, "não publicado (opcional: publicar_celular.bat)")
    if versao_do_celular_publicada() is False:
        return _item("App do celular", AVISO, "publicado numa versão antiga: dê dois cliques em publicar_celular.bat "
                                              "para o celular receber a nova")
    if FORA_DO_APP:
        return _item("App do celular", OK, f"publicado em {config.NUVEM_URL} (a conexão é conferida com a Ametista aberta)")
    n = nuvem.instancia()
    return _item("App do celular", OK if n.conectada else ERRO,
                 "PC conectado ao serviço do celular" if n.conectada else "o PC não conseguiu se conectar ao serviço")


def _memoria() -> list[dict]:
    from . import arquivos, memoria, semantica

    itens = []
    try:
        n = memoria._consulta("SELECT COUNT(*) AS n FROM conversas")[0]["n"]
        f = len(memoria.fatos())
        c = memoria._consulta("SELECT COUNT(*) AS n FROM caderno")[0]["n"]
        itens.append(_item("Memória", OK, f"{f} fatos, {c} itens no caderno, {n} falas guardadas"))
    except Exception as e:
        itens.append(_item("Memória", ERRO, f"banco com problema: {e}"))
    if config.BUSCA_SEMANTICA:
        sit = semantica.situacao()
        itens.append(_item("Busca por significado", OK if sit == "ativa" else AVISO,
                           {"ativa": "ativa", "carregando": "carregando o modelo (fica pronta sozinha)",
                            "desligada": "desligada no painel: usando busca por palavras"}.get(
                               sit, "indisponível: usando busca por palavras")))
    total = arquivos.total()
    itens.append(_item("Índice de arquivos", OK if total else AVISO,
                       f"{total} arquivos" if total else "ainda montando (leva alguns minutos depois de ligar)"))
    return itens


def _sistema() -> list[dict]:
    import shutil
    from pathlib import Path

    import psutil

    itens = []
    uso = shutil.disk_usage(Path.home().anchor or "/")
    livre = uso.free / 1e9
    itens.append(_item("Disco", OK if livre > 10 else AVISO, f"{livre:.0f} GB livres no disco principal"))
    mem = psutil.virtual_memory()
    itens.append(_item("Memória RAM", OK if mem.percent < 90 else AVISO, f"{mem.percent:.0f}% usada"))
    cpu = psutil.cpu_percent(interval=0.5)
    itens.append(_item("Processador", OK if cpu < 90 else AVISO, f"{cpu:.0f}% em uso"))
    return itens


def _erros_recentes() -> dict:
    log = config.DADOS / "ametista.log"
    if not log.exists():
        return _item("Erros recentes", OK, "sem registro de erros")
    try:
        linhas = log.read_text(encoding="utf-8", errors="ignore").splitlines()[-3000:]
    except OSError:
        return _item("Erros recentes", AVISO, "não consegui ler o log")
    erros = [l for l in linhas if any(p in l.lower() for p in ("falhou", "erro", "error", "traceback"))]
    if not erros:
        return _item("Erros recentes", OK, "nenhum erro no log recente")
    return _item("Erros recentes", AVISO, f"{len(erros)} linha(s) de erro no log; a última: {erros[-1][:150]}")


FORA_DO_APP = False   # True no diagnostico.bat (processo separado do app)


def _app_aberto() -> dict:
    import socket

    with socket.socket() as sock:
        sock.settimeout(0.3)
        aberto = sock.connect_ex(("127.0.0.1", config.PORTA)) == 0
    return _item("Ametista aberta", OK if aberto else AVISO,
                 "rodando agora" if aberto else "fechada no momento (abra com o iniciar.bat)")


def executar() -> list[dict]:
    tarefas = [_internet, _claude, _ollama, _ouvido, _voz, _contas, _casa, _celular, _memoria, _sistema,
               _erros_recentes] + ([_app_aberto] if FORA_DO_APP else [])
    itens: list[dict] = [_item("Ametista", OK, f"versão {__version__}, Python {platform.python_version()}, "
                                               f"{platform.system()} {platform.release()}")]
    with ThreadPoolExecutor(max_workers=6) as ex:
        futuros = [ex.submit(t) for t in tarefas]
        for t, fut in zip(tarefas, futuros):
            try:
                r = fut.result(timeout=40)
            except Exception as e:
                r = _item(t.__name__.strip("_").capitalize(), ERRO, f"o teste falhou: {e}")
            itens += r if isinstance(r, list) else [r]
    return itens


def resumir(itens: list[dict]) -> str:
    erros = [i for i in itens if i["situacao"] == ERRO]
    avisos = [i for i in itens if i["situacao"] == AVISO and "opcional" not in i["detalhe"]]
    oks = sum(1 for i in itens if i["situacao"] == OK)
    if not erros and not avisos:
        return f"Fiz o diagnóstico: está tudo funcionando, {oks} itens ok."
    partes = [f"Fiz o diagnóstico: {oks} itens ok."]
    if erros:
        partes.append("Com problema: " + "; ".join(f"{i['item']}, {i['detalhe']}" for i in erros[:3]) + ".")
    if avisos:
        partes.append("Atenção: " + "; ".join(f"{i['item']}, {i['detalhe']}" for i in avisos[:3]) + ".")
    if not FORA_DO_APP:
        partes.append("O relatório completo está no painel.")
    return " ".join(partes)


def relatorio(itens: list[dict]) -> str:
    marcas = {OK: "[ OK ]", AVISO: "[AVISO]", ERRO: "[ERRO]"}
    linhas = [f"Diagnóstico da {config.NOME} — {datetime.now():%d/%m/%Y %H:%M}", ""]
    linhas += [f"{marcas[i['situacao']]} {i['item']}: {i['detalhe']}" for i in itens]
    return "\n".join(linhas)


ultimo: dict = {"itens": [], "quando": None}


def executar_e_resumir() -> str:
    itens = executar()
    ultimo.update(itens=itens, quando=datetime.now().isoformat(timespec="seconds"))
    try:
        (config.DADOS / "diagnostico.txt").write_text(relatorio(itens), encoding="utf-8")
    except OSError:
        pass
    eventos.publicar({"tipo": "diagnostico", "itens": itens, "quando": ultimo["quando"]})
    return resumir(itens)


if __name__ == "__main__":  # python -m ametista.diagnostico
    FORA_DO_APP = True
    itens = executar()
    print(relatorio(itens))
    print("\n" + resumir(itens))
    sys.exit(0)
