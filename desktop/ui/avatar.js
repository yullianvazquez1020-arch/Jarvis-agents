const c = document.getElementById("c"), x = c.getContext("2d");
let animationId = 0;
let particleMode = true, paused = matchMedia("(prefers-reduced-motion: reduce)").matches, lastFrame = 0;
let blink = 0, talk = 0, smile = 0, talking = false, t = 0, viseme = "rest";
const shapes = { a: 1, e: 0.7, i: 0.35, o: 0.9, u: 0.6, m: 0.05, rest: 0.15 };

// Voz real: envolvente + reloj que publica la ventana de conversación al reproducir (lipsync.js).
// La frase de prueba del botón sigue siendo aproximada y sin audio, y se rotula así.
const L = window.JarvisLipsync;
const voice = { env: null, clock: null, filter: L ? new L.ClockFilter() : null, follower: L ? new L.Follower() : null,
                active: false, why: "" };
const measure = /[?&]medir=1\b/.test(location.search), syncLog = [];
function wallNow() { return (performance.timeOrigin || Date.now() - performance.now()) + performance.now(); }
function voiceStatus(text) { const el = document.getElementById("voice-status"); if (el && el.textContent !== text) el.textContent = text; }
let channel = null;
try { if (L && "BroadcastChannel" in window) channel = new BroadcastChannel(L.CHANNEL); } catch (e) { channel = null; }
if (channel) {
  channel.onmessage = (ev) => {
    const m = ev.data;
    if (!L.valid(m)) return;
    if (m.k === "env") { voice.env = m; if (voice.clock && voice.clock.id !== m.id) voice.clock = null; }
    else if (m.k === "clock") {
      if (!voice.clock || voice.clock.id !== m.id || m.at >= voice.clock.at) { voice.clock = m; voice.filter.push(m); }
    }
    else if (m.k === "stop") {
      if (!voice.clock || voice.clock.id === m.id) { voice.clock = null; voice.why = m.why || ""; }
    }
    lastFrame = 0;
  };
  voiceStatus("Boca: sin audio sonando. Sigue la voz que suena en la ventana de conversación.");
} else {
  voiceStatus("Boca: este navegador no comparte el audio entre ventanas; solo la frase de prueba aproximada.");
}

/* Nivel de boca según el audio que suena ahora. null = no hay voz real activa. */
function voiceLevel(now, dt) {
  const c = voice.clock, env = voice.env;
  if (!c || !env || c.id !== env.id) {
    if (voice.active) { voice.active = false; voiceStatus("Boca: sin audio sonando." + (voice.why ? " (" + voice.why + ")" : "")); }
    return null;
  }
  const pos = voice.filter.position(now);
  const playing = c.playing && pos <= env.duration + 0.05;
  const target = playing ? L.level(env, pos + L.LOOKAHEAD_S) : 0;
  const value = voice.follower.step(target, dt);
  if (measure && syncLog.length < 20000) syncLog.push([now, pos, target, value, playing ? 1 : 0]);
  if (playing !== voice.active) {
    voice.active = playing;
    voiceStatus(playing ? "Boca: sigue la amplitud del audio real (no fonemas)." : "Boca: audio en pausa o terminado.");
  }
  return playing || value > 0.01 ? value : null;
}
window.JarvisAvatar = { syncLog: () => (measure ? syncLog.slice() : []) };

function hand() {
  const h = window.JarvisHands;
  if (!h) return { x: 0, y: 0, open: 0, seen: false, landmarks: null };
  return h;
}

const HAND_LINKS = [
  [0, 1], [1, 2], [2, 3], [3, 4],
  [0, 5], [5, 6], [6, 7], [7, 8],
  [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16],
  [13, 17], [17, 18], [18, 19], [19, 20],
  [0, 17]
];

function drawHand(h) {
  if (h.landmarks && h.landmarks.length === 21) {
    x.strokeStyle = "#50c878";
    x.lineWidth = 2;
    x.fillStyle = "#ffd700";
    HAND_LINKS.forEach(function (pair) {
      var a = h.landmarks[pair[0]], b = h.landmarks[pair[1]];
      x.beginPath();
      x.moveTo(a.x * 960, a.y * 540);
      x.lineTo(b.x * 960, b.y * 540);
      x.stroke();
    });
    h.landmarks.forEach(function (p) {
      x.beginPath();
      x.arc(p.x * 960, p.y * 540, 3, 0, Math.PI * 2);
      x.fill();
    });
    return;
  }
  const hx = 480 + h.x * 220;
  const hy = 430 + h.y * 40;
  const reach = 18 + h.open * 46;
  x.strokeStyle = "rgba(87,215,255,.35)";
  x.fillStyle = "#57d7ff";
  x.lineWidth = 2;
  x.beginPath();
  x.arc(hx, hy, 10, 0, Math.PI * 2);
  x.stroke();
  for (let f = 0; f < 5; f++) {
    const a = -2.4 + f * 0.55;
    const tx = hx + Math.cos(a) * reach;
    const ty = hy + Math.sin(a) * reach;
    x.beginPath();
    x.moveTo(hx, hy);
    x.lineTo(tx, ty);
    x.stroke();
  }
}

function particles() {
  const h = hand();
  const cx = 480 + h.x * 80;
  const yaw = h.x;
  const depth = 0.72 + (1 - Math.abs(yaw)) * 0.28;
  x.clearRect(0, 0, 960, 540);
  const phase = paused ? 0 : t / 50;
  for (let row = 0; row < 58; row++) {
    const y = 90 + row * 6 + h.y * 24;
    const head = y < 252 + h.y * 24;
    const width = (head ? 72 * Math.sqrt(Math.max(0, 1 - Math.pow((y - 170 - h.y * 24) / 82, 2))) :
      30 + Math.min(175, Math.max(0, (y - 265) * 2.6))) * depth * (0.9 + h.open * 0.2);
    for (let col = 0; col < 24; col++) {
      const a = col / 24 * Math.PI * 2 + Math.sin(phase + row * .08) * .09;
      const px = cx + Math.cos(a) * width;
      const py = y + Math.sin(a) * (head ? 11 : 16);
      x.fillStyle = head && row > 12 && row < 28 ? "#ffd27a" : (h.seen ? "#7cf0c2" : "#57d7ff");
      x.globalAlpha = .22 + (Math.sin(a) + 1) * .32;
      x.beginPath(); x.arc(px, py, 1.1 + (talking ? talk : 0), 0, Math.PI * 2); x.fill();
    }
  }
  x.globalAlpha = 1; x.lineWidth = 1;
  for (let ring = 0; ring < 5; ring++) {
    x.strokeStyle = "rgba(77,194,249,.18)"; x.beginPath();
    x.ellipse(cx, 250 + h.y * 20, (115 + ring * 19) * depth, 150 + ring * 16, yaw * 0.4, 0, Math.PI * 2); x.stroke();
  }
  drawHand(h);
  x.fillStyle = "#83dafa"; x.font = "13px sans-serif";
  x.fillText("PRESENCIA LOCAL · " + (h.seen ? "MANO" : "VISUAL"), 32, 38);
  const mouthY = 205 + h.y * 24;
  x.fillStyle = "#ffd27a"; x.globalAlpha = .85;
  x.beginPath(); x.ellipse(cx, mouthY, 20 * depth, 1.5 + talk * 12, 0, 0, Math.PI * 2); x.fill();
  x.globalAlpha = 1; x.fillStyle = "#83dafa";
  x.fillText(voice.active ? "VOZ REAL · BOCA SEGÚN AMPLITUD" : talking ? "FRASE DE PRUEBA (APROXIMADA, SIN AUDIO)" :
    (h.seen ? "SIGUE LA PALMA" : "ANIMACIÓN AMBIENTE"), 32, 510);
}

let lastVoice = 0;
function loop(time) {
  requestAnimationFrame(loop);
  const speaking = voice.active || (voice.clock && voice.clock.playing);
  // Con voz real se dibuja a la frecuencia de pantalla (no a 25 cuadros) para no sumar hasta 40 ms de retraso.
  // Con movimiento reducido, solo se mueve la boca mientras habla.
  if (document.hidden || time - lastFrame < (speaking ? 0 : 40) || (paused && lastFrame && !hand().seen && !speaking)) return;
  lastFrame = time;
  t += 1;
  blink = Math.max(0, blink - 0.07);
  if (!paused && Math.random() < 0.006) blink = 1;
  const now = wallNow(), real = L && voice.follower ? voiceLevel(now, lastVoice ? now - lastVoice : 16) : null;
  lastVoice = now;
  if (real !== null) { talking = false; animationId++; talk = real; }
  else talk = talking ? (shapes[viseme] || 0.2) : talk * 0.85;
  smile *= 0.98;
  if (particleMode) { particles(); return; }
  const h = hand();
  const cx = 480 + h.x * 70;
  x.clearRect(0, 0, 960, 540);
  x.strokeStyle = "#1c6c90"; x.strokeRect(20, 20, 220, 120); x.strokeRect(720, 20, 220, 120);
  x.strokeRect(20, 400, 220, 110); x.strokeRect(720, 400, 220, 110);
  x.fillStyle = "#7fd4ff"; x.font = "14px sans-serif";
  x.fillText("AVATAR LOCAL", 36, 50);
  x.fillText(h.seen ? "MANO ACTIVA" : ("ANIMACIÓN " + (talking ? "ACTIVA" : "LISTA")), 736, 50);
  x.beginPath(); x.strokeStyle = "#3ec4ff"; x.arc(cx, 250, 150 + (paused ? 0 : Math.sin(t / 20) * 4), 0, Math.PI * 2); x.stroke();
  x.beginPath(); x.arc(cx, 390, 70, 0, Math.PI * 2); x.stroke();
  const g = x.createRadialGradient(cx - 20, 200, 10, cx, 230, 120);
  g.addColorStop(0, "#8fd6ff"); g.addColorStop(1, "#0a3148");
  x.fillStyle = g; x.beginPath(); x.ellipse(cx, 230 + h.y * 16, 78 * (0.8 + (1 - Math.abs(h.x)) * 0.2), 96, h.x * 0.3, 0, Math.PI * 2); x.fill();
  for (const side of [-1, 1]) {
    x.save(); x.translate(cx + side * 28, 214 + h.y * 16); x.scale(1, 1 - blink * 0.92);
    x.fillStyle = "#e9fbff"; x.beginPath(); x.ellipse(0, 0, 10, 7, 0, 0, Math.PI * 2); x.fill();
    x.fillStyle = "#083044"; x.beginPath(); x.arc(h.x * 3, 0, 3, 0, Math.PI * 2); x.fill();
    x.restore();
  }
  x.strokeStyle = "#dff6ff"; x.lineWidth = 2;
  x.beginPath(); x.arc(cx, 268, 16, 0.15 - smile, Math.PI - 0.15 + smile); x.stroke();
  x.fillStyle = "#062033";
  x.beginPath(); x.ellipse(cx, 276, 10, 3 + talk * 10, 0, 0, Math.PI * 2); x.fill();
  const lift = talk * 24 + h.open * 30;
  for (const side of [-1, 1]) {
    const hx = cx + side * 150, hy = 340 - lift;
    x.strokeStyle = "#3ec4ff"; x.lineWidth = 6;
    x.beginPath(); x.moveTo(cx + side * 60, 300); x.quadraticCurveTo(cx + side * 100, hy, hx, hy); x.stroke();
    x.beginPath(); x.arc(hx, hy, 12, 0, Math.PI * 2); x.stroke();
  }
  drawHand(h);
}
requestAnimationFrame(loop);
document.getElementById("speak").onclick = () => {
  const id = ++animationId;
  const text = document.getElementById("phrase").value.slice(0, 1000).toLowerCase();
  const timeline = [];
  let at = 0;
  for (const ch of text) {
    const base = ch.normalize("NFD")[0];
    const boca = "aeiou".includes(base) ? base : "mbp".includes(base) ? "m" : "rest";
    timeline.push({ t: at, boca });
    at += boca === "rest" ? 60 : 140;
  }
  talking = true;
  const start = Date.now();
  const run = () => {
    if (id !== animationId) return;
    const now = Date.now() - start;
    const hit = timeline.filter(item => item.t <= now).pop();
    if (!hit || now > at) { talking = false; viseme = "rest"; return; }
    viseme = hit.boca;
    requestAnimationFrame(run);
  };
  run();
};
document.getElementById("smile").onclick = () => { particleMode = false; lastFrame = 0; document.getElementById("style").textContent = "Ver partículas"; smile = 0.8; };
async function pulso() {
  const status = document.getElementById("status");
  if (location.protocol === "file:") {
    status.textContent = "Vista previa sin conexión. La boca es aproximada; este botón no genera audio.";
    return;
  }
  try {
    const r = await fetch("/api/state", { credentials: "same-origin" });
    if (!r.ok) throw new Error("sin sesión");
    const s = await r.json();
    status.textContent = (s.demo ? "DEMO · " : "") + "Servidor: " + ((s.server || {}).state || "sin comprobar") +
      " · Animación local. La cámara, si la enciendes, no se envía.";
  } catch (e) { status.textContent = "Sin conexión comprobada al escritorio. Animación sin audio."; }
  setTimeout(pulso, 5000);
}
pulso();

function motionLabel() {
  document.getElementById("motion").textContent = paused ? "Activar animación" : "Pausar animación";
  document.getElementById("motion").setAttribute("aria-pressed", String(paused));
}
document.getElementById("style").onclick = () => {
  particleMode = !particleMode; lastFrame = 0;
  document.getElementById("style").textContent = particleMode ? "Ver rostro" : "Ver partículas";
};
document.getElementById("motion").onclick = () => { paused = !paused; lastFrame = 0; motionLabel(); };
motionLabel();
