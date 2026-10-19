// Jarvis · Mercado. Solo lee /api/panels/practica (dinero simulado). No envía órdenes ni cambia nada.
(function () {
  "use strict";
  var css = getComputedStyle(document.documentElement);
  function tok(n) { return css.getPropertyValue(n).trim(); }
  var C = { series: tok("--series"), glow: tok("--glow"), sell: tok("--sell"), ink: tok("--ink"),
            ink2: tok("--ink-2"), ink3: tok("--ink-3"), surface: tok("--surface"), data: tok("--f-data") };
  var reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  var $ = function (id) { return document.getElementById(id); };
  var money = new Intl.NumberFormat("es-PR", { style: "currency", currency: "USD", minimumFractionDigits: 2 });
  var money0 = new Intl.NumberFormat("es-PR", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  var whenFmt = new Intl.DateTimeFormat("es-PR", { timeZone: "America/Puerto_Rico", day: "numeric", month: "short",
                                                   hour: "2-digit", minute: "2-digit", hour12: false });
  var state = { chart: null, demo: false, pts: [], hover: -1, born: 0 };

  function num(x) { return typeof x === "number" && isFinite(x) ? x : null; }
  function stamp(t) { var d = new Date(t); return isNaN(d) ? null : d; }
  function label(t) { var d = stamp(t); return d ? whenFmt.format(d) : t; }
  function signed(x, f) { return (x > 0 ? "+" : x < 0 ? "−" : "") + f(Math.abs(x)); }

  // ---------- resumen ----------
  function setKpi(id, text, dir) {
    var el = $(id); el.textContent = text;
    if (dir !== undefined) { el.classList.toggle("up", dir > 0); el.classList.toggle("down", dir < 0); }
  }
  function renderSummary(ch) {
    var s = ch.summary || {};
    setKpi("k-equity", s.equity == null ? "—" : money.format(s.equity));
    setKpi("k-pnl", s.pnl_total == null ? "—" :
      signed(s.pnl_total, money.format) + " (" + signed(s.pnl_pct || 0, function (v) { return v.toFixed(2); }) + "%) desde el inicio",
      s.pnl_total || 0);
    setKpi("k-dd", s.max_drawdown_pct == null ? "—" : s.max_drawdown_pct.toFixed(2) + "%");
    setKpi("k-ddnow", s.drawdown_now_pct == null ? "—" : "ahora " + s.drawdown_now_pct.toFixed(2) + "% bajo el máximo");
    setKpi("k-pf", s.profit_factor == null ? "—" : s.profit_factor.toFixed(2));
    setKpi("k-win", s.win_rate_pct == null ? "—" : s.win_rate_pct.toFixed(0) + "%");
    setKpi("k-n", (s.closed_trades || 0) + " operación(es) cerrada(s)");
    setKpi("k-exp", s.expectancy == null ? "—" : signed(s.expectancy, money.format), s.expectancy || 0);
    setKpi("k-fees", s.fees_share_pct == null ? "comisiones: —" : "comisiones: " + s.fees_share_pct.toFixed(0) + "% de lo ganado");
    $("sample").textContent = s.sample_ok ? "" :
      "Muestra chica: con menos de 30 operaciones cerradas todavía no se puede concluir si la estrategia funciona.";
    var p = $("paused");
    p.hidden = !ch.paused;
    p.textContent = ch.paused === "drawdown" ? "ENTRADAS EN PAUSA · CAÍDA MÁXIMA" :
                    ch.paused === "daily_loss" ? "ENTRADAS EN PAUSA · PÉRDIDA DEL DÍA" : "";
  }

  // ---------- curva ----------
  var canvas = $("chart"), ctx = canvas.getContext("2d");
  var M = { l: 74, r: 92, t: 18, b: 34 };
  function niceStep(span, n) {
    var raw = span / Math.max(1, n), mag = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / mag;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * mag;
  }
  function geometry() {
    var r = canvas.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
    if (canvas.width !== Math.round(r.width * dpr) || canvas.height !== Math.round(r.height * dpr)) {
      canvas.width = Math.round(r.width * dpr); canvas.height = Math.round(r.height * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { w: r.width, h: r.height, pw: r.width - M.l - M.r, ph: r.height - M.t - M.b };
  }
  function scales(g) {
    var pts = state.pts, start = num(state.chart.start);
    var lo = Math.min.apply(null, pts.map(function (p) { return p.v; }).concat(start == null ? [] : [start]));
    var hi = Math.max.apply(null, pts.map(function (p) { return p.v; }).concat(start == null ? [] : [start]));
    if (hi - lo < 1) { hi += 1; lo -= 1; }
    var step = niceStep(hi - lo, g.ph > 360 ? 6 : 4);
    lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    var n = pts.length;
    return { lo: lo, hi: hi, step: step,
             x: function (i) { return M.l + (n <= 1 ? g.pw / 2 : g.pw * i / (n - 1)); },
             y: function (v) { return M.t + g.ph * (1 - (v - lo) / (hi - lo)); } };
  }
  function floor(g, t) {                                   // rejilla en perspectiva: decorativa, muy tenue
    var top = M.t + g.ph * 0.62, bottom = M.t + g.ph, cx = M.l + g.pw / 2;
    ctx.save(); ctx.strokeStyle = "rgba(160,180,255,0.07)"; ctx.lineWidth = 1;
    for (var i = -10; i <= 10; i++) {
      ctx.beginPath(); ctx.moveTo(cx + i * g.pw * 0.03, top); ctx.lineTo(cx + i * g.pw * 0.11, bottom); ctx.stroke();
    }
    var shift = reduce ? 0 : (t / 4000) % 1;
    for (var k = 0; k < 8; k++) {
      var f = Math.pow((k + shift) / 8, 2), y = top + (bottom - top) * f;
      ctx.globalAlpha = 0.35 + 0.65 * f;
      ctx.beginPath(); ctx.moveTo(M.l, y); ctx.lineTo(M.l + g.pw, y); ctx.stroke();
    }
    ctx.restore();
  }
  function draw(t) {
    if (!state.pts.length) return;
    var g = geometry(), s = scales(g), pts = state.pts, n = pts.length;
    ctx.clearRect(0, 0, g.w, g.h);
    floor(g, t);
    // ejes y rejilla horizontal (recesivos)
    ctx.font = "11px " + C.data; ctx.textBaseline = "middle"; ctx.textAlign = "right";
    for (var v = s.lo; v <= s.hi + s.step / 2; v += s.step) {
      var y = s.y(v);
      ctx.strokeStyle = "rgba(157,179,184,0.10)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(M.l, y); ctx.lineTo(M.l + g.pw, y); ctx.stroke();
      ctx.fillStyle = C.ink3; ctx.fillText(money0.format(v), M.l - 10, y);
    }
    ctx.textAlign = "center"; ctx.textBaseline = "top";
    var ticks = Math.max(2, Math.min(7, Math.floor(g.pw / 150)));
    for (var k = 0; k < ticks; k++) {
      var i = Math.round((n - 1) * k / (ticks - 1));
      ctx.fillStyle = C.ink3; ctx.fillText(label(pts[i].t), s.x(i), M.t + g.ph + 10);
    }
    // capital inicial
    var start = num(state.chart.start);
    if (start != null) {
      var ys = s.y(start);
      ctx.save(); ctx.setLineDash([4, 5]); ctx.strokeStyle = C.ink3; ctx.beginPath();
      ctx.moveTo(M.l, ys); ctx.lineTo(M.l + g.pw, ys); ctx.stroke(); ctx.restore();
      ctx.fillStyle = C.ink2; ctx.textAlign = "right"; ctx.textBaseline = "bottom";   // dentro del área: nunca se corta
      ctx.fillText("Inicio " + money0.format(start), M.l + g.pw, ys - 4);
    }
    // revelado inicial de la curva
    var grow = reduce ? 1 : Math.min(1, (t - state.born) / 1400);
    // Con UN solo registro, Math.max(1, …) daba last = 1 y el bucle leía pts[1], que no existe.
    // Fallo viejo que no se veía porque el lienzo quedaba fuera de pantalla; la barra lo destapó.
    var last = Math.min(n - 1, Math.max(1, Math.floor((n - 1) * grow)));
    // área
    var grad = ctx.createLinearGradient(0, M.t, 0, M.t + g.ph);
    grad.addColorStop(0, "rgba(47,143,230,0.22)"); grad.addColorStop(1, "rgba(47,143,230,0)");
    ctx.beginPath(); ctx.moveTo(s.x(0), M.t + g.ph);
    for (var a = 0; a <= last; a++) ctx.lineTo(s.x(a), s.y(pts[a].v));
    ctx.lineTo(s.x(last), M.t + g.ph); ctx.closePath(); ctx.fillStyle = grad; ctx.fill();
    // línea con resplandor
    function path() { ctx.beginPath(); for (var b = 0; b <= last; b++) { var X = s.x(b), Y = s.y(pts[b].v); b ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); } }
    ctx.save(); ctx.lineJoin = "round"; ctx.lineCap = "round";
    ctx.shadowColor = "rgba(124,200,255,0.7)"; ctx.shadowBlur = 16; ctx.strokeStyle = "rgba(124,200,255,0.35)"; ctx.lineWidth = 4; path(); ctx.stroke();
    ctx.shadowBlur = 0; ctx.strokeStyle = C.series; ctx.lineWidth = 2; path(); ctx.stroke(); ctx.restore();
    // barrido de escaneo
    if (!reduce && grow >= 1) {
      var sx = M.l + ((t / 7000) % 1) * g.pw, beam = ctx.createLinearGradient(sx - 60, 0, sx, 0);
      beam.addColorStop(0, "rgba(255,255,255,0)"); beam.addColorStop(1, "rgba(255,255,255,0.06)");
      ctx.fillStyle = beam; ctx.fillRect(sx - 60, M.t, 60, g.ph);
    }
    // operaciones
    if (grow >= 1) {
      var times = pts.map(function (p) { var d = stamp(p.t); return d ? d.getTime() : null; });
      (state.chart.trades || []).forEach(function (tr) {
        var d = stamp(tr.t); if (!d) return;
        var idx = 0; for (var q = 0; q < n; q++) { if (times[q] != null && times[q] <= d.getTime()) idx = q; }
        var X = s.x(idx), Y = s.y(pts[idx].v), up = tr.side === "buy";
        ctx.fillStyle = up ? C.series : C.sell; ctx.strokeStyle = C.surface; ctx.lineWidth = 2;
        ctx.beginPath();
        if (up) { ctx.moveTo(X, Y + 7); ctx.lineTo(X - 6, Y + 17); ctx.lineTo(X + 6, Y + 17); }
        else { ctx.moveTo(X, Y - 7); ctx.lineTo(X - 6, Y - 17); ctx.lineTo(X + 6, Y - 17); }
        ctx.closePath(); ctx.stroke(); ctx.fill();
      });
      // último valor: punto destacado y etiqueta directa
      var lx = s.x(n - 1), ly = s.y(pts[n - 1].v), pulse = reduce ? 0 : (t / 1600) % 1;
      ctx.strokeStyle = "rgba(124,200,255," + (0.6 * (1 - pulse)) + ")"; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(lx, ly, 5 + pulse * 14, 0, 6.283); ctx.stroke();
      ctx.fillStyle = C.ink; ctx.strokeStyle = C.series; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(lx, ly, 4.5, 0, 6.283); ctx.fill(); ctx.stroke();
      ctx.fillStyle = C.ink; ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.font = "600 12px " + C.data;
      ctx.fillText(money.format(pts[n - 1].v), lx + 10, ly);
    }
    // cursor
    if (state.hover >= 0 && state.hover < n) {
      var hx = s.x(state.hover), hy = s.y(pts[state.hover].v);
      ctx.strokeStyle = "rgba(230,241,242,0.35)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(hx, M.t); ctx.lineTo(hx, M.t + g.ph); ctx.stroke();
      ctx.fillStyle = C.surface; ctx.strokeStyle = C.glow; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(hx, hy, 5, 0, 6.283); ctx.fill(); ctx.stroke();
    }
  }

  // tooltip con el capital del punto más cercano
  var tip = $("tip");
  function onMove(e) {
    if (!state.pts.length) return;
    var r = canvas.getBoundingClientRect(), g = { pw: r.width - M.l - M.r }, n = state.pts.length;
    var i = Math.round(((e.clientX - r.left - M.l) / g.pw) * (n - 1));
    if (i < 0 || i >= n) { leave(); return; }
    state.hover = i;
    var p = state.pts[i], start = num(state.chart.start), diff = start == null ? null : p.v - start;
    tip.innerHTML = "";
    var a = document.createElement("div"); a.textContent = label(p.t);
    var b = document.createElement("div"); var bb = document.createElement("b"); bb.textContent = money.format(p.v);
    b.appendChild(bb); b.appendChild(document.createTextNode(" capital simulado"));
    tip.appendChild(a); tip.appendChild(b);
    if (diff != null) { var c = document.createElement("div"); c.textContent = signed(diff, money.format) + " contra el inicio"; tip.appendChild(c); }
    tip.hidden = false;
    var x = e.clientX - r.left + 14, y = e.clientY - r.top + 14;
    if (x + tip.offsetWidth > r.width) x -= tip.offsetWidth + 28;
    if (y + tip.offsetHeight > r.height) y -= tip.offsetHeight + 28;
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }
  function leave() { state.hover = -1; tip.hidden = true; }
  canvas.addEventListener("pointermove", onMove);
  canvas.addEventListener("pointerleave", leave);

  // ---------- mercados (anillos de RSI) ----------
  function ring(cv, rsi, t) {
    var dpr = Math.min(2, devicePixelRatio || 1), S = cv.clientWidth || 110;
    if (cv.width !== S * dpr) { cv.width = S * dpr; cv.height = S * dpr; }
    var c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, S, S);
    var cx = S / 2, cy = S / 2, R = S * 0.36, a0 = Math.PI * 0.75, span = Math.PI * 1.5;
    c.lineCap = "round";
    c.strokeStyle = "rgba(157,179,184,0.18)"; c.lineWidth = 5;
    c.beginPath(); c.arc(cx, cy, R, a0, a0 + span); c.stroke();
    [30, 70].forEach(function (z) {                              // zonas de referencia del RSI
      var ang = a0 + span * z / 100;
      c.strokeStyle = C.ink3; c.lineWidth = 1.5; c.beginPath();
      c.moveTo(cx + Math.cos(ang) * (R - 8), cy + Math.sin(ang) * (R - 8));
      c.lineTo(cx + Math.cos(ang) * (R + 8), cy + Math.sin(ang) * (R + 8)); c.stroke();
    });
    if (rsi != null) {
      c.save(); c.shadowColor = "rgba(124,200,255,0.7)"; c.shadowBlur = 10;
      c.strokeStyle = C.series; c.lineWidth = 5;
      c.beginPath(); c.arc(cx, cy, R, a0, a0 + span * rsi / 100); c.stroke(); c.restore();
    }
    var spin = reduce ? 0 : t / 6000;                             // anillo exterior decorativo
    c.strokeStyle = "rgba(124,200,255,0.25)"; c.lineWidth = 1; c.setLineDash([2, 6]);
    c.beginPath(); c.arc(cx, cy, R + 13, spin, spin + Math.PI * 2); c.stroke(); c.setLineDash([]);
    c.fillStyle = C.ink; c.textAlign = "center"; c.textBaseline = "middle";
    c.font = "300 " + Math.round(S * 0.2) + "px " + C.data;
    c.fillText(rsi == null ? "—" : Math.round(rsi), cx, cy - 2);
    c.fillStyle = C.ink3; c.font = Math.round(S * 0.09) + "px " + C.data; c.fillText("RSI", cx, cy + S * 0.16);
  }
  var ringNodes = [];
  function renderRings(products) {
    var host = $("rings"); host.innerHTML = ""; ringNodes = [];
    products.forEach(function (m) {
      var box = document.createElement("article"); box.className = "ring";
      var cv = document.createElement("canvas");
      cv.setAttribute("role", "img");
      cv.setAttribute("aria-label", m.product + ": RSI " + (m.rsi == null ? "sin dato" : Math.round(m.rsi)));
      var meta = document.createElement("div"); meta.className = "meta";
      var name = document.createElement("div"); name.className = "name"; name.textContent = m.product.split("-")[0];
      var trend = document.createElement("div");
      trend.textContent = m.trend ? (m.trend === "alcista" ? "▲ tendencia alcista" : m.trend === "bajista" ? "▼ tendencia bajista" : "◆ lateral") : "sin lectura";
      var price = document.createElement("div");
      price.textContent = m.price == null ? "precio: —" : "precio: " + money.format(m.price) +
        (m.change_24h_pct == null ? "" : " · " + signed(m.change_24h_pct, function (v) { return v.toFixed(2); }) + "% 24 h");
      meta.appendChild(name); meta.appendChild(trend); meta.appendChild(price);
      if (m.open) { var chip = document.createElement("span"); chip.className = "chip"; chip.textContent = "POSICIÓN SIMULADA ABIERTA"; meta.appendChild(chip); }
      box.appendChild(cv); box.appendChild(meta); host.appendChild(box);
      ringNodes.push({ cv: cv, rsi: num(m.rsi) });
    });
  }

  function renderTable() {
    var body = $("table-body"); body.innerHTML = "";
    state.pts.slice(-24).reverse().forEach(function (p) {
      var tr = document.createElement("tr"), a = document.createElement("td"), b = document.createElement("td");
      a.textContent = label(p.t); b.textContent = money.format(p.v); tr.appendChild(a); tr.appendChild(b); body.appendChild(tr);
    });
  }

  // ---------- datos ----------
  function showEmpty(text) {
    var e = $("empty"); e.textContent = text; e.hidden = false;
    state.pts = []; ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
  function load() {
    fetch("/api/panels/practica", { credentials: "same-origin" }).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok, j: j }; });
    }).then(function (res) {
      if (!res.ok) { showEmpty("Sin datos: " + (res.j.error || "no pude leer la práctica") + "."); return; }
      var p = res.j; state.demo = !!p.demo; $("demo").hidden = !state.demo;
      if (!p.chart) { showEmpty("La gráfica solo muestra la práctica con dinero simulado, y no hay datos todavía."); return; }
      var first = !state.chart;
      state.chart = p.chart;
      window.JarvisMercado = { chart: p.chart };            // la barra de arriba lee de aquí
      state.pts = (p.chart.equity || []).filter(function (e) { return num(e.v) != null; });
      if (window.JarvisBarra) window.JarvisBarra.pintar(p.chart);   // la barra: también cuando no hay curva
      $("when").textContent = state.demo ? "datos de ejemplo" : "actualizado " + whenFmt.format(new Date());
      renderSummary(p.chart); renderRings(p.chart.products || []); renderTable();
      if (!state.pts.length) { showEmpty("La práctica todavía no ha corrido. La curva aparece después de la primera revisión."); return; }
      $("empty").hidden = true;
      if (first) state.born = performance.now();
    }).catch(function () { showEmpty("Sin conexión con la app de escritorio."); });
  }

  // ---------- cielo: estrellas, titileo y alguna estrella fugaz (decorativo) ----------
  var sky = $("sky"), sk = sky.getContext("2d"), stars = [], meteor = null;
  function sizeSky() {
    var dpr = Math.min(2, devicePixelRatio || 1);
    sky.width = innerWidth * dpr; sky.height = innerHeight * dpr; sk.setTransform(dpr, 0, 0, dpr, 0, 0);
    var count = Math.round(innerWidth * innerHeight / 3800);
    stars = [];
    for (var i = 0; i < count; i++) {
      var big = Math.random() < 0.06;
      stars.push({ x: Math.random() * innerWidth, y: Math.random() * innerHeight, r: big ? 1.1 + Math.random() * 0.9 : 0.3 + Math.random() * 0.7,
                   p: Math.random() * 6.28, s: 0.4 + Math.random() * 1.6,
                   c: Math.random() < 0.15 ? "200,190,255" : Math.random() < 0.15 ? "255,230,200" : "255,255,255" });
    }
  }
  function drawSky(t) {
    sk.clearRect(0, 0, innerWidth, innerHeight);
    for (var i = 0; i < stars.length; i++) {
      var st = stars[i], a = reduce ? 0.7 : 0.35 + 0.65 * Math.abs(Math.sin(st.p + t / 1000 * st.s * 0.6));
      sk.fillStyle = "rgba(" + st.c + "," + a.toFixed(3) + ")";
      sk.beginPath(); sk.arc(st.x, st.y, st.r, 0, 6.283); sk.fill();
      if (st.r > 1.2) { sk.fillStyle = "rgba(" + st.c + "," + (a * 0.12).toFixed(3) + ")"; sk.beginPath(); sk.arc(st.x, st.y, st.r * 4, 0, 6.283); sk.fill(); }
    }
    if (reduce) return;
    if (!meteor && Math.random() < 0.0015) {
      meteor = { x: Math.random() * innerWidth * 0.8, y: Math.random() * innerHeight * 0.4, born: t };
    }
    if (meteor) {
      var k = (t - meteor.born) / 900;
      if (k > 1) { meteor = null; return; }
      var hx = meteor.x + k * 320, hy = meteor.y + k * 140, tail = sk.createLinearGradient(hx - 120, hy - 52, hx, hy);
      tail.addColorStop(0, "rgba(255,255,255,0)"); tail.addColorStop(1, "rgba(255,255,255," + (0.8 * (1 - k)).toFixed(3) + ")");
      sk.strokeStyle = tail; sk.lineWidth = 1.5; sk.beginPath(); sk.moveTo(hx - 120, hy - 52); sk.lineTo(hx, hy); sk.stroke();
    }
  }
  sizeSky(); addEventListener("resize", sizeSky);

  function frame(t) {
    drawSky(t);
    draw(t);
    ringNodes.forEach(function (r) { ring(r.cv, r.rsi, t); });
    requestAnimationFrame(frame);
  }

  $("toggle-table").addEventListener("click", function () {
    var w = $("table-wrap"), on = w.hidden; w.hidden = !on; this.setAttribute("aria-pressed", String(on));
    this.textContent = on ? "Ocultar tabla" : "Ver tabla";
  });
  $("fullscreen").addEventListener("click", function () {
    var b = this;
    Promise.resolve().then(function () {
      return document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
    }).catch(function () { b.textContent = "No disponible"; setTimeout(function () { b.textContent = "Pantalla completa"; }, 2000); });
  });

  load(); setInterval(load, 60000);
  requestAnimationFrame(frame);
})();
