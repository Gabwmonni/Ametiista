"""Spotify Premium: tocar qualquer música, artista, álbum ou playlist pelo nome.

Configuração (uma vez):
  1. https://developer.spotify.com/dashboard -> Create app
  2. Redirect URI: http://127.0.0.1:8765/spotify/callback   (marque "Web API")
  3. Copie o Client ID para SPOTIFY_CLIENT_ID no .env
  4. Na bandeja da Ametista: "Conectar Spotify" (autoriza no navegador)
"""
import os
import re
import socket
import subprocess
import sys
import time
import unicodedata
import webbrowser

from . import config

ESCOPOS = ("user-read-playback-state user-modify-playback-state user-read-currently-playing "
           "user-library-read user-library-modify playlist-read-private playlist-read-collaborative")
REDIRECT = f"http://127.0.0.1:{config.PORTA}/spotify/callback"
CACHE = config.DADOS / "spotify_token.json"

_auth = None
_sp = None


def configurado() -> bool:
    return bool(config.SPOTIFY_CLIENT_ID)


def conectado() -> bool:
    return configurado() and CACHE.exists()


def autenticador():
    global _auth
    if _auth is None:
        from spotipy.cache_handler import CacheFileHandler
        from spotipy.oauth2 import SpotifyPKCE

        _auth = SpotifyPKCE(client_id=config.SPOTIFY_CLIENT_ID, redirect_uri=REDIRECT, scope=ESCOPOS,
                            cache_handler=CacheFileHandler(cache_path=str(CACHE)), open_browser=False)
    return _auth


def url_login() -> str:
    return autenticador().get_authorize_url()


def concluir_login(codigo: str) -> None:
    global _sp
    autenticador().get_access_token(codigo, check_cache=False)
    _sp = None


def cliente():
    global _sp
    if not configurado():
        raise RuntimeError("Spotify não configurado: coloque SPOTIFY_CLIENT_ID no .env.")
    if not CACHE.exists():
        raise RuntimeError("Spotify ainda não conectado: use 'Conectar Spotify' no ícone da bandeja.")
    if _sp is None:
        import spotipy

        _sp = spotipy.Spotify(auth_manager=autenticador(), requests_timeout=8, retries=1)
    return _sp


# ------------------------------------------------------------------ aparelhos
def _abrir_app_spotify() -> None:
    if sys.platform == "win32":
        os.startfile("spotify:")  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-a", "Spotify"])
    else:
        subprocess.Popen(["spotify"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _escolher_aparelho(sp, nome: str | None = None) -> str:
    """Devolve o id do aparelho: o pedido, o ativo, este PC ou abre o Spotify do PC."""
    for tentativa in range(12):
        aparelhos = sp.devices().get("devices", [])
        if nome:
            alvo = _norm(nome)
            for a in aparelhos:
                if alvo in _norm(a["name"]) or alvo in _norm(a["type"]):
                    return a["id"]
            if tentativa == 0:
                raise RuntimeError(f"Não achei o aparelho '{nome}'. Disponíveis: "
                                   + (", ".join(a["name"] for a in aparelhos) or "nenhum"))
        for a in aparelhos:
            if a.get("is_active"):
                return a["id"]
        meu_pc = _norm(socket.gethostname())
        for a in aparelhos:
            if a["type"] == "Computer" and _norm(a["name"]) == meu_pc:
                return a["id"]
        for a in aparelhos:
            if a["type"] == "Computer":
                return a["id"]
        if tentativa == 0:
            _abrir_app_spotify()  # nenhum aparelho: abre o Spotify deste PC e espera ele aparecer
        time.sleep(1)
    raise RuntimeError("O Spotify não apareceu como aparelho. Abra o app do Spotify e tente de novo.")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return re.sub(r"[^a-z0-9 ]", "", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


# ------------------------------------------------------------------ busca
def _limpar_pedido(busca: str) -> tuple[str, str]:
    """'a playlist de rock' -> ('rock', 'playlist'); 'músicas do Coldplay' -> ('Coldplay', 'artista')."""
    b = busca.strip()
    b = re.sub(r"\s+(no|pelo|do) spotify$", "", b, flags=re.I)
    regras = [
        (r"^(a |uma )?playlist\s+(de |do |da |chamada )?", "playlist"),
        (r"^(o |um )?[áa]lbum\s+(de |do |da )?", "album"),
        (r"^(as )?m[úu]sicas\s+(de |do |da |dos |das )", "artista"),
        (r"^(algo|alguma coisa)\s+(de |do |da |dos |das )", "artista"),
        (r"^(o |a )?(artista|banda|cantora?)\s+", "artista"),
        (r"^(a |uma )?m[úu]sica\s+", "musica"),
        (r"^(minhas )?(m[úu]sicas )?curtidas$", "curtidas"),
    ]
    for padrao, tipo in regras:
        if re.search(padrao, b, re.I):
            return re.sub(padrao, "", b, flags=re.I).strip() or b, tipo
    return b, "auto"


def _buscar(sp, busca: str, tipo: str) -> dict:
    """Devolve {'uris':[...]} para faixa ou {'context_uri':...} para artista/álbum/playlist."""
    if tipo == "curtidas":
        itens = sp.current_user_saved_tracks(limit=50)["items"]
        if not itens:
            raise RuntimeError("Você ainda não tem músicas curtidas.")
        return {"uris": [i["track"]["uri"] for i in itens], "nome": "suas músicas curtidas"}

    if tipo == "playlist":  # primeiro as playlists da própria pessoa
        for p in sp.current_user_playlists(limit=50).get("items", []):
            if p and _norm(busca) in _norm(p["name"]):
                return {"context_uri": p["uri"], "nome": f"a playlist {p['name']}"}

    mapa = {"musica": "track", "artista": "artist", "album": "album", "playlist": "playlist",
            "auto": "track,artist,playlist"}
    r = sp.search(q=busca, type=mapa[tipo], limit=5, market="from_token")
    faixas = [x for x in (r.get("tracks") or {}).get("items", []) if x]
    artistas = [x for x in (r.get("artists") or {}).get("items", []) if x]
    listas = [x for x in (r.get("playlists") or {}).get("items", []) if x]
    albuns = [x for x in (r.get("albums") or {}).get("items", []) if x]

    if tipo == "auto":
        # nome batendo com um artista -> toca o artista; senão a faixa mais relevante
        if artistas and _parecido(busca, artistas[0]["name"]):
            tipo = "artista"
        elif faixas:
            tipo = "musica"
        elif artistas:
            tipo = "artista"
        elif listas:
            tipo = "playlist"
    if tipo == "musica" and faixas:
        f = faixas[0]
        return {"uris": [f["uri"]], "nome": f"{f['name']}, de {f['artists'][0]['name']}"}
    if tipo == "artista" and artistas:
        return {"context_uri": artistas[0]["uri"], "nome": artistas[0]["name"], "tipo": "artista"}
    if tipo == "album" and albuns:
        a = albuns[0]
        return {"context_uri": a["uri"], "nome": f"o álbum {a['name']}, de {a['artists'][0]['name']}"}
    if tipo == "playlist" and listas:
        return {"context_uri": listas[0]["uri"], "nome": f"a playlist {listas[0]['name']}"}
    raise RuntimeError(f"Não encontrei '{busca}' no Spotify.")


def _parecido(a: str, b: str) -> bool:
    a, b = _norm(a).replace(" ", ""), _norm(b).replace(" ", "")
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    from difflib import SequenceMatcher

    return SequenceMatcher(None, a, b).ratio() >= 0.8


# ------------------------------------------------------------------ ações (ferramentas)
def tocar(busca: str = "", tipo: str = "auto", aparelho: str = "", aleatorio: bool = False) -> str:
    sp = cliente()
    if not busca:
        return continuar()
    if tipo == "auto":
        busca, tipo = _limpar_pedido(busca)
    alvo = _buscar(sp, busca, tipo)
    dev = _escolher_aparelho(sp, aparelho or None)
    if aleatorio or alvo.get("tipo", tipo) in ("artista", "curtidas"):
        try:
            sp.shuffle(True, device_id=dev)
        except Exception:
            pass
    if "uris" in alvo:
        sp.start_playback(device_id=dev, uris=alvo["uris"])
    else:
        sp.start_playback(device_id=dev, context_uri=alvo["context_uri"])
    return f"Tocando {alvo['nome']}."


def controle(acao: str) -> str:
    sp = cliente()
    dev = _escolher_aparelho(sp)
    if acao == "pausar":
        sp.pause_playback(device_id=dev)
    elif acao == "continuar":
        return continuar()
    elif acao == "proxima":
        sp.next_track(device_id=dev)
    elif acao == "anterior":
        sp.previous_track(device_id=dev)
    elif acao in ("aleatorio_ligar", "aleatorio_desligar"):
        sp.shuffle(acao == "aleatorio_ligar", device_id=dev)
    elif acao in ("repetir_faixa", "repetir_lista", "repetir_desligar"):
        sp.repeat({"repetir_faixa": "track", "repetir_lista": "context", "repetir_desligar": "off"}[acao],
                  device_id=dev)
    else:
        return f"Ação desconhecida: {acao}"
    return "Feito."


def continuar() -> str:
    sp = cliente()
    dev = _escolher_aparelho(sp)
    sp.start_playback(device_id=dev)
    return "Continuando."


def volume(percentual: int) -> str:
    sp = cliente()
    sp.volume(max(0, min(100, int(percentual))), device_id=_escolher_aparelho(sp))
    return f"Volume do Spotify em {int(percentual)}%."


def tocando() -> str:
    sp = cliente()
    atual = sp.current_playback()
    if not atual or not atual.get("item"):
        return "Nada tocando no Spotify agora."
    f = atual["item"]
    estado = "tocando" if atual.get("is_playing") else "pausado"
    return (f"{estado}: {f['name']} - {', '.join(a['name'] for a in f.get('artists', []))} "
            f"(álbum {f.get('album', {}).get('name', '?')}), no aparelho {atual['device']['name']}.")


def curtir() -> str:
    sp = cliente()
    atual = sp.current_playback()
    if not atual or not atual.get("item"):
        return "Nada tocando para curtir."
    sp.current_user_saved_tracks_add([atual["item"]["uri"]])
    return f"Curti {atual['item']['name']}."


def fila(busca: str) -> str:
    sp = cliente()
    alvo = _buscar(sp, _limpar_pedido(busca)[0], "musica")
    sp.add_to_queue(alvo["uris"][0], device_id=_escolher_aparelho(sp))
    return f"Coloquei na fila: {alvo['nome']}."


def aparelhos() -> str:
    sp = cliente()
    lista = sp.devices().get("devices", [])
    if not lista:
        return "Nenhum aparelho com Spotify aberto."
    return "\n".join(f"{a['name']} ({a['type']}){' - ativo' if a.get('is_active') else ''}" for a in lista)


def transferir(aparelho: str) -> str:
    sp = cliente()
    sp.transfer_playback(_escolher_aparelho(sp, aparelho), force_play=True)
    return f"Música transferida para {aparelho}."


def abrir_login() -> None:
    webbrowser.open(f"http://127.0.0.1:{config.PORTA}/spotify/login")


DEFINICOES = [
    {"name": "spotify_tocar",
     "description": "Toca no Spotify uma música, artista, álbum, playlist ou as músicas curtidas. "
                    "Corrija nomes mal transcritos (ex.: 'code play' -> 'Coldplay').",
     "input_schema": {"type": "object", "properties": {
         "busca": {"type": "string", "description": "O que tocar, ex.: 'Bohemian Rhapsody', 'Coldplay'"},
         "tipo": {"type": "string", "enum": ["auto", "musica", "artista", "album", "playlist", "curtidas"]},
         "aparelho": {"type": "string", "description": "Opcional: nome do aparelho (ex.: 'celular', 'TV')"},
         "aleatorio": {"type": "boolean"}}, "required": ["busca"]}},
    {"name": "spotify_controle",
     "description": "Controla o que está tocando no Spotify.",
     "input_schema": {"type": "object", "properties": {"acao": {"type": "string", "enum": [
         "pausar", "continuar", "proxima", "anterior", "aleatorio_ligar", "aleatorio_desligar",
         "repetir_faixa", "repetir_lista", "repetir_desligar"]}}, "required": ["acao"]}},
    {"name": "spotify_volume", "description": "Volume do Spotify (0-100).",
     "input_schema": {"type": "object", "properties": {"percentual": {"type": "integer"}},
                      "required": ["percentual"]}},
    {"name": "spotify_tocando", "description": "Diz qual música está tocando.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "spotify_curtir", "description": "Curte (salva) a música que está tocando.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "spotify_fila", "description": "Adiciona uma música à fila.",
     "input_schema": {"type": "object", "properties": {"busca": {"type": "string"}}, "required": ["busca"]}},
    {"name": "spotify_aparelhos", "description": "Lista aparelhos com Spotify disponível.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "spotify_transferir", "description": "Passa a música para outro aparelho (celular, TV, caixa).",
     "input_schema": {"type": "object", "properties": {"aparelho": {"type": "string"}},
                      "required": ["aparelho"]}},
]

FUNCOES = {
    "spotify_tocar": tocar, "spotify_controle": controle, "spotify_volume": volume,
    "spotify_tocando": tocando, "spotify_curtir": curtir, "spotify_fila": fila,
    "spotify_aparelhos": aparelhos, "spotify_transferir": transferir,
}
