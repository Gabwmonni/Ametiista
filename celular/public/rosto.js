// Ametista: o rosto dela é uma malha 3D (modelo/ametista.blend → ametista.glb), feita no Blender em cima da
// pintura dela (a ficha de personagem): cada vértice fica no lugar do desenho e usa a cor dele. Parada, é a
// própria pintura; mexendo, é uma malha com relevo, ossos e shape keys: pisca (os cílios giram com a pálpebra),
// olha, fala (a, e, i, o, u), sorri, franze, cora, e a cabeça acena, nega, inclina e respira com profundidade.
//
// Estados (Rosto.modo):  dormindo | ocioso | ouvindo | pensando | falando |
//                        executando | alerta | offline | aguardando | privado
// Emoções (Rosto.emocao): neutra | feliz | pensativa | surpresa | triste | brava
// Gestos (Rosto.gesto):  acenar (sim com a cabeça) | negar | inclinar
//
// Leve de propósito: uma textura, poucas chamadas de desenho, ossos na placa de vídeo; só as partes que mexem
// (olhos, boca, sobrancelhas) são recalculadas, e só quando mudam. 24 quadros/s falando, 30 só no instante de
// uma piscada ou gesto, 8 parada, nada quando a janela ou o app estão escondidos. Sem WebGL (ou sem o modelo),
// usa o rosto de reserva (rosto2d.js, a ilustração animada em 2D).
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
    feliz:     { cor: [255, 190, 230], forca: 0.10, luz: 1.03, sat: 1.00 },
    pensativa: { cor: [190, 200, 255], forca: 0.08, luz: 0.99, sat: 0.96 },
    surpresa:  { cor: [255, 255, 255], forca: 0.08, luz: 1.04, sat: 1.00 },
    triste:    { cor: [150, 170, 230], forca: 0.16, luz: 0.93, sat: 0.82 },
    brava:     { cor: [255, 120, 130], forca: 0.12, luz: 0.98, sat: 1.00 },
  };
  // expressões (pesos das shape keys) de cada emoção
  const EXPRESSOES = {
    neutra:    {},
    feliz:     { sorriso: 0.85, olhos_felizes: 0.3, sobrancelhas_cima: 0.25, blush: 1 },
    pensativa: { sobrancelha_pensativa: 0.9, boca_u: 0.15, triste: 0.15 },
    surpresa:  { arregalar: 0.9, sobrancelhas_cima: 1, boca_o: 0.4 },
    triste:    { sobrancelhas_tristes: 0.9, triste: 0.8, piscar: 0.25 },
    brava:     { sobrancelhas_bravas: 1, bravo: 0.8, piscar: 0.12 },
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
    cabeca: { yaw: 0, pitch: 0, roll: 0 },
    gesto: null, gestoT: 0,
    olhar: { x: 0, y: 0, alvoX: 0, alvoY: 0, prox: 1.5 },
    vogal: "boca_a", proxVogal: 0,
    reflexo: -1, proxReflexo: 5,               // o brilho iridescente que atravessa a pintura de vez em quando
    pesos: {},                                 // shape keys suavizadas
    forcado: null,                             // testes: {piscar, boca, sorriso, olhar: [x, y], pesos, cabeca}
    malha: null,                               // informações do modelo carregado
  };

  // ================================================================= WebGL
  const tela3d = document.createElement("canvas");
  const opcoesGL = { alpha: true, antialias: true, stencil: false, premultipliedAlpha: true, depth: true };
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

  // os ossos (até 8) movem os vértices na placa de vídeo; a cor vem da pintura (textura com alfa pré-multiplicado)
  const VERT = `
    attribute vec3 aP; attribute vec2 aUV; attribute vec4 aJ; attribute vec4 aW;
    uniform mat4 uOssos[8]; uniform mat4 uP;
    varying vec2 vUV; varying vec2 vTela;
    void main() {
      mat4 m = uOssos[int(aJ.x)] * aW.x + uOssos[int(aJ.y)] * aW.y + uOssos[int(aJ.z)] * aW.z + uOssos[int(aJ.w)] * aW.w;
      vec4 p = uP * (m * vec4(aP, 1.0));
      vUV = aUV; vTela = p.xy;
      gl_Position = p;
    }`;
  const FRAG_PINTURA = `
    precision mediump float;
    varying vec2 vUV; varying vec2 vTela;
    uniform sampler2D uTex; uniform float uReflexo; uniform float uOpaco; uniform float uNitidez;
    vec3 irid(float x) {              // rosa → lilás → azul-cristal → rosa
      float f = fract(x) * 3.0;
      vec3 a = vec3(1.0, 0.78, 0.93), b = vec3(0.8, 0.7, 0.97), c = vec3(0.7, 0.88, 1.0);
      return f < 1.0 ? mix(a, b, f) : f < 2.0 ? mix(b, c, f - 1.0) : mix(c, a, f - 2.0);
    }
    void main() {
      vec4 c = texture2D(uTex, vUV, uNitidez);
      if (uOpaco > 0.5) c.a = 1.0;
      float d = vTela.x * 0.55 + vTela.y * 0.84 - uReflexo;
      float faixa = exp(-d * d * 14.0);
      float lum = dot(c.rgb, vec3(0.3, 0.59, 0.11));
      c.rgb += irid(vTela.x * 0.7 - vTela.y * 0.4 + uReflexo * 0.5) * faixa * (0.05 + 0.22 * lum * lum) * c.a;
      gl_FragColor = c;
    }`;
  const FRAG_BLUSH = `
    precision mediump float;
    varying vec2 vUV;
    uniform vec3 uCor; uniform float uAlfa;
    void main() {
      float r = length((vUV - 0.5) * 2.0);
      float a = uAlfa * pow(1.0 - smoothstep(0.0, 1.0, r), 1.6);
      gl_FragColor = vec4(uCor * a, a);
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
    ["aP", "aUV", "aJ", "aW"].forEach((n, i) => gl.bindAttribLocation(p, i, n));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) || "programa");
    const u = {};
    const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
    for (let i = 0; i < n; i++) {
      const a = gl.getActiveUniform(p, i);
      u[a.name.replace(/\[0\]$/, "")] = gl.getUniformLocation(p, a.name);
    }
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
    const out = comoFloat ? new Float32Array(total) : new T(total);
    const escala = comoFloat && a.normalized ? 1 / MAXNORM[a.componentType] : 1;
    if (a.bufferView !== undefined) {
      const bv = g.json.bufferViews[a.bufferView];
      const tam = nc * T.BYTES_PER_ELEMENT;
      const passo = bv.byteStride || tam;
      const ini = (bv.byteOffset || 0) + (a.byteOffset || 0);
      if (passo === tam && ini % T.BYTES_PER_ELEMENT === 0) {          // o caso comum: copia direto
        const src = new T(g.bin, ini, total);
        if (escala === 1) out.set(src); else for (let k = 0; k < total; k++) out[k] = src[k] * escala;
      } else {
        const dv = new DataView(g.bin, ini);
        const ler = { 5120: "getInt8", 5121: "getUint8", 5122: "getInt16", 5123: "getUint16", 5125: "getUint32", 5126: "getFloat32" }[a.componentType];
        for (let k = 0; k < a.count; k++)
          for (let c = 0; c < nc; c++) out[k * nc + c] = dv[ler](k * passo + c * T.BYTES_PER_ELEMENT, true) * escala;
      }
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
    rz(a) { const c = Math.cos(a), s = Math.sin(a); return new Float32Array([c, s, 0, 0, -s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]); },
    rot(yaw, pitch, roll) {           // Y (virar), X (acenar), Z (inclinar)
      const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
      const ry = new Float32Array([cy, 0, -sy, 0, 0, 1, 0, 0, sy, 0, cy, 0, 0, 0, 0, 1]);
      const rx = new Float32Array([1, 0, 0, 0, 0, cp, sp, 0, 0, -sp, cp, 0, 0, 0, 0, 1]);
      return M.mul(ry, M.mul(rx, M.rz(roll)));
    },
    persp(fov, asp, perto, longe) {
      const f = 1 / Math.tan(fov / 2), nf = 1 / (perto - longe);
      return new Float32Array([f / asp, 0, 0, 0, 0, f, 0, 0, 0, 0, (longe + perto) * nf, -1, 0, 0, 2 * longe * perto * nf, 0]);
    },
    ortho(l, r, b, t, perto, longe) {
      return new Float32Array([2 / (r - l), 0, 0, 0, 0, 2 / (t - b), 0, 0, 0, 0, -2 / (longe - perto), 0,
        -(r + l) / (r - l), -(t + b) / (t - b), -(longe + perto) / (longe - perto), 1]);
    },
    aplicar(m, p) {
      return [m[0] * p[0] + m[4] * p[1] + m[8] * p[2] + m[12], m[1] * p[0] + m[5] * p[1] + m[9] * p[2] + m[13],
        m[2] * p[0] + m[6] * p[1] + m[10] * p[2] + m[14]];
    },
  };

  // Como desenhar cada material: pelo nome (o contrato com o Blender)
  //   corpo, olho, boca_dentro: opacos, com a cor da textura     rosto: a máscara do rosto (a borda some aos poucos)
  //   iris, cilios: com transparência      blush: o rubor (aparece com o peso "blush")
  //   brilho: estrelinhas que cintilam nos cristais
  function tipoMaterial(nome) {
    const base = String(nome || "").toLowerCase().replace(/\.\d+$/, "");
    const e = (k) => base === k || base.startsWith(k + "_");
    if (e("brilho")) return "brilho";
    if (e("blush")) return "blush";
    if (e("iris") || e("cilios")) return "camada";
    if (e("rosto")) return "mascara";
    return "opaco";
  }
  const ORDEM = { opaco: 0, mascara: 1, camada: 2, blush: 3 };

  // ================================================================= o modelo na GPU
  let progs = null, modelo = null;

  const fonteDe = (tex) => tex.source !== undefined ? tex.source : tex.extensions && Object.values(tex.extensions)[0].source;

  async function carregarImagem(g, indice) {
    const im = g.json.images[indice];
    const bv = g.json.bufferViews[im.bufferView];
    const blob = new Blob([new Uint8Array(g.bin, bv.byteOffset || 0, bv.byteLength)], { type: im.mimeType || "image/png" });
    if (window.createImageBitmap)
      return createImageBitmap(blob, { premultiplyAlpha: "premultiply", colorSpaceConversion: "none" });
    return new Promise((ok, erro) => {
      const i = new Image(); i.onload = () => ok(i); i.onerror = () => erro(new Error("textura ilegível"));
      i.src = URL.createObjectURL(blob);
    });
  }

  // as imagens do modelo (cada uma lida uma vez só, com mipmaps e alfa pré-multiplicado); devolve, para cada
  // textura do glTF (o Blender repete a mesma imagem em várias), a textura da placa correspondente
  async function texturas(g) {
    const lista = g.json.textures || [];
    if (!lista.length) throw new Error("o modelo não tem textura");
    const usadas = [...new Set(lista.map(fonteDe))];
    const imagens = await Promise.all(usadas.map((i) => carregarImagem(g, i)));
    const naPlaca = {};
    usadas.forEach((indice, k) => {
      const img = imagens[k];
      const t = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, t);
      gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
      gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
      gl.generateMipmap(gl.TEXTURE_2D);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      const ext = gl.getExtension("EXT_texture_filter_anisotropic");
      if (ext && ext.TEXTURE_MAX_ANISOTROPY_EXT) gl.texParameterf(gl.TEXTURE_2D, ext.TEXTURE_MAX_ANISOTROPY_EXT, 4);
      if (img.close) img.close();
      naPlaca[indice] = t;
    });
    return lista.map((tex) => naPlaca[fonteDe(tex)]);
  }

  function montar(g) {
    const mats = (g.json.materials || []).map((m) => {
      const pbr = m.pbrMetallicRoughness || {};
      const bc = pbr.baseColorFactor || [1, 1, 1, 1];
      const tex = pbr.baseColorTexture ? pbr.baseColorTexture.index : 0;
      return { nome: m.name, tipo: tipoMaterial(m.name), cor: bc.slice(0, 3), tex };
    });
    const pecas = [];
    const nomesAlvos = new Set();
    const brilhos = [];
    const meshes = (g.json.meshes || []).map((mesh, mi) => {
      const nomes = (mesh.extras && mesh.extras.targetNames) || [];
      nomes.forEach((n) => nomesAlvos.add(n));
      return mesh.primitives.map((pr) => {
        if (pr.mode !== undefined && pr.mode !== 4) return null;          // só triângulos
        const at = pr.attributes;
        const pos = acessor(g, at.POSITION);
        const nv = pos.length / 3;
        const mat = mats[pr.material] || { tipo: "opaco", cor: [1, 1, 1] };
        const uv = at.TEXCOORD_0 !== undefined ? acessor(g, at.TEXCOORD_0) : new Float32Array(nv * 2);
        const jt = at.JOINTS_0 !== undefined ? acessor(g, at.JOINTS_0) : new Float32Array(nv * 4);
        let w = at.WEIGHTS_0 !== undefined ? acessor(g, at.WEIGHTS_0) : null;
        if (!w) { w = new Float32Array(nv * 4); for (let k = 0; k < nv; k++) w[k * 4] = 1; }
        const idx = pr.indices !== undefined ? acessor(g, pr.indices, false) : null;
        if (mat.tipo === "brilho") {                                     // os brilhos: só o centro de cada um
          const tri = idx || [...Array(nv).keys()];
          for (let i = 0; i + 5 < tri.length; i += 6) {
            const vs = [...new Set([tri[i], tri[i + 1], tri[i + 2], tri[i + 3], tri[i + 4], tri[i + 5]])];
            const c = [0, 1, 2].map((e) => vs.reduce((s, v) => s + pos[v * 3 + e], 0) / vs.length);
            brilhos.push({ mesh: mi, p: c, j: Array.from(jt.subarray(vs[0] * 4, vs[0] * 4 + 4)), w: Array.from(w.subarray(vs[0] * 4, vs[0] * 4 + 4)) });
          }
          return null;
        }
        const alvos = (pr.targets || []).map((t) => t.POSITION !== undefined ? acessor(g, t.POSITION) : null);
        const p = {
          mesh: mi, nomes, mat,
          base: pos, atual: new Float32Array(pos), alvos, pesos: new Float32Array(alvos.length),
          n: idx ? idx.length : nv,
          bufP: buffer(pos, alvos.length ? gl.DYNAMIC_DRAW : gl.STATIC_DRAW),
          bufUV: buffer(uv), bufJ: buffer(jt), bufW: buffer(w),
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
    // nós, ossos e a pele (skin)
    const nos = (g.json.nodes || []).map((n) => ({
      nome: n.name || "", filhos: n.children || [], mesh: n.mesh, pele: n.skin, extras: n.extras || {},
      local: n.matrix ? new Float32Array(n.matrix) : M.trs(n.translation, n.rotation, n.scale),
      t: n.translation || [0, 0, 0], r: n.rotation, s: n.scale,
    }));
    const pai = new Array(nos.length).fill(-1);
    nos.forEach((n, i) => n.filhos.forEach((f) => { pai[f] = i; }));
    const peles = (g.json.skins || []).map((s) => {
      const ibm = s.inverseBindMatrices !== undefined ? acessor(g, s.inverseBindMatrices) : null;
      return { juntas: s.joints, ibm: s.joints.map((_, k) => ibm ? ibm.subarray(k * 16, k * 16 + 16) : M.id()) };
    });
    if (peles.some((s) => s.juntas.length > 8)) throw new Error("ossos demais (até 8)");
    const raiz = nos.find((n) => n.extras && n.extras.quadro_tudo) || { extras: {} };
    const ex = raiz.extras;
    const info = {                                   // enquadramentos: [centro x, centro y, altura], em unidades
      tudo: ex.quadro_tudo || [0, 0.655, 0.52], rosto: ex.quadro_rosto || [0, 0.705, 0.34],
      inclinacao: ex.inclinacao_rosto || 0,
    };
    const ossos = {};
    nos.forEach((n, i) => { if (/^(raiz|peito|pescoco|cabeca|cabelo_e|cabelo_d)$/.test(n.nome)) ossos[n.nome] = i; });
    const tri = pecas.reduce((s, p) => s + p.n / 3, 0);
    return { mats, meshes, pecas, nos, pai, peles, info, ossos, brilhos, texturas: null,
             alvos: [...nomesAlvos], triangulos: Math.round(tri) };
  }

  function buffer(dados, uso) {
    const b = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, b);
    gl.bufferData(gl.ARRAY_BUFFER, dados, uso || gl.STATIC_DRAW);
    return b;
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

  // ================================================================= ossos: a cabeça, o pescoço, o peito, as mechas
  function posarOssos(t) {
    const cab = estado.cabeca, info = modelo.info;
    if (estado.forcado && estado.forcado.quieto) t = 0;
    // os gestos são em volta dos eixos do rosto dela (a cabeça está inclinada na pintura)
    const incl = info.inclinacao;
    const noRosto = (yaw, pitch, roll) => M.mul(M.rz(incl), M.mul(M.rot(yaw, pitch, roll), M.rz(-incl)));
    const extra = {
      pescoco: noRosto(cab.yaw * 0.35, cab.pitch * 0.35, cab.roll * 0.35),
      cabeca: noRosto(cab.yaw * 0.65, cab.pitch * 0.65, cab.roll * 0.65),
      cabelo_e: M.rz(0.012 * Math.sin(t * 1.1) + 0.006 * Math.sin(t * 2.3 + 1) - cab.roll * 0.2 + cab.yaw * 0.15),
      cabelo_d: M.rz(0.01 * Math.sin(t * 1.3 + 2) + 0.005 * Math.sin(t * 2.1) - cab.roll * 0.2 - cab.yaw * 0.15),
    };
    const resp = Math.sin(t * 1.6) * 0.0035;
    const mundos = new Array(modelo.nos.length);
    const nomeDe = {};
    for (const [n, i] of Object.entries(modelo.ossos)) nomeDe[i] = n;
    const visitar = (i, paiM) => {
      const n = modelo.nos[i];
      let local = n.local;
      const nome = nomeDe[i];
      if (nome === "peito") local = M.mul(M.trs([n.t[0], n.t[1] + resp, n.t[2]]), M.trs([0, 0, 0], n.r, n.s));
      if (nome && extra[nome]) local = M.mul(local, extra[nome]);
      mundos[i] = M.mul(paiM, local);
      n.filhos.forEach((f) => visitar(f, mundos[i]));
    };
    modelo.nos.forEach((n, i) => { if (modelo.pai[i] < 0) visitar(i, M.id()); });
    return mundos;
  }

  function matrizesDaPele(mundos, no) {
    const n = modelo.nos[no];
    const out = new Float32Array(16 * 8);
    if (n.pele === undefined) { out.set(mundos[no], 0); return out; }
    const pele = modelo.peles[n.pele];
    pele.juntas.forEach((j, k) => out.set(M.mul(mundos[j], pele.ibm[k]), k * 16));
    return out;
  }

  // ================================================================= desenho 3D
  let ultimaProj = null;
  function enquadrar(largura, altura) {
    // molduras altas mostram o busto; molduras mais quadradas (ou largas) fecham no rosto
    const info = modelo.info, asp = largura / altura;
    const f = Math.min(1, Math.max(0, (asp - 0.66) / (0.95 - 0.66)));
    const [tx, ty, th] = info.tudo, [rx, ry, rh] = info.rosto;
    let cx = tx + (rx - tx) * f, cy = ty + (ry - ty) * f, h = th + (rh - th) * f;
    if (estado.forcado && estado.forcado.quadro) [cx, cy, h] = estado.forcado.quadro;     // prévias e testes
    const fov = 0.32;                                // ~18°: pouca perspectiva, como uma lente de retrato
    const dist = h / 2 / Math.tan(fov / 2);
    const plano = 0.1;                               // o plano do rosto (a frente dela fica em z ~0,15)
    const P = M.persp(fov, asp, dist * 0.6, dist * 1.6);
    return M.mul(P, M.trs([-cx, -cy, -(plano + dist)]));
  }

  function desenhar3d(largura, altura, t) {
    if (tela3d.width !== largura || tela3d.height !== altura) { tela3d.width = largura; tela3d.height = altura; }
    gl.viewport(0, 0, largura, altura);
    gl.clearColor(0, 0, 0, 0); gl.clearDepth(1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    const P = enquadrar(largura, altura);
    ultimaProj = P;
    const mundos = posarOssos(t);
    modelo.mundos = mundos;
    const lista = [];
    const esconder = (estado.forcado && estado.forcado.esconder) || [];                 // prévias: peças escondidas
    modelo.nos.forEach((n, i) => {
      if (n.mesh === undefined || !modelo.meshes[n.mesh] || esconder.includes(n.nome)) return;
      const ossos = matrizesDaPele(mundos, i);
      modelo.meshes[n.mesh].forEach((p) => lista.push({ p, ossos }));
    });
    lista.sort((a, b) => ORDEM[a.p.mat.tipo] - ORDEM[b.p.mat.tipo]);
    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL);
    gl.disable(gl.CULL_FACE);
    gl.activeTexture(gl.TEXTURE0);
    // a nitidez: um pouco menos de desfoque ao diminuir as texturas (são pintadas, aguentam bem)
    const nitidez = -0.3;
    const reflexo = estado.reflexo < 0 || (estado.forcado && estado.forcado.quieto) ? 9 : -2.2 + estado.reflexo * 4.4;
    for (const d of lista) {
      const m = d.p.mat;
      if (m.tipo === "opaco" || m.tipo === "mascara" || m.tipo === "camada") {
        const pr = progs.pintura;
        gl.useProgram(pr.p);
        gl.bindTexture(gl.TEXTURE_2D, modelo.texturas[m.tex] || modelo.texturas[0]);
        gl.uniformMatrix4fv(pr.u.uP, false, P);
        gl.uniform1i(pr.u.uTex, 0);
        gl.uniform1f(pr.u.uReflexo, reflexo);
        gl.uniform1f(pr.u.uNitidez, nitidez);
        gl.uniform1f(pr.u.uOpaco, m.tipo === "opaco" ? 1 : 0);
        if (m.tipo === "opaco") { gl.disable(gl.BLEND); gl.depthMask(true); }
        else { gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA); gl.depthMask(m.tipo === "mascara"); }
        desenharPeca(pr, d);
      } else if (m.tipo === "blush") {
        const alfa = (estado.pesos.blush || 0) * 0.3;
        if (alfa < 0.01) continue;
        const pr = progs.blush;
        gl.useProgram(pr.p);
        gl.uniformMatrix4fv(pr.u.uP, false, P);
        gl.uniform3fv(pr.u.uCor, m.cor);
        gl.uniform1f(pr.u.uAlfa, alfa);
        gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA); gl.depthMask(false);
        desenharPeca(pr, d);
      }
    }
    gl.depthMask(true); gl.disable(gl.BLEND);
  }

  function desenharPeca(pr, d) {
    const p = d.p;
    gl.uniformMatrix4fv(pr.u.uOssos, false, d.ossos);
    const attr = (loc, buf, n) => {
      gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, n, gl.FLOAT, false, 0, 0);
    };
    attr(0, p.bufP, 3); attr(1, p.bufUV, 2); attr(2, p.bufJ, 4); attr(3, p.bufW, 4);
    if (p.bufI) { gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, p.bufI); gl.drawElements(gl.TRIANGLES, p.n, p.tipoI, 0); }
    else gl.drawArrays(gl.TRIANGLES, 0, p.n);
  }

  // onde cada brilho está na tela agora (segue a cabeça)
  function brilhosNaTela(q) {
    if (!modelo || !modelo.mundos || !ultimaProj) return [];
    const out = [];
    const cache = {};
    for (const b of modelo.brilhos) {
      const no = modelo.nos.findIndex((n) => n.mesh === b.mesh);
      if (no < 0) continue;
      const ossos = cache[no] || (cache[no] = matrizesDaPele(modelo.mundos, no));
      let p = [0, 0, 0];
      for (let k = 0; k < 4; k++) {
        if (!b.w[k]) continue;
        const r = M.aplicar(ossos.subarray(b.j[k] * 16, b.j[k] * 16 + 16), b.p);
        p = p.map((v, e) => v + r[e] * b.w[k]);
      }
      const c = M.aplicar(ultimaProj, p);
      out.push([q.x + (c[0] * 0.5 + 0.5) * q.w, q.y + (0.5 - c[1] * 0.5) * q.h]);
    }
    return out;
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
  function estrela(x, y, r, a) {
    ctx.save(); ctx.translate(x, y); ctx.globalAlpha = a;
    const g = ctx.createRadialGradient(0, 0, 0, 0, 0, r);
    g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.4, "rgba(214,200,255,0.8)"); g.addColorStop(1, "rgba(214,200,255,0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.moveTo(0, -r); ctx.quadraticCurveTo(r * 0.12, -r * 0.12, r, 0); ctx.quadraticCurveTo(r * 0.12, r * 0.12, 0, r);
    ctx.quadraticCurveTo(-r * 0.12, r * 0.12, -r, 0); ctx.quadraticCurveTo(-r * 0.12, -r * 0.12, 0, -r);
    ctx.fill(); ctx.restore();
  }
  function cintilar(q, t) {
    const intenso = estado.modo === "pensando" || estado.modo === "executando" ? 1.6 : 1;
    const esc = q.h / 330;
    brilhosNaTela(q).forEach(([x, y], i) => {
      const f = Math.sin(t * (0.9 + (i % 5) * 0.23) + i * 1.7);
      if (f > 0.55) estrela(x, y, (4 + f * 3.5 * intenso) * esc, (f - 0.55) * 2.2);
    });
  }
  const COM_ICONE = ["dormindo", "pensando", "executando", "aguardando", "privado", "offline"];
  function selo(q, t) {
    const m = estado.modo;
    if (!COM_ICONE.includes(m)) return;
    const r = Math.max(9, Math.min(W, H) * 0.11);
    ctx.save();
    // inteiro dentro da moldura (onde o fundo é repintado a cada quadro)
    ctx.translate(q.x + q.w - r - q.r * 0.3, q.y + r + q.r * 0.3);
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

    // o brilho iridescente que atravessa a pintura
    estado.proxReflexo -= dt;
    if (estado.proxReflexo <= 0 && !olhosFechados && m !== "offline") {
      estado.reflexo = 0; estado.proxReflexo = 7 + Math.random() * 8; movimento(1.3);
    }
    if (estado.reflexo >= 0) estado.reflexo = estado.reflexo + dt / 1.2 > 1 ? -1 : estado.reflexo + dt / 1.2;

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
      alvo.bravo = (alvo.bravo || 0) * (1 - a);                 // falando, os lábios não ficam apertados
    }
    const piscada = Math.sin(Math.min(1, estado.piscar) * Math.PI);
    const f = estado.forcado;
    const fechado = f && f.piscar != null ? f.piscar : Math.max(estado.fechar, piscada, alvo.piscar || 0);
    delete alvo.piscar;
    alvo.piscar_direito = alvo.piscar_esquerdo = fechado;
    if (fechado > 0.5) alvo.olhos_felizes = (alvo.olhos_felizes || 0) * (1 - fechado);
    alvo.olhar_esquerda = Math.max(0, -o.x); alvo.olhar_direita = Math.max(0, o.x);
    alvo.olhar_cima = Math.max(0, o.y); alvo.olhar_baixo = Math.max(0, -o.y);
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
      if (modelo && modelo.texturas) {
        try {
          aplicarPesos(estado.pesos);
          desenhar3d(Math.round(q.w * dpr), Math.round(q.h * dpr), t);
          ctx.drawImage(tela3d, q.x, q.y, q.w, q.h);
          if (!olhosFechados && estado.modo !== "offline" && !(estado.forcado && estado.forcado.quieto)) cintilar(q, t);
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
    forcar(f) { estado.forcado = f; acordar(); },          // testes: {piscar, boca, sorriso, olhar: [x, y], pesos, cabeca, quieto}
    get estado() { return estado; },
  };

  // ================================================================= começar
  redimensionar();
  if (!gl) { usarReserva("este navegador não tem WebGL"); return; }
  tela3d.addEventListener("webglcontextlost", (e) => { e.preventDefault(); usarReserva("a placa de vídeo reiniciou"); });
  try {
    progs = { pintura: compilar(VERT, FRAG_PINTURA), blush: compilar(VERT, FRAG_BLUSH) };
  } catch (e) { usarReserva("shader: " + e.message); return; }
  fetch(MODELO).then((r) => {
    if (!r.ok) throw new Error(`modelo ${r.status}`);
    return r.arrayBuffer();
  }).then(async (buf) => {
    const g = lerGLB(buf);
    const m = montar(g);
    m.texturas = await texturas(g);
    modelo = m;
    estado.malha = { triangulos: m.triangulos, pecas: m.pecas.length, expressoes: m.alvos,
                     cabeca: m.ossos.cabeca !== undefined, ossos: Object.keys(m.ossos), brilhos: m.brilhos.length };
    movimento(1);
  }).catch((e) => usarReserva(e.message));
  agendar();
})();
