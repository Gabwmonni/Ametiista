// Ametista: o rosto dela é uma malha 3D (modelo/ametista.blend → ametista.glb), feita para editar e animar no
// Blender, e desenhada aqui com um motor WebGL próprio e leve, no estilo anime: luz e sombra chapadas, contorno,
// íris e boca "desenhadas" por cima do rosto (com máscara, como nos desenhos), brilho de cabelo e cristais
// iridescentes. As expressões são as shape keys do modelo: piscar, olhar, falar (a, e, i, o, u), sorrir...
//
// Estados (Rosto.modo):  dormindo | ocioso | ouvindo | pensando | falando |
//                        executando | alerta | offline | aguardando | privado
// Emoções (Rosto.emocao): neutra | feliz | pensativa | surpresa | triste | brava
// Gestos (Rosto.gesto):  acenar (sim com a cabeça) | negar | inclinar
//
// Leve de propósito: ~19 mil triângulos, sem texturas; só as partes que mexem (olhos, boca, sobrancelhas) são
// recalculadas, e só quando mudam. 24 quadros/s falando, 30 só no instante de uma piscada ou gesto, 8 parada,
// nada quando a janela ou o app estão escondidos. Sem WebGL (ou sem o modelo), usa o rosto de reserva
// (rosto2d.js, a ilustração animada).
(() => {
  const canvas = document.getElementById("rosto");
  const ctx = canvas.getContext("2d");
  const TRANSPARENTE = canvas.dataset.transparente === "1";
  const script = document.currentScript;
  const PASTA = script && script.src ? script.src.replace(/[^/]*$/, "") : "";
  const MODELO = canvas.dataset.modelo || PASTA + "ametista.glb";

  // ================================================================= estado (o mesmo contrato do rosto 2D)
  const EMOCOES = {        // luz por cima: cor, força, brilho, saturação
    neutra:    { cor: [255, 255, 255], forca: 0.00, luz: 1.00, sat: 1.00 },
    feliz:     { cor: [255, 190, 230], forca: 0.12, luz: 1.03, sat: 1.00 },
    pensativa: { cor: [190, 200, 255], forca: 0.10, luz: 0.99, sat: 0.96 },
    surpresa:  { cor: [255, 255, 255], forca: 0.10, luz: 1.05, sat: 1.00 },
    triste:    { cor: [150, 170, 230], forca: 0.18, luz: 0.92, sat: 0.8 },
    brava:     { cor: [255, 120, 130], forca: 0.14, luz: 0.98, sat: 1.00 },
  };
  // expressões (pesos das shape keys) de cada emoção
  const EXPRESSOES = {
    neutra:    { sorriso: 0.18 },
    feliz:     { sorriso: 0.85, olhos_felizes: 0.22, sobrancelhas_cima: 0.2, blush: 1 },
    pensativa: { sobrancelha_pensativa: 0.85, boca_u: 0.12, triste: 0.1 },
    surpresa:  { arregalar: 0.9, sobrancelhas_cima: 1, boca_o: 0.45 },
    triste:    { sobrancelhas_tristes: 0.9, triste: 0.8, piscar: 0.22 },
    brava:     { sobrancelhas_bravas: 1, bravo: 0.75, piscar: 0.12 },
  };
  const HALO = { normal: [203, 178, 248], alerta: [255, 176, 120], ouvindo: [179, 206, 251], feliz: [252, 201, 242] };
  const estado = {
    modo: "dormindo", emocao: "neutra",
    voz: 0, mic: 0,
    boca: 0,                                   // abertura suavizada (0..1)
    fechar: 1,                                 // olhos: 0 abertos, 1 fechados (dormindo)
    piscar: 0, proxPiscada: 2, piscadaDupla: false,
    efeito: { ...EMOCOES.neutra, cor: [...EMOCOES.neutra.cor] },
    brilho: [...HALO.normal], cinza: 0,
    cabeca: { rot: 0, dx: 0, dy: 0, yaw: 0, pitch: 0, roll: 0 },
    gesto: null, gestoT: 0,
    olhar: { x: 0, y: 0, alvoX: 0, alvoY: 0, prox: 1.5 },
    vogal: "boca_a", proxVogal: 0,
    pesos: {},                                 // shape keys suavizadas
    forcado: null,                             // testes: {piscar, boca, sorriso, olhar: [x, y]}
    malha: null,                               // informações do modelo carregado
  };

  // ================================================================= WebGL
  const tela3d = document.createElement("canvas");
  const opcoesGL = { alpha: true, antialias: true, stencil: true, premultipliedAlpha: true, depth: true };
  let gl = null;
  try { gl = tela3d.getContext("webgl2", opcoesGL) || tela3d.getContext("webgl", opcoesGL); } catch { gl = null; }
  let reserva = false;

  function usarReserva(motivo) {                 // sem WebGL ou sem o modelo: o rosto 2D da ilustração
    if (reserva) return;
    reserva = true;
    console.warn("[rosto] usando o rosto 2D:", motivo);
    if (espera !== null) clearTimeout(espera);
    if (pedido) cancelAnimationFrame(pedido);
    const guardado = { modo: estado.modo, emocao: estado.emocao };
    const s = document.createElement("script");
    s.src = PASTA + "rosto2d.js";
    s.onload = () => { try { window.Rosto.modo(guardado.modo); window.Rosto.emocao(guardado.emocao); } catch { } };
    document.head.appendChild(s);
  }

  const VERT_TOON = `
    attribute vec3 aP; attribute vec3 aN; attribute vec4 aC;
    uniform mat4 uMV; uniform mat4 uP; uniform mat3 uNM; uniform float uLarg; uniform float uBal; uniform float uT;
    varying vec3 vN; varying vec3 vV; varying vec4 vC; varying vec3 vL;
    void main() {
      vec3 p = aP;
      // o cabelo balança (mais nas pontas, que ficam mais para baixo)
      float w = clamp((0.55 - p.y) / 1.8, 0.0, 1.0); w = w * w * uBal;
      p.x += (sin(uT * 1.3 + p.y * 2.1) * 0.012 + sin(uT * 0.7 + p.z * 3.0) * 0.008) * w;
      p.z += sin(uT * 1.1 + p.x * 2.5) * 0.008 * w;
      vec4 mv = uMV * vec4(p, 1.0);
      vec3 n = normalize(uNM * aN);
      mv.xyz += n * uLarg * (-mv.z);            // contorno: casca empurrada para fora (largura constante na tela)
      vN = n; vV = normalize(-mv.xyz); vC = aC; vL = p;
      gl_Position = uP * mv;
    }`;
  const FRAG_TOON = `
    precision mediump float;
    varying vec3 vN; varying vec3 vV; varying vec4 vC; varying vec3 vL;
    uniform vec3 uCor; uniform vec3 uSombra; uniform vec3 uLuz; uniform float uIrid; uniform float uBrilho;
    uniform float uMetal; uniform float uModo; uniform float uAlfa;
    vec3 irid(float x) {              // rosa → lilás → azul-cristal → rosa
      float f = fract(x) * 3.0;
      vec3 a = vec3(1.0, 0.78, 0.93), b = vec3(0.8, 0.7, 0.97), c = vec3(0.7, 0.88, 1.0);
      return f < 1.0 ? mix(a, b, f) : f < 2.0 ? mix(b, c, f - 1.0) : mix(c, a, f - 2.0);
    }
    void main() {
      if (uModo > 1.5) { gl_FragColor = vec4(uCor, 1.0); return; }            // contorno
      vec3 N = normalize(vN); vec3 V = normalize(vV);
      if (!gl_FrontFacing) N = -N;
      float nl = dot(N, uLuz);
      float luz = smoothstep(0.0, 0.07, nl);
      vec3 c = mix(uSombra, uCor, luz) * vC.rgb;
      float fres = pow(1.0 - max(dot(N, V), 0.0), 2.5);
      c += uIrid * fres * irid(fres * 1.3 + vL.y * 0.4 + vL.x * 0.3) * 0.4;
      if (uBrilho > 0.0) {                                                    // brilho de cabelo (anel de anime)
        float faixa = N.y - 0.42 - 0.04 * sin(vL.x * 38.0) - 0.02 * sin(vL.z * 57.0);
        float anel = smoothstep(0.075, 0.035, abs(faixa)) * luz;
        c = mix(c, mix(vec3(1.0), irid(vL.x * 0.8 + 0.2), 0.35), anel * 0.7 * uBrilho);
      }
      if (uMetal > 0.0) {
        vec3 r = reflect(-uLuz, N);
        float esp = smoothstep(0.86, 0.9, dot(r, V));
        c = mix(c, vec3(1.0, 0.98, 0.95), esp * uMetal);
        c = mix(c, c * irid(dot(N, V) * 1.5 + 0.1) * 1.25, 0.18 * uMetal);
      }
      gl_FragColor = vec4(c, uAlfa);
    }`;
  const VERT_PLANO = `
    attribute vec3 aP; attribute vec4 aC;
    uniform mat4 uMV; uniform mat4 uP;
    varying vec4 vC;
    void main() { vC = aC; gl_Position = uP * (uMV * vec4(aP, 1.0)); }`;
  const FRAG_PLANO = `
    precision mediump float;
    varying vec4 vC; uniform vec3 uCor; uniform float uAlfa;
    void main() { gl_FragColor = vec4(uCor * vC.rgb * uAlfa * vC.a, uAlfa * vC.a); }`;
  const FRAG_VIDRO = `
    precision mediump float;
    varying vec3 vN; varying vec3 vV; varying vec4 vC; varying vec3 vL;
    uniform vec3 uCor; uniform float uAlfa; uniform vec3 uLuz;
    vec3 irid(float x) {
      float f = fract(x) * 3.0;
      vec3 a = vec3(1.0, 0.78, 0.93), b = vec3(0.8, 0.7, 0.97), c = vec3(0.7, 0.88, 1.0);
      return f < 1.0 ? mix(a, b, f) : f < 2.0 ? mix(b, c, f - 1.0) : mix(c, a, f - 2.0);
    }
    void main() {
      vec3 N = normalize(vN); vec3 V = normalize(vV);
      float fres = pow(1.0 - abs(dot(N, V)), 2.0);
      vec3 c = mix(uCor, irid(fres + vL.x * 1.5 + vL.y), 0.35);
      float riscos = smoothstep(0.035, 0.0, abs(vL.x * 0.7 + vL.y - 0.02 - 0.25)) * 0.5;
      float a = uAlfa + fres * 0.35 + riscos * 0.4;
      gl_FragColor = vec4(c * a + riscos * 0.5, a);
    }`;

  function compilar(vs, fs) {
    const sh = (tipo, src) => {
      const s = gl.createShader(tipo);
      gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) || "shader");
      return s;
    };
    const p = gl.createProgram();
    gl.attachShader(p, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, fs));
    gl.bindAttribLocation(p, 0, "aP"); gl.bindAttribLocation(p, 1, "aN"); gl.bindAttribLocation(p, 2, "aC");
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) || "programa");
    const u = {};
    const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
    for (let i = 0; i < n; i++) { const a = gl.getActiveUniform(p, i); u[a.name] = gl.getUniformLocation(p, a.name); }
    return { p, u };
  }

  // ================================================================= leitura do .glb (o que o Blender exporta)
  const TIPOS = { 5120: Int8Array, 5121: Uint8Array, 5122: Int16Array, 5123: Uint16Array, 5125: Uint32Array, 5126: Float32Array };
  const COMPS = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT4: 16 };
  const MAXNORM = { 5120: 127, 5121: 255, 5122: 32767, 5123: 65535 };

  function lerGLB(buf) {
    const dv = new DataView(buf);
    if (dv.getUint32(0, true) !== 0x46546c67) throw new Error("o arquivo não é um .glb");
    let off = 12, json = null, bin = null;
    while (off + 8 <= buf.byteLength) {
      const len = dv.getUint32(off, true), tipo = dv.getUint32(off + 4, true);
      if (tipo === 0x4e4f534a) json = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, off + 8, len)));
      else if (tipo === 0x004e4942) bin = buf.slice(off + 8, off + 8 + len);
      off += 8 + len;
    }
    if (!json) throw new Error("glb sem JSON");
    return { json, bin };
  }

  function acessor(g, i, comoFloat = true) {
    const a = g.json.accessors[i];
    const nc = COMPS[a.type], T = TIPOS[a.componentType], total = a.count * nc;
    let out = comoFloat ? new Float32Array(total) : new T(total);
    const escala = comoFloat && a.normalized ? 1 / MAXNORM[a.componentType] : 1;
    if (a.bufferView !== undefined) {
      const bv = g.json.bufferViews[a.bufferView];
      const passo = bv.byteStride || nc * T.BYTES_PER_ELEMENT;
      const dv = new DataView(g.bin, (bv.byteOffset || 0) + (a.byteOffset || 0));
      const ler = { 5120: "getInt8", 5121: "getUint8", 5122: "getInt16", 5123: "getUint16", 5125: "getUint32", 5126: "getFloat32" }[a.componentType];
      for (let k = 0; k < a.count; k++)
        for (let c = 0; c < nc; c++) out[k * nc + c] = dv[ler](k * passo + c * T.BYTES_PER_ELEMENT, true) * escala;
    }
    if (a.sparse) {
      const s = a.sparse;
      const idx = acessorBruto(g, s.indices.bufferView, s.indices.byteOffset || 0, s.indices.componentType, s.count);
      const val = acessorBruto(g, s.values.bufferView, s.values.byteOffset || 0, a.componentType, s.count * nc);
      for (let k = 0; k < s.count; k++)
        for (let c = 0; c < nc; c++) out[idx[k] * nc + c] = val[k * nc + c] * escala;
    }
    return out;
  }
  function acessorBruto(g, bvi, off, tipo, n) {
    const bv = g.json.bufferViews[bvi], T = TIPOS[tipo];
    const inicio = (bv.byteOffset || 0) + off;
    if (inicio % T.BYTES_PER_ELEMENT === 0) return new T(g.bin, inicio, n);
    return new T(g.bin.slice(inicio, inicio + n * T.BYTES_PER_ELEMENT));
  }

  // matrizes 4x4 (coluna a coluna, como o WebGL)
  const M = {
    id: () => new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]),
    mul(a, b) {
      const o = new Float32Array(16);
      for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++)
        o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
      return o;
    },
    trs(t = [0, 0, 0], q = [0, 0, 0, 1], s = [1, 1, 1]) {
      const [x, y, z, w] = q;
      return new Float32Array([
        (1 - 2 * (y * y + z * z)) * s[0], 2 * (x * y + z * w) * s[0], 2 * (x * z - y * w) * s[0], 0,
        2 * (x * y - z * w) * s[1], (1 - 2 * (x * x + z * z)) * s[1], 2 * (y * z + x * w) * s[1], 0,
        2 * (x * z + y * w) * s[2], 2 * (y * z - x * w) * s[2], (1 - 2 * (x * x + y * y)) * s[2], 0,
        t[0], t[1], t[2], 1]);
    },
    rot(yaw, pitch, roll) {           // Y (virar), X (acenar), Z (inclinar)
      const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch), cr = Math.cos(roll), sr = Math.sin(roll);
      const ry = new Float32Array([cy, 0, -sy, 0, 0, 1, 0, 0, sy, 0, cy, 0, 0, 0, 0, 1]);
      const rx = new Float32Array([1, 0, 0, 0, 0, cp, sp, 0, 0, -sp, cp, 0, 0, 0, 0, 1]);
      const rz = new Float32Array([cr, sr, 0, 0, -sr, cr, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
      return M.mul(ry, M.mul(rx, rz));
    },
    persp(fov, asp, perto, longe) {
      const f = 1 / Math.tan(fov / 2), nf = 1 / (perto - longe);
      return new Float32Array([f / asp, 0, 0, 0, 0, f, 0, 0, 0, 0, (longe + perto) * nf, -1, 0, 0, 2 * longe * perto * nf, 0]);
    },
    normal(m) {                        // inversa transposta da 3x3 (para as normais)
      const a = m[0], b = m[1], c = m[2], d = m[4], e = m[5], f = m[6], g = m[8], h = m[9], i = m[10];
      const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
      const det = a * A + b * B + c * C || 1;
      return new Float32Array([A / det, B / det, C / det, -(b * i - c * h) / det, (a * i - c * g) / det,
        -(a * h - b * g) / det, (b * f - c * e) / det, -(a * f - c * d) / det, (a * e - b * d) / det]);
    },
  };

  // Como pintar cada material: pelo nome (o contrato com o Blender); os extras do material podem mudar as cores
  const PLANOS = {       // [ordem, máscara: 1 grava 2 respeita, número da máscara]
    pele_sombra: [0], nariz: [1], blush: [1], sombra_olho: [1], labio: [2], vinco: [2],
    olho_branco: [3, 1, 1], iris: [4, 2, 1], iris_estrela: [5, 2, 1], pupila: [6, 2, 1], brilho_olho: [7, 2, 1],
    cilios_baixo: [8], cilios: [9], sobrancelha: [10, 0, 0, 1],   // a sobrancelha aparece por cima da franja
    boca_dentro: [3, 1, 2], dentes: [4, 2, 2], lingua: [5, 2, 2], linha_boca: [6],
  };
  const TOONS = {        // brilho de cabelo, metal, iridescência, contorno (px)
    pele: { contorno: 1 }, cabelo: { brilho: 1, irid: 0.6, contorno: 1 }, roupa: { contorno: 1.1 },
    roupa_detalhe: { contorno: 0.8, irid: 0.3 }, metal: { metal: 1, irid: 0.8, contorno: 0.6 },
    cristal: { irid: 1, metal: 0.6, contorno: 0.6 },
  };
  const hexa = (h) => { const n = parseInt(String(h).replace("#", ""), 16); return [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255]; };
  const paraSRGB = (v) => v <= 0.0031308 ? v * 12.92 : 1.055 * Math.pow(v, 1 / 2.4) - 0.055;
  const escurecer = (c, k) => c.map((v) => v * k);

  function tipoMaterial(nome) {
    const base = String(nome || "").toLowerCase().replace(/\.\d+$/, "");
    if (base.startsWith("vidro")) return { modo: "vidro" };
    for (const k of Object.keys(PLANOS)) if (base === k || base.startsWith(k + "_")) return { modo: "plano", chave: k };
    for (const k of Object.keys(TOONS).sort((a, b) => b.length - a.length))
      if (base === k || base.startsWith(k + "_") || base.startsWith(k)) return { modo: "toon", chave: k };
    return { modo: "toon", chave: "pele" };
  }

  // ================================================================= o modelo na GPU
  let progs = null, modelo = null;

  function montar(g) {
    const mats = (g.json.materials || []).map((m) => {
      const pbr = m.pbrMetallicRoughness || {};
      const bc = pbr.baseColorFactor || [1, 1, 1, 1];
      const ex = m.extras || {};
      const t = tipoMaterial(m.name);
      const cor = bc.slice(0, 3).map(paraSRGB);
      const toon = TOONS[t.chave] || {};
      return {
        nome: m.name, ...t, cor, alfa: m.alphaMode === "BLEND" ? bc[3] : 1,
        sombra: ex.sombra ? hexa(ex.sombra) : escurecer(cor, 0.78),
        contorno: ex.contorno ? hexa(ex.contorno) : escurecer(cor, 0.45),
        irid: ex.iridescente !== undefined ? +ex.iridescente : (toon.irid || 0),
        brilho: ex.brilho ? 1 : (toon.brilho || 0), metal: toon.metal || 0,
        larguraContorno: ex.largura_contorno !== undefined ? +ex.largura_contorno : (toon.contorno || 0),
        plano: PLANOS[t.chave] || [0],
      };
    });
    const pecas = [];
    const nomesAlvos = new Set();
    const meshes = (g.json.meshes || []).map((mesh, mi) => {
      const nomes = (mesh.extras && mesh.extras.targetNames) || [];
      nomes.forEach((n) => nomesAlvos.add(n));
      return mesh.primitives.map((pr) => {
        if (pr.mode !== undefined && pr.mode !== 4) return null;          // só triângulos
        const pos = acessor(g, pr.attributes.POSITION);
        const nv = pos.length / 3;
        const plano = (mats[pr.material] || {}).modo === "plano";       // desenhado por cima: não usa normais
        const nor = pr.attributes.NORMAL !== undefined ? acessor(g, pr.attributes.NORMAL)
          : plano ? new Float32Array(3) : normaisDe(pos, pr, g);
        let cor = new Float32Array(nv * 4).fill(1);
        if (pr.attributes.COLOR_0 !== undefined) {
          const c = acessor(g, pr.attributes.COLOR_0);
          const nc = c.length / nv;
          for (let k = 0; k < nv; k++) {
            for (let j = 0; j < 3; j++) cor[k * 4 + j] = paraSRGB(c[k * nc + j]);
            cor[k * 4 + 3] = nc === 4 ? c[k * nc + 3] : 1;
          }
        }
        const idx = pr.indices !== undefined ? acessor(g, pr.indices, false) : null;
        const alvos = (pr.targets || []).map((t) => t.POSITION !== undefined ? acessor(g, t.POSITION) : null);
        const p = {
          mesh: mi, nomes, mat: mats[pr.material] || { modo: "toon", cor: [0.9, 0.9, 0.9], sombra: [0.7, 0.7, 0.7], contorno: [0.3, 0.3, 0.3], alfa: 1, irid: 0, brilho: 0, metal: 0, larguraContorno: 1, plano: [0] },
          base: pos, atual: new Float32Array(pos), alvos, pesos: new Float32Array(alvos.length),
          n: idx ? idx.length : nv,
          bufP: buffer(pos, gl.DYNAMIC_DRAW), bufN: buffer(nor), bufC: buffer(cor),
          bufI: null, tipoI: gl.UNSIGNED_SHORT,
        };
        if (idx) {
          const grande = nv > 65535;
          if (grande && !(gl instanceof (window.WebGL2RenderingContext || Object)) && !gl.getExtension("OES_element_index_uint"))
            throw new Error("malha grande demais para este WebGL");
          const arr = grande ? new Uint32Array(idx) : new Uint16Array(idx);
          p.bufI = gl.createBuffer(); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, p.bufI);
          gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, arr, gl.STATIC_DRAW);
          p.tipoI = grande ? gl.UNSIGNED_INT : gl.UNSIGNED_SHORT;
        }
        pecas.push(p);
        return p;
      }).filter(Boolean);
    });
    // nós
    const nos = (g.json.nodes || []).map((n) => ({
      nome: n.name || "", filhos: n.children || [], mesh: n.mesh,
      local: n.matrix ? new Float32Array(n.matrix) : M.trs(n.translation, n.rotation, n.scale),
    }));
    const raizes = (g.json.scenes && g.json.scenes[g.json.scene || 0] || { nodes: nos.map((_, i) => i) }).nodes;
    const cabeca = nos.findIndex((n) => /^cabe[cç]a$/i.test(n.nome));
    const tri = pecas.reduce((s, p) => s + p.n / 3, 0);
    // limites (para enquadrar)
    return { mats, meshes, pecas, nos, raizes, cabeca, alvos: [...nomesAlvos], triangulos: Math.round(tri) };
  }

  function buffer(dados, uso) {
    const b = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, b);
    gl.bufferData(gl.ARRAY_BUFFER, dados, uso || gl.STATIC_DRAW);
    return b;
  }

  function normaisDe(pos, pr, g) {                   // se o arquivo vier sem normais
    const n = new Float32Array(pos.length);
    const idx = pr.indices !== undefined ? acessor(g, pr.indices, false) : [...Array(pos.length / 3).keys()];
    for (let i = 0; i < idx.length; i += 3) {
      const [a, b, c] = [idx[i] * 3, idx[i + 1] * 3, idx[i + 2] * 3];
      const u = [pos[b] - pos[a], pos[b + 1] - pos[a + 1], pos[b + 2] - pos[a + 2]];
      const v = [pos[c] - pos[a], pos[c + 1] - pos[a + 1], pos[c + 2] - pos[a + 2]];
      const cr = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
      for (const k of [a, b, c]) for (let j = 0; j < 3; j++) n[k + j] += cr[j];
    }
    for (let i = 0; i < n.length; i += 3) {
      const l = Math.hypot(n[i], n[i + 1], n[i + 2]) || 1;
      n[i] /= l; n[i + 1] /= l; n[i + 2] /= l;
    }
    return n;
  }

  // aplica os pesos das shape keys (só nas peças que têm, e só quando mudam)
  function aplicarPesos(pesos) {
    for (const p of modelo.pecas) {
      if (!p.alvos.length) continue;
      let mudou = false;
      for (let i = 0; i < p.alvos.length; i++) {
        const w = pesos[p.nomes[i]] || 0;
        if (Math.abs(w - p.pesos[i]) > 0.002) { p.pesos[i] = w; mudou = true; }
      }
      if (!mudou) continue;
      p.atual.set(p.base);
      for (let i = 0; i < p.alvos.length; i++) {
        const w = p.pesos[i], d = p.alvos[i];
        if (w < 0.002 || !d) continue;
        for (let k = 0; k < d.length; k++) p.atual[k] += d[k] * w;
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, p.bufP);
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, p.atual);
    }
  }

  // ================================================================= desenho 3D
  const FOV = 0.36;                                          // ~20°: pouca perspectiva, jeito de desenho
  const ENQ = { y: -0.28, h: 3.5, w: 2.75 };                 // cabeça, pescoço e ombros (unidades do modelo)
  const LUZ = (() => { const v = [-0.52, 0.56, 0.64]; const l = Math.hypot(...v); return v.map((x) => x / l); })();

  function desenhar3d(largura, altura, t) {
    if (tela3d.width !== largura || tela3d.height !== altura) { tela3d.width = largura; tela3d.height = altura; }
    gl.viewport(0, 0, largura, altura);
    gl.clearColor(0, 0, 0, 0); gl.clearDepth(1); gl.clearStencil(0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT | gl.STENCIL_BUFFER_BIT);
    const asp = largura / altura;
    // em telas pequenas (a barra, o celular) o enquadramento fecha no rosto; nas grandes mostra os ombros
    const aberto = Math.min(1, Math.max(0, (altura / dpr - 120) / 280));
    const enq = { y: -0.1 + (ENQ.y + 0.1) * aberto, h: 2.8 + (ENQ.h - 2.8) * aberto, w: 2.3 + (ENQ.w - 2.3) * aberto };
    const alturaVista = Math.max(enq.h, enq.w / asp);
    const dist = alturaVista / 2 / Math.tan(FOV / 2);
    const P = M.persp(FOV, asp, dist - 4, dist + 4);
    const view = M.trs([0, -enq.y, -dist]);
    // mundo de cada nó (a cabeça gira em volta do pescoço)
    const cab = estado.cabeca;
    const resp = Math.sin(t * 1.6) * 0.012;
    const mundos = new Array(modelo.nos.length);
    const visitar = (i, pai) => {
      const n = modelo.nos[i];
      let local = n.local;
      if (i === modelo.cabeca) local = M.mul(local, M.rot(cab.yaw, cab.pitch, cab.roll));
      mundos[i] = M.mul(pai, local);
      n.filhos.forEach((f) => visitar(f, mundos[i]));
    };
    const raiz = M.trs([0, resp, 0]);
    modelo.raizes.forEach((i) => visitar(i, raiz));

    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL);
    gl.enable(gl.CULL_FACE); gl.cullFace(gl.BACK);
    gl.disable(gl.BLEND); gl.disable(gl.STENCIL_TEST);
    const pxMundo = 2 * Math.tan(FOV / 2) / altura;           // tamanho de um pixel a 1 unidade da câmera
    const lista = [];
    modelo.nos.forEach((n, i) => {
      if (n.mesh === undefined || !modelo.meshes[n.mesh]) return;
      const mv = M.mul(view, mundos[i]);
      modelo.meshes[n.mesh].forEach((p) => lista.push({ p, mv, nm: M.normal(mv), no: n }));
    });
    const toon = lista.filter((d) => d.p.mat.modo === "toon");
    const planos = lista.filter((d) => d.p.mat.modo === "plano").sort((a, b) => a.p.mat.plano[0] - b.p.mat.plano[0]);
    const vidros = lista.filter((d) => d.p.mat.modo === "vidro");
    // 1) sólidos com luz de anime
    usar(progs.toon, P);
    gl.uniform3fv(progs.toon.u.uLuz, LUZ);
    gl.uniform1f(progs.toon.u.uT, t);
    for (const d of toon) {
      const m = d.p.mat;
      gl.uniform1f(progs.toon.u.uModo, 0); gl.uniform1f(progs.toon.u.uLarg, 0);
      gl.uniform3fv(progs.toon.u.uCor, m.cor); gl.uniform3fv(progs.toon.u.uSombra, m.sombra);
      gl.uniform1f(progs.toon.u.uIrid, m.irid); gl.uniform1f(progs.toon.u.uBrilho, m.brilho);
      gl.uniform1f(progs.toon.u.uMetal, m.metal); gl.uniform1f(progs.toon.u.uAlfa, 1);
      gl.uniform1f(progs.toon.u.uBal, m.chave === "cabelo" ? 1 : 0);
      desenharPeca(progs.toon, d, true);
    }
    // 2) contornos: a casca de trás, empurrada para fora
    gl.cullFace(gl.FRONT);
    gl.uniform1f(progs.toon.u.uModo, 2);
    for (const d of toon) {
      const m = d.p.mat;
      if (!m.larguraContorno) continue;
      gl.uniform1f(progs.toon.u.uLarg, pxMundo * m.larguraContorno * Math.max(1, altura / 260));
      gl.uniform3fv(progs.toon.u.uCor, m.contorno);
      gl.uniform1f(progs.toon.u.uBal, m.chave === "cabelo" ? 1 : 0);
      desenharPeca(progs.toon, d, true);
    }
    gl.cullFace(gl.BACK);
    // 3) o que é desenhado por cima do rosto: olhos, boca, sobrancelhas, blush... (com máscara)
    gl.disable(gl.CULL_FACE);
    gl.depthMask(false);
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.enable(gl.STENCIL_TEST);
    usar(progs.plano, P);
    for (const d of planos) {
      const m = d.p.mat;
      const [, masc, num] = m.plano;
      if (masc === 1) { gl.stencilFunc(gl.ALWAYS, num, 0xff); gl.stencilOp(gl.KEEP, gl.KEEP, gl.REPLACE); }
      else if (masc === 2) { gl.stencilFunc(gl.EQUAL, num, 0xff); gl.stencilOp(gl.KEEP, gl.KEEP, gl.KEEP); }
      else { gl.stencilFunc(gl.ALWAYS, 0, 0xff); gl.stencilOp(gl.KEEP, gl.KEEP, gl.KEEP); }
      let alfa = m.alfa;
      if (m.chave === "blush") alfa *= estado.pesos.blush || 0;
      if (m.plano[3]) gl.disable(gl.DEPTH_TEST); else gl.enable(gl.DEPTH_TEST);
      if (alfa < 0.01) continue;
      gl.uniform3fv(progs.plano.u.uCor, m.cor); gl.uniform1f(progs.plano.u.uAlfa, alfa);
      desenharPeca(progs.plano, d, false);
    }
    gl.disable(gl.STENCIL_TEST);
    gl.enable(gl.DEPTH_TEST);
    // 4) vidro do monóculo
    usar(progs.vidro, P);
    gl.uniform3fv(progs.vidro.u.uLuz, LUZ);
    for (const d of vidros) {
      gl.uniform3fv(progs.vidro.u.uCor, d.p.mat.cor); gl.uniform1f(progs.vidro.u.uAlfa, d.p.mat.alfa);
      desenharPeca(progs.vidro, d, true);
    }
    gl.depthMask(true); gl.disable(gl.BLEND);
  }

  function usar(pr, P) {
    gl.useProgram(pr.p);
    gl.uniformMatrix4fv(pr.u.uP, false, P);
  }

  function desenharPeca(pr, d, comNormal) {
    const p = d.p;
    gl.uniformMatrix4fv(pr.u.uMV, false, d.mv);
    if (pr.u.uNM) gl.uniformMatrix3fv(pr.u.uNM, false, d.nm);
    gl.bindBuffer(gl.ARRAY_BUFFER, p.bufP); gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
    if (comNormal) {
      gl.bindBuffer(gl.ARRAY_BUFFER, p.bufN); gl.enableVertexAttribArray(1);
      gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);
    } else gl.disableVertexAttribArray(1);
    gl.bindBuffer(gl.ARRAY_BUFFER, p.bufC); gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 4, gl.FLOAT, false, 0, 0);
    if (p.bufI) { gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, p.bufI); gl.drawElements(gl.TRIANGLES, p.n, p.tipoI, 0); }
    else gl.drawArrays(gl.TRIANGLES, 0, p.n);
  }

  // ================================================================= moldura, fundo, brilho e selo (2D, por cima)
  let W = 0, H = 0, dpr = 1, quadroQ = null, fundo = null;
  function redimensionar() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = canvas.clientWidth || innerWidth; H = canvas.clientHeight || innerHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    quadroQ = null; fundo = null;
    if (typeof acordar === "function") acordar();
  }
  addEventListener("resize", redimensionar);
  if (window.ResizeObserver) new ResizeObserver(redimensionar).observe(canvas);

  const lerp = (a, b, t) => a + (b - a) * t;
  const rgba = (c, a = 1) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;

  function quadro() {
    if (quadroQ) return quadroQ;
    const m = Math.max(4, Math.round(Math.min(W, H) * 0.045));
    quadroQ = { x: m, y: m, w: W - 2 * m, h: H - 2 * m, r: Math.min(W, H) * 0.16 };
    return quadroQ;
  }
  function moldura(q) {
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(q.x, q.y, q.w, q.h, q.r);
    else ctx.rect(q.x, q.y, q.w, q.h);
  }
  function fundoPronto(q) {                 // fundo lilás com um bokeh de cristal (desenhado uma vez)
    if (fundo && fundo.w === q.w && fundo.dpr === dpr) return fundo.c;
    const c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(q.w * dpr)); c.height = Math.max(1, Math.round(q.h * dpr));
    const g = c.getContext("2d");
    const grad = g.createLinearGradient(0, 0, 0, c.height);
    grad.addColorStop(0, "#3a2a66"); grad.addColorStop(0.55, "#281c4a"); grad.addColorStop(1, "#171030");
    g.fillStyle = grad; g.fillRect(0, 0, c.width, c.height);
    const cores = ["252,201,242", "203,178,248", "179,206,251"];
    for (let i = 0; i < 14; i++) {
      const x = ((i * 97) % 100) / 100 * c.width, y = ((i * 57 + 13) % 100) / 100 * c.height * 0.8;
      const r = (0.04 + ((i * 31) % 10) / 100) * c.width;
      const rg = g.createRadialGradient(x, y, 0, x, y, r);
      rg.addColorStop(0, `rgba(${cores[i % 3]},0.22)`); rg.addColorStop(1, `rgba(${cores[i % 3]},0)`);
      g.fillStyle = rg; g.fillRect(x - r, y - r, 2 * r, 2 * r);
    }
    fundo = { c, w: q.w, dpr };
    return c;
  }
  function halo(q, t) {
    const m = estado.modo;
    let forca = 0.35, extra = 0;
    if (m === "ouvindo") { forca = 0.55 + estado.mic * 0.45; extra = estado.mic * 6 + Math.sin(t * 3) * 1.5; }
    else if (m === "alerta") forca = 0.5 + (Math.sin(t * 6) * 0.5 + 0.5) * 0.4;
    else if (m === "falando") forca = 0.45 + estado.boca * 0.3;
    else if (m === "dormindo" || m === "offline" || m === "privado") forca = 0.15;
    ctx.save();
    ctx.shadowColor = rgba(estado.brilho, forca); ctx.shadowBlur = (8 + extra) * dpr;
    moldura(q); ctx.fillStyle = rgba(estado.brilho, 0.9); ctx.fill();
    ctx.restore();
  }
  function borda(q, t) {
    let g;
    if (ctx.createConicGradient) {
      g = ctx.createConicGradient(t * 0.6, q.x + q.w / 2, q.y + q.h / 2);
      [["#cbb2f8", 0], ["#b3cefb", 0.25], ["#fcc9f2", 0.5], ["#e6c7a2", 0.75], ["#cbb2f8", 1]].forEach(([c, p]) => g.addColorStop(p, c));
    } else {
      g = ctx.createLinearGradient(q.x, q.y, q.x + q.w, q.y + q.h);
      g.addColorStop(0, "#cbb2f8"); g.addColorStop(0.5, "#fcc9f2"); g.addColorStop(1, "#b3cefb");
    }
    ctx.strokeStyle = g; ctx.lineWidth = Math.max(1.5, Math.min(W, H) * 0.018);
    moldura(q); ctx.stroke();
  }
  function tingir(q, olhosFechados) {
    const ef = estado.efeito;
    const luz = ef.luz * (olhosFechados ? 0.92 : 1) * (1 - estado.cinza * 0.2);
    const sat = Math.min(1, ef.sat * (1 - estado.cinza));
    ctx.save();
    if (sat < 0.99) { ctx.globalCompositeOperation = "saturation"; ctx.fillStyle = `rgba(128,128,128,${1 - sat})`; ctx.fillRect(q.x, q.y, q.w, q.h); }
    if (luz < 0.995) { ctx.globalCompositeOperation = "multiply"; const v = Math.round(255 * luz); ctx.fillStyle = `rgb(${v},${v},${v})`; ctx.fillRect(q.x, q.y, q.w, q.h); }
    else if (luz > 1.005) { ctx.globalCompositeOperation = "screen"; ctx.fillStyle = `rgba(255,255,255,${(luz - 1) * 1.6})`; ctx.fillRect(q.x, q.y, q.w, q.h); }
    if (ef.forca > 0.01) { ctx.globalCompositeOperation = "soft-light"; ctx.fillStyle = rgba(ef.cor, ef.forca * 2.2); ctx.fillRect(q.x, q.y, q.w, q.h); }
    ctx.restore();
  }
  const COM_ICONE = ["dormindo", "pensando", "executando", "aguardando", "privado", "offline"];
  function selo(q, t) {
    const m = estado.modo;
    if (!COM_ICONE.includes(m)) return;
    const r = Math.max(9, Math.min(W, H) * 0.12);
    ctx.save();
    ctx.translate(q.x + q.w - r * 0.75, q.y + r * 0.75);
    ctx.fillStyle = "rgba(22,14,38,0.78)"; ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "rgba(203,178,248,0.6)"; ctx.lineWidth = Math.max(1, r * 0.08); ctx.stroke();
    ctx.fillStyle = "#e0d2fb"; ctx.strokeStyle = "#e0d2fb"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    const s = r / 46;
    ctx.scale(s, s);
    if (m === "dormindo") {
      ctx.font = "bold 30px system-ui";
      for (let i = 0; i < 3; i++) { const f = (t * 0.3 + i / 3) % 1; ctx.globalAlpha = Math.sin(f * Math.PI); ctx.fillText("z", -12 + f * 24, 20 - f * 40); }
    } else if (m === "pensando") {
      for (let i = 0; i < 3; i++) {
        const a = t * 2 + i * 2.1;
        ctx.globalAlpha = 0.95; ctx.beginPath(); ctx.arc(Math.cos(a) * 22, Math.sin(a) * 9, 7 + Math.sin(t * 4 + i) * 2.5, 0, Math.PI * 2); ctx.fill();
      }
    } else if (m === "executando") {
      ctx.lineWidth = 6; ctx.lineCap = "round"; ctx.beginPath(); ctx.arc(0, 0, 26, t * 3, t * 3 + 4); ctx.stroke();
    } else if (m === "aguardando") {
      ctx.font = "bold 56px system-ui"; ctx.globalAlpha = 0.7 + Math.sin(t * 3) * 0.3; ctx.fillText("?", 0, 4);
    } else if (m === "privado") {
      ctx.lineWidth = 6; ctx.beginPath(); ctx.arc(0, -8, 13, Math.PI, 0); ctx.stroke(); ctx.fillRect(-20, -8, 40, 30);
    } else if (m === "offline") {
      ctx.lineWidth = 5; ctx.lineCap = "round";
      ctx.beginPath(); ctx.arc(-12, 4, 12, Math.PI * 0.5, Math.PI * 1.5); ctx.arc(0, -6, 14, Math.PI, 0); ctx.arc(13, 4, 12, Math.PI * 1.5, Math.PI * 0.5); ctx.closePath(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(-26, 24); ctx.lineTo(26, -24); ctx.stroke();
    }
    ctx.restore();
  }

  // ================================================================= animação: estado → pesos e cabeça
  const VOGAIS = [["boca_a", 0.36], ["boca_e", 0.24], ["boca_o", 0.2], ["boca_i", 0.12], ["boca_u", 0.08]];
  function sortearVogal() {
    let r = Math.random();
    for (const [v, p] of VOGAIS) { if ((r -= p) <= 0) return v; }
    return "boca_a";
  }

  function atualizar(dt, t) {
    const m = estado.modo, ef = estado.efeito;
    const alvoEf = EMOCOES[estado.emocao] || EMOCOES.neutra;
    const k = 1 - Math.pow(0.001, dt);
    for (const c of ["forca", "luz", "sat"]) ef[c] = lerp(ef[c], alvoEf[c], k);
    for (let i = 0; i < 3; i++) ef.cor[i] = lerp(ef.cor[i], alvoEf.cor[i], k);
    const corAlvo = m === "alerta" ? HALO.alerta : m === "ouvindo" ? HALO.ouvindo : estado.emocao === "feliz" ? HALO.feliz : HALO.normal;
    for (let i = 0; i < 3; i++) estado.brilho[i] = lerp(estado.brilho[i], corAlvo[i], 1 - Math.pow(0.02, dt));
    estado.cinza = lerp(estado.cinza, m === "offline" ? 0.8 : 0, 1 - Math.pow(0.02, dt));
    const olhosFechados = m === "dormindo" || m === "privado";
    estado.fechar = lerp(estado.fechar, olhosFechados ? 1 : m === "offline" ? 0.45 : 0, 1 - Math.pow(0.01, dt));
    const abreAlvo = m === "falando" ? Math.min(1, estado.voz * 1.15) : m === "alerta" ? 0.25 : 0;
    estado.boca = lerp(estado.boca, abreAlvo, 1 - Math.pow(0.0003, dt));

    // piscar (às vezes duas vezes seguidas)
    estado.proxPiscada -= dt;
    if (estado.proxPiscada <= 0 && estado.fechar < 0.3) {
      estado.piscar = 1;
      estado.piscadaDupla = !estado.piscadaDupla && Math.random() < 0.18;
      estado.proxPiscada = estado.piscadaDupla ? 0.28 : 2.2 + Math.random() * 4.2;
      movimento(0.35);
    }
    estado.piscar = Math.max(0, estado.piscar - dt * 6.2);

    // olhar: pequenas mudanças de foco; olha para você quando ouve; para cima pensando
    const o = estado.olhar;
    o.prox -= dt;
    if (m === "ouvindo" || m === "aguardando" || m === "falando" && Math.random() < dt * 0.5) { o.alvoX = 0; o.alvoY = 0; }
    else if (m === "pensando") { o.alvoX = -0.55; o.alvoY = 0.6; }
    else if (m === "executando") { o.alvoX = 0.35; o.alvoY = -0.35; }
    else if (o.prox <= 0) {
      o.alvoX = (Math.random() - 0.5) * 0.9; o.alvoY = (Math.random() - 0.5) * 0.5;
      o.prox = 1.2 + Math.random() * 3; movimento(0.4);
    }
    if (estado.emocao === "triste") o.alvoY = Math.min(o.alvoY, -0.3);
    const ko = 1 - Math.pow(0.00002, dt);                    // o olho vai rápido (sacada)
    o.x = lerp(o.x, o.alvoX, ko); o.y = lerp(o.y, o.alvoY, ko);

    // fala: vogais que mudam com o som
    estado.proxVogal -= dt;
    if (estado.proxVogal <= 0) { estado.vogal = sortearVogal(); estado.proxVogal = 0.08 + Math.random() * 0.07; }

    // cabeça: respiração, balanço, gestos, e acompanha o olhar
    const cab = estado.cabeca;
    let yaw = 0.05 * Math.sin(t * 0.47) + 0.025 * Math.sin(t * 1.13) + o.x * 0.1;
    let pitch = 0.03 * Math.sin(t * 0.61) - o.y * 0.05;
    let roll = 0.02 * Math.sin(t * 0.37);
    if (m === "ouvindo") { roll += 0.07; pitch -= 0.02; }
    else if (m === "pensando") { roll -= 0.05; pitch -= 0.04; }
    else if (m === "dormindo" || m === "offline") { pitch += 0.14; roll += 0.06; }
    else if (m === "aguardando") roll += 0.05;
    if (estado.gesto) {
      const f = (t - estado.gestoT) / 0.9;
      if (f >= 1) estado.gesto = null;
      else {
        const env = Math.sin(f * Math.PI);
        if (estado.gesto === "acenar") pitch += Math.sin(f * Math.PI * 4) * 0.13 * env;
        else if (estado.gesto === "negar") yaw += Math.sin(f * Math.PI * 5) * 0.2 * env;
        else if (estado.gesto === "inclinar") roll += 0.14 * env;
      }
    }
    const kc = 1 - Math.pow(0.004, dt);
    cab.yaw = estado.gesto ? yaw : lerp(cab.yaw, yaw, kc);
    cab.pitch = estado.gesto ? pitch : lerp(cab.pitch, pitch, kc);
    cab.roll = lerp(cab.roll, roll, kc);
    if (estado.forcado && estado.forcado.cabeca) Object.assign(cab, estado.forcado.cabeca);   // testes e prévias

    // pesos das shape keys
    const alvo = {};
    const exp = EXPRESSOES[estado.emocao] || EXPRESSOES.neutra;
    for (const [n, v] of Object.entries(exp)) alvo[n] = v;
    if (m === "ouvindo") { alvo.arregalar = Math.max(alvo.arregalar || 0, 0.18); alvo.sobrancelhas_cima = Math.max(alvo.sobrancelhas_cima || 0, 0.25); }
    if (m === "alerta") { alvo.arregalar = Math.max(alvo.arregalar || 0, 0.45); alvo.sobrancelhas_cima = 0.6; }
    if (m === "falando" || estado.boca > 0.02) {
      const a = estado.boca;
      for (const [v] of VOGAIS) alvo[v] = (alvo[v] || 0) * (1 - a);
      alvo[estado.vogal] = Math.max(alvo[estado.vogal] || 0, a);
      alvo.sorriso = (alvo.sorriso || 0) * (1 - a * 0.4);
    }
    const piscada = Math.sin(Math.min(1, estado.piscar) * Math.PI);
    const fechado = Math.max(estado.fechar, piscada, alvo.piscar || 0);
    delete alvo.piscar;
    alvo.piscar_direito = alvo.piscar_esquerdo = fechado;
    if (fechado > 0.5) alvo.olhos_felizes = (alvo.olhos_felizes || 0) * (1 - fechado);
    alvo.olhar_esquerda = Math.max(0, -o.x); alvo.olhar_direita = Math.max(0, o.x);
    alvo.olhar_cima = Math.max(0, o.y); alvo.olhar_baixo = Math.max(0, -o.y);
    const f = estado.forcado;
    if (f) {
      if (f.piscar != null) alvo.piscar_direito = alvo.piscar_esquerdo = f.piscar;
      if (f.boca != null) { for (const [v] of VOGAIS) alvo[v] = 0; alvo.boca_a = f.boca; }
      if (f.sorriso != null) alvo.sorriso = f.sorriso;
      if (f.olhar) { alvo.olhar_esquerda = Math.max(0, -f.olhar[0]); alvo.olhar_direita = Math.max(0, f.olhar[0]); alvo.olhar_cima = Math.max(0, f.olhar[1]); alvo.olhar_baixo = Math.max(0, -f.olhar[1]); }
      if (f.pesos) Object.assign(alvo, f.pesos);
    }
    const rapidos = new Set(["piscar_direito", "piscar_esquerdo", "olhar_esquerda", "olhar_direita", "olhar_cima", "olhar_baixo", ...VOGAIS.map((v) => v[0])]);
    const kl = 1 - Math.pow(0.02, dt), kr = 1 - Math.pow(0.000001, dt);
    const todos = new Set([...Object.keys(alvo), ...Object.keys(estado.pesos)]);
    for (const n of todos) {
      const v = alvo[n] || 0, atual = estado.pesos[n] || 0;
      const kk = f ? 1 : rapidos.has(n) ? kr : kl;
      const novo = lerp(atual, v, kk);
      if (Math.abs(novo) < 0.001 && !v) delete estado.pesos[n]; else estado.pesos[n] = novo;
    }
    return olhosFechados;
  }

  // ================================================================= quadros por segundo (economia)
  const QPS = { falando: 24, ouvindo: 30, alerta: 30, pensando: 20, executando: 20, aguardando: 16,
                ocioso: 8, offline: 8, dormindo: 8, privado: 8 };
  let ultimo = performance.now(), ultimoDesenho = 0, turboAte = 0, espera = null, pedido = 0;
  function movimento(segundos) { turboAte = Math.max(turboAte, performance.now() + segundos * 1000); acordar(); }
  function agendar() {
    if (reserva || espera !== null || pedido || document.hidden) return;
    const agora = performance.now();
    const qps = Math.max(QPS[estado.modo] || 10, agora < turboAte ? 30 : 0, estado.gesto ? 30 : 0);
    const falta = 1000 / qps - (agora - ultimoDesenho);
    if (falta <= 8) pedido = requestAnimationFrame(passo);
    else espera = setTimeout(() => { espera = null; pedido = requestAnimationFrame(passo); }, falta);
  }
  function acordar() {
    if (espera !== null) { clearTimeout(espera); espera = null; }
    agendar();
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { ultimo = performance.now(); acordar(); } });

  function passo(agora) {
    pedido = 0;
    if (reserva) return;
    ultimoDesenho = performance.now();
    const dt = Math.min((agora - ultimo) / 1000, 0.25);
    ultimo = agora;
    const t = agora / 1000;
    const olhosFechados = atualizar(dt, t);
    if (W > 4 && H > 4) {
      const q = quadro();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (!TRANSPARENTE) { ctx.fillStyle = "#0b0712"; ctx.fillRect(0, 0, W, H); }
      halo(q, t);
      ctx.save();
      moldura(q); ctx.clip();
      ctx.drawImage(fundoPronto(q), q.x, q.y, q.w, q.h);
      if (modelo) {
        try {
          aplicarPesos(estado.pesos);
          desenhar3d(Math.round(q.w * dpr), Math.round(q.h * dpr), t);
          ctx.drawImage(tela3d, q.x, q.y, q.w, q.h);
        } catch (e) { usarReserva(e.message); ctx.restore(); return; }
      }
      tingir(q, olhosFechados);
      ctx.restore();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      borda(q, t);
      selo(q, t);
    }
    agendar();
  }

  window.Rosto = {
    modo(m) { if (m !== estado.modo) { estado.modo = m; movimento(0.8); } },
    emocao(e) {
      const nova = EMOCOES[e] ? e : "neutra";
      if (nova !== estado.emocao) { estado.emocao = nova; movimento(0.8); }
    },
    voz(v) { estado.voz = v; },
    mic(v) { estado.mic = v; },
    gesto(g) { estado.gesto = g; estado.gestoT = performance.now() / 1000; movimento(1); },
    forcar(f) { estado.forcado = f; acordar(); },          // testes: {piscar, boca, sorriso, olhar: [x, y], pesos, cabeca}
    get estado() { return estado; },
  };

  // ================================================================= começar
  redimensionar();
  if (!gl) { usarReserva("este navegador não tem WebGL"); return; }
  tela3d.addEventListener("webglcontextlost", (e) => { e.preventDefault(); usarReserva("a placa de vídeo reiniciou"); });
  try {
    progs = {
      toon: compilar(VERT_TOON, FRAG_TOON),
      plano: compilar(VERT_PLANO, FRAG_PLANO),
      vidro: compilar(VERT_TOON, FRAG_VIDRO),
    };
  } catch (e) { usarReserva("shader: " + e.message); return; }
  fetch(MODELO).then((r) => {
    if (!r.ok) throw new Error(`modelo ${r.status}`);
    return r.arrayBuffer();
  }).then((buf) => {
    modelo = montar(lerGLB(buf));
    estado.malha = { triangulos: modelo.triangulos, pecas: modelo.pecas.length, expressoes: modelo.alvos,
                     cabeca: modelo.cabeca >= 0 };
    movimento(1);
  }).catch((e) => usarReserva(e.message));
  agendar();
})();
