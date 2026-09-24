// Notificações Web Push (chegam no celular mesmo com o app fechado).
//
// Padrões usados (sem bibliotecas, só WebCrypto):
//   RFC 8291 - criptografia da mensagem (aes128gcm)
//   RFC 8292 - VAPID (o servidor se identifica para o serviço de push do Google/Apple/Mozilla)

const enc = new TextEncoder();

export function b64url(bytes) {
  const b = bytes instanceof ArrayBuffer ? new Uint8Array(bytes) : bytes;
  let s = "";
  for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function deB64url(texto) {
  const s = atob(texto.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((texto.length + 3) % 4));
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
}

function juntar(...partes) {
  const total = partes.reduce((n, p) => n + p.length, 0);
  const saida = new Uint8Array(total);
  let i = 0;
  for (const p of partes) { saida.set(p, i); i += p.length; }
  return saida;
}

async function hmac(chave, dados) {
  const k = await crypto.subtle.importKey("raw", chave, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", k, dados));
}

// ------------------------------------------------------------------ chaves VAPID
export async function gerarVapid() {
  const par = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
  return {
    publica: b64url(await crypto.subtle.exportKey("raw", par.publicKey)),
    privada: await crypto.subtle.exportKey("jwk", par.privateKey),
  };
}

export async function jwtVapid(vapid, endpoint, contato) {
  const aud = new URL(endpoint).origin;
  const cabecalho = b64url(enc.encode(JSON.stringify({ typ: "JWT", alg: "ES256" })));
  const corpo = b64url(enc.encode(JSON.stringify({ aud, exp: Math.floor(Date.now() / 1000) + 12 * 3600, sub: contato })));
  const chave = await crypto.subtle.importKey("jwk", vapid.privada, { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const assinatura = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, chave, enc.encode(`${cabecalho}.${corpo}`));
  return `${cabecalho}.${corpo}.${b64url(assinatura)}`;
}

// ------------------------------------------------------------------ criptografia (RFC 8291)
export async function criptografar(inscricao, texto, sal = null, parLocal = null) {
  const uaPublica = deB64url(inscricao.keys.p256dh);
  const segredoAuth = deB64url(inscricao.keys.auth);
  const par = parLocal || await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
  const asPublica = new Uint8Array(await crypto.subtle.exportKey("raw", par.publicKey));
  const chaveUa = await crypto.subtle.importKey("raw", uaPublica, { name: "ECDH", namedCurve: "P-256" }, false, []);
  const segredoEcdh = new Uint8Array(await crypto.subtle.deriveBits({ name: "ECDH", public: chaveUa }, par.privateKey, 256));

  // IKM = HKDF(auth, ecdh, "WebPush: info" || 0 || ua_public || as_public, 32)
  const prkChave = await hmac(segredoAuth, segredoEcdh);
  const infoChave = juntar(enc.encode("WebPush: info\0"), uaPublica, asPublica, new Uint8Array([1]));
  const ikm = (await hmac(prkChave, infoChave)).slice(0, 32);

  sal = sal || crypto.getRandomValues(new Uint8Array(16));
  const prk = await hmac(sal, ikm);
  const cek = (await hmac(prk, juntar(enc.encode("Content-Encoding: aes128gcm\0"), new Uint8Array([1])))).slice(0, 16);
  const nonce = (await hmac(prk, juntar(enc.encode("Content-Encoding: nonce\0"), new Uint8Array([1])))).slice(0, 12);

  const claro = juntar(enc.encode(texto), new Uint8Array([2]));   // 2 = último registro, sem enchimento
  const chaveAes = await crypto.subtle.importKey("raw", cek, { name: "AES-GCM" }, false, ["encrypt"]);
  const cifrado = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce, tagLength: 128 }, chaveAes, claro));

  const rs = new Uint8Array([0, 0, 0x10, 0]);                        // tamanho do registro: 4096
  return juntar(sal, rs, new Uint8Array([asPublica.length]), asPublica, cifrado);
}

// ------------------------------------------------------------------ envio
export async function enviarPush(inscricao, dados, vapid, contato) {
  const corpo = await criptografar(inscricao, JSON.stringify(dados));
  const jwt = await jwtVapid(vapid, inscricao.endpoint, contato);
  return fetch(inscricao.endpoint, {
    method: "POST",
    headers: {
      "Content-Encoding": "aes128gcm",
      "Content-Type": "application/octet-stream",
      TTL: "86400",
      Urgency: "high",
      Authorization: `vapid t=${jwt}, k=${vapid.publica}`,
    },
    body: corpo,
  });
}
