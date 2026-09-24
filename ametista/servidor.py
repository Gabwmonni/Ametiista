"""Servidor local da Ametista: a sobreposição, o painel de configuração e a conversa por WebSocket.

Segurança (o servidor só escuta em 127.0.0.1, mas qualquer site aberto no navegador poderia tentar falar
com ele):
  - o endereço (Host) precisa ser 127.0.0.1 ou localhost (bloqueia o truque de "DNS rebinding");
  - toda chamada de /api precisa do cabeçalho X-Ametista-Token, uma chave nova a cada vez que a Ametista
    liga, que só as páginas servidas por ela conhecem;
  - o WebSocket confere a origem e a mesma chave.
"""
import asyncio
import re
import base64
import io
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import (__version__, acoes, agente, avisos, cerebro, config, estado, eventos, ferramentas, memoria, nucleo,
               spotify, voz)

WEB = config.RAIZ / "web"
TOKEN = secrets.token_urlsafe(24)
PORTA = config.PORTA  # a porta em que este servidor está rodando (mudar no painel só vale depois de reiniciar)
conexoes: set[WebSocket] = set()
SEM_TOKEN = {"/api/chamar", "/api/saude"}


def hosts_permitidos() -> set[str]:
    return {f"127.0.0.1:{PORTA}", f"localhost:{PORTA}"}


async def transmitir(msg: dict) -> None:
    for ws in list(conexoes):
        try:
            await ws.send_json(msg)
        except Exception:
            conexoes.discard(ws)


# ====================================================================== serviços em segundo plano
async def vigia_agenda() -> None:
    """A cada minuto, avisa dos compromissos que estão para começar (Google e Outlook)."""
    from . import agenda

    while True:
        await asyncio.sleep(60)
        try:
            for fala_ in await asyncio.to_thread(agenda.proximos_para_avisar):
                await asyncio.to_thread(avisos.alerta, fala_, "surpresa", "Compromisso")
        except Exception as e:
            print(f"[agenda] aviso falhou: {e}")


async def vigia_lembretes() -> None:
    """A cada segundo, dispara timers, alarmes, lembretes e aniversários."""
    while True:
        try:
            for item in await asyncio.to_thread(memoria.retirar_vencidos, datetime.now()):
                titulo = {"timer": "Timer", "aniversario": "Aniversário", "aniversario_vespera": "Aniversário"}.get(
                    item["tipo"], "Lembrete")
                threading.Thread(target=avisos.alerta, args=(ferramentas.texto_do_alerta(item), "surpresa", titulo),
                                 daemon=True).start()
        except Exception as e:
            print(f"[lembretes] erro: {e}")
        await asyncio.sleep(1)


async def faxina() -> None:
    while True:
        try:
            await asyncio.to_thread(memoria.limpar_antigas)
        except Exception as e:
            print(f"[memoria] limpeza falhou: {e}")
        await asyncio.sleep(24 * 3600)


_servicos_ligados = False


def iniciar_servicos() -> None:
    """Iniciativa, rotinas com horário e índice de arquivos (uma vez por processo)."""
    global _servicos_ligados
    if _servicos_ligados:
        return
    _servicos_ligados = True
    from . import arquivos, foco, proatividade, rotinas, semantica

    proatividade.iniciar()
    foco.ligar()
    rotinas.iniciar_agendador()
    arquivos.iniciar_vigia()
    semantica.aquecer(depois=memoria.vetorizar_pendentes)   # busca por significado fica pronta sozinha


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    eventos.ligar_transmissor(asyncio.get_running_loop(), transmitir)
    tarefas = [asyncio.create_task(t()) for t in (vigia_lembretes, vigia_agenda, faxina)]
    memoria.db()
    iniciar_servicos()
    print(f"\n  {config.NOME} {__version__} acordou em http://127.0.0.1:{PORTA}")
    print(f"  Nuvem (Claude): {'ativa - ' + config.CLAUDE_MODELO + ' / ' + config.CLAUDE_MODELO_FORTE if config.ANTHROPIC_API_KEY else 'sem chave'}")
    print(f"  Local (Ollama): {'disponível' if await asyncio.to_thread(cerebro.ollama_disponivel) else 'desligado'}")
    print(f"  Spotify: {'conectado' if spotify.conectado() else 'configurado' if spotify.configurado() else 'não configurado'}")
    print(f"  Casa (Home Assistant): {'configurada' if ferramentas.casa_configurada() else 'não configurada'}\n")
    yield
    for t in tarefas:
        t.cancel()


app = FastAPI(title="Ametista", lifespan=ciclo_de_vida, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def seguranca(request: Request, chamar_proximo):
    if request.headers.get("host", "") not in hosts_permitidos():
        return JSONResponse({"erro": "endereço não permitido"}, status_code=403)
    caminho = request.url.path
    if caminho.startswith("/api/") and caminho not in SEM_TOKEN:
        if not secrets.compare_digest(request.headers.get("x-ametista-token", ""), TOKEN):
            return JSONResponse({"erro": "não autorizado"}, status_code=401)
    resposta = await chamar_proximo(request)
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


app.mount("/static", StaticFiles(directory=WEB), name="static")


def _pagina_com_token(arquivo: str) -> HTMLResponse:
    html = (WEB / arquivo).read_text(encoding="utf-8").replace("{{TOKEN}}", TOKEN)
    return HTMLResponse(html)


@app.get("/")
async def inicio():
    return _pagina_com_token("sobreposicao.html")


@app.get("/painel")
async def painel():
    return _pagina_com_token("painel.html")


# ====================================================================== estado geral
INICIO = time.time()          # quando esta Ametista abriu (o instalador confere que é a nova que respondeu)


@app.get("/api/saude")
async def saude():
    return {"ok": True, "versao": __version__, "inicio": INICIO}


@app.get("/api/chamar")
async def chamar():
    """Usado pelo atalho e por uma segunda instância para trazer a Ametista à tela."""
    eventos.publicar({"tipo": "chamar", "interno": True})
    return {"ok": True}


def _inicial() -> dict:
    with memoria._trava:
        conversa = [{"papel": m["role"], "texto": m["content"], "quando": m["quando"].isoformat(timespec="seconds")}
                    for m in list(memoria._recente)[-40:]]
    return {"tipo": "inicial", "nome": config.NOME, "dono": config.DONO, "versao": __version__, **estado.resumo(),
            "avisos": avisos.lista()[:40], "tarefas": agente.listar(), "acoes": acoes.listar(40, somente_publico=True),
            "conversa": conversa, "pendente": (acoes.pendente() or {}).get("pergunta")}


@app.get("/api/estado")
async def api_estado():
    from . import nuvem

    return {**_inicial(), "nuvem": bool(config.ANTHROPIC_API_KEY), "spotify": spotify.conectado(),
            "casa": ferramentas.casa_configurada(), "celular": nuvem.configurada() and nuvem.instancia().conectada,
            "lembretes": memoria.lembretes_pendentes(), "fatos": memoria.fatos()}


# ====================================================================== configurações
def _campo_publico(c: config.Campo) -> dict:
    valor = config.valor_texto(c.chave)
    d = {"chave": c.chave, "rotulo": c.rotulo, "ajuda": c.ajuda, "tipo": c.tipo, "secao": c.secao,
         "opcoes": [{"valor": v, "rotulo": r} for v, r in c.opcoes], "reiniciar": c.reiniciar}
    if c.tipo == "segredo":
        d["valor"], d["definido"] = "", bool(valor)
        d["dica"] = f"••••{valor[-4:]}" if len(valor) > 8 else ("••••" if valor else "")
    else:
        d["valor"] = valor
    return d


@app.get("/api/config")
async def ler_config():
    campos = [_campo_publico(c) for c in config.CAMPOS if not c.oculto]
    secoes = list(dict.fromkeys(c["secao"] for c in campos))
    return {"secoes": secoes, "campos": campos}


@app.post("/api/config")
async def gravar_config(request: Request):
    corpo = await request.json()
    valores = {k: str(v) for k, v in (corpo.get("valores") or {}).items()}
    for k in list(valores):
        c = config.POR_CHAVE.get(k)
        if c is None or c.oculto:
            raise HTTPException(400, f"configuração desconhecida: {k}")
        if c.tipo == "segredo" and valores[k] == "":
            valores.pop(k)  # segredo em branco = manter o atual
    reiniciar = await asyncio.to_thread(config.salvar, valores)
    if "ANTHROPIC_API_KEY" in valores:
        cerebro.reiniciar_cliente()
    eventos.publicar({"tipo": "config_salva", "reiniciar": reiniciar})
    return {"ok": True, "reiniciar": reiniciar}


@app.post("/api/config/apagar-segredo")
async def apagar_segredo(request: Request):
    chave = (await request.json()).get("chave", "")
    if chave not in config.POR_CHAVE or config.POR_CHAVE[chave].tipo != "segredo":
        raise HTTPException(400, "chave inválida")
    await asyncio.to_thread(config.salvar, {chave: ""})
    return {"ok": True}


@app.get("/api/microfones")
async def api_microfones():
    from . import ouvido

    return {"microfones": await asyncio.to_thread(ouvido.microfones)}


_vozes_cache: list = []


@app.get("/api/vozes")
async def api_vozes():
    global _vozes_cache
    if not _vozes_cache:
        try:
            import edge_tts

            todas = await edge_tts.list_voices()
            _vozes_cache = [{"id": v["ShortName"], "nome": v["ShortName"].split("-")[-1].replace("Neural", ""),
                             "genero": v.get("Gender", "")} for v in todas if v["Locale"] in ("pt-BR", "pt-PT")]
        except Exception:
            _vozes_cache = [{"id": "pt-BR-FranciscaNeural", "nome": "Francisca", "genero": "Female"},
                            {"id": "pt-BR-ThalitaMultilingualNeural", "nome": "Thalita", "genero": "Female"},
                            {"id": "pt-BR-AntonioNeural", "nome": "Antonio", "genero": "Male"}]
    return {"vozes": _vozes_cache}


_VOZ_OK = re.compile(r"^[a-z]{2}-[A-Z]{2}-[A-Za-z]+Neural$")


@app.post("/api/testar-voz")
async def testar_voz(request: Request):
    """Ouve a voz. Com voz/velocidade/tom (vindos do painel, ainda sem salvar), ouve a combinação escolhida."""
    corpo = await request.json()
    texto = (corpo.get("texto") or f"Oi, {config.DONO}! Que bom te ouvir. Se precisar de alguma coisa, é só "
                                    "me chamar, tá bom?")[:300]
    previa = {k: str(corpo[k]) for k in ("voz", "velocidade", "tom") if corpo.get(k)}
    if previa and (corpo.get("provedor") or config.VOZ_PROVEDOR) == "edge":
        voz_id = previa.get("voz", config.VOZ)
        vel = previa.get("velocidade", config.VOZ_VELOCIDADE)
        tom = previa.get("tom", config.VOZ_TOM)
        if not (_VOZ_OK.match(voz_id) and re.fullmatch(r"[+-]\d{1,2}%", vel) and re.fullmatch(r"[+-]\d{1,2}Hz", tom)):
            return JSONResponse({"erro": "combinação de voz inválida"}, status_code=400)
        audio = await asyncio.to_thread(voz.amostra_edge, texto, voz_id, vel, tom)
    else:
        audio = await asyncio.to_thread(voz.sintetizar_sync, texto)
    return {"audio": audio, "mime": voz.mime_de(audio)}


@app.post("/api/testar-claude")
async def testar_claude():
    from . import diagnostico

    return await asyncio.to_thread(diagnostico._claude)


@app.get("/api/cidade")
async def buscar_cidade(q: str = ""):
    import httpx

    if len(q.strip()) < 2:
        return {"cidades": []}
    async with httpx.AsyncClient(timeout=8) as c:
        r = await c.get("https://geocoding-api.open-meteo.com/v1/search",
                        params={"name": q.strip(), "count": 6, "language": "pt", "format": "json"})
    res = r.json().get("results") or []
    return {"cidades": [{"nome": x["name"], "regiao": ", ".join(p for p in (x.get("admin1"), x.get("country")) if p),
                         "latitude": round(x["latitude"], 4), "longitude": round(x["longitude"], 4)} for x in res]}


@app.get("/api/identidade")
async def ler_identidade():
    arq = config.IDENTIDADE_DOC
    return {"texto": arq.read_text(encoding="utf-8") if arq.exists() else ""}


@app.post("/api/identidade")
async def gravar_identidade(request: Request):
    texto = (await request.json()).get("texto", "")
    if len(texto.strip()) < 40:
        raise HTTPException(400, "O documento ficou curto demais.")
    config.IDENTIDADE_DOC.write_text(texto.replace("\r\n", "\n"), encoding="utf-8")
    return {"ok": True}


# ====================================================================== pessoas
@app.get("/api/pessoas")
async def api_pessoas():
    from . import identidade

    return {"pessoas": identidade.pessoas(), "modo": config.MODO_VOZ, "disponivel": identidade.disponivel()}


@app.post("/api/pessoas/{acao}")
async def api_pessoas_acao(acao: str, request: Request):
    from . import identidade

    corpo = await request.json()
    nome, nivel = str(corpo.get("nome", "")).strip(), corpo.get("nivel", "familia")
    if not nome:
        raise HTTPException(400, "faltou o nome")
    if acao == "cadastrar":
        if nivel not in identidade.NIVEIS:
            raise HTTPException(400, "nível inválido")
        eventos.publicar({"tipo": "cadastrar", "nome": nome, "nivel": nivel, "interno": True})
        return {"ok": True}
    if acao == "remover":
        return {"ok": identidade.remover_pessoa(nome)}
    if acao == "nivel":
        if nivel not in identidade.NIVEIS:
            raise HTTPException(400, "nível inválido")
        return {"ok": identidade.alterar_nivel(nome, nivel)}
    raise HTTPException(404, "ação desconhecida")


# ====================================================================== histórico, ações, tarefas, avisos
@app.get("/api/acoes")
async def api_acoes(limite: int = 60):
    return {"acoes": acoes.listar(max(1, min(limite, 500)), somente_publico=True)}


@app.post("/api/acoes/desfazer")
async def api_desfazer(request: Request):
    id_ = int((await request.json()).get("id", 0))
    return {"resultado": await asyncio.to_thread(acoes.desfazer, id_)}


@app.get("/api/tarefas")
async def api_tarefas():
    return {"tarefas": agente.listar()}


@app.post("/api/tarefas/cancelar")
async def api_cancelar_tarefa(request: Request):
    return {"resultado": agente.cancelar(str((await request.json()).get("id", "")))}


@app.get("/api/avisos")
async def api_avisos():
    return {"avisos": avisos.lista()}


@app.get("/api/conversas")
async def api_conversas(dia: str = ""):
    try:
        d = date.fromisoformat(dia) if dia else date.today()
    except ValueError:
        raise HTTPException(400, "data inválida")
    ini = datetime.combine(d, datetime.min.time())
    return {"dia": d.isoformat(), "conversas": memoria.conversas_do_periodo(ini, ini + timedelta(days=1))}


@app.post("/api/conversas/apagar")
async def api_apagar_conversas():
    return {"apagadas": await asyncio.to_thread(memoria.apagar_conversas)}


@app.get("/api/memoria")
async def api_memoria():
    return {"fatos": memoria.fatos(), "caderno": memoria.caderno_listar(), "lembretes": memoria.lembretes_pendentes()}


@app.post("/api/memoria/{acao}")
async def api_memoria_acao(acao: str, request: Request):
    corpo = await request.json()
    if acao == "esquecer-fato":
        return {"resultado": memoria.esquecer_fato(corpo.get("texto", ""))
                if not memoria.esquecer_fato_exato(corpo.get("texto", "")) else "Esqueci."}
    if acao == "caderno-apagar":
        return {"apagados": memoria.caderno_apagar(corpo.get("nome", ""))}
    if acao == "caderno-guardar":
        return {"resultado": memoria.caderno_guardar(corpo.get("nome", ""), corpo.get("detalhes", ""),
                                                     corpo.get("categoria", "outro"))}
    if acao == "lembrete-cancelar":
        return {"ok": memoria.remover_lembrete(corpo.get("id", ""))}
    raise HTTPException(404, "ação desconhecida")


# ====================================================================== rotinas
@app.get("/api/rotinas")
async def api_rotinas():
    from . import rotinas

    return {"rotinas": rotinas.carregar(), "tipos": sorted(rotinas.TIPOS_PASSO)}


@app.post("/api/rotinas")
async def api_salvar_rotinas(request: Request):
    from . import rotinas

    lista = (await request.json()).get("rotinas")
    if not isinstance(lista, list):
        raise HTTPException(400, "formato inválido")
    try:
        for r in lista:
            if not str(r.get("nome", "")).strip():
                raise ValueError("toda rotina precisa de nome")
            r["passos"] = rotinas.validar_passos(r.get("passos"))
            if r.get("horario"):
                datetime.strptime(r["horario"], "%H:%M")
    except (ValueError, AttributeError) as e:
        raise HTTPException(400, str(e))
    rotinas.salvar(lista)
    return {"ok": True}


@app.post("/api/rotinas/executar")
async def api_executar_rotina(request: Request):
    nome = (await request.json()).get("nome", "")
    nucleo.atender_em_segundo_plano(f"executa a rotina {nome}")
    return {"ok": True}


# ====================================================================== controles
@app.post("/api/parar-tudo")
async def api_parar_tudo():
    return {"resultado": await asyncio.to_thread(nucleo.parar_tudo)}


@app.post("/api/privado")
async def api_privado(request: Request):
    estado.definir_privado(bool((await request.json()).get("valor")))
    return estado.resumo()


@app.post("/api/nao-perturbe")
async def api_nao_perturbe(request: Request):
    minutos = int((await request.json()).get("minutos", 60))
    return {"resultado": ferramentas.nao_perturbe(minutos), **estado.resumo()}


@app.post("/api/diagnostico")
async def api_diagnostico():
    from . import diagnostico

    resumo = await asyncio.to_thread(diagnostico.executar_e_resumir)
    return {"resumo": resumo, **diagnostico.ultimo}


@app.get("/api/log")
async def api_log():
    log = config.DADOS / "ametista.log"
    if not log.exists():
        return {"linhas": []}
    return {"linhas": log.read_text(encoding="utf-8", errors="ignore").splitlines()[-300:]}


@app.post("/api/reiniciar")
async def api_reiniciar():
    eventos.publicar({"tipo": "reiniciar", "interno": True})
    return {"ok": True}


# ====================================================================== contas e celular
@app.post("/api/contas/{qual}")
async def api_contas(qual: str):
    from . import agenda

    if qual == "spotify":
        if not spotify.configurado():
            raise HTTPException(400, "Coloque o Client ID do Spotify e salve antes.")
        return {"url": f"http://127.0.0.1:{PORTA}/spotify/login"}
    funcoes = {"google": agenda.conectar_google, "outlook": agenda.conectar_outlook}
    if qual not in funcoes:
        raise HTTPException(404, "conta desconhecida")

    def rodar():
        try:
            msg = funcoes[qual]()
        except Exception as e:
            msg = f"Não deu certo: {e}"
        eventos.publicar({"tipo": "aviso", "texto": msg})
    threading.Thread(target=rodar, daemon=True).start()
    return {"ok": True, "mensagem": "Abri o navegador para você autorizar."}


@app.get("/api/contas")
async def api_estado_contas():
    from . import agenda, nuvem, steam

    return {"spotify": {"configurado": spotify.configurado(), "conectado": spotify.conectado()},
            "google": {"configurado": agenda.GOOGLE_CRED.exists() or agenda.google_conectado(),
                       "conectado": agenda.google_conectado()},
            "outlook": {"configurado": bool(config.MS_CLIENT_ID), "conectado": agenda.outlook_conectado()},
            "celular": {"configurado": nuvem.configurada(), "conectado": nuvem.configurada() and nuvem.instancia().conectada},
            "casa": {"configurado": ferramentas.casa_configurada()}, "steam": {"encontrada": steam.disponivel()}}


@app.post("/api/celular/parear")
async def api_parear():
    from . import nuvem

    try:
        codigo, link = await asyncio.to_thread(nuvem.instancia().novo_codigo)
    except Exception as e:
        raise HTTPException(400, str(e))
    import qrcode

    img = qrcode.make(link, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return {"codigo": codigo, "link": link, "qr": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}


@app.post("/api/celular/revogar")
async def api_revogar():
    from . import nuvem

    return {"ok": await asyncio.to_thread(nuvem.instancia().revogar_celulares)}


# ====================================================================== Spotify (login pelo navegador)
@app.get("/spotify/login")
async def spotify_login():
    if not spotify.configurado():
        return HTMLResponse(_pagina("Spotify não configurado",
                                    "Coloque o Client ID do Spotify no painel de configurações e salve."))
    return RedirectResponse(spotify.url_login())


@app.get("/spotify/callback")
async def spotify_callback(code: str = "", error: str = ""):
    if error or not code:
        return HTMLResponse(_pagina("Spotify não conectado", f"O Spotify respondeu: {error or 'sem código'}."))
    try:
        await asyncio.to_thread(spotify.concluir_login, code)
    except Exception as e:
        return HTMLResponse(_pagina("Erro ao conectar", str(e)))
    return HTMLResponse(_pagina("Spotify conectado 💜", "Pode fechar esta aba e dizer: Ametista, toca alguma coisa."))


def _pagina(titulo: str, texto: str) -> str:
    import html

    titulo, texto = html.escape(titulo), html.escape(texto)
    return (f"<!doctype html><meta charset=utf-8><title>{titulo}</title>"
            "<body style='font-family:system-ui;background:#0d0816;color:#eee;display:grid;place-items:center;"
            f"height:100vh;margin:0'><div style='text-align:center'><h1>{titulo}</h1><p>{texto}</p></div>")


# ====================================================================== WebSocket da sobreposição
@app.websocket("/ws")
async def conversa(ws: WebSocket):
    origem = ws.headers.get("origin", "")
    permitidas = {f"http://{h}" for h in hosts_permitidos()}
    if origem not in permitidas or not secrets.compare_digest(ws.query_params.get("token", ""), TOKEN):
        await ws.close(code=1008)
        return
    await ws.accept()
    conexoes.add(ws)
    try:
        await ws.send_json(_inicial())
        while True:
            msg = await ws.receive_json()
            tipo = msg.get("tipo")
            if tipo == "texto":
                eventos.publicar({"tipo": "cancelar_escuta", "interno": True})
                nucleo.atender_em_segundo_plano(str(msg.get("texto", ""))[:2000])
            elif tipo in ("fala_terminou", "esconder", "chamar", "cancelar_escuta", "tamanho", "abrir_painel"):
                if tipo == "cancelar_escuta":  # Esc / clique no rosto: cala e cancela a resposta em andamento
                    estado.cancelar_pedidos("pc")
                eventos.publicar({**msg, "interno": True})
            elif tipo == "falando":
                estado.definir_falando(bool(msg.get("valor")))
            elif tipo == "parar_tudo":
                threading.Thread(target=nucleo.parar_tudo, daemon=True).start()
            elif tipo == "privado":
                estado.definir_privado(bool(msg.get("valor")))
            elif tipo == "desfazer":
                r = await asyncio.to_thread(acoes.desfazer, int(msg.get("id", 0)))
                eventos.publicar({"tipo": "aviso", "texto": r})
            elif tipo == "cancelar_tarefa":
                agente.cancelar(str(msg.get("id", "")))
            elif tipo == "responder":  # botões Sim/Não de uma confirmação
                nucleo.atender_em_segundo_plano("sim" if msg.get("resposta") == "sim" else "não")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[servidor] conexão da tela caiu: {e}")
    finally:
        conexoes.discard(ws)


def rodar_em_segundo_plano() -> threading.Thread:
    """Sobe o servidor numa thread (usado pelo app de desktop)."""
    import uvicorn

    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORTA, log_level="warning"))
    t = threading.Thread(target=servidor.run, daemon=True, name="servidor")
    t.start()
    return t
