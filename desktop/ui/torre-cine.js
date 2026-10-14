/* Jarvis · Torre de Aincrad, versión cine (three.js r180 local, sin CDN).
   Castillo flotante procedimental (gradas con almenas, columnas y arcos, piedra PBR con mapas normal/rugosidad
   generados), luz de luna + resplandor cálido de ciudades bajo las nubes, sombras suaves, nubes en capas,
   brasas y motas holográficas, bloom (UnrealBloomPass), profundidad de campo (BokehPass) y órbita lenta.
   Núcleo Jarvis FUERA de la torre: shader aditivo con fresnel, líneas de barrido, anillos HUD y haz de proyector.
   Modo Ultron (aviso): núcleo, rejilla y resplandor de nubes en rojo-naranja con glitch.
   Si no hay WebGL o la copia de three.js no está disponible, queda la escena 2D (torre-aincrad.js).
   ?calidad=eco reduce GPU; prefers-reduced-motion detiene órbita y glitch. Cifras de negocio: DEMO. */
import * as THREE from "./vendor/three/three.module.js";
import { EffectComposer } from "./vendor/three/postprocessing/EffectComposer.js";
import { RenderPass } from "./vendor/three/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "./vendor/three/postprocessing/UnrealBloomPass.js";
import { BokehPass } from "./vendor/three/postprocessing/BokehPass.js";
import { OutputPass } from "./vendor/three/postprocessing/OutputPass.js";
import { ShaderPass } from "./vendor/three/postprocessing/ShaderPass.js";
import { GTAOPass } from "./vendor/three/postprocessing/GTAOPass.js";
import { AfterimagePass } from "./vendor/three/postprocessing/AfterimagePass.js";
import { HDRLoader } from "./vendor/three/loaders/HDRLoader.js";

const qs = new URLSearchParams(location.search);
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const cores = navigator.hardwareConcurrency || 4;
const ECO = qs.get("calidad") === "eco" || (qs.get("calidad") !== "alta" && cores <= 4);
const TIERS = 25, FLOORS = 100;

function webglOk() {
  try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch (e) { return false; }
}

let rs = 1020;
const rnd = () => (rs = (rs * 16807) % 2147483647) / 2147483647;

/* ---------- texturas procedimentales de piedra (color, normal, rugosidad) ---------- */
function stoneMaps(size) {
  const h = new Float32Array(size * size);
  const oct = [[8, 0.5], [16, 0.25], [32, 0.15], [64, 0.1]];
  const grid = oct.map(([n]) => { const g = []; for (let i = 0; i < (n + 1) * (n + 1); i++) g.push(rnd()); return g; });
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    let v = 0;
    oct.forEach(([n, a], k) => {
      const fx = x / size * n, fy = y / size * n, ix = Math.floor(fx), iy = Math.floor(fy), tx = fx - ix, ty = fy - iy;
      const G = grid[k], w = n + 1, s = (t) => t * t * (3 - 2 * t);
      const a0 = G[iy * w + ix] + (G[iy * w + ix + 1] - G[iy * w + ix]) * s(tx);
      const a1 = G[(iy + 1) * w + ix] + (G[(iy + 1) * w + ix + 1] - G[(iy + 1) * w + ix]) * s(tx);
      v += (a0 + (a1 - a0) * s(ty)) * a;
    });
    const row = Math.floor(y / (size / 8)), bx = (x + (row % 2) * size / 8) % (size / 4), by = y % (size / 8);
    const mortar = (bx < 2 || by < 2) ? -0.35 : 0;                         // bloques de sillería
    h[y * size + x] = v + mortar;
  }
  const mk = () => { const c = document.createElement("canvas"); c.width = c.height = size; return c; };
  const col = mk(), nor = mk(), rou = mk();
  const ci = col.getContext("2d").createImageData(size, size), ni = nor.getContext("2d").createImageData(size, size), ri = rou.getContext("2d").createImageData(size, size);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const i = y * size + x, v = h[i], p = i * 4;
    const g = Math.max(0, Math.min(255, 70 + v * 95));
    ci.data[p] = g * 1.04; ci.data[p + 1] = g; ci.data[p + 2] = g * 0.92; ci.data[p + 3] = 255;
    const dx = h[y * size + ((x + 1) % size)] - h[y * size + ((x - 1 + size) % size)];
    const dy = h[((y + 1) % size) * size + x] - h[((y - 1 + size) % size) * size + x];
    const nx = -dx * 3, ny = -dy * 3, nz = 1, l = Math.hypot(nx, ny, nz);
    ni.data[p] = (nx / l * 0.5 + 0.5) * 255; ni.data[p + 1] = (ny / l * 0.5 + 0.5) * 255; ni.data[p + 2] = (nz / l * 0.5 + 0.5) * 255; ni.data[p + 3] = 255;
    const r = Math.max(0, Math.min(255, 200 - v * 60)); ri.data[p] = ri.data[p + 1] = ri.data[p + 2] = r; ri.data[p + 3] = 255;
  }
  col.getContext("2d").putImageData(ci, 0, 0); nor.getContext("2d").putImageData(ni, 0, 0); rou.getContext("2d").putImageData(ri, 0, 0);
  const tex = (c, srgb) => { const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(6, 1); if (srgb) t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t; };
  return { map: tex(col, true), normalMap: tex(nor), roughnessMap: tex(rou) };
}

function softSprite(size, warmEdge) {
  const c = document.createElement("canvas"); c.width = c.height = size; const g = c.getContext("2d");
  for (let i = 0; i < 26; i++) {                                             // nube: manchas suaves superpuestas
    const x = size * (0.25 + rnd() * 0.5), y = size * (0.35 + rnd() * 0.3), r = size * (0.12 + rnd() * 0.22);
    const gr = g.createRadialGradient(x, y, 0, x, y, r);
    gr.addColorStop(0, "rgba(255,255,255,0.22)"); gr.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = gr; g.beginPath(); g.arc(x, y, r, 0, 6.283); g.fill();
  }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

function dotSprite() {
  const c = document.createElement("canvas"); c.width = c.height = 64; const g = c.getContext("2d");
  const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32); gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(0.3, "rgba(255,255,255,0.5)"); gr.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = gr; g.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c);
}

/* ---------- escena ---------- */
function start() {
  if (!webglOk()) return false;
  const host = document.getElementById("stage") || document.body;
  const canvas = document.createElement("canvas"); canvas.id = "cine"; canvas.setAttribute("aria-label", "Núcleo Jarvis en 3D sobre un mar de nubes nocturno");
  host.appendChild(canvas);
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ canvas, antialias: !ECO, powerPreference: ECO ? "low-power" : "high-performance" }); }
  catch (e) { canvas.remove(); return false; }
  document.body.classList.add("cine");
  if (window.JarvisAincradScene && window.JarvisAincradScene.stop) window.JarvisAincradScene.stop();
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, ECO ? 1 : 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 0.82;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = !ECO; renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x03060d, 0.0016);
  const camera = new THREE.PerspectiveCamera(38, 16 / 9, 0.5, 2000);

  /* cielo: degradado + halo de luna + estrellas */
  const skyU = { uMoon: { value: new THREE.Vector3(0.55, 0.42, -0.72).normalize() } };
  scene.add(new THREE.Mesh(new THREE.SphereGeometry(900, 32, 16), new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, fog: false, uniforms: skyU,
    vertexShader: "varying vec3 vD; void main(){ vD = normalize(position); gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }",
    fragmentShader: "uniform vec3 uMoon; varying vec3 vD; void main(){ float h = clamp(vD.y*0.5+0.5,0.0,1.0);" +
      " vec3 c = mix(vec3(0.012,0.02,0.045), vec3(0.0015,0.003,0.009), smoothstep(0.45,1.0,h));" +
      " c = mix(vec3(0.02,0.03,0.06), c, smoothstep(0.3,0.55,h)); float m = max(dot(vD,uMoon),0.0);" +
      " float mw = exp(-pow(dot(vD, normalize(vec3(0.35,0.55,0.75)))*4.2,2.0)); float nz = fract(sin(dot(floor(vD*180.0),vec3(12.9,78.2,37.7)))*43758.5);" +
      " c += vec3(0.03,0.034,0.05)*mw*(0.55+0.45*sin(vD.x*23.0+vD.z*17.0)*sin(vD.y*31.0)) + vec3(0.025,0.03,0.045)*mw*nz*smoothstep(0.2,0.6,h);" +
      " c += vec3(0.5,0.52,0.58)*pow(m,60.0)*0.35 + vec3(0.2,0.22,0.28)*pow(m,8.0)*0.06; c += vec3(1.0)*smoothstep(0.9993,0.9996,m);" +
      " gl_FragColor = vec4(c,1.0); }" })));
  const starU = { uTime: { value: 0 } };                                          // estrellas: más, mayores, titileo, banda de vía láctea
  { const n = ECO ? 2500 : 7000, p = new Float32Array(n * 3), sz = new Float32Array(n), ph = new Float32Array(n), cl = new Float32Array(n * 3);
    const band = new THREE.Vector3(0.35, 0.55, 0.75).normalize(), v = new THREE.Vector3();
    for (let i = 0; i < n; i++) {
      do { const th = rnd() * 6.283, z = rnd() * 1.9 - 0.9; const q = Math.sqrt(1 - z * z); v.set(q * Math.cos(th), z, q * Math.sin(th)); } while (i % 2 && Math.abs(v.dot(band)) > 0.18);
      p.set([v.x * 850, v.y * 850, v.z * 850], i * 3); sz[i] = 1.2 + Math.pow(rnd(), 6) * 4.5; ph[i] = rnd() * 6.283;
      const w = rnd(); cl.set(w < 0.15 ? [1, 0.85, 0.7] : w < 0.35 ? [0.75, 0.85, 1] : [0.95, 0.97, 1], i * 3); }
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(p, 3)); g.setAttribute("size", new THREE.BufferAttribute(sz, 1));
    g.setAttribute("phase", new THREE.BufferAttribute(ph, 1)); g.setAttribute("color", new THREE.BufferAttribute(cl, 3));
    scene.add(new THREE.Points(g, new THREE.ShaderMaterial({ uniforms: starU, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false,
      vertexShader: "uniform float uTime; attribute float size; attribute float phase; attribute vec3 color; varying vec3 vC; varying float vA;" +
        " void main(){ vC = color; vA = 0.75 + 0.25*sin(uTime*(1.5+phase) + phase*7.0); gl_PointSize = size*(0.85+0.3*vA); gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }",
      fragmentShader: "varying vec3 vC; varying float vA; void main(){ float d = length(gl_PointCoord-0.5); float a = smoothstep(0.5,0.0,d); gl_FragColor = vec4(vC*vA*1.4, a*vA); }" }))); }

  /* luces: luna fría con sombra suave, resplandor cálido desde abajo, relleno */
  scene.add(new THREE.HemisphereLight(0x4a5060, 0x3a2410, 0.35));
  const moon = new THREE.DirectionalLight(0xe2dccf, 4.6); moon.position.set(320, 240, 220); moon.castShadow = !ECO;
  moon.shadow.mapSize.set(ECO ? 1024 : 4096, ECO ? 1024 : 4096); moon.shadow.blurSamples = 16; Object.assign(moon.shadow.camera, { left: -120, right: 120, top: 160, bottom: -80, near: 50, far: 900 }); moon.shadow.radius = 4; moon.shadow.bias = -0.0005;
  scene.add(moon);
  const warmLights = [];
  for (let i = 0; i < 5; i++) { const l = new THREE.PointLight(0xff9a50, 1100, 320, 1.4); const a = i / 5 * 6.283; l.position.set(Math.cos(a) * 140, -95, Math.sin(a) * 140); scene.add(l); warmLights.push(l); }

  /* castillo: 25 gradas -> 100 pisos */
  const maps = stoneMaps(ECO ? 256 : 512);                                        // respaldo procedimental inmediato
  const pmrem = new THREE.PMREMGenerator(renderer);
  new HDRLoader().load("/ui/assets/noche-1k.hdr", (hdr) => {                       // HDRI nocturno CC0 (Poly Haven): luz ambiental IBL
    scene.environment = pmrem.fromEquirectangular(hdr).texture; scene.environmentIntensity = 0.35; hdr.dispose(); }, undefined, () => {});
  const tl = new THREE.TextureLoader();
  function pbr(mat, base, rep, withAo) {                                            // texturas CC0 (ambientCG) servidas localmente
    const set = (slot, file, srgb) => tl.load("/ui/assets/" + base + "-" + file + ".jpg", (tx) => {
      tx.wrapS = tx.wrapT = THREE.RepeatWrapping; tx.repeat.set(rep[0], rep[1]); tx.anisotropy = ECO ? 2 : 8; if (srgb) tx.colorSpace = THREE.SRGBColorSpace;
      mat[slot] = tx; mat.needsUpdate = true; }, undefined, () => {});
    set("map", "color", true); set("normalMap", "normal"); set("roughnessMap", "rugosidad"); if (withAo) set("aoMap", "ao");
  }
  const stone = new THREE.MeshStandardMaterial({ ...maps, color: 0xc9c2b6, roughness: 0.95, metalness: 0.05, normalScale: new THREE.Vector2(1.4, 1.4) });
  const stoneDark = stone.clone(); stoneDark.color = new THREE.Color(0x9a9286);
  const winMat = new THREE.MeshBasicMaterial({ color: 0xffb066 });
  if (!ECO) { pbr(stone, "piedra", [8, 1], true); pbr(stoneDark, "piedra", [10, 0.3], true); stone.aoMapIntensity = stoneDark.aoMapIntensity = 0.9; }
  const stoneV = stone.clone(); stoneV.color = new THREE.Color(1.5, 1.5, 1.5); stoneV.vertexColors = true;   // ocre, pizarra, arenisca, manchas de agua
  if (!ECO) pbr(stoneV, "piedra", [8, 1], true);
  const PAL = [0xe6a24e, 0x6688b0, 0xf2d29a, 0xb0aca2, 0x8f9a74].map(c => new THREE.Color(c));
  const tint = (geo, t) => { const pos = geo.attributes.position, col = new Float32Array(pos.count * 3), c = new THREE.Color();
    for (let i = 0; i < pos.count; i++) { const x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i), blk = Math.floor((Math.atan2(z, x) + 3.15) * 3.2), hs = Math.abs(Math.sin(blk * 12.9898 + t * 78.233) * 43758.5) % 1;
      c.copy(PAL[Math.floor(hs * PAL.length)]).lerp(PAL[(t + 1) % PAL.length], 0.1).multiplyScalar(1.25);
      const stain = Math.abs(Math.sin(blk * 7.1 + t * 3.3)) > 0.82 ? 0.55 : 1; c.multiplyScalar(stain * (y < 0 ? 0.88 : 1)); col.set([c.r, c.g, c.b], i * 3); }
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
    for (let i = 0; i < pos.count; i++) { const j = 1 + (Math.abs(Math.sin(i * 12.9898 + t * 4.1) * 43758.5) % 1 - 0.5) * 0.05; pos.setX(i, pos.getX(i) * j); pos.setZ(i, pos.getZ(i) * j); }   // bloques toscos
    geo.computeVertexNormals(); return geo; };
  const greens = new THREE.MeshStandardMaterial({ color: 0x3f6b2a, roughness: 1 }), vineMat = new THREE.MeshStandardMaterial({ color: 0x2c4a1e, roughness: 1 });
  const bannerMats = [0x8e1f2a, 0x1f4f8e, 0x6e2a8e, 0xb07a1c].map(c => new THREE.MeshStandardMaterial({ color: c, roughness: 0.85, side: THREE.DoubleSide, emissive: c, emissiveIntensity: 0.12 }));
  const lantTex = dotSprite(), accents = [];
  const slitMat = new THREE.MeshBasicMaterial({ color: 0x0a0806 }), slate = new THREE.MeshStandardMaterial({ color: 0x4a5566, roughness: 0.7, metalness: 0.1 });
  const rockMat = stoneDark.clone(); if (!ECO) pbr(rockMat, "roca", [5, 3], false);
  const castle = new THREE.Group(); scene.add(castle);
  const baseY = -30, topY = 150, tierH = (topY - baseY) / TIERS, R0 = 50, R1 = 15;
  const tiers = [], bodies = [];
  const dummy = new THREE.Object3D();
  let winCount = 0; const winMats = [];
  for (let t = 0; t < TIERS; t++) {
    const k = t / (TIERS - 1), r = R1 + (R0 - R1) * Math.pow(1 - k, 0.85) * (1 + 0.06 * Math.sin(k * 13)), y0 = baseY + t * tierH;
    const seg = ECO ? 32 : 64;
    const body = new THREE.Mesh(tint(new THREE.CylinderGeometry(r * 0.84, r * 0.86, tierH * 0.8, seg, 4, true), t), stoneV);
    body.position.y = y0 + tierH * 0.4; body.castShadow = body.receiveShadow = !ECO; body.userData.tier = t; castle.add(body); bodies.push(body);
    const deck = new THREE.Mesh(new THREE.CylinderGeometry(r * 1.08, r * 0.9, tierH * 0.2, seg), stoneDark);   // reborde voladizo
    deck.position.y = y0 + tierH * 0.9; deck.castShadow = deck.receiveShadow = !ECO; castle.add(deck);
    const lip = new THREE.Mesh(new THREE.TorusGeometry(r * 1.08, tierH * 0.06, 6, seg), stoneDark); lip.rotation.x = Math.PI / 2; lip.position.y = y0 + tierH * 1.0; castle.add(lip);
    { const nM = ECO ? 10 : 26, moss = new THREE.InstancedMesh(new THREE.SphereGeometry(1, 6, 4), greens, nM), vines = new THREE.InstancedMesh(new THREE.BoxGeometry(0.35, 1, 0.35), vineMat, nM);
      for (let i = 0; i < nM; i++) { const a = rnd() * 6.283, rr = r * 1.06; dummy.position.set(Math.cos(a) * rr, y0 + tierH * 0.95, Math.sin(a) * rr); dummy.rotation.set(0, -a, 0); dummy.scale.set(1.6 + rnd() * 2.5, 0.5 + rnd() * 0.5, 1.2 + rnd()); dummy.updateMatrix(); moss.setMatrixAt(i, dummy.matrix);
        const L = tierH * (0.3 + rnd() * 0.9); dummy.position.set(Math.cos(a) * rr * 1.01, y0 + tierH * 0.9 - L / 2, Math.sin(a) * rr * 1.01); dummy.scale.set(1, L, 1); dummy.updateMatrix(); vines.setMatrixAt(i, dummy.matrix); }
      castle.add(moss, vines); }
    if (t % 2 === 0 && t < TIERS - 3) { for (let i = 0; i < 3; i++) { const a = rnd() * 6.283, L = tierH * 0.75;                  // estandartes
      const b = new THREE.Mesh(new THREE.PlaneGeometry(2.2, L), bannerMats[(t + i) % 4]); b.position.set(Math.cos(a) * r * 1.1, y0 + tierH * 0.88 - L / 2, Math.sin(a) * r * 1.1); b.rotation.y = -a + Math.PI / 2; b.castShadow = !ECO; castle.add(b); } }
    for (let i = 0; i < (t % 2 ? 2 : 3); i++) { const a = rnd() * 6.283, cy = (t + i) % 3 === 0;                                   // faroles cálidos y cian
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: lantTex, color: cy ? 0x4fe0ff : 0xffb35c, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }));
      sp.position.set(Math.cos(a) * r * 1.09, y0 + tierH * 1.05, Math.sin(a) * r * 1.09); sp.scale.setScalar(cy ? 7 : 6); castle.add(sp); accents.push(sp); }
    const nB = Math.max(16, Math.round(r * (ECO ? 1.0 : 1.4)));                        // almenas
    const merl = new THREE.InstancedMesh(new THREE.BoxGeometry(r * 6.283 / nB * 0.5, tierH * 0.45, 2.0), stone, nB); const mc = new THREE.Color();
    for (let i = 0; i < nB; i++) { const a = i / nB * 6.283; dummy.position.set(Math.cos(a) * r * 1.06, y0 + tierH * 1.22, Math.sin(a) * r * 1.06); dummy.rotation.set(0, -a + Math.PI / 2, 0); dummy.updateMatrix(); merl.setMatrixAt(i, dummy.matrix); merl.setColorAt(i, mc.copy(PAL[(i * 7 + t * 3) % PAL.length]).lerp(new THREE.Color(1, 1, 1), 0.35)); }
    merl.castShadow = !ECO; castle.add(merl);
    { const mach = new THREE.InstancedMesh(new THREE.BoxGeometry(1.1, tierH * 0.22, 1.6), stoneDark, nB), slit = new THREE.InstancedMesh(new THREE.BoxGeometry(0.35, tierH * 0.3, 0.3), slitMat, nB);   // matacanes y saeteras
      for (let i = 0; i < nB; i++) { const a = (i + 0.5) / nB * 6.283; dummy.scale.set(1, 1, 1); dummy.rotation.set(0, -a + Math.PI / 2, 0);
        dummy.position.set(Math.cos(a) * r * 1.03, y0 + tierH * 0.74, Math.sin(a) * r * 1.03); dummy.updateMatrix(); mach.setMatrixAt(i, dummy.matrix);
        dummy.position.set(Math.cos(a + 0.07) * r * 0.86, y0 + tierH * 0.5, Math.sin(a + 0.07) * r * 0.86); dummy.updateMatrix(); slit.setMatrixAt(i, dummy.matrix); }
      castle.add(mach, slit); }
    const nC = Math.max(8, Math.round(r * (ECO ? 0.45 : 0.8)));                         // columnas
    const colM = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.7, 0.85, tierH * 0.8, 10), stoneDark, nC);
    for (let i = 0; i < nC; i++) { const a = (i + 0.5) / nC * 6.283; dummy.position.set(Math.cos(a) * r * 0.88, y0 + tierH * 0.4, Math.sin(a) * r * 0.88); dummy.rotation.set(0, 0, 0); dummy.updateMatrix(); colM.setMatrixAt(i, dummy.matrix); }
    colM.castShadow = !ECO; castle.add(colM);
    const nA = nC * 2;                                                                    // arcos/ventanas encendidas
    const arch = new THREE.InstancedMesh(archGeometry(r * 0.84 * 6.283 / nA * 0.45, tierH * 0.48), winMat, nA);
    let used = 0;
    for (let i = 0; i < nA; i++) { if (((t * 31 + i * 17) % 7) > 3) continue; const a = i / nA * 6.283; dummy.position.set(Math.cos(a) * r * 0.85, y0 + tierH * 0.15, Math.sin(a) * r * 0.85); dummy.rotation.set(0, -a + Math.PI / 2, 0); dummy.updateMatrix(); arch.setMatrixAt(used++, dummy.matrix); }
    arch.count = used; winCount += used; castle.add(arch);
    if (t % 3 === 1 && t < TIERS - 2) {                                           // torretas irregulares
      const nT = 3 + (t % 2), off = rnd() * 6.283;
      for (let i = 0; i < nT; i++) { const a = off + i / nT * 6.283, tr = Math.max(1.6, r * 0.09), th2 = tierH * (1.4 + rnd() * 1.2);
        const tw = new THREE.Mesh(new THREE.CylinderGeometry(tr, tr * 1.1, th2, 12), stone); tw.position.set(Math.cos(a) * r * 1.0, y0 + tierH + th2 / 2, Math.sin(a) * r * 1.0); tw.castShadow = !ECO; castle.add(tw);
        const roof = new THREE.Mesh(new THREE.ConeGeometry(tr * 1.45, th2 * 0.8, 12), slate); roof.position.set(tw.position.x, tw.position.y + th2 / 2 + th2 * 0.27, tw.position.z); roof.castShadow = !ECO; castle.add(roof);
        const wl = new THREE.Mesh(archGeometry(tr * 0.6, th2 * 0.25), winMat); wl.position.set(Math.cos(a) * (r * 1.0 + tr * 1.02), tw.position.y, Math.sin(a) * (r * 1.0 + tr * 1.02)); wl.rotation.y = -a + Math.PI / 2; castle.add(wl); }
    }
    tiers.push({ r, y0, y1: y0 + tierH });
  }
  const spire = new THREE.Mesh(new THREE.ConeGeometry(R1 * 0.75, 30, 24), stone); spire.position.y = topY + 15; spire.castShadow = !ECO; castle.add(spire);
  { const g = new THREE.ConeGeometry(R0 * 0.95, 60, 48, 10, true), pos = g.attributes.position;  // roca colgante
    for (let i = 0; i < pos.count; i++) { const v = new THREE.Vector3().fromBufferAttribute(pos, i); const n = 1 + (rnd() - 0.5) * 0.22 * (1 - Math.abs(v.y) / 30); pos.setXYZ(i, v.x * n, v.y + (rnd() - 0.5) * 2, v.z * n); }
    g.computeVertexNormals(); const rock = new THREE.Mesh(g, rockMat); rock.rotation.x = Math.PI; rock.position.y = baseY - 30; rock.castShadow = !ECO; castle.add(rock); }

  /* barbacana en la grada base: torres, rastrillo y puente levadizo */
  { const gt = tiers[0], gr = gt.r * 0.9, gy = gt.y0, gate = new THREE.Group(); gate.rotation.y = -0.9; castle.add(gate);
    const tw = (x) => { const m = new THREE.Mesh(new THREE.CylinderGeometry(4, 4.4, tierH * 1.5, 14), stone); m.position.set(x, gy + tierH * 0.75, gr + 3); m.castShadow = !ECO; gate.add(m);
      const rf = new THREE.Mesh(new THREE.ConeGeometry(5.2, 9, 14), slate); rf.position.set(x, gy + tierH * 1.5 + 4.5, gr + 3); gate.add(rf); };
    tw(-8); tw(8);
    const wall = new THREE.Mesh(new THREE.BoxGeometry(12, tierH * 1.1, 5), stone); wall.position.set(0, gy + tierH * 0.55, gr + 3); gate.add(wall);
    const port = new THREE.Mesh(new THREE.PlaneGeometry(6, tierH * 0.7), new THREE.MeshStandardMaterial({ color: 0x1b1612, metalness: 0.6, roughness: 0.5 })); port.position.set(0, gy + tierH * 0.35, gr + 5.6); gate.add(port);
    for (let i = -2; i <= 2; i++) { const bar = new THREE.Mesh(new THREE.BoxGeometry(0.3, tierH * 0.7, 0.3), slitMat); bar.position.set(i * 1.3, gy + tierH * 0.35, gr + 5.8); gate.add(bar); }
    const bridge = new THREE.Mesh(new THREE.BoxGeometry(6, 0.6, 14), new THREE.MeshStandardMaterial({ color: 0x4a3524, roughness: 0.95 })); bridge.position.set(0, gy - 0.2, gr + 12); bridge.rotation.x = 0.35; gate.add(bridge); }
  const torches = [], emberN = ECO ? 60 : 220, emberP = new Float32Array(emberN * 3), emberB = [];
  for (let i = 0; i < (ECO ? 4 : 8); i++) { const tt = tiers[(i * 3 + 1) % (TIERS - 2)], a = i * 2.4; const p = new THREE.Vector3(Math.cos(a) * tt.r * 1.1, tt.y1 + 1.5, Math.sin(a) * tt.r * 1.1);
    const L = new THREE.PointLight(0xff8a3a, 160, 40, 2); L.position.copy(p); castle.add(L);
    const f = new THREE.Sprite(new THREE.SpriteMaterial({ map: lantTex, color: 0xffa040, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false })); f.position.copy(p); f.scale.setScalar(5); castle.add(f);
    torches.push({ L, f, ph: i * 1.7 }); emberB.push(p); }
  for (let i = 0; i < emberN; i++) { const b = emberB[i % emberB.length]; emberP.set([b.x, b.y + rnd() * 12, b.z], i * 3); }
  const brasas = new THREE.Points(new THREE.BufferGeometry().setAttribute("position", new THREE.BufferAttribute(emberP, 3)),
    new THREE.PointsMaterial({ color: 0xff7a2a, size: 0.8, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false })); castle.add(brasas);

  /* escena = solo el núcleo: la torre no se dibuja (el dueño la quitó). Queda un punto focal de energía tenue. */
  scene.remove(castle);
  const focal = new THREE.Sprite(new THREE.SpriteMaterial({ map: lantTex, color: 0x5ad2ff, transparent: true, opacity: 0.35, blending: THREE.AdditiveBlending, depthWrite: false }));
  focal.position.set(0, 55, 0); focal.scale.setScalar(14); scene.add(focal);
  const focalRing = new THREE.Mesh(new THREE.RingGeometry(18, 18.4, 96), new THREE.MeshBasicMaterial({ color: 0x5ad2ff, transparent: true, opacity: 0.18, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
  focalRing.rotation.x = Math.PI / 2; focalRing.position.y = 55; scene.add(focalRing);

  /* pisos: resaltado de negocios y de la selección */
  const ringMat = (op) => new THREE.MeshBasicMaterial({ color: 0x5ad2ff, transparent: true, opacity: op, blending: THREE.AdditiveBlending, depthWrite: false });
  const floorY = (f) => { const t = Math.floor((f - 1) / 4), q = (f - 1) % 4; return { y: tiers[t].y0 + (q + 0.5) * tierH / 4, r: tiers[t].r }; };
  const namedRings = [], runes = [];
  for (let f = 1; f <= 5; f++) { const { y, r } = floorY(f); const m = new THREE.Mesh(new THREE.TorusGeometry(r * 0.96, 0.18, 6, 96), ringMat(0.7)); m.rotation.x = Math.PI / 2; m.position.y = y; castle.add(m); namedRings.push(m);
    const rune = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.855, r * 0.855, 0.9, 96, 1, true), new THREE.ShaderMaterial({ uniforms: { uC: { value: new THREE.Color(0x5ad2ff) }, uT: starU.uTime }, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      vertexShader: "varying vec2 vU; void main(){ vU = uv; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }",
      fragmentShader: "uniform vec3 uC; uniform float uT; varying vec2 vU; void main(){ float g = step(0.55, fract(sin(floor(vU.x*160.0)*91.7)*437.5)); float s = 0.6+0.4*sin(vU.x*40.0 - uT*2.0); gl_FragColor = vec4(uC, g*s*0.85); }" }));
    rune.position.y = y; castle.add(rune); runes.push(rune); }
  const selRing = new THREE.Mesh(new THREE.TorusGeometry(1, 0.32, 8, 128), ringMat(0.95)); selRing.rotation.x = Math.PI / 2; selRing.visible = false; castle.add(selRing);
  const hovRing = new THREE.Mesh(new THREE.TorusGeometry(1, 0.2, 8, 128), ringMat(0.55)); hovRing.rotation.x = Math.PI / 2; hovRing.visible = false; castle.add(hovRing);
  const place = (ring, f) => { if (f < 1) { ring.visible = false; return; } const { y, r } = floorY(f); ring.position.y = y; ring.scale.setScalar(r * 0.97); ring.visible = true; };

  /* nubes en capas, encendidas desde abajo */
  const cloudTex = softSprite(256);
  const clouds = [];
  const nCl = ECO ? 70 : 170;
  for (let i = 0; i < nCl; i++) {
    const m = new THREE.SpriteMaterial({ map: cloudTex, color: 0x4a5670, transparent: true, opacity: 0.75, depthWrite: false, fog: false });
    const s = new THREE.Sprite(m); const a = rnd() * 6.283, d = 30 + Math.pow(rnd(), 0.7) * 420, layer = rnd();
    s.position.set(Math.cos(a) * d, -75 - layer * 35, Math.sin(a) * d); const sc = 80 + rnd() * 140; s.scale.set(sc, sc * 0.4, 1);
    s.userData = { a, d, sp: 0.004 + rnd() * 0.01, layer }; scene.add(s); clouds.push(s);
  }

  const glowTex = dotSprite(), glows = [];                                       // ciudades lejanas bajo las nubes
  for (let i = 0; i < (ECO ? 18 : 40); i++) {
    const m = new THREE.SpriteMaterial({ map: glowTex, color: 0xff9a4a, transparent: true, opacity: 0.34, blending: THREE.AdditiveBlending, depthWrite: false });
    const g = new THREE.Sprite(m); const a = rnd() * 6.283, d = 60 + rnd() * 500; g.position.set(Math.cos(a) * d, -150 - rnd() * 20, Math.sin(a) * d);
    const sc = 70 + rnd() * 120; g.scale.set(sc, sc * 0.5, 1); scene.add(g); glows.push(g);
  }

  /* rejilla HUD bajo el mar de nubes */
  const gridU = { uColor: { value: new THREE.Color(0x46c8ff) }, uTime: { value: 0 } };
  const grid = new THREE.Mesh(new THREE.PlaneGeometry(1600, 1600), new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms: gridU,
    vertexShader: "varying vec2 vP; void main(){ vP = position.xy; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }",
    fragmentShader: "uniform vec3 uColor; uniform float uTime; varying vec2 vP; void main(){ vec2 g = abs(fract(vP/20.0)-0.5); float l = 1.0-smoothstep(0.0,0.04,min(g.x,g.y));" +
      " float fade = 1.0 - smoothstep(80.0, 700.0, length(vP)); float pulse = 0.6+0.4*sin(length(vP)*0.05 - uTime*1.5); gl_FragColor = vec4(uColor, l*fade*0.05*pulse); }" }));
  grid.rotation.x = -Math.PI / 2; grid.position.y = -150; scene.add(grid);

  /* partículas: brasas cálidas que suben y motas holográficas alrededor del núcleo */
  const dot = dotSprite();
  function points(n, spread, color, size) {
    const p = new Float32Array(n * 3), v = new Float32Array(n);
    for (let i = 0; i < n; i++) { p.set([(rnd() - 0.5) * spread.x, (rnd() - 0.5) * spread.y, (rnd() - 0.5) * spread.z], i * 3); v[i] = 0.3 + rnd(); }
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(p, 3));
    const m = new THREE.PointsMaterial({ map: dot, color, size, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
    const o = new THREE.Points(g, m); o.userData.v = v; return o;
  }
  const embers = points(ECO ? 250 : 700, new THREE.Vector3(260, 200, 260), 0xffa060, 1.3); embers.position.y = 20; scene.add(embers);

  /* núcleo Jarvis/Ultron fuera de la torre */
  const coreU = { uTime: { value: 0 }, uColor: { value: new THREE.Color(0x5ad2ff) }, uGlitch: { value: 0 } };
  const holoVS = "uniform float uTime; uniform float uGlitch; varying vec3 vN; varying vec3 vV; varying vec3 vW;" +
    " float h(float x){ return fract(sin(x)*43758.5453); }" +
    " void main(){ vec4 w = modelMatrix*vec4(position,1.0); float gt = step(0.94, h(floor(uTime*9.0)+floor(w.y*0.6)));" +
    " w.x += (h(w.y+uTime)-0.5)*gt*uGlitch*2.5; vW = w.xyz; vN = normalize(mat3(modelMatrix)*normal); vV = normalize(cameraPosition - w.xyz);" +
    " gl_Position = projectionMatrix*viewMatrix*w; }";
  const holoFS = "uniform float uTime; uniform vec3 uColor; varying vec3 vN; varying vec3 vV; varying vec3 vW;" +
    " void main(){ float fr = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 2.4); float scan = pow(0.5+0.5*sin(vW.y*7.0 - uTime*4.0), 6.0);" +
    " float stripes = 0.6+0.4*sin(vW.y*40.0 + uTime*0.6); float a = clamp(fr*1.3 + scan*0.35 + 0.06, 0.0, 1.0)*stripes;" +
    " gl_FragColor = vec4(uColor*(0.3 + fr*1.4 + scan*0.4), a*0.12); }";
  const holo = new THREE.ShaderMaterial({ uniforms: coreU, vertexShader: holoVS, fragmentShader: holoFS, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide });
  const core = new THREE.Group(); core.position.set(118, 80, 30); scene.add(core);
  core.add(new THREE.Mesh(new THREE.IcosahedronGeometry(7, ECO ? 2 : 4), holo));
  const inner = new THREE.Mesh(new THREE.SphereGeometry(1.4, 24, 16), new THREE.MeshBasicMaterial({ color: 0xcfeeff, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false })); core.add(inner); inner.visible = false;
  const coreLight = new THREE.PointLight(0x5ad2ff, 400, 120, 1.8); core.add(coreLight);
  const ringMatC = new THREE.MeshBasicMaterial({ color: 0x5ad2ff, transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
  const rings = [];
  [[10, 10.5, 6, 0.6, [0.3, 0, 0]], [12.5, 12.8, 24, 0.85, [1.2, 0.3, 0]], [15, 15.6, 3, 0.45, [0.1, 0.8, 0.2]], [18, 18.25, 72, 0.9, [Math.PI / 2, 0, 0]]].forEach(([ri, ro, segs, fill, rot]) => {
    const grp = new THREE.Group();
    for (let s = 0; s < segs; s++) { const len = 6.283 / segs * fill; const m = new THREE.Mesh(new THREE.RingGeometry(ri, ro, Math.max(4, Math.round(len * 24)), 1, s * 6.283 / segs, len), ringMatC); grp.add(m); }
    grp.rotation.set(...rot); core.add(grp); rings.push(grp);
  });
  const ultronRings = new THREE.Group(); core.add(ultronRings);                              // anillos angulares (Ultron)
  [[12, 9], [16, 14]].forEach(([r, n]) => { const pts = []; for (let s = 0; s <= n * 2; s++) { const a = s * Math.PI / n, q = r * (s % 2 ? 1.12 : 0.9); pts.push(new THREE.Vector3(Math.cos(a) * q, Math.sin(a) * q, 0)); }
    ultronRings.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0xff5a28, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending }))); });
  ultronRings.visible = false;
  const motes = points(ECO ? 120 : 320, new THREE.Vector3(60, 60, 60), 0x7fe3ff, 0.9); core.add(motes);
  /* núcleo libre: cristal físico (transmisión/IOR) + rayos + onda de choque; orbita la torre */
  coreLight.intensity = 500;
  /* esfera holográfica translúcida: borde fresnel, centro transparente, bandas curvadas tipo refracción; capas internas visibles
     (sin transmisión física: sobre cielo oscuro se veía sólida y con borde oscuro) */
  const glassU = { uColor: coreU.uColor, uTime: coreU.uTime, uLvl: { value: 0 } };
  const glass = new THREE.Mesh(new THREE.SphereGeometry(8.2, 64, 48), new THREE.ShaderMaterial({ uniforms: glassU, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    vertexShader: "varying vec3 vN; varying vec3 vV; varying vec3 vP; void main(){ vec4 w = modelMatrix*vec4(position,1.0); vP = position; vN = normalize(mat3(modelMatrix)*normal); vV = normalize(cameraPosition - w.xyz); gl_Position = projectionMatrix*viewMatrix*w; }",
    fragmentShader: "uniform vec3 uColor; uniform float uTime; uniform float uLvl; varying vec3 vN; varying vec3 vV; varying vec3 vP;" +
      " void main(){ float ndv = abs(dot(normalize(vN), normalize(vV))); float rim = pow(1.0 - ndv, 2.6);" +
      " float warp = sin(vP.y*1.6 + sin(vP.x*0.9 + uTime*0.7)*1.5 - uTime*0.9);" +
      " float band = smoothstep(0.9, 1.0, warp) * 0.16 * (1.0 - ndv*0.5); float body = 0.025 + 0.05*uLvl;" +
      " vec3 c = uColor*(rim*1.5 + band + body) + vec3(0.75,0.9,1.0)*pow(rim, 6.0)*0.5;" +
      " gl_FragColor = vec4(c, clamp(rim*0.9 + band + body, 0.0, 1.0)); }" }));
  glass.renderOrder = 3; core.add(glass);
  const shells = [];
  [[6.2, 1, 0.1, 0.25], [5.0, 1, 0.08, -0.4]].forEach(([r, det, op, sp]) => {
    const m = new THREE.Mesh(new THREE.IcosahedronGeometry(r, det), new THREE.MeshBasicMaterial({ color: 0x4fd8ff, wireframe: true, transparent: true, opacity: op, blending: THREE.AdditiveBlending, depthWrite: false }));
    m.userData.sp = sp; core.add(m); shells.push(m); });
  const glowS = new THREE.Sprite(new THREE.SpriteMaterial({ map: dot, color: 0x4fb8ff, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false }));
  glowS.scale.setScalar(9); core.add(glowS);
  const orbP = points(ECO ? 200 : 700, new THREE.Vector3(1, 1, 1), 0x8fe6ff, 0.5); core.add(orbP);              // partículas en órbita (anillo toroidal)
  { const pa = orbP.geometry.attributes.position; for (let i = 0; i < pa.count; i++) { const a = rnd() * 6.283, r = 9.5 + rnd() * 4, h = (rnd() - 0.5) * 1.6; pa.setXYZ(i, Math.cos(a) * r, h, Math.sin(a) * r); } orbP.rotation.x = 1.2; }
  const rayMat = new THREE.ShaderMaterial({ uniforms: { uColor: coreU.uColor, uI: { value: 0.2 }, uTime: coreU.uTime }, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    vertexShader: "varying vec2 vU; void main(){ vU = uv; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }",
    fragmentShader: "uniform vec3 uColor; uniform float uI; uniform float uTime; varying vec2 vU; void main(){ float a = (1.0 - vU.y) * smoothstep(0.0, 0.5, 1.0 - abs(vU.x - 0.5) * 2.0);" +
      " a *= 0.7 + 0.3 * sin(vU.y * 30.0 - uTime * 8.0); gl_FragColor = vec4(uColor, a * uI); }" });
  const rays = new THREE.Group(); core.add(rays); rays.scale.set(0.45, 1, 0.45);
  for (let i = 0; i < 14; i++) { const len = 30 + rnd() * 40, w = 1.2 + rnd() * 2.2; const g = new THREE.PlaneGeometry(w, len); g.translate(0, len / 2 + 6, 0);
    const m = new THREE.Mesh(g, rayMat); m.rotation.z = i / 14 * 6.283 + rnd() * 0.2; rays.add(m); }
  const shock = new THREE.Mesh(new THREE.TorusGeometry(1, 0.08, 8, 128), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }));
  core.add(shock);
  /* cáusticas falsas: foco desde el núcleo hacia la torre con textura animada proyectada */
  let caustic = null;
  if (!ECO) {
    const cc = document.createElement("canvas"); cc.width = cc.height = 256; const cg = cc.getContext("2d");
    cg.fillStyle = "#000"; cg.fillRect(0, 0, 256, 256); cg.strokeStyle = "rgba(255,255,255,0.55)"; cg.lineWidth = 2;
    for (let i = 0; i < 60; i++) { cg.beginPath(); let x = rnd() * 256, y = rnd() * 256; cg.moveTo(x, y); for (let j = 0; j < 4; j++) { x += (rnd() - 0.5) * 70; y += (rnd() - 0.5) * 70; cg.quadraticCurveTo(x + 20, y - 20, x, y); } cg.stroke(); }
    const ct = new THREE.CanvasTexture(cc); ct.wrapS = ct.wrapT = THREE.RepeatWrapping; ct.colorSpace = THREE.SRGBColorSpace;
    caustic = new THREE.SpotLight(0x9fe8ff, 4000, 400, 0.32, 0.6, 1.4); caustic.map = ct; caustic.castShadow = true; caustic.shadow.mapSize.set(512, 512);
    core.add(caustic); scene.add(caustic.target);
  }

  /* posproceso: GTAO, bloom, DoF, estela (desenfoque de movimiento aproximado), salida ACES y película */
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  if (!ECO) { const gtao = new GTAOPass(scene, camera, 512, 512); gtao.output = GTAOPass.OUTPUT.Default; gtao.blendIntensity = 0.9;
    const gRender = gtao.render.bind(gtao), hidden = [];                          // AO solo para lo opaco: los sprites/HUD aditivos no deben dejar cuadros oscuros
    gtao.render = (...args) => { scene.traverse(o => { if (o.visible && o.material && !Array.isArray(o.material) && (o.material.transparent || o.isSprite || o.isPoints || o.isLine)) { o.visible = false; hidden.push(o); } });
      try { gRender(...args); } finally { hidden.forEach(o => { o.visible = true; }); hidden.length = 0; } };
    gtao.updateGtaoMaterial({ radius: 6, distanceExponent: 1.5, thickness: 2, scale: 1.2 }); composer.addPass(gtao); }
  const bloom = new UnrealBloomPass(new THREE.Vector2(512, 512), ECO ? 0.6 : 0.8, 0.5, 0.9); composer.addPass(bloom);
  let bokeh = null;
  if (!ECO) { bokeh = new BokehPass(scene, camera, { focus: 150, aperture: 0.00008, maxblur: 0.004 }); composer.addPass(bokeh); }
  let trail = null;
  if (!ECO && !reduce) { trail = new AfterimagePass(0.55); composer.addPass(trail); }
  composer.addPass(new OutputPass());
  const film = new ShaderPass({
    uniforms: { tDiffuse: { value: null }, uTime: { value: 0 }, uGrain: { value: ECO ? 0.03 : 0.05 }, uCA: { value: 0.0015 }, uVig: { value: 1.1 }, uFlash: { value: 0 }, uTint: { value: new THREE.Color(1, 1, 1) } },
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }",
    fragmentShader: "uniform sampler2D tDiffuse; uniform float uTime, uGrain, uCA, uVig, uFlash; uniform vec3 uTint; varying vec2 vUv;" +
      " float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233)) + uTime*7.0) * 43758.5453); }" +
      " void main(){ vec2 d = vUv - 0.5; float r2 = dot(d,d); vec2 o = d * uCA * (1.0 + r2*4.0);" +
      " vec3 c = vec3(texture2D(tDiffuse, vUv + o).r, texture2D(tDiffuse, vUv).g, texture2D(tDiffuse, vUv - o).b);" +
      " c *= 1.0 - smoothstep(0.25, 0.9, r2 * uVig * 2.0); c += (h(vUv*1000.0) - 0.5) * uGrain; c = mix(c, uTint, uFlash);" +
      " gl_FragColor = vec4(c, 1.0); }" });
  composer.addPass(film);

  function resize() {
    const w = host.clientWidth || innerWidth, h = host.clientHeight || innerHeight;
    renderer.setSize(w, h, false); composer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix();
  }
  addEventListener("resize", resize); resize();

  /* modo Jarvis/Ultron con transición dramática (~1.2 s) */
  let mode = qs.get("modo") === "ultron" ? "ultron" : "jarvis", k = mode === "ultron" ? 1 : 0, shown = mode, trans = -1;
  let speaking = false;
  if (!qs.get("modo")) {
    const poll = () => fetch("/api/state", { credentials: "same-origin" }).then(r => r.json()).then(j => { mode = j.mode || "jarvis"; speaking = !!j.speaking; if (window.__cineTopics) window.__cineTopics(j.speaking_topics); }).catch(() => {});
    poll(); setInterval(poll, 3000);
  }
  const TRANS_S = 1.2;
  const freezeTrans = qs.get("trans") !== null ? Math.max(0, Math.min(1, parseFloat(qs.get("trans")) || 0.5)) : -1;
  const fakeTalk = qs.get("habla") !== null, DEMO = qs.get("demo") !== null;      // demo: 0-2.5 reposo, 2.5-5 habla, 5-7.5 apunta BTC, 7.5+ Ultron
  const BLUE = new THREE.Color(0x0a84ff), RED = new THREE.Color(0xff3a00), WARM = new THREE.Color(0xff9a50), WARM_R = new THREE.Color(0xff3a14);
  const CL = new THREE.Color(0x56607a), CL_R = new THREE.Color(0x5a3a34);

  /* voz de Alan: nivel real por BroadcastChannel (lipsync.js de la ventana de conversación); si no, estado del servidor */
  const L = window.JarvisLipsync;
  const voice = { env: null, clock: null, filter: L ? new L.ClockFilter() : null, follower: L ? new L.Follower() : null, level: 0 };
  try { if (L && "BroadcastChannel" in window) { const ch = new BroadcastChannel(L.CHANNEL); ch.onmessage = (ev) => { const m = ev.data; if (!L.valid(m)) return;
    if (m.k === "env") voice.env = m; else if (m.k === "clock") { voice.clock = m; voice.filter.push(m); } else if (m.k === "stop") voice.clock = null; }; } } catch (e) { /* sin canal */ }
  function voiceLevel(t, dtMs) {
    if (fakeTalk || (DEMO && t >= 2.5 && t < 5)) return 0.55 + 0.45 * Math.abs(Math.sin(t * 9.0) * Math.sin(t * 3.1 + 1.0));
    const c = voice.clock, env = voice.env;
    if (c && env && c.id === env.id && voice.follower) { const pos = voice.filter.position(performance.now());
      const target = c.playing && pos <= env.duration + 0.05 ? L.level(env, pos + L.LOOKAHEAD_S) : 0; return (voice.level = voice.follower.step(target, dtMs)); }
    voice.level += ((speaking ? 0.45 + 0.25 * Math.sin(t * 11) : 0) - voice.level) * 0.2;           // respaldo: "hablando" del servidor
    return voice.level;
  }

  /* HUD del núcleo (estilo HUD sci-fi genérico, código original): anillos finos, arcos, reglas, espectro de voz, satélites */
  const hud = new THREE.Group(); scene.add(hud);
  const hudMats = [], hudCol = (op, dashed) => { const m = dashed ? new THREE.LineDashedMaterial({ color: 0x4fd8ff, transparent: true, opacity: op, dashSize: 1.2, gapSize: 0.8, blending: THREE.AdditiveBlending, depthWrite: false })
    : new THREE.LineBasicMaterial({ color: 0x4fd8ff, transparent: true, opacity: op, blending: THREE.AdditiveBlending, depthWrite: false }); hudMats.push(m); return m; };
  const arc = (r, a0, a1, n = 64, jag = 0) => { const p = []; for (let i = 0; i <= n; i++) { const a = a0 + (a1 - a0) * i / n, q = r + (jag ? (i % 2 ? jag : -jag) : 0); p.push(new THREE.Vector3(Math.cos(a) * q, Math.sin(a) * q, 0)); } return new THREE.BufferGeometry().setFromPoints(p); };
  const hudRings = [], brokenRings = [];
  [[15, 0.9, 0, 0.35], [19, 0.5, 1, -0.22], [23.5, 0.7, 0, 0.12], [29, 0.35, 1, -0.08], [37, 0.55, 0, 0.05]].forEach(([r, op, dashed, sp]) => {
    const g = new THREE.Group(); const L = new THREE.Line(arc(r, 0, 6.283, 160), hudCol(op, dashed)); if (dashed) L.computeLineDistances(); g.add(L);
    for (let s2 = 0; s2 < 3; s2++) { const a0 = s2 * 2.094 + r; g.add(new THREE.Line(arc(r + 1.4, a0, a0 + 0.9 + (r % 3) * 0.2, 40), hudCol(op * 0.9))); }   // arcos segmentados
    g.userData.sp = sp; hud.add(g); hudRings.push(g);
    const b = new THREE.Group(); for (let s2 = 0; s2 < 7; s2++) { const a0 = s2 * 0.897; b.add(new THREE.Line(arc(r, a0, a0 + 0.55, 18, 0.7), hudCol(op))); } b.userData.sp = -sp * 2.2; b.visible = false; hud.add(b); brokenRings.push(b); });
  { const p = []; for (let i = 0; i < 120; i++) { const a = i / 120 * 6.283, L = i % 10 === 0 ? 2.6 : i % 5 === 0 ? 1.6 : 0.8; p.push(new THREE.Vector3(Math.cos(a) * 33, Math.sin(a) * 33, 0), new THREE.Vector3(Math.cos(a) * (33 + L), Math.sin(a) * (33 + L), 0)); }
    const ticks = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(p), hudCol(0.6)); ticks.userData.sp = 0.03; hud.add(ticks); hudRings.push(ticks); }   // regla de marcas
  const NB = 96, specP = new Float32Array(NB * 6), spec = new THREE.LineSegments(new THREE.BufferGeometry().setAttribute("position", new THREE.BufferAttribute(specP, 3)), hudCol(0.95)); hud.add(spec);   // espectro radial por voz
  const sats = []; for (let i = 0; i < 4; i++) { const sp2 = new THREE.Sprite(new THREE.SpriteMaterial({ map: lantTex, color: 0x9fe8ff, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false })); sp2.scale.setScalar(2.4); hud.add(sp2); sats.push({ s: sp2, r: [26, 31, 41, 45][i], w: [0.5, -0.32, 0.21, -0.15][i], a: i * 1.7 }); }
  const sweep = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), new THREE.Vector3(37, 0, 0)]), hudCol(0.8)); hud.add(sweep);
  const hex = new THREE.Mesh(new THREE.PlaneGeometry(120, 120), new THREE.ShaderMaterial({ uniforms: { uC: { value: new THREE.Color(0x4fd8ff) } }, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: "varying vec2 vP; void main(){ vP = position.xy; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }",
    fragmentShader: "uniform vec3 uC; varying vec2 vP; void main(){ vec2 p = vP/3.0; vec2 r = vec2(1.0,1.732); vec2 h = r*0.5; vec2 a = mod(p,r)-h; vec2 b = mod(p-h,r)-h; vec2 g = dot(a,a)<dot(b,b)?a:b;" +
      " float e = smoothstep(0.42,0.5,max(abs(g.x)*0.866+abs(g.y)*0.5, abs(g.y))); float f = 1.0 - smoothstep(20.0,60.0,length(vP)); gl_FragColor = vec4(uC, e*f*0.07); }" })); hex.position.z = -2; hud.add(hex);
  const txtC = document.createElement("canvas"); txtC.width = 512; txtC.height = 128; const txtX = txtC.getContext("2d"), txtT = new THREE.CanvasTexture(txtC);
  const readout = new THREE.Sprite(new THREE.SpriteMaterial({ map: txtT, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })); readout.scale.set(26, 6.5, 1); readout.position.set(-24, 27, 0); hud.add(readout);
  let btc = "--", lastTxt = -1;
  fetch("/api/cripto", { credentials: "same-origin" }).then(r => r.json()).then(j => { const c = (j.precios || j.monedas || []).find(x => /btc|bitcoin/i.test(JSON.stringify(x))); if (c && c.usd != null) btc = "$" + Number(c.usd).toLocaleString("en-US", { maximumFractionDigits: 0 }); }).catch(() => {});
  function drawReadout(t, lvl, colCss) { txtX.clearRect(0, 0, 512, 128); txtX.font = "bold 26px monospace"; txtX.fillStyle = colCss;
    const d = new Date(); txtX.fillText("T " + d.toTimeString().slice(0, 8) + "   CPU " + (navigator.hardwareConcurrency || "--") + " hilos", 8, 40);
    txtX.fillText("BTC " + btc + "   VOZ " + String(Math.round(lvl * 100)).padStart(3, "0") + "%", 8, 84); txtX.fillRect(8, 100, 496 * Math.min(1, lvl), 3); txtT.needsUpdate = true; }
  const flareS = new THREE.Sprite(new THREE.SpriteMaterial({ map: lantTex, color: 0x6fd8ff, transparent: true, opacity: 0.5, blending: THREE.AdditiveBlending, depthWrite: false })); flareS.scale.set(110, 3.5, 1); hud.add(flareS);   // destello anamórfico
  function updHud(t, dt, lvl, col, k) {
    hud.position.copy(core.position); hud.quaternion.copy(camera.quaternion);
    if (!reduce) { hud.rotateX(Math.sin(t * 0.23) * 0.12 + 0.18); hud.rotateY(Math.cos(t * 0.17) * 0.1); }   // inclinación 3D sutil
    hudMats.forEach(m => m.color.copy(col)); hex.material.uniforms.uC.value.copy(col); flareS.material.color.copy(col);
    const ult = k >= 0.6; hudRings.forEach((g, i) => { g.visible = !ult || i === hudRings.length - 1; if (!reduce) g.rotation.z += dt * g.userData.sp * (1 + lvl * 3); });
    brokenRings.forEach(g => { g.visible = ult; if (!reduce) g.rotation.z += dt * g.userData.sp; });
    for (let i = 0; i < NB; i++) { const a = i / NB * 6.283, v = Math.max(0.05, lvl) * (0.4 + 0.6 * Math.abs(Math.sin(i * 1.3 + t * 9) * Math.sin(i * 0.37 - t * 4))), r0 = 10, r1 = r0 + 0.6 + v * 7;
      specP.set([Math.cos(a) * r0, Math.sin(a) * r0, 0, Math.cos(a) * r1, Math.sin(a) * r1, 0], i * 6); } spec.geometry.attributes.position.needsUpdate = true;
    sats.forEach(o => { const a = o.a + (reduce ? 0 : t * o.w); o.s.position.set(Math.cos(a) * o.r, Math.sin(a) * o.r, 0.5); o.s.material.color.copy(col).lerp(new THREE.Color(1, 1, 1), 0.4); });
    sweep.rotation.z = reduce ? 0.8 : -t * 1.4; flareS.material.opacity = 0.25 + lvl * 0.5;
    if (t - lastTxt > 0.25) { lastTxt = t; drawReadout(t, lvl, "#" + col.getHexString()); }
  }
  /* reactor de arco dentro del cristal (geometría original): disco central, anillos, 10 bobinas trapezoidales, triángulo tenue, bisel metálico con pernos */
  const reactor = new THREE.Group(); hud.add(reactor); reactor.position.z = 0.5;
  const emi = (op) => new THREE.MeshBasicMaterial({ color: 0xbfeaff, transparent: true, opacity: op, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
  const rDisc = new THREE.Mesh(new THREE.CircleGeometry(2.6, 48), emi(1)); reactor.add(rDisc);
  const rRings = [[3.1, 3.5, 0.9], [8.9, 9.25, 0.85], [9.6, 9.75, 0.6]].map(([a, b, op]) => { const m = new THREE.Mesh(new THREE.RingGeometry(a, b, 96), emi(op)); reactor.add(m); return m; });
  const coilMat = emi(0.8), windMat = new THREE.LineBasicMaterial({ color: 0x0a2a44, transparent: true, opacity: 0.55 });
  const coils = new THREE.Group(); reactor.add(coils);
  for (let i = 0; i < 10; i++) { const a = i / 10 * 6.283, g = new THREE.Group(); g.rotation.z = a;
    const sh = new THREE.Shape(); sh.moveTo(4.0, -0.75); sh.lineTo(8.5, -1.45); sh.lineTo(8.5, 1.45); sh.lineTo(4.0, 0.75); sh.lineTo(4.0, -0.75);
    g.add(new THREE.Mesh(new THREE.ShapeGeometry(sh), coilMat));
    const w = []; for (let k = 0; k <= 9; k++) { const x = 4.2 + k * 0.47, h = 0.75 + (x - 4.0) / 4.5 * 0.7; w.push(new THREE.Vector3(x, -h, 0.05), new THREE.Vector3(x, h, 0.05)); }   // devanado
    g.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(w), windMat)); coils.add(g); }
  const tri = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints([0, 1, 2].map(i => new THREE.Vector3(Math.cos(i * 2.094 + 1.571) * 3.0, Math.sin(i * 2.094 + 1.571) * 3.0, 0.1))), new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.22 }));
  reactor.add(tri);
  const metal = new THREE.MeshStandardMaterial({ color: 0x9aa6b4, metalness: 0.95, roughness: 0.28, emissive: 0x0a1c2c, emissiveIntensity: 1 });
  const bezel = new THREE.Mesh(new THREE.TorusGeometry(10.4, 0.55, 16, 128), metal); reactor.add(bezel);
  const bolts = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.28, 0.28, 0.3, 10), metal, 10);
  for (let i = 0; i < 10; i++) { const a = (i + 0.5) / 10 * 6.283; dummy.position.set(Math.cos(a) * 10.4, Math.sin(a) * 10.4, 0.55); dummy.rotation.set(Math.PI / 2, 0, 0); dummy.scale.set(1, 1, 1); dummy.updateMatrix(); bolts.setMatrixAt(i, dummy.matrix); }
  reactor.add(bolts);
  const rLight = new THREE.PointLight(0x9fdcff, 60, 40, 2); rLight.position.z = 6; reactor.add(rLight);   // ilumina el bisel
  reactor.scale.setScalar(1.25);
  function updReactor(t, lvl, breath, col) {
    const hot = col.clone().lerp(new THREE.Color(1, 1, 1), 0.55), p = 0.75 + 0.15 * breath + 0.6 * lvl;
    rDisc.material.color.copy(hot); rDisc.material.opacity = Math.min(1, 0.85 + 0.15 * lvl); rDisc.scale.setScalar(1 + 0.05 * breath + 0.18 * lvl);
    rRings.forEach((m, i) => { m.material.color.copy(i ? col : hot); m.material.opacity = Math.min(1, (i ? 0.55 : 0.9) * p); });
    coilMat.color.copy(col.clone().lerp(new THREE.Color(1, 1, 1), 0.35)); coilMat.opacity = Math.min(1, 0.55 * p);
    tri.material.color.copy(hot); rLight.color.copy(col); rLight.intensity = 50 + 120 * lvl;
    if (!reduce) coils.rotation.z = Math.sin(t * 0.3) * 0.02;
  }
  /* rayos eléctricos: rayos finos dentados con ramas y parpadeo, núcleo blanco-cian + halo; siguen la dirección de cada rayo (idle/speak/scan/point) */
  const BOLT_MAX = 6000, boltP = new Float32Array(BOLT_MAX * 3), boltG = new THREE.BufferGeometry(); boltG.setAttribute("position", new THREE.BufferAttribute(boltP, 3)); boltG.setDrawRange(0, 0);
  const boltCore = new THREE.LineSegments(boltG, new THREE.LineBasicMaterial({ color: 0xeefcff, transparent: true, opacity: 1, blending: THREE.AdditiveBlending, depthWrite: false }));
  const boltGlow = []; [[0.25, 0.6], [-0.25, 0.6], [0.6, 0.3], [-0.6, 0.3]].forEach(([o, op]) => { const m = new THREE.LineSegments(boltG, new THREE.LineBasicMaterial({ color: 0x4fd8ff, transparent: true, opacity: op, blending: THREE.AdditiveBlending, depthWrite: false })); m.position.set(o, o * 0.5, -0.1); boltGlow.push(m); });
  const boltGrp = new THREE.Group(); boltGrp.add(boltCore, ...boltGlow); hud.add(boltGrp);
  let boltN = 0, boltNext = 0;
  function seg(ax, ay, bx2, by2) { if (boltN + 2 > BOLT_MAX) return; boltP.set([ax, ay, 0.3, bx2, by2, 0.3], boltN * 3); boltN += 2; }
  function bolt(x0, y0, ang, len, jag, depth) {
    const n = 9 + Math.floor(rnd() * 5); let px = x0, py = y0; const nx = -Math.sin(ang), ny = Math.cos(ang);
    for (let i = 1; i <= n; i++) { const f = i / n, off = (rnd() - 0.5) * jag * (1 - f * 0.4), x = x0 + Math.cos(ang) * len * f + nx * off, y = y0 + Math.sin(ang) * len * f + ny * off;
      seg(px, py, x, y); if (depth < 2 && rnd() < 0.15) bolt(x, y, ang + (rnd() - 0.5) * 1.3, len * (0.25 + rnd() * 0.3), jag * 0.6, depth + 1); px = x; py = y; }
  }
  function updBolts(t, lvl, col, flare) {
    boltGlow.forEach(m => m.material.color.copy(col));
    if (t < boltNext && !reduce) return; boltNext = t + 0.05 + rnd() * 0.05; boltN = 0;                       // parpadeo ~15 Hz
    const pts = raysM === "speak" || (raysM === "idle" && lvl > 0.15) ? "speak" : raysM, n = rays.children.length;
    rays.children.forEach((r, i) => { const on = pts === "idle" ? rnd() < 0.35 : pts === "speak" ? rnd() < 0.55 : rnd() < 0.85; if (!on) return;
      const ang = r.rotation.z + Math.PI / 2, L = (pts === "idle" ? 14 + rnd() * 10 : pts === "point" ? 46 + rnd() * 10 : 26 + lvl * 26 + rnd() * 8) + flare * 20;
      bolt(Math.cos(ang) * 11, Math.sin(ang) * 11, ang, L, pts === "point" ? 2.2 : 3.6, 0); });
    boltG.attributes.position.needsUpdate = true; boltG.setDrawRange(0, boltN);
    const fl = 0.65 + 0.35 * rnd(); boltCore.material.opacity = Math.min(1, fl * (0.6 + lvl * 0.8 + flare)); boltGlow.forEach(m => { m.material.opacity = Math.min(1, fl * (0.25 + lvl * 0.5 + flare * 0.5)); });
  }
  /* detalle high-tech: anillo de micro-texto/glifos y pistas de circuito (canvas original) + líneas de escaneo holográficas */
  const glyC = document.createElement("canvas"); glyC.width = glyC.height = 1024; { const g = glyC.getContext("2d"); g.translate(512, 512); g.strokeStyle = g.fillStyle = "#fff";
    g.font = "15px monospace"; g.textAlign = "center"; const hex = "0123456789ABCDEF";
    for (let i = 0; i < 72; i++) { g.save(); g.rotate(i / 72 * 6.283); let w = ""; for (let k = 0; k < 4; k++) w += hex[Math.floor(rnd() * 16)]; g.globalAlpha = 0.85; g.fillText(w, 0, -470); g.restore(); }
    g.lineWidth = 1.5; for (let i = 0; i < 40; i++) { const a = rnd() * 6.283, r0 = 300 + rnd() * 60, r1 = r0 + 50 + rnd() * 70, a2 = a + (rnd() - 0.5) * 0.25;   // pistas: radial + quiebre + vía
      g.globalAlpha = 0.6; g.beginPath(); g.moveTo(Math.cos(a) * r0, Math.sin(a) * r0); g.lineTo(Math.cos(a) * (r0 + r1) / 2, Math.sin(a) * (r0 + r1) / 2); g.lineTo(Math.cos(a2) * r1, Math.sin(a2) * r1); g.stroke();
      g.beginPath(); g.arc(Math.cos(a2) * r1, Math.sin(a2) * r1, 3.5, 0, 6.283); g.stroke(); }
    for (let i = 0; i < 180; i++) { const a = i / 180 * 6.283; g.globalAlpha = i % 6 ? 0.35 : 0.9; g.fillRect(Math.cos(a) * 430 - 1, Math.sin(a) * 430 - 1, i % 6 ? 2 : 4, i % 6 ? 2 : 4); } }
  const glyT = new THREE.CanvasTexture(glyC); glyT.anisotropy = 4;
  const glyph = new THREE.Mesh(new THREE.PlaneGeometry(64, 64), new THREE.MeshBasicMaterial({ map: glyT, color: 0x4fd8ff, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending, depthWrite: false })); glyph.position.z = -0.5; hud.add(glyph);
  const scanU = { uC: { value: new THREE.Color(0x4fd8ff) }, uT: { value: 0 } };
  const scanl = new THREE.Mesh(new THREE.CircleGeometry(17, 64), new THREE.ShaderMaterial({ uniforms: scanU, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: "varying vec2 vP; void main(){ vP = position.xy; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }",
    fragmentShader: "uniform vec3 uC; uniform float uT; varying vec2 vP; void main(){ float l = 0.5+0.5*sin(vP.y*9.0 - uT*6.0); float sw = exp(-pow(mod(vP.y + uT*12.0, 40.0) - 20.0, 2.0)*0.08); float e = smoothstep(17.0, 12.0, length(vP));" +
      " gl_FragColor = vec4(uC, (pow(l, 8.0)*0.07 + sw*0.25) * e); }" })); scanl.position.z = 1; hud.add(scanl);
  rays.parent.remove(rays); hud.add(rays); rays.scale.set(0.9, 2, 0.9);      // rayos en el plano de pantalla: apuntan de verdad
  rings.forEach(g => g.parent.remove(g)); ultronRings.parent.remove(ultronRings);   // los anillos 3D antiguos dan paso al HUD

  /* la torre es decorado de fondo: sin pisos clicables ni anillos de negocio en 3D (los datos viven en el panel principal) */
  namedRings.forEach(m => { m.visible = false; }); runes.forEach(m => { m.visible = false; }); selRing.visible = hovRing.visible = false;
  /* foco de cámara: el núcleo manda; focusOn("core" | "tower" | {x,y,z}) desplaza la mirada */
  let focusT = "core"; const focusP = new THREE.Vector3(), camLook = new THREE.Vector3(0, 80, 0), camPos = new THREE.Vector3(0, 60, 300);
  const focusOn = (target) => { focusT = (target === "tower" || target === "core" || (target && isFinite(target.x))) ? target : "core"; return focusT; };
  let push = 0, camInit = false, raysM = "idle", raysA = 0;
  /* objetivo de los rayos: {cripto:"BTC"}, {negocio:id}, selector CSS / elemento DOM, o {x,y} en pantalla */
  const beam = document.createElement("canvas"); beam.id = "rayo"; host.appendChild(beam); const bx = beam.getContext("2d");
  let chip = null, target = null, datos = { negocios: [], cripto: [] }; const chan = (() => { try { return new BroadcastChannel("jarvis-rayos"); } catch (e) { return null; } })();
  fetch("/api/negocios", { credentials: "same-origin" }).then(r => r.json()).then(t => { datos.negocios = t.negocios || []; }).catch(() => {});
  fetch("/api/cripto", { credentials: "same-origin" }).then(r => r.json()).then(m => { datos.cripto = m.precios || []; }).catch(() => {});
  const selOf = (tg) => tg && tg.cripto ? '[data-cripto="' + String(tg.cripto).toUpperCase().replace(/[^A-Z]/g, "") + '"]' : tg && tg.negocio != null ? '[data-negocio="' + String(tg.negocio).replace(/[^\w-]/g, "") + '"]' : typeof tg === "string" ? tg : null;
  const labelOf = (tg) => { if (tg && tg.cripto) { const c = datos.cripto.find(p => String(p.par).toUpperCase().startsWith(String(tg.cripto).toUpperCase())); return tg.cripto.toUpperCase() + (c && c.usd != null ? "  $" + Number(c.usd).toLocaleString("en-US", { maximumFractionDigits: 2 }) : ""); }
    if (tg && tg.negocio != null) { const n = datos.negocios.find(x => String(x.id) === String(tg.negocio)); return n ? "PISO " + n.piso + " · " + n.nombre : "NEGOCIO " + tg.negocio; } return ""; };
  function aimAt(tg) {                                   // devuelve el punto de pantalla del objetivo (y crea un rótulo si no está en esta página)
    if (!tg) return null; if (isFinite(tg.x) && isFinite(tg.y)) return { x: tg.x, y: tg.y };
    let e = tg instanceof Element ? tg : null; const sel = selOf(tg); if (!e && sel) { try { e = document.querySelector(sel); } catch (x) { e = null; } }
    if (e) { const r = e.getBoundingClientRect(), h = host.getBoundingClientRect(); return { x: r.left + r.width / 2 - h.left, y: r.top + r.height / 2 - h.top }; }
    if (!chip) { chip = document.createElement("div"); chip.className = "rayo-chip jarvis-scan"; host.appendChild(chip); }
    chip.textContent = labelOf(tg) || String(sel || ""); chip.style.left = "76%"; chip.style.top = "30%"; chip.hidden = false;
    const r = chip.getBoundingClientRect(), h = host.getBoundingClientRect(); return { x: r.left + r.width / 2 - h.left, y: r.top + r.height / 2 - h.top };
  }
  const raysMode = (m, tg) => { raysM = ["idle", "speak", "scan", "point"].includes(m) ? m : "idle"; target = raysM === "point" ? (tg === undefined ? target : tg) : null;
    if (chip && !target) chip.hidden = true;
    if (target) { const sel = selOf(target); if (sel) { if (window.JarvisMarcar) window.JarvisMarcar(sel); if (chan) chan.postMessage({ sel }); } }
    return raysM; };
  function drawBeam(t, col) {                            // haz 2D que se estira del núcleo al objetivo
    const w = beam.clientWidth, h = beam.clientHeight; if (beam.width !== w || beam.height !== h) { beam.width = w; beam.height = h; }
    bx.clearRect(0, 0, w, h); if (raysM !== "point" || !target) return;
    const p = aimAt(target); if (!p) return; const c = core.position.clone().project(camera), cx = (c.x * 0.5 + 0.5) * w, cy = (-c.y * 0.5 + 0.5) * h;
    raysA = Math.atan2(-(p.y - cy), p.x - cx) - Math.PI / 2; const css = "#" + col.getHexString();
    bx.globalCompositeOperation = "lighter"; [[14, 0.10], [6, 0.25], [2, 0.9]].forEach(([lw, al]) => { bx.strokeStyle = css; bx.globalAlpha = al; bx.lineWidth = lw; bx.beginPath(); bx.moveTo(cx, cy); bx.lineTo(p.x, p.y); bx.stroke(); });
    const u = reduce ? 0.6 : (t * 0.9) % 1; bx.globalAlpha = 1; bx.fillStyle = "#e8fbff"; bx.beginPath(); bx.arc(cx + (p.x - cx) * u, cy + (p.y - cy) * u, 3, 0, 6.283); bx.fill();
    bx.globalAlpha = 0.9; bx.lineWidth = 1.5; bx.beginPath(); bx.arc(p.x, p.y, 18 + (reduce ? 0 : Math.sin(t * 5) * 3), 0, 6.283); bx.stroke(); bx.globalAlpha = 1; }
  addEventListener("jarvis-accion", e => raysMode("point", e.detail && (e.detail.objetivo || e.detail)));   // acción u orden -> apunta
  addEventListener("jarvis-escanear", () => raysMode("scan"));
  addEventListener("jarvis-reposo", () => raysMode("idle"));
  let lastTopic = "";
  function onTopics(tp) { const k = (tp || [])[0] || ""; if (k === lastTopic) return; lastTopic = k;      // la voz menciona BTC o un negocio -> apunta
    if (!k) { if (raysM === "point") raysMode("idle"); return; } raysMode("point", k.startsWith("negocio:") ? { negocio: k.slice(8) } : { cripto: k }); }

  /* animación */
  const clock = new THREE.Clock(); let last = 0;
  const minDt = ECO ? 1 / 30 : 1 / 60;
  const t0 = parseFloat(qs.get("t") || "0") || 0;                                   // previsualización determinista
  const towerC = new THREE.Vector3(0, 55, 0), ORBIT_S = 60, ORBIT_R = 120; core.scale.setScalar(2);            // núcleo ~2x
  const ease = (x) => x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
  function frame() {
    requestAnimationFrame(frame);
    const t = clock.getElapsedTime() + t0; if (t - last < minDt) return; const dt = Math.min(0.1, Math.max(0.001, t - last)); last = t;
    if (mode !== shown && trans < 0) { trans = 0; shown = mode; }
    let flash = 0, glitch = 0, flare = 0, sh = -1;
    if (DEMO) { if (t >= 5 && t < 7.5 && raysM !== "point") raysMode("point", { cripto: "BTC" }); if (t >= 7.5 && raysM === "point") raysMode("idle"); }
    const ft = DEMO ? (t >= 7.5 ? Math.min(1, (t - 7.5) / TRANS_S) : -1) : freezeTrans;
    if (ft >= 0) { trans = ft * TRANS_S; shown = "ultron"; }
    if (trans >= 0) {
      const p = Math.min(1, trans / TRANS_S), target = shown === "ultron" ? 1 : 0;
      k = target ? ease(p) : 1 - ease(p);
      flash = Math.max(0, 1 - Math.abs(p - 0.18) / 0.18) * 0.55; glitch = Math.sin(p * Math.PI) * 1.6; flare = Math.sin(p * Math.PI); sh = p;
      if (ft < 0) { trans += reduce ? TRANS_S : dt; if (trans >= TRANS_S) trans = -1; }
    } else k += ((shown === "ultron" ? 1 : 0) - k) * Math.min(1, dt * 3);
    const lvl = voiceLevel(t, dt * 1000), breath = reduce ? 0 : 0.5 + 0.5 * Math.sin(t * 1.3);
    const col = BLUE.clone().lerp(RED, k);
    coreU.uColor.value.copy(col); inner.material.color.copy(col).lerp(new THREE.Color(1, 1, 1), 0.3); glassU.uLvl.value = lvl; shells.forEach(m => { m.material.color.copy(col); if (!reduce) { m.rotation.y += dt * m.userData.sp; m.rotation.x += dt * m.userData.sp * 0.5; } }); glowS.material.color.copy(col); glowS.material.opacity = 0.55 + 0.25 * breath + 0.4 * lvl; orbP.material.color.copy(col).lerp(new THREE.Color(1, 1, 1), 0.3); if (!reduce) orbP.rotation.z += dt * (0.15 + lvl); starU.uTime.value = reduce ? 0 : t;
    torches.forEach(o => { const fl = reduce ? 1 : 0.75 + 0.25 * Math.sin(t * 13 + o.ph) * Math.sin(t * 7.3 + o.ph * 2); o.L.intensity = 160 * fl; o.f.scale.setScalar(4.2 + fl * 1.6); });
    if (!reduce) { const ep = brasas.geometry.attributes.position; for (let i = 0; i < emberN; i++) { const b = emberB[i % emberB.length]; let y = ep.getY(i) + dt * (3 + (i % 5)); if (y > b.y + 14) y = b.y; ep.setXYZ(i, b.x + Math.sin(t * 2 + i) * 0.8, y, b.z + Math.cos(t * 1.7 + i) * 0.8); } ep.needsUpdate = true; }
    runes.forEach(m => m.material.uniforms.uC.value.copy(col));
    focal.material.color.copy(col); focalRing.material.color.copy(col); focal.material.opacity = 0.25 + 0.15 * breath + 0.3 * lvl; if (!reduce) focalRing.rotation.z += dt * 0.2; accents.forEach((a, i) => { if (!reduce) a.material.opacity = 0.75 + 0.25 * Math.sin(t * 3 + i * 1.7); }); coreU.uTime.value = t; coreU.uGlitch.value = reduce ? 0 : Math.max(k * 0.6, glitch);
    ringMatC.color.copy(col); coreLight.color.copy(col); coreLight.intensity = 380 + breath * 180 + lvl * 900 + flare * 1500;
    gridU.uColor.value.copy(new THREE.Color(0x46c8ff).lerp(RED, k)); gridU.uTime.value = t;
    warmLights.forEach(l => l.color.copy(WARM.clone().lerp(WARM_R, k)));
    glows.forEach(g => g.material.color.copy(WARM.clone().lerp(WARM_R, k)));
    namedRings.forEach(m => m.material.color.copy(col)); selRing.material.color.copy(col); hovRing.material.color.copy(col);
    clouds.forEach(c => { c.material.color.copy(CL.clone().lerp(CL_R, k * 0.8));
      if (!reduce) { c.userData.a += c.userData.sp * dt * 0.2; c.position.x = Math.cos(c.userData.a) * c.userData.d; c.position.z = Math.sin(c.userData.a) * c.userData.d; } });
    rings.forEach((g, i) => { g.visible = k < 0.6; if (!reduce) g.rotation.z += dt * (0.25 + i * 0.12 + lvl * 0.8) * (i % 2 ? -1 : 1); });
    ultronRings.visible = k >= 0.6; if (!reduce) { ultronRings.rotation.z -= dt * 1.2; ultronRings.children[1].rotation.z += dt * 2.0; }
    inner.scale.setScalar(1 + 0.06 * breath + 0.35 * lvl + 0.4 * flare);
    glass.scale.setScalar(1 + 0.02 * breath + 0.06 * lvl);
    rayMat.uniforms.uI.value = 0.05 + 0.06 * breath + lvl * 0.5 + flare * 1.0 + (raysM === "idle" ? 0 : 0.35);
    { const pts = raysM === "speak" || (raysM === "idle" && lvl > 0.15) ? "speak" : raysM;            // idle: deriva; speak: haz barrido; scan: arco; point: apunta
      rays.children.forEach((r, i) => { const n = rays.children.length, base = i / n * 6.283; let a;
        if (pts === "speak") a = (reduce ? 0 : Math.sin(t * 1.6) * 0.5) + (i / n - 0.5) * (1.4 + lvl * 0.8);
        else if (pts === "scan") a = (reduce ? 0 : Math.sin(t * 1.1) * 1.3) + (i / n - 0.5) * 0.9;
        else if (pts === "point") a = raysA + (i / n - 0.5) * 0.12;
        else a = base + (reduce ? 0 : t * 0.08);
        const dA = Math.atan2(Math.sin(a - r.rotation.z), Math.cos(a - r.rotation.z)); r.rotation.z += dA * (reduce ? 1 : Math.min(1, dt * 6 + (pts === "point" ? 0.35 : 0))); r.scale.y = pts === "idle" ? 0.8 : 1.15 + lvl * 0.4; }); }
    if (sh >= 0) { shock.visible = true; shock.scale.setScalar(4 + sh * 70); shock.material.opacity = (1 - sh) * 0.9; shock.material.color.copy(col).lerp(new THREE.Color(1, 1, 1), 0.5); } else shock.visible = false;
    film.uniforms.uTime.value = t; film.uniforms.uFlash.value = flash; film.uniforms.uCA.value = 0.0015 + glitch * 0.004;
    film.uniforms.uTint.value.copy(new THREE.Color(1, 1, 1).lerp(col, 0.4));
    bloom.strength = (ECO ? 0.7 : 0.75) + flare * 1.0 + lvl * 0.35;
    /* órbita del núcleo alrededor de la torre (~60 s por vuelta), mirando a la torre */
    const oa = reduce ? 0.9 : (t / ORBIT_S) * 6.283 + 0.9;
    core.position.set(Math.cos(oa) * ORBIT_R, 80 + (reduce ? 0 : Math.sin(t * 0.8) * 3), Math.sin(oa) * ORBIT_R);
    core.lookAt(towerC.x, core.position.y, towerC.z);
    if (caustic) { caustic.target.position.copy(towerC).setY(core.position.y - 10); caustic.color.copy(col); caustic.intensity = 2500 + lvl * 4000 + flare * 6000;
      caustic.map.offset.set(t * 0.03, t * 0.02); }
    if (!reduce) {
      const ep = embers.geometry.attributes.position, v = embers.userData.v;
      for (let i = 0; i < ep.count; i++) { let y = ep.getY(i) + v[i] * dt * 6; if (y > 100) y = -100; ep.setY(i, y); } ep.needsUpdate = true;
      motes.rotation.y += dt * 0.15;
    }
    /* cámara: sigue al núcleo por su órbita; acercamiento (dolly) al hablar o en alerta */
    push += (Math.min(1, lvl * 1.4 + k * 0.6 + flare * 0.5) - push) * Math.min(1, dt * (push < lvl ? 4 : 1.2));
    if (focusT === "core") focusP.copy(core.position); else if (focusT === "tower") focusP.copy(towerC).setY(70); else focusP.set(focusT.x, focusT.y, focusT.z);
    const out = new THREE.Vector3(core.position.x, 0, core.position.z).normalize();          // hacia fuera de la torre
    const side = new THREE.Vector3(-out.z, 0, out.x), dist = 62 - push * 8;                                        // primer plano: núcleo+HUD ~75% del alto
    const want = core.position.clone().addScaledVector(out, dist * 0.92).addScaledVector(side, dist * 0.38).add(new THREE.Vector3(0, -dist * 0.12 + (reduce ? 0 : Math.sin(t * 0.21) * 3), 0));
    const ease2 = (reduce || !camInit) ? 1 : Math.min(1, dt * 2.2); camInit = true;
    camPos.lerp(want, ease2); camLook.lerp(focusP, focusT === "core" ? 1 : ease2);
    camera.position.copy(camPos); camera.lookAt(camLook); camera.updateMatrixWorld(); updHud(t, dt, lvl, col, k); drawBeam(t, col); updReactor(t, lvl, breath, col); updBolts(t, lvl, col, flare); glyph.material.color.copy(col); if (!reduce) glyph.rotation.z = -t * 0.04; scanU.uC.value.copy(col); scanU.uT.value = reduce ? 0 : t; rayMat.uniforms.uI.value *= 0.35;
    if (bokeh) bokeh.uniforms.focus.value = camera.position.distanceTo(focusP);            // torre fuera de foco detrás
    composer.render(dt);
  }
  frame();
  window.JarvisTorreCine = { mode: () => mode, focusOn, raysMode }; window.__cineTopics = onTopics;
  { const rm = qs.get("rayos"), ob = qs.get("objetivo"); if (rm) raysMode(rm, ob ? (/^[A-Z]{3,4}$/.test(ob) ? { cripto: ob } : { negocio: ob }) : undefined); }
  return true;
}

function archGeometry(w, h) {                                // arco apuntado (ventana iluminada)
  const s = new THREE.Shape(); s.moveTo(-w / 2, 0); s.lineTo(-w / 2, h * 0.6);           // arco apuntado gótico
  s.quadraticCurveTo(-w / 2, h * 0.9, 0, h); s.quadraticCurveTo(w / 2, h * 0.9, w / 2, h * 0.6); s.lineTo(w / 2, 0); s.lineTo(-w / 2, 0);
  return new THREE.ShapeGeometry(s, 6);
}

try { start(); } catch (e) {                                   // cualquier fallo: vuelve la escena 2D
  document.body.classList.remove("cine"); const c = document.getElementById("cine"); if (c) c.remove();
  if (window.JarvisAincradScene && window.JarvisAincradScene.resume) window.JarvisAincradScene.resume();
}
