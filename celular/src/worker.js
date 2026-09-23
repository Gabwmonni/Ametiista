// Ametista — ponte entre o celular e o PC (Cloudflare Worker + Durable Object).
//
// O PC abre uma conexão de saída para cá (não precisa abrir portas no roteador).
// O celular conecta aqui também, e o "Rele" repassa as mensagens entre os dois.
// Autenticação:
//   PC      -> chave secreta CHAVE_PC (mesma do NUVEM_CHAVE no .env do PC)
//   celular -> token recebido no pareamento (código mostrado pelo PC, vale 10 minutos)

import { DurableObject } from "cloudflare:workers";

const ONLINE_SEM_SINAL_MS = 90_000; // sem notícias do PC há 90 s = desligado/sem internet

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(req);
    const rele = env.RELE.get(env.RELE.idFromName("casa"));
    return rele.fetch(req);
  },
};

// ------------------------------------------------------------------ utilidades
async function sha256(texto) {
  const dados = new TextEncoder().encode(texto);
  const h = await crypto.subtle.digest("SHA-256", dados);
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function iguais(a, b) {
  // comparação em tempo constante (não vaza quantos caracteres acertaram)
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

function aleatorio(bytes = 32) {
  const a = crypto.getRandomValues(new Uint8Array(bytes));
  return btoa(String.fromCharCode(...a)).replace(/[+/=]/g, (c) => ({ "+": "-", "/": "_", "=": "" }[c]));
}

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json; charset=utf-8" } });

// ------------------------------------------------------------------ Durable Object
export class Rele extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.env = env;
  }

  async fetch(req) {
    const url = new URL(req.url);
    const caminho = url.pathname;

    if (caminho === "/api/ws") return this.conectar(req, url);
    if (caminho === "/api/parear" && req.method === "POST") return this.parear(req);
    if (caminho === "/api/estado") {
      const cel = await this.celularValido(this.tokenDe(req, url));
      if (!cel) return json({ erro: "não autorizado" }, 401);
      return json(await this.estado());
    }
    return json({ erro: "não encontrado" }, 404);
  }

  tokenDe(req, url) {
    const auth = req.headers.get("authorization") || "";
    return auth.startsWith("Bearer ") ? auth.slice(7) : url.searchParams.get("token") || "";
  }

  // ---------------------------------------------------------------- autenticação
  async celularValido(token) {
    if (!token || token.length < 20) return null;
    const tokens = (await this.ctx.storage.get("tokens")) || {};
    const h = await sha256(token);
    return tokens[h] ? { hash: h, ...tokens[h] } : null;
  }

  async parear(req) {
    // limite de tentativas: 10 erros em 10 minutos bloqueiam o pareamento
    const agora = Date.now();
    const tent = (await this.ctx.storage.get("tentativas")) || { n: 0, desde: agora };
    if (agora - tent.desde > 600_000) { tent.n = 0; tent.desde = agora; }
    if (tent.n >= 10) return json({ erro: "Muitas tentativas. Espere 10 minutos." }, 429);

    let corpo = {};
    try { corpo = await req.json(); } catch {}
    const codigo = String(corpo.codigo || "").trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
    const pendente = await this.ctx.storage.get("pareamento");
    const ok = pendente && pendente.expira > agora && iguais(await sha256(codigo), pendente.hash);
    if (!ok) {
      tent.n++;
      await this.ctx.storage.put("tentativas", tent);
      return json({ erro: "Código inválido ou vencido. Gere outro no PC." }, 403);
    }
    await this.ctx.storage.delete("pareamento"); // código de uso único
    const token = aleatorio(32);
    const tokens = (await this.ctx.storage.get("tokens")) || {};
    const nome = String(corpo.nome || "Celular").slice(0, 40);
    tokens[await sha256(token)] = { nome, criado: agora };
    await this.ctx.storage.put("tokens", tokens);
    this.paraPC({ tipo: "celular_pareado", nome });
    return json({ token, nome });
  }

  // ---------------------------------------------------------------- estado do PC
  async estado() {
    const pc = (await this.ctx.storage.get("pc")) || {};
    const conectado = this.ctx.getWebSockets("pc").length > 0;
    const online = conectado && Date.now() - (pc.ultimo || 0) < ONLINE_SEM_SINAL_MS;
    return {
      online,
      desde: pc.ligado_desde || null,     // quando o Windows ligou (boot)
      conectado_desde: pc.conectado_desde || null,
      ultimo: pc.ultimo || null,
      info: pc.info || {},
      notificacoes: ((await this.ctx.storage.get("notificacoes")) || []).slice(-20),
    };
  }

  async avisarCelulares() {
    const e = await this.estado();
    this.paraCelulares({ tipo: "estado", ...e });
  }

  // ---------------------------------------------------------------- WebSockets
  async conectar(req, url) {
    if (req.headers.get("Upgrade") !== "websocket") return json({ erro: "esperado websocket" }, 426);
    const papel = url.searchParams.get("papel");
    const par = new WebSocketPair();
    const [cliente, servidor] = Object.values(par);

    if (papel === "pc") {
      const chave = req.headers.get("x-chave") || url.searchParams.get("chave") || "";
      if (!this.env.CHAVE_PC || !iguais(chave, this.env.CHAVE_PC)) return json({ erro: "chave inválida" }, 401);
      for (const velho of this.ctx.getWebSockets("pc")) { try { velho.close(4000, "substituído"); } catch {} }
      this.ctx.acceptWebSocket(servidor, ["pc"]);
      const pc = (await this.ctx.storage.get("pc")) || {};
      pc.conectado_desde = Date.now();
      pc.ultimo = Date.now();
      await this.ctx.storage.put("pc", pc);
      await this.avisarCelulares();
    } else if (papel === "celular") {
      const cel = await this.celularValido(this.tokenDe(req, url));
      if (!cel) return json({ erro: "não autorizado" }, 401);
      const id = aleatorio(9);
      this.ctx.acceptWebSocket(servidor, ["cel", "cel:" + id]);
      servidor.serializeAttachment({ id, nome: cel.nome, hash: cel.hash });
      servidor.send(JSON.stringify({ tipo: "estado", ...(await this.estado()) }));
    } else {
      return json({ erro: "papel inválido" }, 400);
    }
    return new Response(null, { status: 101, webSocket: cliente });
  }

  paraPC(msg) {
    const [pc] = this.ctx.getWebSockets("pc");
    if (!pc) return false;
    try { pc.send(JSON.stringify(msg)); return true; } catch { return false; }
  }

  paraCelulares(msg, id = null) {
    const alvo = id ? this.ctx.getWebSockets("cel:" + id) : this.ctx.getWebSockets("cel");
    const texto = JSON.stringify(msg);
    for (const ws of alvo) { try { ws.send(texto); } catch {} }
  }

  async webSocketMessage(ws, bruto) {
    let msg;
    try { msg = JSON.parse(typeof bruto === "string" ? bruto : new TextDecoder().decode(bruto)); } catch { return; }
    const tags = this.ctx.getTags(ws);

    if (tags.includes("pc")) return this.doPC(msg);
    if (tags.includes("cel")) return this.doCelular(ws, msg);
  }

  async doPC(msg) {
    const pc = (await this.ctx.storage.get("pc")) || {};
    pc.ultimo = Date.now();
    switch (msg.tipo) {
      case "ola":
        pc.ligado_desde = msg.ligado_desde || null;
        pc.info = msg.info || {};
        await this.ctx.storage.put("pc", pc);
        await this.avisarCelulares();
        return;
      case "status":
        pc.info = { ...(pc.info || {}), ...(msg.info || {}) };
        await this.ctx.storage.put("pc", pc);
        this.paraCelulares({ tipo: "estado", ...(await this.estado()) });
        return;
      case "parear_codigo": // o PC gerou um código para parear um celular novo
        await this.ctx.storage.put("pareamento", { hash: msg.hash, expira: Date.now() + 600_000 });
        return;
      case "revogar_celulares":
        await this.ctx.storage.put("tokens", {});
        for (const ws of this.ctx.getWebSockets("cel")) { try { ws.close(4001, "desconectado pelo PC"); } catch {} }
        return;
      case "notificar": {
        const lista = (await this.ctx.storage.get("notificacoes")) || [];
        const n = { titulo: msg.titulo || "Ametista", texto: msg.texto || "", quando: Date.now() };
        lista.push(n);
        await this.ctx.storage.put("notificacoes", lista.slice(-50));
        this.paraCelulares({ tipo: "notificacao", ...n });
        await this.ctx.storage.put("pc", pc);
        return;
      }
      default: // respostas para um celular específico (ou todos)
        await this.ctx.storage.put("pc", pc);
        if (msg.para) {
          const { para, ...resto } = msg;
          this.paraCelulares(resto, para);
        } else {
          this.paraCelulares(msg);
        }
    }
  }

  async doCelular(ws, msg) {
    const quem = ws.deserializeAttachment() || {};
    // o token pode ter sido revogado depois da conexão
    const tokens = (await this.ctx.storage.get("tokens")) || {};
    if (!tokens[quem.hash]) { try { ws.close(4001, "não autorizado"); } catch {} return; }

    if (msg.tipo === "estado") return ws.send(JSON.stringify({ tipo: "estado", ...(await this.estado()) }));
    if (!["pedido", "tela", "cancelar"].includes(msg.tipo)) return;
    // limite de tamanho (áudio de até ~1 minuto)
    if (JSON.stringify(msg).length > 900_000) {
      return ws.send(JSON.stringify({ tipo: "erro", id: msg.id, texto: "Mensagem grande demais." }));
    }
    const e = await this.estado();
    if (!e.online) {
      return ws.send(JSON.stringify({ tipo: "erro", id: msg.id, texto: "O PC está desligado ou sem internet." }));
    }
    this.paraPC({ ...msg, de: quem.id, nome_celular: quem.nome });
  }

  async webSocketClose(ws) {
    if (this.ctx.getTags(ws).includes("pc")) {
      const pc = (await this.ctx.storage.get("pc")) || {};
      pc.ultimo = Date.now();
      await this.ctx.storage.put("pc", pc);
      // avisa depois que o socket sair da lista
      await this.ctx.storage.setAlarm(Date.now() + 1000);
    }
  }

  async webSocketError(ws) {
    return this.webSocketClose(ws);
  }

  async alarm() {
    await this.avisarCelulares();
  }
}
