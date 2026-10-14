/* Núcleo holográfico de Jarvis (canvas 2D, sin librerías, arte original). Solo lectura: GET /api/state.
   Modo JARVIS (normal): cian/azul, esfera de puntos y anillos HUD concéntricos que giran.
   Modo ULTRON (aviso reciente o servidor caído): rojo/naranja, anillos angulares en dientes de sierra,
   triángulos y pulso agresivo. ?estado=alerta | ?modo=ultron para previsualizar. ~30 fps. */
(function () {
  "use strict";
  var cv = document.getElementById("orbe"), ctx = cv.getContext("2d");
  var label = document.getElementById("orbe-estado");
  var N = 160, LINK = 0.42, pts = [], i;
  for (i = 0; i < N; i++) {                         // esfera de Fibonacci: reparto uniforme
    var y = 1 - (i / (N - 1)) * 2, r = Math.sqrt(1 - y * y), t = i * 2.39996;
    pts.push([Math.cos(t) * r, y, Math.sin(t) * r]);
  }
  var alert = 0, target = 0, rot = 0, last = 0;
  function size() { cv.width = innerWidth * (devicePixelRatio || 1); cv.height = innerHeight * (devicePixelRatio || 1); }
  addEventListener("resize", size); size();
  function mix(a, b, k) { return Math.round(a + (b - a) * k); }
  function ringJarvis(cx, cy, R, now, col, k) {      // arcos segmentados tipo HUD
    var rings = [[1.25, 6, 0.0006, 2], [1.42, 24, -0.0004, 1], [1.6, 3, 0.0003, 3], [1.78, 60, -0.0002, 1]];
    rings.forEach(function (g, n) {
      var rr = R * g[0], seg = g[1], sp = now * g[2], gap = 0.35 / Math.max(1, seg / 6);
      ctx.lineWidth = g[3] * (devicePixelRatio || 1);
      ctx.strokeStyle = "rgba(" + col + "," + (0.55 - n * 0.1) * k + ")";
      for (var s = 0; s < seg; s++) {
        var a0 = sp + s * 6.283 / seg, a1 = a0 + 6.283 / seg - gap;
        ctx.beginPath(); ctx.arc(cx, cy, rr, a0, a1); ctx.stroke();
      }
    });
    ctx.strokeStyle = "rgba(" + col + "," + 0.25 * k + ")"; ctx.lineWidth = 1;
    for (var m = 0; m < 72; m++) {                    // marcas de escala
      var a = m * 6.283 / 72 - now * 0.0001, l = m % 6 ? 6 : 14;
      ctx.beginPath(); ctx.moveTo(cx + Math.cos(a) * R * 1.9, cy + Math.sin(a) * R * 1.9);
      ctx.lineTo(cx + Math.cos(a) * (R * 1.9 + l), cy + Math.sin(a) * (R * 1.9 + l)); ctx.stroke();
    }
  }
  function ringUltron(cx, cy, R, now, col, k) {      // anillos angulares, dientes de sierra
    [[1.3, 18, 0.0012], [1.6, 9, -0.0018], [1.9, 36, 0.0008]].forEach(function (g, n) {
      var rr = R * g[0], seg = g[1], sp = now * g[2];
      ctx.lineWidth = (3 - n) * (devicePixelRatio || 1);
      ctx.strokeStyle = "rgba(" + col + "," + (0.75 - n * 0.15) * k + ")";
      ctx.beginPath();
      for (var s = 0; s <= seg * 2; s++) {
        var a = sp + s * 3.1416 / seg, q = s % 2 ? rr * 1.07 : rr * 0.93;
        var x = cx + Math.cos(a) * q, y = cy + Math.sin(a) * q;
        if (s) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      }
      ctx.closePath(); ctx.stroke();
    });
    ctx.fillStyle = "rgba(" + col + "," + 0.35 * k + ")";
    for (var tIdx = 0; tIdx < 3; tIdx++) {            // tres cuchillas triangulares
      var a = now * -0.0015 + tIdx * 2.094;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a) * R * 2.15, cy + Math.sin(a) * R * 2.15);
      ctx.lineTo(cx + Math.cos(a + 0.12) * R * 1.75, cy + Math.sin(a + 0.12) * R * 1.75);
      ctx.lineTo(cx + Math.cos(a - 0.12) * R * 1.75, cy + Math.sin(a - 0.12) * R * 1.75);
      ctx.closePath(); ctx.fill();
    }
  }
  function frame(now) {
    requestAnimationFrame(frame);
    if (now - last < 33) return; last = now;         // tope 30 fps para la MacBook 2015
    alert += (target - alert) * 0.08; rot += 0.004 + 0.01 * alert;
    var W = cv.width, H = cv.height, R = Math.min(W, H) * 0.2;
    var pulse = 1 + Math.sin(now / (420 - 260 * alert)) * 0.04 * (1 + 2 * alert);
    var col = [mix(90, 255, alert), mix(220, 70, alert), mix(255, 30, alert)];   // cian → rojo/naranja
    ctx.fillStyle = "rgba(" + (alert > 0.5 ? "12,2,2" : "2,6,12") + ",0.35)"; ctx.fillRect(0, 0, W, H);
    var c = Math.cos(rot), s = Math.sin(rot), P = [];
    for (i = 0; i < N; i++) {
      var p = pts[i], x = p[0] * c - p[2] * s, z = p[0] * s + p[2] * c;
      P.push([W / 2 + x * R * pulse, H / 2 + p[1] * R * pulse, z, x, p[1]]);
    }
    ctx.lineWidth = 1;
    for (i = 0; i < N; i++) for (var j = i + 1; j < N; j++) {
      var dx = P[i][3] - P[j][3], dy = P[i][4] - P[j][4], dz = P[i][2] - P[j][2];
      var d = dx * dx + dy * dy + dz * dz;
      if (d < LINK * LINK) {
        var a = (1 - d / (LINK * LINK)) * (0.25 + 0.2 * (P[i][2] + 1));
        ctx.strokeStyle = "rgba(" + col + "," + a.toFixed(3) + ")";
        ctx.beginPath(); ctx.moveTo(P[i][0], P[i][1]); ctx.lineTo(P[j][0], P[j][1]); ctx.stroke();
      }
    }
    for (i = 0; i < N; i++) {
      var k = (P[i][2] + 1) / 2;
      ctx.fillStyle = "rgba(" + col + "," + (0.3 + 0.7 * k).toFixed(3) + ")";
      ctx.beginPath(); ctx.arc(P[i][0], P[i][1], 1 + 2.2 * k, 0, 6.283); ctx.fill();
    }
    if (alert < 0.98) ringJarvis(W / 2, H / 2, R, now, col, 1 - alert);
    if (alert > 0.02) ringUltron(W / 2, H / 2, R, now, col, alert);
    var g = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, R * 0.6);
    g.addColorStop(0, "rgba(" + col + ",0.45)"); g.addColorStop(1, "rgba(" + col + ",0)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(W / 2, H / 2, R * 0.6, 0, 6.283); ctx.fill();
  }
  function setMode(mode, why) {
    var ultron = mode === "ultron";
    target = ultron ? 1 : 0;
    document.body.className = ultron ? "ultron" : "jarvis";
    label.textContent = ultron ? "ULTRON · AVISO" + (why ? " · " + why : "") : "JARVIS · EN LÍNEA";
    label.className = ultron ? "estado alerta" : "estado";
  }
  function poll() {
    fetch("/api/state", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : { mode: "ultron", server: { state: "error" } }; })
      .then(function (j) { setMode(j.mode || "jarvis", j.alert ? j.alert.text : (j.mode === "ultron" && j.server ? j.server.state : "")); })
      .catch(function () { setMode("ultron", "sin conexión"); });
  }
  var qs = new URLSearchParams(location.search), q = qs.get("modo") || qs.get("estado");
  if (q) setMode(q === "alerta" || q === "ultron" ? "ultron" : "jarvis"); else { poll(); setInterval(poll, 10000); }
  requestAnimationFrame(frame);
})();
