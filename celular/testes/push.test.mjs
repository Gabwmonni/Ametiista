// Testa a criptografia Web Push (RFC 8291) decifrando com uma implementação independente (node:crypto).
// Rode com: node --test celular/testes
import { test } from "node:test";
import assert from "node:assert/strict";
import * as nodeCrypto from "node:crypto";
import { criptografar, gerarVapid, b64url, deB64url } from "../src/push.js";

function decifrar(corpo, uaPrivada, uaPublica, auth) {
  const sal = corpo.subarray(0, 16);
  const rs = corpo.readUInt32BE(16);
  const idlen = corpo[20];
  const asPublica = corpo.subarray(21, 21 + idlen);
  const cifrado = corpo.subarray(21 + idlen);
  assert.equal(rs, 4096);
  const ecdh = nodeCrypto.createECDH("prime256v1");
  ecdh.setPrivateKey(uaPrivada);
  const segredo = ecdh.computeSecret(asPublica);
  const info = Buffer.concat([Buffer.from("WebPush: info\0"), uaPublica, asPublica]);
  const ikm = Buffer.from(nodeCrypto.hkdfSync("sha256", segredo, auth, info, 32));
  const cek = Buffer.from(nodeCrypto.hkdfSync("sha256", ikm, sal, Buffer.from("Content-Encoding: aes128gcm\0"), 16));
  const nonce = Buffer.from(nodeCrypto.hkdfSync("sha256", ikm, sal, Buffer.from("Content-Encoding: nonce\0"), 12));
  const d = nodeCrypto.createDecipheriv("aes-128-gcm", cek, nonce);
  d.setAuthTag(cifrado.subarray(cifrado.length - 16));
  const claro = Buffer.concat([d.update(cifrado.subarray(0, cifrado.length - 16)), d.final()]);
  assert.equal(claro[claro.length - 1], 2, "delimitador de último registro");
  return claro.subarray(0, claro.length - 1).toString("utf8");
}

test("mensagem criptografada é lida pelo celular", async () => {
  const ua = nodeCrypto.createECDH("prime256v1");
  const uaPublica = ua.generateKeys();
  const auth = nodeCrypto.randomBytes(16);
  const inscricao = { endpoint: "https://push.example.com/abc", keys: { p256dh: b64url(uaPublica), auth: b64url(auth) } };
  const texto = JSON.stringify({ titulo: "Instalação concluída", texto: "ELDEN RING terminou de instalar! 💜 ação" });
  const corpo = Buffer.from(await criptografar(inscricao, texto));
  assert.equal(decifrar(corpo, ua.getPrivateKey(), uaPublica, auth), texto);
});

test("chaves VAPID e base64url", async () => {
  const v = await gerarVapid();
  const bruto = deB64url(v.publica);
  assert.equal(bruto.length, 65);
  assert.equal(bruto[0], 4);
  assert.equal(b64url(bruto), v.publica);
  assert.equal(v.privada.kty, "EC");
});

test("assinatura VAPID (ES256) é válida para o serviço de push", async () => {
  const { jwtVapid } = await import("../src/push.js");
  const v = await gerarVapid();
  const jwt = await jwtVapid(v, "https://fcm.googleapis.com/fcm/send/xyz", "https://ametista.exemplo.workers.dev");
  const [cab, corpo, assinatura] = jwt.split(".");
  const dados = JSON.parse(Buffer.from(deB64url(corpo)).toString());
  assert.equal(dados.aud, "https://fcm.googleapis.com");
  assert.ok(dados.exp > Date.now() / 1000);
  const chave = nodeCrypto.createPublicKey({ key: { kty: "EC", crv: "P-256", x: v.privada.x, y: v.privada.y }, format: "jwk" });
  const ok = nodeCrypto.verify("sha256", Buffer.from(`${cab}.${corpo}`), { key: chave, dsaEncoding: "ieee-p1363" },
    Buffer.from(deB64url(assinatura)));
  assert.ok(ok);
});
