
const c = document.getElementById("c"), x = c.getContext("2d");
let animationId = 0;
let blink = 0, talk = 0, smile = 0, talking = false, t = 0, viseme = "rest";
const shapes = { a: 1, e: 0.7, i: 0.35, o: 0.9, u: 0.6, m: 0.05, rest: 0.15 };
function loop() {
  t += 1;
  blink = Math.max(0, blink - 0.07);
  if (Math.random() < 0.006) blink = 1;
  talk = talking ? (shapes[viseme] || 0.2) : talk * 0.85;
  smile *= 0.98;
  x.clearRect(0, 0, 960, 540);
  x.strokeStyle = "#1c6c90"; x.strokeRect(20, 20, 220, 120); x.strokeRect(720, 20, 220, 120);
  x.strokeRect(20, 400, 220, 110); x.strokeRect(720, 400, 220, 110);
  x.fillStyle = "#7fd4ff"; x.font = "14px sans-serif";
  x.fillText("AVATAR LOCAL", 36, 50);
  x.fillText("ANIMACIÓN " + (talking ? "ACTIVA" : "LISTA"), 736, 50);
  x.beginPath(); x.strokeStyle = "#3ec4ff"; x.arc(480, 250, 150 + Math.sin(t / 20) * 4, 0, Math.PI * 2); x.stroke();
  x.beginPath(); x.arc(480, 390, 70, 0, Math.PI * 2); x.stroke();
  const g = x.createRadialGradient(460, 200, 10, 480, 230, 120);
  g.addColorStop(0, "#8fd6ff"); g.addColorStop(1, "#0a3148");
  x.fillStyle = g; x.beginPath(); x.ellipse(480, 230, 78, 96, 0, 0, Math.PI * 2); x.fill();
  for (const side of [-1, 1]) {
    x.save(); x.translate(480 + side * 28, 214); x.scale(1, 1 - blink * 0.92);
    x.fillStyle = "#e9fbff"; x.beginPath(); x.ellipse(0, 0, 10, 7, 0, 0, Math.PI * 2); x.fill();
    x.fillStyle = "#083044"; x.beginPath(); x.arc(0, 0, 3, 0, Math.PI * 2); x.fill();
    x.restore();
  }
  x.strokeStyle = "#dff6ff"; x.lineWidth = 2;
  x.beginPath(); x.arc(480, 268, 16, 0.15 - smile, Math.PI - 0.15 + smile); x.stroke();
  x.fillStyle = "#062033";
  x.beginPath(); x.ellipse(480, 276, 10, 3 + talk * 10, 0, 0, Math.PI * 2); x.fill();
  const lift = talk * 24;
  for (const side of [-1, 1]) {
    const hx = 480 + side * 150, hy = 340 - lift;
    x.strokeStyle = "#3ec4ff"; x.lineWidth = 6;
    x.beginPath(); x.moveTo(480 + side * 60, 300); x.quadraticCurveTo(480 + side * 100, hy, hx, hy); x.stroke();
    x.beginPath(); x.arc(hx, hy, 12, 0, Math.PI * 2); x.stroke();
  }
  requestAnimationFrame(loop);
}
loop();
document.getElementById("speak").onclick = () => {
  const id = ++animationId;
  const text = document.getElementById("phrase").value.slice(0, 1000).toLowerCase();
  const timeline = [];
  let t = 0;
  for (const ch of text) {
    const base = ch.normalize("NFD")[0];
    const boca = "aeiou".includes(base) ? base : "mbp".includes(base) ? "m" : "rest";
    timeline.push({ t, boca });
    t += boca === "rest" ? 60 : 140;
  }
  talking = true;
  const start = Date.now();
  const run = () => {
    if (id !== animationId) return;
    const now = Date.now() - start;
    const hit = timeline.filter(item => item.t <= now).pop();
    if (!hit || now > t) { talking = false; viseme = "rest"; return; }
    viseme = hit.boca;
    requestAnimationFrame(run);
  };
  run();
};
document.getElementById("smile").onclick = () => { smile = 0.8; };
async function pulso() {
  const status = document.getElementById("status");
  if (location.protocol === "file:") {
    status.textContent = "Vista previa sin conexión. La boca es aproximada; este botón no genera audio.";
    return;
  }
  try {
    const r = await fetch("/api/state", {credentials:"same-origin"});
    if (!r.ok) throw new Error("sin sesión");
    const s = await r.json();
    status.textContent = (s.demo ? "DEMO · " : "") + "Servidor: " + ((s.server || {}).state || "sin comprobar") +
      " · Animación aproximada, sin audio ni acceso al micrófono.";
  } catch (e) { status.textContent = "Sin conexión comprobada al escritorio. Animación sin audio."; }
  setTimeout(pulso, 5000);
}
pulso();
