// Jarvis · Torre de Aincrad (arte original en canvas, sin imágenes ni marcas ajenas).
// Castillo flotante de piedra en gradas (100 pisos, ancho abajo y estrecho arriba), mar de nubes iluminado
// por ciudades lejanas, cielo nocturno con luna, rejilla HUD tenue y el núcleo Jarvis/Ultron flotando FUERA
// de la torre con haz de proyector. Azul normal; rojo-naranja con aviso (/api/state.mode). Pisos clicables.
// Respeta prefers-reduced-motion. Cifras de negocio: DEMO (ver /api/negocios).
(function () {
  "use strict";
  var cv = document.getElementById("aincrad"), mini = false;
  if (!cv) {                                   // vista compacta (p. ej. /avatar/ironman)
    cv = document.createElement("canvas"); cv.id = "aincrad"; cv.className = "aincrad-mini"; mini = true;
    document.body.appendChild(cv);
  }
  var ctx = cv.getContext("2d");
  var reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  var FLOORS = 100, TIERS = 25, mode = "jarvis", alertK = 0, pisos = [], hover = -1, sel = -1;
  var stars = [], clouds = [], W = 0, H = 0, dpr = 1, geo = null, stone = null;
  var rnd = (function (s) { return function () { s = (s * 16807) % 2147483647; return s / 2147483647; }; })(1020);

  function size() {
    dpr = Math.min(2, devicePixelRatio || 1);
    var r = cv.getBoundingClientRect();
    W = cv.width = Math.max(320, Math.round((r.width || innerWidth) * dpr));
    H = cv.height = Math.max(240, Math.round((r.height || innerHeight) * dpr));
    stars = []; for (var i = 0; i < 260; i++) stars.push([rnd() * W, rnd() * H * 0.62, rnd() * 1.3 + 0.2, rnd() * 6.28]);
    clouds = []; for (i = 0; i < 70; i++) clouds.push([rnd() * W * 1.4 - W * 0.2, H * (0.7 + rnd() * 0.32), W * (0.08 + rnd() * 0.16), rnd()]);
    stone = makeStone(); layout();
  }
  function makeStone() {                       // textura de piedra/cemento generada
    var c = document.createElement("canvas"); c.width = c.height = 128; var g = c.getContext("2d");
    g.fillStyle = "#6d7178"; g.fillRect(0, 0, 128, 128);
    for (var i = 0; i < 2200; i++) { var v = 80 + rnd() * 70 | 0; g.fillStyle = "rgba(" + v + "," + v + "," + (v + 6) + ",0.35)"; g.fillRect(rnd() * 128, rnd() * 128, 1 + rnd() * 2, 1 + rnd() * 2); }
    g.strokeStyle = "rgba(30,32,36,0.35)"; g.lineWidth = 1;
    for (var y = 0; y < 128; y += 16) { g.beginPath(); g.moveTo(0, y); g.lineTo(128, y); g.stroke();
      for (var x = (y / 16) % 2 ? 0 : 16; x < 128; x += 32) { g.beginPath(); g.moveTo(x, y); g.lineTo(x, y + 16); g.stroke(); } }
    return ctx.createPattern(c, "repeat");
  }
  function layout() {
    var cx = mini ? W * 0.42 : W * 0.5, base = H * 0.7, top = H * 0.14, wb = W * (mini ? 0.62 : 0.4), wt = wb * 0.22;
    var tiers = [], th = (base - top) / TIERS;
    for (var t = 0; t < TIERS; t++) {
      var k = t / (TIERS - 1), w = wt + (wb - wt) * Math.pow(1 - k, 1.25) * (1 + 0.05 * Math.sin(k * 9)), y1 = base - t * th;
      tiers.push({ w: w, y1: y1, y0: y1 - th, f0: t * 4 + 1 });
    }
    geo = { cx: cx, base: base, top: top, th: th, tiers: tiers, core: { x: mini ? W * 0.84 : W * 0.82, y: H * 0.34, r: Math.min(W, H) * (mini ? 0.07 : 0.06) } };
  }
  function col(a) { var b = [90, 210, 255], r = [255, 90, 40]; return "rgba(" + b.map(function (v, i) { return Math.round(v + (r[i] - v) * alertK); }) + "," + a + ")"; }
  function warm(a) { var w = [255, 175, 95], r = [255, 80, 40]; return "rgba(" + w.map(function (v, i) { return Math.round(v + (r[i] - v) * alertK); }) + "," + a + ")"; }

  function sky(t) {
    var g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, "#02040b"); g.addColorStop(0.45, "#071533"); g.addColorStop(0.72, "#0c1f45"); g.addColorStop(1, "#050a18");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    var mx = W * 0.86, my = H * 0.12, m = ctx.createRadialGradient(mx, my, 0, mx, my, H * 0.35);
    m.addColorStop(0, "rgba(220,230,255,0.35)"); m.addColorStop(0.08, "rgba(190,205,240,0.12)"); m.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = m; ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "rgba(235,240,255,0.9)"; ctx.beginPath(); ctx.arc(mx, my, H * 0.022, 0, 6.283); ctx.fill();
    stars.forEach(function (s) { var a = 0.35 + 0.35 * Math.sin(s[3] + t * 0.0012); ctx.fillStyle = "rgba(220,230,255," + a.toFixed(2) + ")"; ctx.fillRect(s[0], s[1], s[2] * dpr, s[2] * dpr); });
  }
  function grid() {                              // rejilla HUD en perspectiva cerca del horizonte
    var hy = H * 0.66; ctx.lineWidth = 1;
    for (var i = 0; i <= 14; i++) { var y = hy + Math.pow(i / 14, 2) * H * 0.34; ctx.strokeStyle = col(0.05 + 0.04 * (1 - i / 14)); ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
    for (i = -20; i <= 20; i++) { ctx.strokeStyle = col(0.05); ctx.beginPath(); ctx.moveTo(W / 2 + i * W * 0.02, hy); ctx.lineTo(W / 2 + i * W * 0.2, H); ctx.stroke(); }
  }
  function cloudSea(t) {
    var drift = reduce ? 0 : t * 0.006 * dpr;
    for (var i = 0; i < 9; i++) {                 // luz de ciudades bajo las nubes
      var x = ((i * 0.13 + 0.05) % 1) * W, y = H * (0.86 + (i % 3) * 0.04), r = W * 0.09;
      var g = ctx.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, warm(0.32)); g.addColorStop(1, warm(0));
      ctx.fillStyle = g; ctx.fillRect(x - r, y - r, 2 * r, 2 * r);
    }
    clouds.forEach(function (c) {
      var x = ((c[0] + drift * (0.5 + c[3])) % (W * 1.4) + W * 1.4) % (W * 1.4) - W * 0.2;
      var g = ctx.createRadialGradient(x, c[1], 0, x, c[1], c[2]);
      g.addColorStop(0, "rgba(120,135,165,0.22)"); g.addColorStop(0.6, "rgba(70,85,115,0.12)"); g.addColorStop(1, "rgba(30,40,60,0)");
      ctx.fillStyle = g; ctx.beginPath(); ctx.ellipse(x, c[1], c[2], c[2] * 0.28, 0, 0, 6.283); ctx.fill();
      var u = ctx.createRadialGradient(x, c[1] + c[2] * 0.12, 0, x, c[1] + c[2] * 0.12, c[2] * 0.7);   // borde inferior encendido
      u.addColorStop(0, warm(0.07)); u.addColorStop(1, warm(0));
      ctx.fillStyle = u; ctx.beginPath(); ctx.ellipse(x, c[1] + c[2] * 0.08, c[2] * 0.8, c[2] * 0.16, 0, 0, 6.283); ctx.fill();
    });
  }
  function tower(t) {
    var g = geo, cx = g.cx;
    ctx.save();                                   // base rocosa invertida que cuelga en el aire
    ctx.beginPath(); ctx.moveTo(cx - g.tiers[0].w / 2, g.base);
    var n = 14; for (var i = 0; i <= n; i++) { var k = i / n, x = cx - g.tiers[0].w / 2 + k * g.tiers[0].w; ctx.lineTo(x, g.base + H * (0.03 + 0.11 * Math.sin(k * Math.PI)) * (0.7 + 0.3 * ((i * 7) % 3) / 2)); }
    ctx.closePath(); ctx.fillStyle = stone; ctx.fill(); ctx.fillStyle = "rgba(10,14,24,0.55)"; ctx.fill(); ctx.restore();
    g.tiers.forEach(function (tr, ti) {                                    // gradas cilíndricas (vista algo desde arriba)
      var x0 = cx - tr.w / 2, h = tr.y1 - tr.y0, ry = tr.w * 0.06, body = tr.w * 0.94;
      ctx.save(); ctx.beginPath();                                           // cuerpo con fondo elíptico
      ctx.moveTo(cx - body / 2, tr.y0); ctx.lineTo(cx - body / 2, tr.y1);
      ctx.ellipse(cx, tr.y1, body / 2, ry, 0, Math.PI, 0, true); ctx.lineTo(cx + body / 2, tr.y0); ctx.closePath();
      ctx.fillStyle = stone; ctx.fill();
      var sh = ctx.createLinearGradient(cx - body / 2, 0, cx + body / 2, 0);
      sh.addColorStop(0, "rgba(3,6,14,0.78)"); sh.addColorStop(0.35, "rgba(8,12,24,0.35)"); sh.addColorStop(0.75, "rgba(150,165,200,0.06)"); sh.addColorStop(1, "rgba(3,6,14,0.55)");
      ctx.fillStyle = sh; ctx.fill(); ctx.clip();
      var cols = Math.max(5, Math.round(body / (12 * dpr)));
      for (var c = 0; c < cols; c++) {                                       // ventanas en arcos, siguen la curva
        var u = (c + 0.5) / cols, ang = Math.acos(1 - 2 * u), s2 = (ti * 31 + c * 17) % 9; if (s2 > 3) continue;
        var wx = cx - Math.cos(ang) * body / 2, fore = Math.sin(ang), flick = reduce ? 1 : 0.8 + 0.2 * Math.sin(t * 0.002 + s2 * 3 + c);
        ctx.fillStyle = warm((0.25 + 0.5 * fore * flick).toFixed(2));
        ctx.fillRect(wx, tr.y0 + h * 0.3 + ry * fore * 0.6, Math.max(1.3, dpr * 1.8 * fore), Math.max(1.5, h * 0.32));
      }
      ctx.restore();
      ctx.beginPath(); ctx.ellipse(cx, tr.y1, tr.w / 2, ry * 1.05, 0, 0, Math.PI); ctx.lineWidth = Math.max(1.5, h * 0.14);   // reborde del piso
      ctx.strokeStyle = "rgba(150,156,168,0.75)"; ctx.stroke();
      ctx.beginPath(); ctx.ellipse(cx, tr.y1 + h * 0.1, tr.w / 2, ry * 1.05, 0, 0.15, Math.PI - 0.15); ctx.lineWidth = Math.max(1, h * 0.08);
      ctx.strokeStyle = "rgba(0,0,0,0.5)"; ctx.stroke();
      if (ti < TIERS - 1) {                                                  // terraza superior visible
        var nb = g.tiers[ti + 1].w * 0.94;
        ctx.beginPath(); ctx.ellipse(cx, tr.y0, body / 2, ry, 0, 0, 6.283); ctx.fillStyle = "rgba(95,100,110,0.9)"; ctx.fill();
        ctx.beginPath(); ctx.ellipse(cx, tr.y0, nb / 2, ry * nb / body, 0, 0, 6.283); ctx.fillStyle = "rgba(20,24,34,0.6)"; ctx.fill();
      }
      for (var f = 0; f < 4; f++) {                                         // resaltado de pisos (negocios / selección)
        var fl = tr.f0 + f, p = pisos[fl - 1], fy = tr.y1 - (f + 1) * h / 4;
        var named = p && !/^libre-/.test(p.id);
        if (named || fl === hover || fl === sel) {
          ctx.strokeStyle = fl === sel ? col(0.95) : fl === hover ? col(0.75) : col(0.5); ctx.lineWidth = (fl === sel ? 2 : 1) * dpr;
          ctx.beginPath(); ctx.ellipse(cx, fy + h / 4, body / 2, ry, 0, 0, Math.PI); ctx.stroke();
        }
      }
    });
    var top = g.tiers[TIERS - 1];                                           // aguja superior
    ctx.fillStyle = stone; ctx.beginPath(); ctx.moveTo(cx - top.w * 0.3, top.y0); ctx.lineTo(cx, top.y0 - H * 0.05); ctx.lineTo(cx + top.w * 0.3, top.y0); ctx.fill();
  }
  function floorAt(px, py) {
    var g = geo; if (!g) return -1;
    for (var i = 0; i < g.tiers.length; i++) { var tr = g.tiers[i];
      if (py >= tr.y0 && py < tr.y1 && Math.abs(px - g.cx) <= tr.w / 2) return tr.f0 + Math.min(3, Math.floor((tr.y1 - py) / ((tr.y1 - tr.y0) / 4))); }
    return -1;
  }
  function core(t) {                                                         // núcleo fuera de la torre
    var c = geo.core, spin = reduce ? 0 : t * 0.0008 * (1 + 2 * alertK), R = c.r * (1 + (reduce ? 0 : 0.04 * Math.sin(t / 380)));
    var px = c.x, py = H * 0.7;                                              // emisor flotante sobre las nubes
    var beam = ctx.createLinearGradient(px, py, px, c.y);
    beam.addColorStop(0, col(0.35)); beam.addColorStop(1, col(0.02));
    ctx.fillStyle = beam; ctx.beginPath(); ctx.moveTo(px - c.r * 0.12, py); ctx.lineTo(px + c.r * 0.12, py); ctx.lineTo(px + c.r * 1.3, c.y); ctx.lineTo(px - c.r * 1.3, c.y); ctx.closePath(); ctx.fill();
    ctx.fillStyle = "rgba(60,66,78,0.95)"; ctx.beginPath(); ctx.ellipse(px, py, c.r * 0.5, c.r * 0.12, 0, 0, 6.283); ctx.fill();
    ctx.fillStyle = col(0.8); ctx.beginPath(); ctx.ellipse(px, py - 1, c.r * 0.18, c.r * 0.04, 0, 0, 6.283); ctx.fill();
    var g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, R * 2.4); g.addColorStop(0, col(0.55)); g.addColorStop(0.35, col(0.18)); g.addColorStop(1, col(0));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(c.x, c.y, R * 2.4, 0, 6.283); ctx.fill();
    ctx.lineWidth = 1.5 * dpr;
    if (alertK < 0.5) {
      [[1.0, 6, 1], [1.35, 18, -0.7], [1.7, 3, 0.4]].forEach(function (r, n) { ctx.strokeStyle = col(0.75 - n * 0.18);
        for (var s = 0; s < r[1]; s++) { var a0 = spin * r[2] + s * 6.283 / r[1]; ctx.beginPath(); ctx.arc(c.x, c.y, R * r[0], a0, a0 + 6.283 / r[1] * 0.72); ctx.stroke(); } });
    } else {
      [[1.1, 9, 1.6], [1.6, 14, -1.2]].forEach(function (r, n) { ctx.strokeStyle = col(0.85 - n * 0.2); ctx.beginPath();
        for (var s = 0; s <= r[1] * 2; s++) { var a = spin * r[2] + s * Math.PI / r[1], q = R * r[0] * (s % 2 ? 1.1 : 0.9); var x = c.x + Math.cos(a) * q, y = c.y + Math.sin(a) * q; s ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
        ctx.closePath(); ctx.stroke(); });
    }
    ctx.fillStyle = col(0.9); ctx.beginPath(); ctx.arc(c.x, c.y, R * 0.42, 0, 6.283); ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,0.75)"; ctx.beginPath(); ctx.arc(c.x, c.y, R * 0.16, 0, 6.283); ctx.fill();
    ctx.font = (11 * dpr) + "px Menlo, monospace"; ctx.textAlign = "center"; ctx.fillStyle = col(0.9);
    ctx.fillText(alertK > 0.5 ? "ULTRON · AVISO" : "JARVIS · AL MANDO", c.x, c.y + R * 2.1);
  }
  function label() {
    var f = sel > 0 ? sel : hover; if (f < 1 || !pisos[f - 1]) return;
    var p = pisos[f - 1], txt = "Piso " + p.piso + " · " + p.nombre + " · " + p.estado;
    ctx.font = (13 * dpr) + "px system-ui, sans-serif"; ctx.textAlign = "left";
    var w = ctx.measureText(txt).width + 20 * dpr, x = geo.cx - w / 2, y = H * 0.04;
    ctx.fillStyle = "rgba(4,14,30,0.8)"; ctx.fillRect(x, y, w, 26 * dpr); ctx.strokeStyle = col(0.6); ctx.strokeRect(x, y, w, 26 * dpr);
    ctx.fillStyle = "#e6f4ff"; ctx.fillText(txt, x + 10 * dpr, y + 17 * dpr);
  }
  var last = 0;
  function frame(t) {
    requestAnimationFrame(frame);
    if (t - last < 40) return; last = t;
    alertK += ((mode === "ultron" ? 1 : 0) - alertK) * (reduce ? 1 : 0.08);
    sky(t); grid(); cloudSea(t); tower(t); core(t); label();
  }
  cv.addEventListener("mousemove", function (e) { var r = cv.getBoundingClientRect(); hover = floorAt((e.clientX - r.left) * dpr, (e.clientY - r.top) * dpr); cv.style.cursor = hover > 0 ? "pointer" : ""; });
  cv.addEventListener("click", function (e) {
    var r = cv.getBoundingClientRect(), f = floorAt((e.clientX - r.left) * dpr, (e.clientY - r.top) * dpr);
    if (f > 0) { sel = f; dispatchEvent(new CustomEvent("jarvis-piso", { detail: f })); }
  });
  addEventListener("jarvis-piso-lista", function (e) { sel = e.detail; });
  addEventListener("resize", size);
  window.JarvisAincradScene = { floorAt: floorAt, setMode: function (m) { mode = m; }, setPisos: function (p) { pisos = p; } };
  function poll() {
    fetch("/api/state", { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (j) { mode = j.mode || "jarvis"; }).catch(function () {});
  }
  var q = new URLSearchParams(location.search).get("modo");
  if (q) mode = q === "ultron" ? "ultron" : "jarvis"; else { poll(); setInterval(poll, 10000); }
  fetch("/api/negocios", { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (t) { pisos = t.pisos || []; }).catch(function () {});
  size(); requestAnimationFrame(frame);
})();
