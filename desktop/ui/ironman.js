/* Holograma: núcleo azul (reactor) como pieza central; la torre de 100 pisos queda en la lista lateral. Solo visualiza.
   No mueve dinero, no aprueba nada, no envía mensajes y no cambia ninguna lógica del servidor.
   Three.js va servido desde esta misma Mac (desktop/ui/vendor/three): sin CDN.
   La voz es Piper local: el núcleo sigue la amplitud (RMS) que publica la ventana de conversación
   por BroadcastChannel (lipsync.js). No hay ningún TTS externo aquí. */
import * as THREE from "./vendor/three/three.module.js";
import { OrbitControls } from "./vendor/three/controls/OrbitControls.js";

const A = window.JarvisAincrad, L = window.JarvisLipsync;
const el = (id) => document.getElementById(id);
const canvas = el("holo"), listHost = el("floor-list"), cardHost = el("floor-card");
const sceneStatus = el("scene-status"), dataNotice = el("data-notice"), voiceStatus = el("voice-status");

const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
let floors = A.demoFloors(), selected = 1, realData = false;
let running = false, paused = reduceMotion, last = 0, clock0 = 0;

/* ---------------------------------------------------------------- texto de estado */
function say(node, text) { if (node && node.textContent !== text) node.textContent = text; }
function noticeText() {
  return realData ? "Panel conectado · " + A.REAL_NOTICE : A.DEMO_NOTICE;
}
function refreshNotice() {
  say(dataNotice, noticeText());
  dataNotice.classList.toggle("real", realData);
  const totals = A.totals(floors);
  say(el("totals"), realData
    ? "Pisos: " + totals.floors + " · sin datos reales por piso"
    : "DEMO · Pisos: " + totals.floors + " · bruto " + A.money(totals.gross) +
      " · costos " + A.money(totals.cost) + " · neto " + A.money(totals.net));
}

/* ---------------------------------------------------------------- lista y ficha (solo nodos y textContent, nunca HTML en crudo) */
function buildList() {
  listHost.textContent = "";
  const frag = document.createDocumentFragment();
  for (const f of floors) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "floor-row";
    b.dataset.floor = String(f.floor);
    b.setAttribute("aria-pressed", f.floor === selected ? "true" : "false");
    const n = document.createElement("span"); n.className = "n"; n.textContent = String(f.floor);
    const name = document.createElement("span"); name.className = "name"; name.textContent = f.sector;
    const val = document.createElement("span"); val.className = "v"; val.textContent = A.money(A.net(f));
    b.append(n, name, val);
    b.style.setProperty("--c", f.color);
    b.addEventListener("click", () => selectFloor(f.floor, true));
    frag.appendChild(b);
  }
  listHost.appendChild(frag);
}

function renderCard() {
  const card = A.floorCard(floors[selected - 1]);
  cardHost.textContent = "";
  if (!card) return;
  const h = document.createElement("h2"); h.textContent = card.title;
  const s = document.createElement("p"); s.className = "sector"; s.textContent = card.sector;
  const dl = document.createElement("dl");
  for (const row of card.rows) {
    const dt = document.createElement("dt"); dt.textContent = row.label;
    const dd = document.createElement("dd"); dd.textContent = row.value;
    dl.append(dt, dd);
  }
  const note = document.createElement("p");
  note.className = card.demo ? "note demo" : "note";
  note.textContent = card.notice;
  cardHost.append(h, s, dl, note);
}

function selectFloor(n, fromUser) {
  if (!(n >= 1 && n <= A.FLOORS)) return;
  selected = n;
  for (const b of listHost.children) b.setAttribute("aria-pressed", b.dataset.floor === String(n) ? "true" : "false");
  renderCard();
  if (marker) {
    marker.position.y = floorY(n);
    marker.scale.setScalar(A.floorRadius(n) * RADIUS + 0.06);
    marker.visible = !marker.userData.hidden;
  }
  if (fromUser) {
    const row = listHost.querySelector('[data-floor="' + n + '"]');
    if (row && row.scrollIntoView) row.scrollIntoView({ block: "nearest" });
  }
  draw();
}

/* ---------------------------------------------------------------- escena */
const RADIUS = 1.35, TOWER_H = 3.4, CORE_R = 1.56;
const RING_SPEC = [
  { r: 2.25, ticks: 72, major: 6, label: "JARVIS · ARC REACTOR", w: 3 },
  { r: 2.7, ticks: 120, major: 10, label: "MARK VII · OUTPUT", w: 2 },
  { r: 3.15, ticks: 36, major: 3, label: "STARK INDUSTRIES", w: 4 }
];

/* Anillo con marcas: trazado en un lienzo 2D una sola vez (barato para el Mac 2015). */
function ringTexture(spec) {
  const S = 1024, c = document.createElement("canvas"); c.width = c.height = S;
  const g = c.getContext("2d"), cx = S / 2, R = S / 2 / 1.1;
  g.strokeStyle = "rgba(87,215,255,0.85)"; g.fillStyle = "rgba(140,220,255,0.9)";
  g.lineWidth = spec.w; g.beginPath(); g.arc(cx, cx, R, 0, Math.PI * 2); g.stroke();
  g.lineWidth = 1; g.beginPath(); g.arc(cx, cx, R - 26, 0, Math.PI * 2); g.stroke();
  for (let i = 0; i < spec.ticks; i++) {
    const a = i / spec.ticks * Math.PI * 2, big = i % spec.major === 0, len = big ? 22 : 10;
    g.lineWidth = big ? 3 : 1.2;
    g.beginPath();
    g.moveTo(cx + Math.cos(a) * (R - 3), cx + Math.sin(a) * (R - 3));
    g.lineTo(cx + Math.cos(a) * (R - 3 - len), cx + Math.sin(a) * (R - 3 - len));
    g.stroke();
  }
  g.font = "bold 22px Menlo, monospace"; g.textAlign = "center";
  for (let k = 0; k < 4; k++) {                          // rótulos y grados en cuatro puntos del anillo
    const a = k * Math.PI / 2 + Math.PI / 4;
    g.save(); g.translate(cx + Math.cos(a) * (R - 46), cx + Math.sin(a) * (R - 46)); g.rotate(a + Math.PI / 2);
    g.fillText(k % 2 ? String(k * 90 + 45).padStart(3, "0") + "°" : spec.label, 0, 0); g.restore();
  }
  const t = new THREE.CanvasTexture(c); t.anisotropy = 1; return t;
}

/* Estrellas: esfera lejana; con band=true se concentran en una franja inclinada (Vía Láctea). */
function starField(n, size, opacity, band) {
  const pos = new Float32Array(n * 3), colr = new Float32Array(n * 3), tilt = 0.5;
  for (let i = 0; i < n; i++) {
    const lon = Math.random() * Math.PI * 2;
    let lat = Math.asin(Math.random() * 2 - 1);
    if (band) lat = (Math.random() + Math.random() + Math.random() - 1.5) * 0.16;
    const rr = 30 + Math.random() * 20;
    let x = Math.cos(lat) * Math.cos(lon) * rr, y = Math.sin(lat) * rr, z = Math.cos(lat) * Math.sin(lon) * rr;
    const y2 = y * Math.cos(tilt) - x * Math.sin(tilt); x = x * Math.cos(tilt) + y * Math.sin(tilt); y = y2;
    pos.set([x, y, z], i * 3);
    const w = 0.7 + Math.random() * 0.3, warm = band && Math.random() < 0.3;
    colr.set(warm ? [w, w * 0.85, w * 0.95] : [w * 0.75, w * 0.88, w], i * 3);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.BufferAttribute(colr, 3));
  return new THREE.Points(g, new THREE.PointsMaterial({ size: size * 4, vertexColors: true, transparent: true,
                                                        opacity: opacity, depthWrite: false, sizeAttenuation: true }));
}
const floorY = (n) => -TOWER_H / 2 + A.floorHeight(n) * TOWER_H;

let renderer = null, scene = null, camera = null, controls = null, core = null, coreMat = null;
let tower = null, marker = null, rings = [], dust = null;

function startScene() {
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true, powerPreference: "low-power" });
  } catch (e) {
    say(sceneStatus, "Este navegador no pudo abrir WebGL: la lista de pisos y las fichas siguen funcionando.");
    return false;
  }
  renderer.setPixelRatio(1);                      // Mac 2015: nunca Retina, nunca bloom
  renderer.setClearColor(0x000000, 0);

  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(46, 16 / 9, 0.1, 100);
  camera.position.set(0, 0, 8.6);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = false;                 // amortiguar obliga a dibujar siempre: en el Mac 2015 no
  controls.enablePan = false;
  controls.minDistance = 3.2;
  controls.maxDistance = 13;
  controls.target.set(0, 0, 0);
  controls.addEventListener("change", draw);

  /* Núcleo: icosaedro de malla fina con shader propio (fresnel + barrido + parpadeo). Sin bloom. */
  coreMat = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.FrontSide,
    uniforms: { uTime: { value: 0 }, uLevel: { value: 0 }, uGlow: { value: A.IDLE_GLOW }, uBlink: { value: 0 } },
    vertexShader: [
      // La misma precisión en los dos shaders: si difieren, el programa no enlaza y el lienzo sale negro.
      "precision mediump float;",
      "uniform float uTime; uniform float uLevel;",
      "varying vec3 vN; varying vec3 vView; varying float vY;",
      "void main() {",
      "  vN = normalize(normalMatrix * normal);",
      "  float wob = sin(position.y * 7.0 + uTime * 1.7) * 0.012 + uLevel * 0.085;",
      "  vec3 p = position * (1.0 + wob);",
      "  vY = position.y;",
      "  vec4 mv = modelViewMatrix * vec4(p, 1.0);",
      "  vView = normalize(-mv.xyz);",
      "  gl_Position = projectionMatrix * mv;",
      "}"
    ].join("\n"),
    fragmentShader: [
      "precision mediump float;",
      "uniform float uTime; uniform float uGlow; uniform float uBlink; uniform float uLevel;",
      "varying vec3 vN; varying vec3 vView; varying float vY;",
      "void main() {",
      // Borde limpio: el fresnel sube y se desvanece suave en la silueta (sin destello blanco ni aro oscuro).
      "  float fres = pow(1.0 - abs(dot(normalize(vN), normalize(vView))), 2.2);",
      "  float edge = 1.0 - smoothstep(0.82, 1.0, fres);",
      "  float scan = 0.55 + 0.45 * sin(vY * 46.0 - uTime * 2.4);",
      "  float flick = 0.94 + 0.06 * sin(uTime * 37.0);",
      "  float a = (fres * 0.7 + 0.22) * edge * (0.75 + 0.25 * scan) * flick * uGlow * (1.0 - uBlink);",
      "  vec3 cold = vec3(0.16, 0.62, 1.0), warm = vec3(0.36, 0.80, 1.0);",
      "  vec3 col = mix(cold, warm, clamp(fres * 0.6 + uLevel * 0.5, 0.0, 1.0));",
      "  gl_FragColor = vec4(col, clamp(a, 0.0, 1.0));",
      "}"
    ].join("\n")
  });
  /* Diseño aprobado: solo el núcleo, al centro y al doble del tamaño anterior (0.78 → 1.56). */
  core = new THREE.Mesh(new THREE.IcosahedronGeometry(CORE_R, 4), coreMat);
  core.position.set(0, 0, 0);
  scene.add(core);

  const heart = new THREE.Mesh(new THREE.IcosahedronGeometry(CORE_R * 0.44, 2),
                               new THREE.MeshBasicMaterial({ color: 0x5fc8ff, transparent: true, opacity: 0.35,
                                                             blending: THREE.AdditiveBlending, depthWrite: false }));
  heart.position.copy(core.position);
  core.add(heart);                                       // late con el núcleo
  heart.position.set(0, 0, 0);

  const wire = new THREE.LineSegments(
    new THREE.WireframeGeometry(new THREE.IcosahedronGeometry(CORE_R * 1.26, 1)),
    new THREE.LineBasicMaterial({ color: 0x4fc3ff, transparent: true, opacity: 0.18 })
  );
  wire.position.copy(core.position);
  scene.add(wire);
  rings.push(wire);

  /* Anillos concéntricos estilo Iron Man, de cara a la cámara, con marcas y rótulos (textura de lienzo). */
  for (let i = 0; i < RING_SPEC.length; i++) {
    const spec = RING_SPEC[i];
    const r = new THREE.Mesh(new THREE.PlaneGeometry(spec.r * 2.2, spec.r * 2.2),
      new THREE.MeshBasicMaterial({ map: ringTexture(spec), transparent: true, depthWrite: false,
                                    blending: THREE.AdditiveBlending, opacity: 0.9 }));
    r.position.set(0, 0, -0.01 * i);
    scene.add(r);
    rings.push(r);
  }

  /* Torre: un cilindro, cien instancias. Cada piso con el color de su sector. */
  const gap = TOWER_H / (A.FLOORS - 1);                 // separación entre pisos
  const geo = new THREE.CylinderGeometry(1, 1, gap * 0.55, 18, 1, false);
  const mat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.62, depthWrite: false });
  tower = new THREE.InstancedMesh(geo, mat, A.FLOORS);
  tower.instanceMatrix.setUsage(THREE.StaticDrawUsage);
  const m = new THREE.Matrix4(), col = new THREE.Color();
  for (let i = 0; i < A.FLOORS; i++) {
    const f = floors[i], rad = A.floorRadius(f.floor) * RADIUS;
    m.makeScale(rad, 1, rad);
    m.setPosition(0, floorY(f.floor), 0);
    tower.setMatrixAt(i, m);
    tower.setColorAt(i, col.set(f.color));
  }
  tower.instanceMatrix.needsUpdate = true;
  if (tower.instanceColor) tower.instanceColor.needsUpdate = true;
  tower.visible = false;                                 // la torre sale de la vista principal (diseño aprobado)
  scene.add(tower);

  const edgeGeo = new THREE.TorusGeometry(1, 0.0055, 4, 40);
  const edges = new THREE.InstancedMesh(edgeGeo, new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.85 }),
                                        A.FLOORS);
  const em = new THREE.Matrix4(), eq = new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI / 2, 0, 0));
  const ev = new THREE.Vector3(), es = new THREE.Vector3();
  for (let i = 0; i < A.FLOORS; i++) {
    const f = floors[i], rad = A.floorRadius(f.floor) * RADIUS;
    ev.set(0, floorY(f.floor), 0); es.set(rad, rad, rad);
    em.compose(ev, eq, es);
    edges.setMatrixAt(i, em);
    edges.setColorAt(i, col.set(f.color));
  }
  edges.instanceMatrix.needsUpdate = true;
  if (edges.instanceColor) edges.instanceColor.needsUpdate = true;
  tower.add(edges);                                      // gira con la torre

  const spine = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, TOWER_H + 0.5, 6),
                               new THREE.MeshBasicMaterial({ color: 0x57d7ff, transparent: true, opacity: 0.35 }));
  spine.visible = false;
  scene.add(spine);

  marker = new THREE.Mesh(
    new THREE.TorusGeometry(1, 0.012, 5, 64),
    new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9 })
  );
  marker.rotation.x = Math.PI / 2;
  marker.visible = false;
  marker.userData.hidden = true;                         // sin torre no hay piso que marcar
  scene.add(marker);

  /* Cielo: muchas más estrellas + banda de la Vía Láctea. Puntos sin textura, un solo dibujo. */
  dust = new THREE.Group();
  dust.add(starField(2600, 0.05, 0.9, false));
  dust.add(starField(5200, 0.035, 0.55, true));
  scene.add(dust);

  resize();
  return true;
}

function resize() {
  if (!renderer) return;
  const r = canvas.getBoundingClientRect();
  const w = Math.max(320, Math.round(r.width)), h = Math.max(240, Math.round(r.width * 9 / 16));
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  draw();
}

/* ---------------------------------------------------------------- clic en un piso */
const ray = new THREE.Raycaster(), pointer = new THREE.Vector2();
function pick(ev) {
  if (!renderer || !tower) return;
  const r = canvas.getBoundingClientRect();
  pointer.x = ((ev.clientX - r.left) / r.width) * 2 - 1;
  pointer.y = -((ev.clientY - r.top) / r.height) * 2 + 1;
  ray.setFromCamera(pointer, camera);
  const hit = ray.intersectObject(tower, false)[0];
  if (hit && hit.instanceId !== undefined && hit.instanceId !== null) selectFloor(hit.instanceId + 1, true);
}
canvas.addEventListener("pointerdown", pick);

/* ---------------------------------------------------------------- voz real (Piper) por BroadcastChannel */
const voice = { env: null, clock: null, filter: L ? new L.ClockFilter() : null,
                follower: L ? new L.Follower() : null, active: false, level: 0 };
let channel = null;
try { if (L && "BroadcastChannel" in window) channel = new BroadcastChannel(L.CHANNEL); } catch (e) { channel = null; }
if (channel) {
  channel.onmessage = (ev) => {
    const msg = ev.data;
    if (!L.valid(msg)) return;
    if (msg.k === "env") { voice.env = msg; if (voice.clock && voice.clock.id !== msg.id) voice.clock = null; }
    else if (msg.k === "clock") {
      if (!voice.clock || voice.clock.id !== msg.id || msg.at >= voice.clock.at) { voice.clock = msg; voice.filter.push(msg); }
    } else if (msg.k === "stop") {
      if (!voice.clock || voice.clock.id === msg.id) voice.clock = null;
    }
  };
  say(voiceStatus, "Núcleo: sigue la voz de Piper que suena en la ventana de conversación.");
} else {
  say(voiceStatus, "Núcleo: este navegador no comparte el audio entre ventanas; el núcleo late en reposo.");
}

function voiceLevel(nowMs, dtMs) {
  const c = voice.clock, env = voice.env;
  if (!c || !env || c.id !== env.id || !voice.follower) {
    if (voice.active) { voice.active = false; say(voiceStatus, "Núcleo: sin audio sonando."); }
    voice.level = voice.follower ? voice.follower.step(0, dtMs) : 0;
    return voice.level;
  }
  const pos = voice.filter.position(nowMs);
  const playing = c.playing && pos <= env.duration + 0.05;
  const target = playing ? L.level(env, pos + L.LOOKAHEAD_S) : 0;
  voice.level = voice.follower.step(target, dtMs);
  if (playing !== voice.active) {
    voice.active = playing;
    say(voiceStatus, playing ? "Núcleo: sigue la amplitud del audio real de Piper (no fonemas)."
                             : "Núcleo: audio en pausa o terminado.");
  }
  return voice.level;
}

/* ---------------------------------------------------------------- animación */
let blinkAt = 2600, blink = 0, motionTime = 0;
function draw() {                                   // un cuadro suelto (tras un clic o un giro de cámara)
  if (renderer && scene && camera) renderer.render(scene, camera);
}

function frame(now) {
  if (!running) return;
  requestAnimationFrame(frame);
  if (document.hidden) return;                      // pestaña oculta: no se dibuja nada
  if (now - last < 1000 / 30) return;               // 30 cuadros por segundo bastan y el Mac 2015 respira
  const dt = last ? now - last : 16;
  last = now;
  if (!paused) motionTime += Math.min(dt, 100) / 1000;
  const t = motionTime;

  const level = voiceLevel(now, dt);
  if (!paused) {
    if (now > blinkAt) { blink = 1; blinkAt = now + 2600 + Math.random() * 4200; }
    blink = Math.max(0, blink - dt / 140);          // parpadeo corto del holograma
    core.rotation.y += 0.0024 * dt / 16;
    core.rotation.x = Math.sin(t * 0.35) * 0.12;
    rings[0].rotation.y = core.rotation.y * -0.6;
    rings[1].rotation.z = t * 0.12;
    rings[2].rotation.z = -t * 0.08;
    rings[3].rotation.z = t * 0.05;
    dust.rotation.y = t * 0.004;
    tower.rotation.y = Math.sin(t * 0.08) * 0.22;
    if (marker) marker.rotation.z = t * 0.6;
  }
  coreMat.uniforms.uTime.value = t;
  coreMat.uniforms.uLevel.value = level;
  coreMat.uniforms.uGlow.value = A.coreGlow(level);
  coreMat.uniforms.uBlink.value = paused ? 0 : Math.min(0.85, blink);
  const breathe = 1 + (paused ? 0 : Math.sin(t * 1.25) * 0.015) + level * 0.1;
  core.scale.setScalar(breathe);
  renderer.render(scene, camera);
}

function start() {
  if (running || !renderer) return;
  running = true; last = 0; clock0 = performance.now();
  requestAnimationFrame(frame);
}
function stop() { running = false; }

document.addEventListener("visibilitychange", () => {
  if (document.hidden) { stop(); say(sceneStatus, "Pausado: la pestaña no está a la vista."); }
  else { start(); say(sceneStatus, paused ? "Animación en pausa." : "Holograma activo · 30 cuadros por segundo."); }
});

/* ---------------------------------------------------------------- controles de la página */
const motionButton = el("toggle-motion");
function paintMotionButton() {
  motionButton.setAttribute("aria-pressed", paused ? "true" : "false");
  motionButton.textContent = paused ? "Reanudar animación" : "Pausar animación";
}
paintMotionButton();                                 // con "Reducir movimiento" el botón ya nace en pausa
motionButton.addEventListener("click", () => {
  paused = !paused;
  paintMotionButton();
  say(sceneStatus, paused ? "Animación en pausa." : "Holograma activo · 30 cuadros por segundo.");
  draw();
});

el("reset-view").addEventListener("click", () => {
  if (!camera) return;
  camera.position.set(0, 0, 8.6);
  if (controls) { controls.target.set(0, 0, 0); controls.update(); }
  draw();
});

/* Datos reales: lee los paneles que ya existen en Jarvis. Nunca inventa cifras por piso. */
const liveHost = el("live-data"), liveStatus = el("live-status");
el("load-real").addEventListener("click", async (ev) => {
  const btn = ev.currentTarget;
  btn.disabled = true;
  say(liveStatus, "Consultando los paneles de Jarvis…");
  liveHost.textContent = "";
  const wanted = ["caja", "cobros"];
  let ok = 0;
  for (const name of wanted) {
    try {
      const res = await fetch("/api/panels/" + name, { credentials: "same-origin", headers: { "Accept": "application/json" } });
      const body = await res.json().catch(() => ({}));
      const box = document.createElement("section");
      const h = document.createElement("h3");
      h.textContent = (body && body.title) ? String(body.title) : name;
      box.appendChild(h);
      if (!res.ok) {
        const p = document.createElement("p");
        p.className = "note demo";
        p.textContent = (body && body.error) ? String(body.error) : "El panel no respondió (" + res.status + ").";
        box.appendChild(p);
      } else {
        ok++;
        const ul = document.createElement("ul");
        for (const line of (body.lines || []).slice(0, 40)) {
          const li = document.createElement("li"); li.textContent = String(line); ul.appendChild(li);
        }
        if (!ul.children.length) { const li = document.createElement("li"); li.textContent = "Sin líneas."; ul.appendChild(li); }
        box.appendChild(ul);
        const when = document.createElement("p");
        when.className = "note";
        when.textContent = (body.demo ? "Panel en modo demostración" : "Datos del servidor") +
                           (body.as_of ? " · al " + String(body.as_of) : "");
        box.appendChild(when);
      }
      liveHost.appendChild(box);
    } catch (e) {
      const p = document.createElement("p");
      p.className = "note demo";
      p.textContent = "No se pudo consultar " + name + ".";
      liveHost.appendChild(p);
    }
  }
  if (ok) {
    realData = true;
    floors = A.emptyFloors();
    buildList(); selectFloor(selected, false); refreshNotice();
    say(liveStatus, "Paneles consultados: " + ok + " de " + wanted.length + ". Los pisos quedan sin cifras propias.");
  } else {
    say(liveStatus, "Sin datos reales: el panel no está conectado. Se mantienen las cifras de demostración.");
  }
  btn.disabled = false;
});

el("back-to-demo").addEventListener("click", () => {
  realData = false;
  floors = A.demoFloors();
  liveHost.textContent = ""; say(liveStatus, "Mostrando la demostración.");
  buildList(); selectFloor(selected, false); refreshNotice();
});

/* ---------------------------------------------------------------- arranque */
buildList();
refreshNotice();
const ready = startScene();
selectFloor(1, false);
if (ready) {
  say(sceneStatus, reduceMotion
    ? "En pausa porque tu Mac tiene \u201cReducir movimiento\u201d. Pulsa \u201cReanudar animaci\u00f3n\u201d para verla."
    : "Holograma activo \u00b7 30 cuadros por segundo.");
  if ("ResizeObserver" in window) new ResizeObserver(resize).observe(canvas);
  else addEventListener("resize", resize);
  start();
}

window.JarvisIronman = {
  telemetry: () => ({ floors: floors.length, selected: selected, real: realData,
                      audioActive: voice.active, level: Math.round(voice.level * 1000) / 1000,
                      running: running, paused: paused }),
  select: (n) => selectFloor(n, false)
};
