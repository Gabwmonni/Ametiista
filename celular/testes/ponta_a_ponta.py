"""Teste de ponta a ponta da ponte do celular (rode com: npx wrangler dev --port 8787, CHAVE_PC=chave-de-teste-123)."""
import base64
import hashlib
import json
import sys
import time
import warnings

warnings.simplefilter("ignore", DeprecationWarning)
import httpx
from websockets.sync.client import connect
B = "http://127.0.0.1:8787"
W = "ws://127.0.0.1:8787"
ok = lambda c, m: print(("OK  " if c else "FALHA ") + m) or bool(c)
res = []
# PC conecta com a chave errada e a certa
try:
    connect(W + "/api/ws?papel=pc", additional_headers={"x-chave": "errada"}, open_timeout=5).close(); res.append(ok(False, "chave errada aceita"))
except Exception:
    res.append(ok(True, "PC com chave errada é recusado"))
pc = connect(W + "/api/ws?papel=pc", additional_headers={"x-chave": "chave-de-teste-123"}, open_timeout=5)
quem_olha = []   # avisos da ponte para o PC: quantos celulares estão com o app aberto


def pc_recv():
    """Próxima mensagem para o PC, guardando à parte os avisos de quem está olhando."""
    while True:
        m = json.loads(pc.recv(timeout=5))
        if m.get("tipo") in ("rele", "celulares"):
            quem_olha.append(m)
            continue
        return m


primeira = json.loads(pc.recv(timeout=5))
res.append(ok(primeira["tipo"] == "rele" and primeira["versao"] == 2 and primeira["celulares"] == 0,
              "ponte avisa o PC que é a versão nova (ninguém olhando ainda)"))
pc.send(json.dumps({"tipo": "ola", "ligado_desde": int(time.time()*1000) - 60000, "info": {"nome": "PC", "cpu": 3, "privado": False}}))
codigo = "ABCD2345"
pc.send(json.dumps({"tipo": "parear_codigo", "hash": hashlib.sha256(codigo.encode()).hexdigest()}))
time.sleep(0.3)
r = httpx.post(B + "/api/parear", json={"codigo": "ERRADO11", "nome": "x"})
res.append(ok(r.status_code == 403, "código errado recusado"))
r = httpx.post(B + "/api/parear", json={"codigo": "abcd 2345", "nome": "Celular teste"})
token = r.json().get("token", "")
res.append(ok(r.status_code == 200 and len(token) > 20, "pareamento com código (minúsculas e espaço) funciona"))
avisou = pc_recv()
res.append(ok(avisou["tipo"] == "celular_pareado", "PC avisado do pareamento"))
r = httpx.post(B + "/api/parear", json={"codigo": codigo})
res.append(ok(r.status_code == 403, "código é de uso único"))
e = httpx.get(B + "/api/estado", headers={"authorization": "Bearer " + token}).json()
res.append(ok(e["online"] and e["info"]["cpu"] == 3, "estado: PC online"))
cel = connect(W + f"/api/ws?papel=celular&token={token}", open_timeout=5)
inicial = json.loads(cel.recv(timeout=5))
res.append(ok(inicial["tipo"] == "estado" and inicial["online"] and "notificacoes" in inicial,
              "celular conecta e recebe o estado (com os avisos guardados)"))
m = json.loads(pc.recv(timeout=5))
res.append(ok(m == {"tipo": "celulares", "celulares": 1}, "PC fica sabendo que um celular abriu o app"))
pc.send(json.dumps({"tipo": "status", "info": {"cpu": 7}}))
m = json.loads(cel.recv(timeout=5))
res.append(ok(m["tipo"] == "estado" and m["info"]["cpu"] == 7 and "notificacoes" not in m,
              "status periódico chega sem repetir os avisos antigos"))
for tipo, extra in (("pedido", {"texto": "que horas são"}), ("parar_tudo", {}), ("privado", {"valor": True}), ("tarefas", {}), ("cancelar_tarefa", {"tarefa": "t1"})):
    cel.send(json.dumps({"tipo": tipo, "id": "p1", **extra}))
    m = pc_recv()
    res.append(ok(m["tipo"] == tipo and m.get("de"), f"celular -> PC: {tipo}"))
    de = m["de"]
cel.send(json.dumps({"tipo": "hackear", "id": "x"}))
pc.send(json.dumps({"tipo": "resposta", "para": de, "id": "p1", "texto": "São 10:00."}))
m = json.loads(cel.recv(timeout=5))
res.append(ok(m["tipo"] == "resposta" and m["texto"] == "São 10:00." and "para" not in m, "PC -> celular: resposta (tipo desconhecido ignorado)"))
pc.send(json.dumps({"tipo": "tarefa", "tarefa": {"id": "t1", "objetivo": "organizar", "estado": "executando", "progresso": 50}}))
m = json.loads(cel.recv(timeout=5))
res.append(ok(m["tipo"] == "tarefa" and m["tarefa"]["progresso"] == 50, "andamento da tarefa chega ao celular"))
h = {"authorization": "Bearer " + token}
chave = httpx.get(B + "/api/push/chave", headers=h).json()["chave"]
bruto = base64.urlsafe_b64decode(chave + "=" * (-len(chave) % 4))
res.append(ok(len(bruto) == 65 and bruto[0] == 4, "chave VAPID gerada (65 bytes)"))
res.append(ok(httpx.get(B + "/api/push/chave", headers=h).json()["chave"] == chave, "chave VAPID é estável"))
res.append(ok(httpx.get(B + "/api/push/chave").status_code == 401, "push exige token"))
r = httpx.post(B + "/api/push/inscrever", headers=h, json={"inscricao": {"endpoint": "http://inseguro/x", "keys": {"p256dh": "a", "auth": "b"}}})
res.append(ok(r.status_code == 400, "inscrição sem https recusada"))
import os
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
k = ec.generate_private_key(ec.SECP256R1())
pub = k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
r = httpx.post(B + "/api/push/inscrever", headers=h, json={"inscricao": {"endpoint": "https://push.invalido.example/abc", "keys": {"p256dh": b64(pub), "auth": b64(os.urandom(16))}}})
res.append(ok(r.status_code == 200, "inscrição de push aceita"))
pc.send(json.dumps({"tipo": "notificar", "titulo": "Instalação concluída", "texto": "ELDEN RING terminou de instalar!"}))
m = json.loads(cel.recv(timeout=15))
res.append(ok(m["tipo"] == "notificacao" and "ELDEN" in m["texto"], "notificação chega ao celular aberto (push para endpoint inválido não quebra)"))
r = httpx.post(B + "/api/push/testar", headers=h)
res.append(ok(r.status_code == 200 and r.json()["enviados"] == 0, "teste de push responde (0 enviados: endpoint falso)"))
antes = httpx.get(B + "/api/estado", headers=h).json()["ultimo"]
time.sleep(0.05)
pc.send(json.dumps({"tipo": "vivo"}))
time.sleep(0.3)
e = httpx.get(B + "/api/estado", headers=h).json()
res.append(ok(e["online"] and e["ultimo"] > antes and e["info"]["cpu"] == 7,
              '"estou vivo" do PC mantém online sem mandar o status completo'))
pc.send(json.dumps({"tipo": "revogar_celulares"}))
try:
    cel.recv(timeout=5); fechou = False
except Exception as ex:
    fechou = "4001" in str(ex)
res.append(ok(fechou, "revogar desconecta o celular (código 4001)"))
m = json.loads(pc.recv(timeout=5))
res.append(ok(m == {"tipo": "celulares", "celulares": 0}, "PC fica sabendo que ninguém mais está olhando"))
res.append(ok(httpx.get(B + "/api/estado", headers=h).status_code == 401, "token revogado não vale mais"))
print(f"\n{sum(res)}/{len(res)} ok")
