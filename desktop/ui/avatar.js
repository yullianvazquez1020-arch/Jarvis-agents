const c = document.getElementById("c"), x = c.getContext("2d");

  // Match CSS size and Retina density, bounded for the 8 GB Mac.
  function resizeDisplay() {
    if (typeof c.getBoundingClientRect !== 'function') return;
    const width = c.getBoundingClientRect().width;
    if (!(width > 0)) return;
    const density = Math.min(2, window.devicePixelRatio || 1);
    const scale = Math.min(2.5, width * density / 960, Math.sqrt(3200000 / (960 * 540)));
    const bw = Math.round(960 * scale), bh = Math.round(540 * scale);
    if (c.width === bw && c.height === bh) return;
    c.width = bw; c.height = bh;
    x.setTransform(bw / 960, 0, 0, bh / 540, 0, 0);
  }
  resizeDisplay();
  if ('ResizeObserver' in window) new ResizeObserver(() => { resizeDisplay(); lastFrame = 0; }).observe(c);
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
  voiceStatus("Núcleo: sin audio sonando. Sigue la voz que suena en la ventana de conversación.");
} else {
  voiceStatus("Núcleo: este navegador no comparte el audio entre ventanas; solo la frase de prueba aproximada.");
}

/* Nivel de boca según el audio que suena ahora. null = no hay voz real activa. */
function voiceLevel(now, dt) {
  const c = voice.clock, env = voice.env;
  if (!c || !env || c.id !== env.id) {
    if (voice.active) { voice.active = false; voiceStatus("Núcleo: sin audio sonando." + (voice.why ? " (" + voice.why + ")" : "")); }
    return null;
  }
  const pos = voice.filter.position(now);
  const playing = c.playing && pos <= env.duration + 0.05;
  const target = playing ? L.level(env, pos + L.LOOKAHEAD_S) : 0;
  const value = voice.follower.step(target, dt);
  if (measure && syncLog.length < 20000) syncLog.push([now, pos, target, value, playing ? 1 : 0]);
  if (playing !== voice.active) {
    voice.active = playing;
    voiceStatus(playing ? "Núcleo: sigue la amplitud del audio real (no fonemas)." : "Núcleo: audio en pausa o terminado.");
  }
  return playing || value > 0.01 ? value : null;
}
window.JarvisAvatar = { syncLog: () => (measure ? syncLog.slice() : []), telemetry: () => ({audioActive:voice.active, amplitude:voice.active?talk:0}) };

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

// Procedural orbital geometry. Decorative, never biometric readings.
const orbitColors = ['#69e8ff','#b477ff','#ff62b8','#6bf5ad','#ffd77b'];
function strokePath(points,color,width=0.7,alpha=0.65) {
  x.shadowColor=color;x.shadowBlur=width>=.8?3:0;x.strokeStyle=color;x.lineWidth=width;x.globalAlpha=alpha;x.beginPath();
  points.forEach((p,i)=>i?x.lineTo(p[0],p[1]):x.moveTo(p[0],p[1]));x.stroke();x.globalAlpha=1;x.shadowBlur=0;
}
function brain(cx,cy,s,phase) {
  for(let h of [-1,1])for(let k=0;k<25;k++) {
    const pts=[],band=k/24;
    for(let i=0;i<=100;i++) {
      const a=i/100*Math.PI*2;
      const wrinkle=1+.06*Math.sin(a*13+k*.6)+.03*Math.sin(a*23-k);
      pts.push([cx+h*(3+(22+19*Math.cos(a))*Math.sqrt(1-band*.75)*wrinkle)*s,
        cy+(Math.sin(a)*(31-band*13)+Math.sin(a*8+k*.8)*2)*s]);
    }
    strokePath(pts,orbitColors[(k+(h===1?1:3))%5],.65,.5);
  }
  for(let i=0;i<8;i++){const a=phase+i*.9;x.fillStyle=orbitColors[i%5];x.beginPath();x.arc(cx+Math.sin(a)*32*s,cy+Math.cos(a*1.3)*22*s,1.5,0,7);x.fill();}
}
function panel(px,py,w,h,title,subtitle) {
  x.fillStyle='#03121dd9';x.fillRect(px,py,w,h);x.strokeStyle='#205069';x.lineWidth=.6;x.strokeRect(px,py,w,h);
  x.fillStyle='#0c3042';x.fillRect(px,py,w,21);x.fillStyle='#a0e8f2';x.font='9px monospace';x.fillText(title,px+9,py+14);
  x.fillStyle='#9dbad7';x.font='8px monospace';x.fillText(subtitle,px+9,py+h-9);
  x.strokeStyle='#76dce8';x.beginPath();x.moveTo(px,py+7);x.lineTo(px,py);x.lineTo(px+7,py);x.stroke();
}
function particles() {
  const h=hand(),phase=t*.016;
  x.clearRect(0,0,960,540);
  x.fillStyle='#020912';x.fillRect(0,0,960,540);
  const glow=x.createRadialGradient(478,250,10,478,250,300);glow.addColorStop(0,'#102239');glow.addColorStop(1,'#020912');x.fillStyle=glow;x.fillRect(260,0,440,540);
  x.strokeStyle='#153243';x.lineWidth=.35;
  for(let i=0;i<960;i+=24){x.beginPath();x.moveTo(i,0);x.lineTo(i,540);x.stroke();}
  for(let i=0;i<540;i+=24){x.beginPath();x.moveTo(0,i);x.lineTo(960,i);x.stroke();}
  panel(14,14,234,214,'01 / OPTICAL · GESTURE ENGINE',h.seen?'21 PUNTOS · CÁMARA LOCAL':'SIN DETECCIÓN · ACTIVAR MANO');
  panel(14,242,234,194,'02 / NÚCLEO · ÓRBITA', 'IDENTIDAD VISUAL · NO SENSOR');
  panel(710,14,236,141,'03 / CONEXIONES','SOLO ESTADOS COMPROBADOS');
  panel(710,168,236,112,'04 / VOZ · ENVOLVENTE RMS','AMPLITUD DEL AUDIO · NO FONEMAS');
  panel(710,294,236,142,'05 / CORE · NEURAL FIELD','GEOMETRÍA ARTÍSTICA · NO MÉTRICA DE IA');
  panel(14,450,932,76,'06 / ÓRBITA · ACTIVIDAD VISUAL','VOZ Y MANOS LOCALES · SIN DIAGNÓSTICO MÉDICO');
  // Original orbital identity: projected luminous sphere, no humanoid anatomy.
  const cx=478,cy=250,radius=145+talk*12,turn=phase*.16;
  const halo=x.createRadialGradient(cx,cy,5,cx,cy,230);
  halo.addColorStop(0,'#c6ffff38');halo.addColorStop(.4,'#65eeff28');halo.addColorStop(.72,'#bd8aff28');halo.addColorStop(1,'#040c1800');x.fillStyle=halo;x.fillRect(cx-230,cy-230,460,460);
  for(let ring=0;ring<7;ring++){
    x.beginPath();x.ellipse(cx,cy,radius+12+ring*12,radius+12+ring*12,0,0,Math.PI*2);
    x.strokeStyle=['#65eeff','#ffd878','#bd8aff','#54ffbd','#ff69ce'][ring%5]+'b0';x.lineWidth=ring===0?1.5:.7;x.stroke();
  }
  const bands=particleMode?18:8;
  for(let k=0;k<bands;k++){
    const tilt=k*Math.PI/bands+turn,pts=[];
    for(let j=0;j<=90;j++){
      const angle=j*Math.PI/45,xx=Math.cos(angle)*radius,yy=Math.sin(angle)*radius;
      pts.push([cx+xx*Math.cos(tilt)-yy*.28*Math.sin(tilt),cy+xx*Math.sin(tilt)+yy*.28*Math.cos(tilt)]);
    }
    strokePath(pts,['#d6ffff','#65eeff','#ffd878','#bd8aff','#ff69ce'][k%5],.8,.55+talk*.25);
  }
  for(let i=0;i<85;i++){
    const latitude=Math.asin(-1+2*(i+.5)/85),angle=i*2.399963+turn;
    const xx=cx+Math.cos(angle)*Math.cos(latitude)*radius,yy=cy+Math.sin(latitude)*radius;
    x.fillStyle=['#edffff','#65eeff','#ffd878','#bd8aff','#54ffbd'][i%5];x.beginPath();x.arc(xx,yy,1.2+talk,0,7);x.fill();
  }
  const core=x.createRadialGradient(cx,cy,0,cx,cy,30+talk*30);
  core.addColorStop(0,smile?'#fff1bd':'#e8ffff');core.addColorStop(.15,'#bdffffaa');core.addColorStop(1,'#a2ffff00');x.fillStyle=core;x.fillRect(cx-65,cy-65,130,130);
  x.fillStyle='#d9f7ff';x.font='11px monospace';x.fillText('Ó R B I T A',432,29);x.fillStyle='#9dbad7';x.font='8px monospace';x.fillText('NÚCLEO ORBITAL · VISUAL',391,44);
  // Facial detail; mouth uses the exact existing voice follower.
  for(let ring=0;ring<8;ring++){const pts=[];for(let j=0;j<=60;j++){const a=j*Math.PI/30;pts.push([130+Math.cos(a)*(22+ring*6),337+Math.sin(a)*(22+ring*6)]);}strokePath(pts,ring%2?'#ffe2a0':'#aaffff',.6,.5);}
  // Hand inset displays real landmarks only, never fabricated sensor values.
  if(h.landmarks && h.landmarks.length===21){
    const p=h.landmarks.map(p=>[28+(1-p.x)*204,45+p.y*153]);HAND_LINKS.forEach(([a,b])=>strokePath([p[a],p[b]],'#6bf5ad',1.3));
    p.forEach(v=>{x.fillStyle='#ffd77b';x.beginPath();x.arc(v[0],v[1],2.6,0,7);x.fill();});
  }else{x.fillStyle='#426779';x.font='12px monospace';x.fillText(h.running?'SIN MANO DETECTADA':'CÁMARA APAGADA',42,114);x.font='9px monospace';x.fillText(h.running?'Muestra la palma a la cámara':'Activa la mano para ver',30,140);x.fillText('los puntos detectados.',47,155);}
  const rows=[['MANO',h.seen?'DETECTADA':'SIN SEÑAL'],['AUDIO',voice.active?'REPRODUCIENDO':'EN REPOSO'],['PULSO',talking?'PRUEBA SIN AUDIO':voice.active?'RMS REAL':'EN REPOSO'],['DATOS','VER ESTADO INFERIOR']];
  rows.forEach((r,i)=>{x.font='9px monospace';x.fillStyle='#678fa3';x.fillText(r[0],723,54+i*23);x.fillStyle='#91e6da';x.fillText(r[1],782,54+i*23);});
  const env=voice.env,clock=voice.clock;
  x.strokeStyle='#205069';x.beginPath();x.moveTo(721,241);x.lineTo(934,241);x.stroke();
  if(env && clock && env.id===clock.id){
    const pos=voice.filter.position(wallNow()),pts=[];
    for(let i=0;i<106;i++){const amp=L.level(env,Math.max(0,pos-1+i/106));pts.push([722+i*2,242-amp*43]);}strokePath(pts,'#6bf5ad',1.2);
  }else{x.fillStyle='#65899c';x.font='9px monospace';x.fillText('SIN AUDIO REPRODUCIDO',760,230);}
  brain(825,365,1.15,phase);
  for(let k=0;k<5;k++){const pts=[];for(let i=0;i<155;i++){const z=i/154;pts.push([265+z*425,492+Math.sin(z*15+phase+k)* (4+talk*9)*Math.sin(z*Math.PI)]);}strokePath(pts,orbitColors[k],.8,.65);}
  x.fillStyle='#91cadb';x.font='9px monospace';x.fillText(voice.active?'SEÑAL DE VOZ RECIBIDA':talking?'PRUEBA VISUAL SIN AUDIO':'ANIMACIÓN AMBIENTE',728,489);
}

// Do not render the off-screen body while the tower occupies the viewport.
// Camera inference and native pointer control run independently.
let avatarVisible = true;
if ('IntersectionObserver' in window) {
  new IntersectionObserver(entries => {
    avatarVisible = entries[0].isIntersecting;
    if (avatarVisible) { lastFrame = 0; lastVoice = 0; }
  }, {rootMargin: '80px'}).observe(c);
}
let lastVoice = 0;
function loop(time) {
  requestAnimationFrame(loop);
  const speaking = voice.active || (voice.clock && voice.clock.playing);
  // Con voz real se dibuja a la frecuencia de pantalla (no a 25 cuadros) para no sumar hasta 40 ms de retraso.
  // Con movimiento reducido, solo se mueve la boca mientras habla.
  if (document.hidden || !avatarVisible || time - lastFrame < (speaking ? 0 : 40) || (paused && lastFrame && !hand().seen && !speaking && !talking && talk === 0)) return;
  lastFrame = time;
  if (!paused) t += 1;
  if (!paused) blink = Math.max(0, blink - 0.07);
  if (!paused && Math.random() < 0.006) blink = 1;
  const now = wallNow(), real = L && voice.follower ? voiceLevel(now, lastVoice ? now - lastVoice : 16) : null;
  lastVoice = now;
  if (real !== null) { talking = false; animationId++; talk = real; }
  else talk = talking ? (shapes[viseme] || 0.2) : (talk < 0.01 ? 0 : talk * 0.85);
  particles();
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
function viewLabel() {
  document.getElementById("style").textContent = particleMode ? "Ver anillos" : "Ver núcleo";
  document.getElementById("style").setAttribute("aria-pressed", String(!particleMode));
}
document.getElementById("smile").onclick = () => {
  smile = smile ? 0 : 1;
  particleMode = false; lastFrame = 0; viewLabel();
  document.getElementById("smile").textContent = smile ? "Pulso neutro" : "Saludo luminoso";
  document.getElementById("smile").setAttribute("aria-pressed", String(Boolean(smile)));
};
async function pulso() {
  const status = document.getElementById("status");
  if (location.protocol === "file:") {
    status.textContent = "Vista previa sin conexión. El pulso es aproximado; este botón no genera audio.";
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
  document.getElementById("animation-status").textContent = paused
    ? "Animación ambiente pausada. La boca y la detección de mano siguen activas."
    : "Animación ambiente activa. Ver anillos simplifica el núcleo.";
}
document.getElementById("style").onclick = () => {
  particleMode = !particleMode; lastFrame = 0;
  viewLabel();
};
document.getElementById("motion").onclick = () => { paused = !paused; lastFrame = 0; motionLabel(); };
motionLabel();

viewLabel();

// Fullscreen requires an explicit click; Escape remains the browser exit.
const fullDisplay = document.getElementById('display-fullscreen');
if (fullDisplay) fullDisplay.onclick = async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else if (document.documentElement.requestFullscreen) await document.documentElement.requestFullscreen();
    else fullDisplay.textContent = 'Usa pantalla completa del navegador';
  } catch (_) { fullDisplay.textContent = 'No se pudo ampliar la pantalla'; }
};
