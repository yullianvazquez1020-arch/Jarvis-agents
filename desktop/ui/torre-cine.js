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
  const canvas = document.createElement("canvas"); canvas.id = "cine"; canvas.setAttribute("aria-label", "Torre de Aincrad en 3D con el núcleo Jarvis flotando a su lado");
  host.appendChild(canvas);
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ canvas, antialias: !ECO, powerPreference: ECO ? "low-power" : "high-performance" }); }
  catch (e) { canvas.remove(); return false; }
  document.body.classList.add("cine");
  if (window.JarvisAincradScene && window.JarvisAincradScene.stop) window.JarvisAincradScene.stop();
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, ECO ? 1 : 1.5));
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
      " c += vec3(0.5,0.52,0.58)*pow(m,60.0)*0.35 + vec3(0.2,0.22,0.28)*pow(m,8.0)*0.06; c += vec3(1.0)*smoothstep(0.9993,0.9996,m);" +
      " gl_FragColor = vec4(c,1.0); }" })));
  { const n = ECO ? 900 : 2200, p = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) { const th = rnd() * 6.283, ph = Math.acos(rnd() * 0.9), r = 850; p.set([r * Math.sin(ph) * Math.cos(th), r * Math.cos(ph), r * Math.sin(ph) * Math.sin(th)], i * 3); }
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(p, 3));
    scene.add(new THREE.Points(g, new THREE.PointsMaterial({ size: 1.6, sizeAttenuation: false, color: 0xcfdcff, transparent: true, opacity: 0.8, fog: false }))); }

  /* luces: luna fría con sombra suave, resplandor cálido desde abajo, relleno */
  scene.add(new THREE.HemisphereLight(0x4a5060, 0x3a2410, 0.35));
  const moon = new THREE.DirectionalLight(0xe2dccf, 3.4); moon.position.set(320, 240, 220); moon.castShadow = !ECO;
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
  const rockMat = stoneDark.clone(); if (!ECO) pbr(rockMat, "roca", [5, 3], false);
  const castle = new THREE.Group(); scene.add(castle);
  const baseY = -30, topY = 150, tierH = (topY - baseY) / TIERS, R0 = 50, R1 = 15;
  const tiers = [], bodies = [];
  const dummy = new THREE.Object3D();
  let winCount = 0; const winMats = [];
  for (let t = 0; t < TIERS; t++) {
    const k = t / (TIERS - 1), r = R1 + (R0 - R1) * Math.pow(1 - k, 0.85) * (1 + 0.06 * Math.sin(k * 13)), y0 = baseY + t * tierH;
    const seg = ECO ? 32 : 64;
    const body = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.84, r * 0.86, tierH * 0.8, seg, 1, true), stone);
    body.position.y = y0 + tierH * 0.4; body.castShadow = body.receiveShadow = !ECO; body.userData.tier = t; castle.add(body); bodies.push(body);
    const deck = new THREE.Mesh(new THREE.CylinderGeometry(r * 1.08, r * 0.9, tierH * 0.2, seg), stoneDark);   // reborde voladizo
    deck.position.y = y0 + tierH * 0.9; deck.castShadow = deck.receiveShadow = !ECO; castle.add(deck);
    const lip = new THREE.Mesh(new THREE.TorusGeometry(r * 1.08, tierH * 0.06, 6, seg), stoneDark); lip.rotation.x = Math.PI / 2; lip.position.y = y0 + tierH * 1.0; castle.add(lip);
    const nB = Math.max(16, Math.round(r * (ECO ? 1.0 : 1.4)));                        // almenas
    const merl = new THREE.InstancedMesh(new THREE.BoxGeometry(r * 6.283 / nB * 0.55, tierH * 0.32, 1.6), stone, nB);
    for (let i = 0; i < nB; i++) { const a = i / nB * 6.283; dummy.position.set(Math.cos(a) * r * 1.06, y0 + tierH * 1.16, Math.sin(a) * r * 1.06); dummy.rotation.set(0, -a + Math.PI / 2, 0); dummy.updateMatrix(); merl.setMatrixAt(i, dummy.matrix); }
    merl.castShadow = !ECO; castle.add(merl);
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
        const roof = new THREE.Mesh(new THREE.ConeGeometry(tr * 1.35, th2 * 0.55, 12), stoneDark); roof.position.set(tw.position.x, tw.position.y + th2 / 2 + th2 * 0.27, tw.position.z); roof.castShadow = !ECO; castle.add(roof);
        const wl = new THREE.Mesh(archGeometry(tr * 0.6, th2 * 0.25), winMat); wl.position.set(Math.cos(a) * (r * 1.0 + tr * 1.02), tw.position.y, Math.sin(a) * (r * 1.0 + tr * 1.02)); wl.rotation.y = -a + Math.PI / 2; castle.add(wl); }
    }
    tiers.push({ r, y0, y1: y0 + tierH });
  }
  const spire = new THREE.Mesh(new THREE.ConeGeometry(R1 * 0.75, 30, 24), stone); spire.position.y = topY + 15; spire.castShadow = !ECO; castle.add(spire);
  { const g = new THREE.ConeGeometry(R0 * 0.95, 60, 48, 10, true), pos = g.attributes.position;  // roca colgante
    for (let i = 0; i < pos.count; i++) { const v = new THREE.Vector3().fromBufferAttribute(pos, i); const n = 1 + (rnd() - 0.5) * 0.22 * (1 - Math.abs(v.y) / 30); pos.setXYZ(i, v.x * n, v.y + (rnd() - 0.5) * 2, v.z * n); }
    g.computeVertexNormals(); const rock = new THREE.Mesh(g, rockMat); rock.rotation.x = Math.PI; rock.position.y = baseY - 30; rock.castShadow = !ECO; castle.add(rock); }

  /* pisos: resaltado de negocios y de la selección */
  const ringMat = (op) => new THREE.MeshBasicMaterial({ color: 0x5ad2ff, transparent: true, opacity: op, blending: THREE.AdditiveBlending, depthWrite: false });
  const floorY = (f) => { const t = Math.floor((f - 1) / 4), q = (f - 1) % 4; return { y: tiers[t].y0 + (q + 0.5) * tierH / 4, r: tiers[t].r }; };
  const namedRings = [];
  for (let f = 1; f <= 5; f++) { const { y, r } = floorY(f); const m = new THREE.Mesh(new THREE.TorusGeometry(r * 0.96, 0.18, 6, 96), ringMat(0.7)); m.rotation.x = Math.PI / 2; m.position.y = y; castle.add(m); namedRings.push(m); }
  const selRing = new THREE.Mesh(new THREE.TorusGeometry(1, 0.32, 8, 128), ringMat(0.95)); selRing.rotation.x = Math.PI / 2; selRing.visible = false; castle.add(selRing);
  const hovRing = new THREE.Mesh(new THREE.TorusGeometry(1, 0.2, 8, 128), ringMat(0.55)); hovRing.rotation.x = Math.PI / 2; hovRing.visible = false; castle.add(hovRing);
  const place = (ring, f) => { if (f < 1) { ring.visible = false; return; } const { y, r } = floorY(f); ring.position.y = y; ring.scale.setScalar(r * 0.97); ring.visible = true; };

  /* nubes en capas, encendidas desde abajo */
  const cloudTex = softSprite(256);
  const clouds = [];
  const nCl = ECO ? 70 : 170;
  for (let i = 0; i < nCl; i++) {
    const m = new THREE.SpriteMaterial({ map: cloudTex, color: 0x2c3242, transparent: true, opacity: 0.85, depthWrite: false, fog: true });
    const s = new THREE.Sprite(m); const a = rnd() * 6.283, d = 30 + Math.pow(rnd(), 0.7) * 420, layer = rnd();
    s.position.set(Math.cos(a) * d, -110 - layer * 35, Math.sin(a) * d); const sc = 80 + rnd() * 140; s.scale.set(sc, sc * 0.4, 1);
    s.userData = { a, d, sp: 0.004 + rnd() * 0.01, layer }; scene.add(s); clouds.push(s);
  }

  const glowTex = dotSprite(), glows = [];                                       // ciudades lejanas bajo las nubes
  for (let i = 0; i < (ECO ? 18 : 40); i++) {
    const m = new THREE.SpriteMaterial({ map: glowTex, color: 0xff9a4a, transparent: true, opacity: 0.22, blending: THREE.AdditiveBlending, depthWrite: false });
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
    " gl_FragColor = vec4(uColor*(0.6 + fr*2.2 + scan*0.8), a); }";
  const holo = new THREE.ShaderMaterial({ uniforms: coreU, vertexShader: holoVS, fragmentShader: holoFS, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide });
  const core = new THREE.Group(); core.position.set(118, 80, 30); scene.add(core);
  core.add(new THREE.Mesh(new THREE.IcosahedronGeometry(7, ECO ? 2 : 4), holo));
  const inner = new THREE.Mesh(new THREE.SphereGeometry(2.6, 24, 16), new THREE.MeshBasicMaterial({ color: 0xffffff })); core.add(inner);
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
  const glass = new THREE.Mesh(new THREE.SphereGeometry(8.2, 48, 32), new THREE.MeshPhysicalMaterial({
    color: 0xffffff, metalness: 0, roughness: 0.04, transmission: ECO ? 0 : 1, ior: 1.45, thickness: 3.5,
    transparent: !!ECO, opacity: ECO ? 0.15 : 1, envMapIntensity: 1.2, clearcoat: 1, clearcoatRoughness: 0.05, attenuationColor: new THREE.Color(0x9fe8ff), attenuationDistance: 12 }));
  core.add(glass);
  const rayMat = new THREE.ShaderMaterial({ uniforms: { uColor: coreU.uColor, uI: { value: 0.2 }, uTime: coreU.uTime }, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    vertexShader: "varying vec2 vU; void main(){ vU = uv; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }",
    fragmentShader: "uniform vec3 uColor; uniform float uI; uniform float uTime; varying vec2 vU; void main(){ float a = (1.0 - vU.y) * smoothstep(0.0, 0.5, 1.0 - abs(vU.x - 0.5) * 2.0);" +
      " a *= 0.7 + 0.3 * sin(vU.y * 30.0 - uTime * 8.0); gl_FragColor = vec4(uColor, a * uI); }" });
  const rays = new THREE.Group(); core.add(rays);
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
    gtao.updateGtaoMaterial({ radius: 6, distanceExponent: 1.5, thickness: 2, scale: 1.2 }); composer.addPass(gtao); }
  const bloom = new UnrealBloomPass(new THREE.Vector2(512, 512), ECO ? 0.6 : 0.8, 0.5, 0.9); composer.addPass(bloom);
  let bokeh = null;
  if (!ECO) { bokeh = new BokehPass(scene, camera, { focus: 260, aperture: 0.00009, maxblur: 0.003 }); composer.addPass(bokeh); }
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
    const poll = () => fetch("/api/state", { credentials: "same-origin" }).then(r => r.json()).then(j => { mode = j.mode || "jarvis"; speaking = !!j.speaking; }).catch(() => {});
    poll(); setInterval(poll, 3000);
  }
  const TRANS_S = 1.2;
  const freezeTrans = qs.get("trans") !== null ? Math.max(0, Math.min(1, parseFloat(qs.get("trans")) || 0.5)) : -1;
  const fakeTalk = qs.get("habla") !== null;
  const BLUE = new THREE.Color(0x5ad2ff), RED = new THREE.Color(0xff4a1e), WARM = new THREE.Color(0xff9a50), WARM_R = new THREE.Color(0xff3a14);
  const CL = new THREE.Color(0x2c3242), CL_R = new THREE.Color(0x3a2424);

  /* voz de Alan: nivel real por BroadcastChannel (lipsync.js de la ventana de conversación); si no, estado del servidor */
  const L = window.JarvisLipsync;
  const voice = { env: null, clock: null, filter: L ? new L.ClockFilter() : null, follower: L ? new L.Follower() : null, level: 0 };
  try { if (L && "BroadcastChannel" in window) { const ch = new BroadcastChannel(L.CHANNEL); ch.onmessage = (ev) => { const m = ev.data; if (!L.valid(m)) return;
    if (m.k === "env") voice.env = m; else if (m.k === "clock") { voice.clock = m; voice.filter.push(m); } else if (m.k === "stop") voice.clock = null; }; } } catch (e) { /* sin canal */ }
  function voiceLevel(t, dtMs) {
    if (fakeTalk) return 0.55 + 0.45 * Math.abs(Math.sin(t * 9.0) * Math.sin(t * 3.1 + 1.0));
    const c = voice.clock, env = voice.env;
    if (c && env && c.id === env.id && voice.follower) { const pos = voice.filter.position(performance.now());
      const target = c.playing && pos <= env.duration + 0.05 ? L.level(env, pos + L.LOOKAHEAD_S) : 0; return (voice.level = voice.follower.step(target, dtMs)); }
    voice.level += ((speaking ? 0.45 + 0.25 * Math.sin(t * 11) : 0) - voice.level) * 0.2;           // respaldo: "hablando" del servidor
    return voice.level;
  }

  /* pisos clicables */
  let pisos = [];
  fetch("/api/negocios", { credentials: "same-origin" }).then(r => r.json()).then(t => { pisos = t.pisos || []; }).catch(() => {});
  const ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
  const label = document.createElement("div"); label.className = "cine-label"; host.appendChild(label);
  function pick(e) {
    const r = canvas.getBoundingClientRect(); mouse.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(mouse, camera); const hit = ray.intersectObjects(bodies, false)[0]; if (!hit) return -1;
    const t = hit.object.userData.tier, q = Math.min(3, Math.max(0, Math.floor((hit.point.y - tiers[t].y0) / (tierH / 4))));
    return t * 4 + q + 1;
  }
  let sel = -1;
  function show(f) { const p = pisos[f - 1]; label.textContent = f > 0 ? ("Piso " + f + (p ? " · " + p.nombre + " · " + p.estado : "")) : ""; label.classList.toggle("on", f > 0); }
  canvas.addEventListener("mousemove", e => { const f = pick(e); place(hovRing, f); canvas.style.cursor = f > 0 ? "pointer" : ""; if (sel < 0) show(f); });
  canvas.addEventListener("click", e => { const f = pick(e); if (f > 0) { sel = f; place(selRing, f); show(f); dispatchEvent(new CustomEvent("jarvis-piso", { detail: f })); } });
  addEventListener("jarvis-piso-lista", e => { sel = e.detail; place(selRing, sel); show(sel); });

  /* animación */
  const clock = new THREE.Clock(); let last = 0;
  const minDt = ECO ? 1 / 30 : 1 / 60;
  const t0 = parseFloat(qs.get("t") || "0") || 0;                                   // previsualización determinista
  const towerC = new THREE.Vector3(0, 55, 0), ORBIT_S = 60, ORBIT_R = 105;
  const ease = (x) => x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
  function frame() {
    requestAnimationFrame(frame);
    const t = clock.getElapsedTime() + t0; if (t - last < minDt) return; const dt = Math.min(0.1, Math.max(0.001, t - last)); last = t;
    if (mode !== shown && trans < 0) { trans = 0; shown = mode; }
    let flash = 0, glitch = 0, flare = 0, sh = -1;
    if (freezeTrans >= 0) { trans = freezeTrans * TRANS_S; shown = "ultron"; }
    if (trans >= 0) {
      const p = Math.min(1, trans / TRANS_S), target = shown === "ultron" ? 1 : 0;
      k = target ? ease(p) : 1 - ease(p);
      flash = Math.max(0, 1 - Math.abs(p - 0.18) / 0.18) * 0.55; glitch = Math.sin(p * Math.PI) * 1.6; flare = Math.sin(p * Math.PI); sh = p;
      if (freezeTrans < 0) { trans += reduce ? TRANS_S : dt; if (trans >= TRANS_S) trans = -1; }
    } else k += ((shown === "ultron" ? 1 : 0) - k) * Math.min(1, dt * 3);
    const lvl = voiceLevel(t, dt * 1000), breath = reduce ? 0 : 0.5 + 0.5 * Math.sin(t * 1.3);
    const col = BLUE.clone().lerp(RED, k);
    coreU.uColor.value.copy(col); coreU.uTime.value = t; coreU.uGlitch.value = reduce ? 0 : Math.max(k * 0.6, glitch);
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
    rayMat.uniforms.uI.value = 0.06 + 0.1 * breath + lvl * 0.9 + flare * 1.2; if (!reduce) rays.rotation.z += dt * (0.1 + lvl);
    if (sh >= 0) { shock.visible = true; shock.scale.setScalar(4 + sh * 70); shock.material.opacity = (1 - sh) * 0.9; shock.material.color.copy(col).lerp(new THREE.Color(1, 1, 1), 0.5); } else shock.visible = false;
    film.uniforms.uTime.value = t; film.uniforms.uFlash.value = flash; film.uniforms.uCA.value = 0.0015 + glitch * 0.004;
    film.uniforms.uTint.value.copy(new THREE.Color(1, 1, 1).lerp(col, 0.4));
    bloom.strength = (ECO ? 0.6 : 0.8) + flare * 1.2 + lvl * 0.3;
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
    /* cámara: órbita lenta que mantiene a la torre y al núcleo en cuadro */
    const ca = reduce ? 0.6 : 0.6 + t * 0.03;
    const look = towerC.clone().lerp(core.position, 0.3);
    camera.position.set(Math.cos(ca) * 380, 45 + Math.sin(t * 0.07) * (reduce ? 0 : 8), Math.sin(ca) * 380);
    camera.lookAt(look);
    if (bokeh) bokeh.uniforms.focus.value = camera.position.distanceTo(towerC);
    composer.render(dt);
  }
  frame();
  window.JarvisTorreCine = { mode: () => mode, floorY, pick: (f) => { sel = f; place(selRing, f); show(f); } };
  return true;
}

function archGeometry(w, h) {                                // arco de medio punto (ventana iluminada)
  const s = new THREE.Shape(); s.moveTo(-w / 2, 0); s.lineTo(-w / 2, h * 0.65); s.absarc(0, h * 0.65, w / 2, Math.PI, 0, true); s.lineTo(w / 2, 0); s.lineTo(-w / 2, 0);
  return new THREE.ShapeGeometry(s, 6);
}

try { start(); } catch (e) {                                   // cualquier fallo: vuelve la escena 2D
  document.body.classList.remove("cine"); const c = document.getElementById("cine"); if (c) c.remove();
  if (window.JarvisAincradScene && window.JarvisAincradScene.resume) window.JarvisAincradScene.resume();
}
