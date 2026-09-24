"""Sobe o app de desktop inteiro (Qt + servidor), conversa pelo WebSocket e confere a resposta falada.

Rodado pelo GitHub Actions no Windows (sem microfone, tela "offscreen").
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from websockets.sync.client import connect

RAIZ = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp())
PORTA = 8799
BASE = f"http://127.0.0.1:{PORTA}"
env = {**os.environ, "AMETISTA_DADOS": str(TMP / "dados"), "AMETISTA_ENV": str(TMP / ".env"), "OUVIDO_LIGADO": "0",
       "PORTA": str(PORTA), "QT_QPA_PLATFORM": os.environ.get("QT_QPA_PLATFORM", "offscreen"), "PYTHONUTF8": "1"}
log = open(TMP / "saida.log", "w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, "-m", "ametista"], cwd=RAIZ, env=env, stdout=log, stderr=subprocess.STDOUT)


def falhar(msg):
    log.flush()
    print("FALHOU:", msg)
    print((TMP / "saida.log").read_text(encoding="utf-8", errors="ignore")[-6000:])
    proc.kill()
    sys.exit(1)


try:
    for _ in range(120):
        try:
            if httpx.get(f"{BASE}/api/saude", timeout=1).status_code == 200:
                break
        except Exception:
            pass
        if proc.poll() is not None:
            falhar(f"o app fechou sozinho (código {proc.returncode})")
        time.sleep(0.5)
    else:
        falhar("o servidor não subiu em 60 s")
    html = httpx.get(BASE + "/").text
    token = re.search(r'data-token="([^"]+)"', html).group(1)
    estado = httpx.get(BASE + "/api/estado", headers={"X-Ametista-Token": token}).json()
    assert estado["versao"] == "2.0", estado
    assert httpx.get(BASE + "/painel").status_code == 200
    with connect(f"ws://127.0.0.1:{PORTA}/ws?token={token}", origin=BASE, open_timeout=10) as ws:
        inicial = json.loads(ws.recv(timeout=10))
        assert inicial["tipo"] == "inicial"
        ws.send(json.dumps({"tipo": "texto", "texto": "que horas são?"}))
        trecho = None
        fim = time.time() + 60
        while time.time() < fim:
            m = json.loads(ws.recv(timeout=60))
            if m["tipo"] == "fala_trecho":
                trecho = m
                break
        if not trecho:
            falhar("não recebi a resposta falada")
        print("resposta:", trecho["texto"], "| áudio:", "sim" if trecho["audio"] else "voz do sistema")
        assert trecho["texto"].startswith("São ")
    time.sleep(3)
    if proc.poll() is not None:
        falhar("o app caiu depois de responder")
    print("OK: app de desktop funcionando")
finally:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
