/* Orbe holográfico de Jarvis (canvas 2D, sin librerías). Solo lectura: GET /api/state.
   Azul = trabajando; naranja = alerta (servidor caído, error o lento). Ligero: ~160 puntos, 30 fps. */
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
  function frame(now) {
    requestAnimationFrame(frame);
    if (now - last < 33) return; last = now;         // tope 30 fps para la MacBook 2015
    alert += (target - alert) * 0.08; rot += 0.004;
    var W = cv.width, H = cv.height, R = Math.min(W, H) * 0.3;
    var pulse = 1 + Math.sin(now / 420) * 0.04 * (1 + alert);
    var col = [mix(80, 255, alert), mix(200, 150, alert), mix(255, 60, alert)];
    ctx.fillStyle = "rgba(2,6,12,0.35)"; ctx.fillRect(0, 0, W, H);
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
    var g = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, R * 0.6);
    g.addColorStop(0, "rgba(" + col + ",0.35)"); g.addColorStop(1, "rgba(" + col + ",0)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(W / 2, H / 2, R * 0.6, 0, 6.283); ctx.fill();
  }
  function setState(st) {
    var bad = st !== "ok" && st !== "demo";
    target = bad ? 1 : 0;
    label.textContent = "JARVIS · " + (bad ? "ALERTA (" + st + ")" : "EN LÍNEA");
    label.className = bad ? "estado alerta" : "estado";
  }
  function poll() {
    fetch("/api/state", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : { server: { state: "error" } }; })
      .then(function (j) { setState((j.server && j.server.state) || "unknown"); })
      .catch(function () { setState("down"); });
  }
  var q = new URLSearchParams(location.search).get("estado");   // ?estado=alerta para previsualizar
  if (q) setState(q === "alerta" ? "error" : "ok"); else { poll(); setInterval(poll, 10000); }
  requestAnimationFrame(frame);
})();
