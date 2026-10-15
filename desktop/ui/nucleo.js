/* Núcleo JARVIS (arc reactor) — código original, sin recursos de película. Único avatar del display.
   Núcleo blanco-azul que respira, anillos concéntricos segmentados a distintas velocidades y sentidos,
   anillo triangular interior, resplandor. Late con la voz real de Alan (en-GB, Piper) por BroadcastChannel
   "jarvis-voz" (lipsync.js) y se aviva al escuchar. Sin red, sin TTS propio. */
(function () {
  "use strict";
  var cv = document.getElementById("nucleo"), g = cv.getContext("2d");
  var L = window.JarvisLipsync || null, st = { level: 0, listen: 0, env: null, clock: null, demo: /demo/.test(location.search) };
  var follower = L ? new L.Follower(40, 160) : { v: 0, step: function (t) { this.v += (t - this.v) * 0.2; return this.v; } };
  try {
    if (L && "BroadcastChannel" in window) {
      var bc = new BroadcastChannel(L.CHANNEL);
      bc.onmessage = function (ev) { var m = ev.data; if (!L.valid(m)) return;
        if (m.k === "env") st.env = m; else if (m.k === "clock") st.clock = m; else if (m.k === "stop") st.clock = null; };
    }
    new BroadcastChannel("jarvis-estado").onmessage = function (ev) { st.listening = !!(ev.data && ev.data.escuchando); };
  } catch (e) {}
  window.JarvisNucleo = { escuchar: function (on) { st.listening = !!on; }, nivel: function (v) { st.manual = v; } };
  function voiceTarget(now) {
    if (st.manual != null) return st.manual;
    if (st.demo) { var t = now / 1000, ph = t % 6; st.listening = ph < 1.5;
      return ph > 2 ? Math.max(0, Math.abs(Math.sin(t * 9)) * (0.5 + 0.5 * Math.sin(t * 2.3))) : 0; }
    var c = st.clock, e = st.env; if (!c || !e || c.id !== e.id) return 0;
    var pos = c.t + (Date.now() - c.at) / 1000, i = Math.floor(pos * e.fps);
    return i >= 0 && i < e.values.length ? e.values[i] : 0;
  }
  function fit() { var d = window.devicePixelRatio || 1; cv.width = innerWidth * d; cv.height = innerHeight * d; g.setTransform(d, 0, 0, d, 0, 0); }
  addEventListener("resize", fit); fit();
  var RINGS = [ // radio, grosor, segmentos, hueco, velocidad (rad/s, signo = sentido), alfa
    [0.95, 1.5, 64, 0.35, 0.05, 0.35], [0.86, 6, 24, 0.25, -0.12, 0.55], [0.76, 2, 120, 0.5, 0.2, 0.45],
    [0.68, 9, 10, 0.12, 0.08, 0.75], [0.58, 4, 36, 0.4, -0.3, 0.6], [0.50, 7, 6, 0.2, 0.45, 0.85]];
  var PARTS = []; for (var pi = 0; pi < 140; pi++) PARTS.push({ a: Math.random() * 7, r: 0.2 + Math.random() * 1.1, s: (Math.random() - 0.5) * 0.3, z: Math.random() });
  var scan = document.createElement("canvas"); scan.width = 4; scan.height = 4; var sg = scan.getContext("2d");
  sg.fillStyle = "rgba(0,0,0,0.18)"; sg.fillRect(0, 0, 4, 1); var scanPat = g.createPattern(scan, "repeat");
  function ease(x) { return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; }
  var bolts = [], nextBolt = 0;
  function jag(x0, y0, x1, y1, d, out) {   // rayo procedural: desplazamiento de punto medio con ramas
    if (d <= 0) { out.push([x0, y0, x1, y1]); return; }
    var mx = (x0 + x1) / 2, my = (y0 + y1) / 2, len = Math.hypot(x1 - x0, y1 - y0), o = (Math.random() - 0.5) * len * 0.35;
    mx += -(y1 - y0) / len * o; my += (x1 - x0) / len * o;
    jag(x0, y0, mx, my, d - 1, out); jag(mx, my, x1, y1, d - 1, out);
    if (d > 2 && Math.random() < 0.3) jag(mx, my, mx + (x1 - x0) * 0.4 + o, my + (y1 - y0) * 0.4 - o, d - 2, out);
  }
  var last = performance.now();
  function frame(now) {
    var dt = now - last; last = now;
    var lv = follower.step(Math.min(1, voiceTarget(now)), dt); st.level = lv;
    st.listen += ((st.listening ? 1 : 0) - st.listen) * Math.min(1, dt / 250);
    var w = innerWidth, h = innerHeight, cx = w / 2, cy = h / 2, R = Math.min(w, h) * 0.42, t = now / 1000;
    var breath = 0.5 + 0.5 * Math.sin(t * 1.3), boost = 1 + lv * 0.6 + st.listen * 0.35;
    g.globalCompositeOperation = "source-over"; g.fillStyle = "#01060d"; g.fillRect(0, 0, w, h);
    g.globalCompositeOperation = "lighter";
    var halo = g.createRadialGradient(cx, cy, 0, cx, cy, R * 1.4);
    halo.addColorStop(0, "rgba(120,220,255," + (0.25 + 0.15 * breath + 0.3 * lv) * boost + ")");
    halo.addColorStop(0.4, "rgba(30,140,255,0.12)"); halo.addColorStop(1, "rgba(0,40,90,0)");
    g.fillStyle = halo; g.fillRect(0, 0, w, h);
    g.shadowColor = "rgba(90,200,255,0.9)"; g.shadowBlur = 18 * boost; g.lineCap = "butt";
    RINGS.forEach(function (r, k) {
      var rad = R * r[0] * (1 + lv * 0.03 * (k % 2 ? 1 : -1)), n = r[2], step = Math.PI * 2 / n, rot = t * r[4] * (1 + lv);
      g.lineWidth = r[1]; g.strokeStyle = "rgba(140,215,255," + Math.min(1, r[5] * (0.8 + 0.2 * breath) * boost) + ")";
      for (var i = 0; i < n; i++) { if (k === 2 && i % 7 === 0) continue;
        g.beginPath(); g.arc(cx, cy, rad, rot + i * step, rot + (i + 1 - r[3]) * step); g.stroke(); }
    });
    g.lineWidth = 1; g.strokeStyle = "rgba(170,230,255," + 0.55 * boost + ")";   // marcas finas (ticks)
    [[1.02, 180, -0.03], [0.80, 90, 0.07], [0.62, 60, -0.15]].forEach(function (tk) {
      var rr = R * tk[0], ro = t * tk[2]; g.beginPath();
      for (var i = 0; i < tk[1]; i++) { var a = ro + i * Math.PI * 2 / tk[1], l = i % 5 ? 4 : 10;
        g.moveTo(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr); g.lineTo(cx + Math.cos(a) * (rr + l), cy + Math.sin(a) * (rr + l)); }
      g.stroke(); });
    for (var s2 = 0; s2 < 3; s2++) {   // arcos largos que barren con easing
      var ph = ease((t * (0.15 + s2 * 0.07)) % 1), a1 = ph * Math.PI * 2 * (s2 % 2 ? -1 : 1) + s2 * 2;
      g.lineWidth = 2; g.strokeStyle = "rgba(220,250,255," + 0.8 * boost + ")";
      g.beginPath(); g.arc(cx, cy, R * (1.08 + s2 * 0.05), a1, a1 + 0.6 + s2 * 0.3); g.stroke(); }
    g.shadowBlur = 6; PARTS.forEach(function (p) {   // partículas
      p.a += p.s * dt / 1000 * (1 + lv * 3); var pr = R * p.r * (1 + 0.02 * Math.sin(t + p.z * 9));
      g.fillStyle = "rgba(150,225,255," + (0.25 + 0.5 * p.z) * boost + ")";
      g.fillRect(cx + Math.cos(p.a) * pr, cy + Math.sin(p.a) * pr, 1.5, 1.5); });
    for (var q = 0; q < 2; q++) { // anillo triangular interior (dos triángulos girando en contra)
      var tr = R * (0.40 - q * 0.04), a0 = (q ? -1 : 1) * t * 0.25 - Math.PI / 2;
      g.lineWidth = q ? 3 : 8; g.shadowBlur = 30 * boost; g.strokeStyle = "rgba(215,245,255," + Math.min(1, 0.9 * boost) + ")";
      g.beginPath(); for (var j = 0; j <= 3; j++) { var a = a0 + j * Math.PI * 2 / 3; g[j ? "lineTo" : "moveTo"](cx + Math.cos(a) * tr, cy + Math.sin(a) * tr); }
      g.closePath(); g.stroke(); }
    if (now > nextBolt) {   // nuevos rayos cada 0.3–1.5 s (más seguido y más al hablar)
      bolts = []; var nb = 1 + Math.floor(Math.random() * (2 + lv * 5));
      for (var b = 0; b < nb; b++) { var ba = Math.random() * 7, r0 = R * 0.16, r1 = R * (0.5 + Math.random() * 0.45), seg = [];
        jag(cx + Math.cos(ba) * r0, cy + Math.sin(ba) * r0, cx + Math.cos(ba + (Math.random() - 0.5)) * r1, cy + Math.sin(ba + (Math.random() - 0.5)) * r1, 6, seg);
        bolts.push({ seg: seg, born: now, life: 120 + Math.random() * 260 }); }
      nextBolt = now + (300 + Math.random() * 1200) * (1 - lv * 0.6);
    }
    bolts.forEach(function (bo) { var k = 1 - (now - bo.born) / bo.life; if (k <= 0) return;
      var fl2 = k * (0.6 + 0.4 * Math.random()) * (0.7 + lv);
      [[7, "rgba(60,160,255,"], [3, "rgba(150,220,255,"], [1.2, "rgba(255,255,255,"]].forEach(function (L2) {
        g.lineWidth = L2[0]; g.strokeStyle = L2[1] + Math.min(1, fl2) + ")"; g.shadowBlur = 25; g.beginPath();
        bo.seg.forEach(function (q2) { g.moveTo(q2[0], q2[1]); g.lineTo(q2[2], q2[3]); }); g.stroke(); }); });
    var flick = 0.94 + 0.06 * Math.random();
    [[3.2, "rgba(20,90,255,", 0.18], [2.0, "rgba(40,170,255,", 0.35], [1.2, "rgba(140,230,255,", 0.6]].forEach(function (B) {   // bloom en capas
      var br = R * 0.2 * B[0] * (1 + lv * 0.4), bg = g.createRadialGradient(cx, cy, 0, cx, cy, br);
      bg.addColorStop(0, B[1] + B[2] * boost * flick + ")"); bg.addColorStop(0.5, B[1] + B[2] * 0.35 * flick + ")"); bg.addColorStop(1, B[1] + "0)");
      g.fillStyle = bg; g.beginPath(); g.arc(cx, cy, br, 0, 7); g.fill(); });
    var cr = R * (0.17 + 0.015 * breath + 0.07 * lv + 0.02 * st.listen);
    var core = g.createRadialGradient(cx, cy, 0, cx, cy, cr * 2.2);
    core.addColorStop(0, "rgba(255,255,255,1)"); core.addColorStop(0.15, "rgba(255,250,235," + flick + ")"); core.addColorStop(0.35, "rgba(200,245,255,0.95)");
    core.addColorStop(0.6, "rgba(80,190,255,0.5)"); core.addColorStop(1, "rgba(0,90,200,0)");
    g.shadowBlur = 60 * boost; g.fillStyle = core; g.beginPath(); g.arc(cx, cy, cr * 2.2, 0, 7); g.fill();
    var fl = g.createLinearGradient(cx - R * 1.6, cy, cx + R * 1.6, cy);   // destello de lente horizontal
    fl.addColorStop(0, "rgba(60,170,255,0)"); fl.addColorStop(0.5, "rgba(190,240,255," + (0.35 + 0.4 * lv) * boost + ")"); fl.addColorStop(1, "rgba(60,170,255,0)");
    g.fillStyle = fl; g.fillRect(cx - R * 1.6, cy - 1.5, R * 3.2, 3);
    g.shadowBlur = 0; g.globalCompositeOperation = "source-over";
    g.fillStyle = scanPat; g.fillRect(0, 0, w, h);
    var vig = g.createRadialGradient(cx, cy, R * 0.8, cx, cy, Math.max(w, h) * 0.75);
    vig.addColorStop(0, "rgba(0,0,0,0)"); vig.addColorStop(1, "rgba(0,0,0,0.7)"); g.fillStyle = vig; g.fillRect(0, 0, w, h);
    var lab = document.getElementById("estado");
    if (lab) lab.textContent = lv > 0.05 ? "HABLANDO" : st.listen > 0.5 ? "ESCUCHANDO" : "EN LÍNEA";
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
