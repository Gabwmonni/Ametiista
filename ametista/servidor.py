"""Servidor local da Ametista: entrega a sobreposição (web/) e conversa por WebSocket."""
import asyncio
import threading
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import cerebro, config, eventos, ferramentas, memoria, nucleo, spotify, voz

WEB = config.RAIZ / "web"
conexoes: set[WebSocket] = set()


async def transmitir(msg: dict) -> None:
    for ws in list(conexoes):
        try:
            await ws.send_json(msg)
        except Exception:
            conexoes.discard(ws)


async def vigia_agenda() -> None:
    """A cada minuto, avisa dos compromissos que estão para começar (Google e Outlook)."""
    from . import agenda

    while True:
        await asyncio.sleep(60)
        try:
            for fala in await asyncio.to_thread(agenda.proximos_para_avisar):
                eventos.publicar({"tipo": "alerta", "texto": fala, "emocao": "surpresa",
                                  "audio": await voz.sintetizar(fala)})
        except Exception as e:
            print(f"[agenda] aviso falhou: {e}")


async def vigia_lembretes() -> None:
    """A cada segundo, dispara timers, alarmes e lembretes vencidos."""
    while True:
        for item in memoria.retirar_vencidos(datetime.now()):
            if item["tipo"] == "timer":
                fala = "Seu timer acabou!" if item["texto"] == "Timer" else f"Tempo esgotado: {item['texto']}"
            else:
                fala = f"Lembrete: {item['texto']}"
            eventos.publicar({"tipo": "alerta", "texto": fala, "emocao": "surpresa",
                              "audio": await voz.sintetizar(fala)})
        await asyncio.sleep(1)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    eventos.ligar_transmissor(asyncio.get_running_loop(), transmitir)
    tarefa = asyncio.create_task(vigia_lembretes())
    tarefa_agenda = asyncio.create_task(vigia_agenda())
    print(f"\n  {config.NOME} acordou em http://127.0.0.1:{config.PORTA}")
    print(f"  Nuvem (Claude): {'ativa - ' + config.CLAUDE_MODELO if config.ANTHROPIC_API_KEY else 'sem chave'}")
    print(f"  Local (Ollama): {'disponível' if cerebro.ollama_disponivel() else 'desligado'}")
    print(f"  Spotify: {'conectado' if spotify.conectado() else 'configurado' if spotify.configurado() else 'não configurado'}")
    print(f"  Casa (Home Assistant): {'configurada' if ferramentas.casa_configurada() else 'não configurada'}\n")
    yield
    tarefa.cancel()
    tarefa_agenda.cancel()


app = FastAPI(title="Ametista", lifespan=ciclo_de_vida)
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
async def inicio():
    return FileResponse(WEB / "sobreposicao.html")


@app.get("/api/estado")
async def estado():
    return {
        "nome": config.NOME,
        "nuvem": bool(config.ANTHROPIC_API_KEY),
        "spotify": spotify.conectado(),
        "casa": ferramentas.casa_configurada(),
        "lembretes": memoria.lembretes_pendentes(),
        "fatos": memoria.fatos(),
    }


@app.get("/api/chamar")
async def chamar():
    """Usado pelo atalho e por uma segunda instância para trazer a Ametista à tela."""
    eventos.publicar({"tipo": "chamar", "interno": True})
    return {"ok": True}


@app.post("/api/esquecer-conversa")
async def esquecer_conversa():
    memoria.limpar_historico()
    return {"ok": True}


# ------------------------------------------------------------------ Spotify
@app.get("/spotify/login")
async def spotify_login():
    if not spotify.configurado():
        return HTMLResponse(_pagina("Spotify não configurado",
                                    "Coloque o SPOTIFY_CLIENT_ID no arquivo .env e reinicie a Ametista."))
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
    return (f"<!doctype html><meta charset=utf-8><title>{titulo}</title>"
            "<body style='font-family:system-ui;background:#0d0816;color:#eee;display:grid;place-items:center;"
            f"height:100vh;margin:0'><div style='text-align:center'><h1>{titulo}</h1><p>{texto}</p></div>")


# ------------------------------------------------------------------ WebSocket
@app.websocket("/ws")
async def conversa(ws: WebSocket):
    # Segurança: só a própria Ametista pode conversar. Sem isso, qualquer site aberto
    # no navegador poderia se conectar em 127.0.0.1 e mandar comandos para o PC.
    origem = ws.headers.get("origin", "")
    if origem not in (f"http://127.0.0.1:{config.PORTA}", f"http://localhost:{config.PORTA}"):
        await ws.close(code=1008)
        return
    await ws.accept()
    conexoes.add(ws)
    try:
        while True:
            msg = await ws.receive_json()
            tipo = msg.get("tipo")
            if tipo == "texto":
                eventos.publicar({"tipo": "cancelar_escuta", "interno": True})
                threading.Thread(target=nucleo.atender, args=(msg.get("texto", ""),), daemon=True).start()
            elif tipo in ("fala_terminou", "esconder", "chamar", "cancelar_escuta"):
                eventos.publicar({"tipo": tipo, "interno": True})
    except WebSocketDisconnect:
        pass
    finally:
        conexoes.discard(ws)


def rodar_em_segundo_plano() -> threading.Thread:
    """Sobe o servidor numa thread (usado pelo app de desktop)."""
    import uvicorn

    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=config.PORTA, log_level="warning"))
    t = threading.Thread(target=servidor.run, daemon=True, name="servidor")
    t.start()
    return t
