// HUD v2: barras de trabajos, línea de tiempo, figura del asistente, seguridad y medidores.
// Solo dibuja lo que manda hud.js (evento jarvis:hud) y el estado del servidor (evento jarvis:health).
// No pide nada al servidor y no inventa números: si no hay dato, lo dice.
(function () {
  "use strict";
  var M = window.JarvisMask, $ = function (id) { return document.getElementById(id); };
  var reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  var data = { cards: [], jobs: null, demo: false }, health = null;
  function reveal() { var r = $("hud-reveal"); return !!(r && r.checked); }
  function show(t, sensitive) { return sensitive && !reveal() ? M.mask(t) : String(t == null ? "" : t); }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  // ---------- trabajos: barra = etapa real ----------
  function renderJobs() {
    var ul = $("hx-jobs"); clear(ul);
    if (!Array.isArray(data.jobs)) { ul.appendChild(el("li", "small", "sin dato")); return; }
    if (!data.jobs.length) { ul.appendChild(el("li", "small", "No hay trabajos abiertos.")); return; }
    data.jobs.forEach(function (j) {
      var li = el("li", "hx-job" + (j.overdue ? " late" : ""));
      var head = el("div", "hx-job-head");
      head.appendChild(el("span", "hx-job-title", show(j.title, true)));
      head.appendChild(el("span", "hx-job-pct", (j.overdue ? "⚠ vencido · " : "") + j.stage + " · " + j.progress + "%"));
      var bar = el("div", "hx-bar"); bar.setAttribute("role", "img");
      bar.setAttribute("aria-label", j.stage + ", " + j.progress + " por ciento" + (j.overdue ? ", vencido" : ""));
      var fill = el("span", "hx-fill"); fill.style.width = j.progress + "%";
      for (var k = 1; k < 5; k++) { var tick = el("i", "hx-tick"); tick.style.left = (k * 20) + "%"; bar.appendChild(tick); }
      bar.appendChild(fill); li.appendChild(head); li.appendChild(bar); ul.appendChild(li);
    });
  }

  // ---------- línea de tiempo: 3 días atrás y 11 adelante ----------
  function day(s) { if (!/^\d{4}-\d{2}-\d{2}$/.test(String(s || ""))) return null;
    var p=s.split("-"), t=Date.UTC(+p[0],+p[1]-1,+p[2]), d=new Date(t);
    return d.getUTCFullYear()===+p[0] && d.getUTCMonth()===+p[1]-1 && d.getUTCDate()===+p[2] ? t : null; }
  function renderGantt() {
    var g = $("hx-gantt"); clear(g);
    var now = new Date(), today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
    var from = today - 3 * 864e5, span = 14 * 864e5;
    var scale = el("div", "hx-scale");
    var prevMonth = -1;
    for (var d = 0; d <= 14; d += 2) {
      var dt = new Date(from + d * 864e5), m = dt.getUTCMonth();         // el mes solo cuando cambia: las fechas no se enciman
      var t = el("span", "", m !== prevMonth ? dt.toLocaleDateString("es-PR", { day: "numeric", month: "short", timeZone: "UTC" })
                                             : String(dt.getUTCDate()));
      prevMonth = m;
      t.style.left = (d / 14 * 100) + "%"; scale.appendChild(t);
    }
    g.appendChild(scale);
    if (!Array.isArray(data.jobs)) { g.appendChild(el("p", "small", "sin dato")); return; }
    var rows = data.jobs.filter(function (j) { return day(j.due) !== null; });
    if (!rows.length) { g.appendChild(el("p", "small", "Ningún trabajo abierto tiene fecha de entrega.")); return; }
    rows.forEach(function (j) {
      var row = el("div", "hx-row"), label = el("span", "hx-row-label", show(j.title, true));
      var lane = el("div", "hx-lane"), b = el("span", "hx-span" + (j.overdue ? " late" : ""));
      var s = day(j.start) || day(j.due), e = day(j.due) + 864e5;
      var l = Math.max(0, (s - from) / span), r = Math.min(1, (e - from) / span);
      if (r <= 0 || l >= 1) { b.className += " off"; l = r <= 0 ? 0 : 0.97; r = l + 0.03; }
      b.style.left = (l * 100) + "%"; b.style.width = Math.max(1.5, (r - l) * 100) + "%";
      b.title = j.stage + (j.overdue ? " · vencido" : "") + " · entrega " + j.due;
      lane.appendChild(b); row.appendChild(label); row.appendChild(lane); g.appendChild(row);
    });
    var mark = el("i", "hx-today"); mark.style.left = (3 / 14 * 100) + "%"; mark.title = "Hoy";
    g.appendChild(mark);
  }

  // ---------- asistente y seguridad: solo lo que el servidor dijo ----------
  function dl(id, pairs) {
    var box = $(id); clear(box);
    pairs.forEach(function (p) {
      var w = el("div", p[2] || ""); w.appendChild(el("dt", "", p[0])); w.appendChild(el("dd", "", p[1])); box.appendChild(w);
    });
  }
  var STATE = { ok: "Conectado", demo: "Demostración", slow: "Con retraso", down: "Sin conexión", error: "Error",
                unpaired: "Sin emparejar", unknown: "Sin comprobar" };
  function renderStatus() {
    var h = health || { state: "unknown", info: {} }, i = h.info || {};
    var known = function (v, yes, no) { return v === undefined || v === null ? "sin dato" : v ? yes : no; };
    dl("hx-assist", [
      ["Servidor", STATE[h.state] || "Sin comprobar", h.state === "ok" || h.state === "demo" ? "good" : "watch"],
      ["Versión", i.jarvis_version || "sin dato"],
      ["Datos", i.storage || "sin dato"],
      ["IA", known(i.ai_configured, "configurada", "sin configurar")],
      ["Respuesta", h.latency_ms == null ? "sin dato" : h.latency_ms + " ms"]
    ]);
    var real = i.real_trading_active;
    dl("hx-secure", [
      ["Modo cripto", i.crypto_mode === "practice" ? "Práctica (simulado)" : i.crypto_mode === "real" ? "REAL" : "sin dato",
       i.crypto_mode === "real" ? "alert" : ""],
      ["Trading real", known(real, "⚠ ACTIVO", "Apagado"), real ? "alert" : "good"],
      ["Topes", "$100 por operación · $300 al día"],
      ["Aprobar o enviar", "Solo tú, en tu chat privado"],
      ["Mouse", "Permiso firmado, de un uso"]
    ]);
  }

  // ---------- figura del asistente (silueta genérica, decorativa) ----------
  var fig = $("hx-figure"), fx = fig.getContext("2d");
  function figure(t) {
    var w = fig.clientWidth, h = fig.clientHeight, dpr = Math.min(2, devicePixelRatio || 1);
    if (!w || !h) return;
    if (fig.width !== Math.round(w * dpr)) { fig.width = Math.round(w * dpr); fig.height = Math.round(h * dpr); }
    fx.setTransform(dpr, 0, 0, dpr, 0, 0); fx.clearRect(0, 0, w, h);
    var cx = w / 2, top = h * 0.06, H = h * 0.8, u = H / 8;               // 8 cabezas de alto
    var OUT = [[0.14, 0.98], [0.16, 1.25], [1.0, 1.45], [1.05, 3.1], [0.92, 4.3], [0.78, 4.35], [0.72, 3.2], [0.62, 1.95],
               [0.55, 3.0], [0.6, 4.0], [0.45, 6.2], [0.42, 7.75], [0.1, 7.75], [0.08, 4.4], [0, 4.1]];
    fx.beginPath();                                                        // volumen: silueta rellena y translúcida
    fx.moveTo(cx - OUT[0][0] * u, top + OUT[0][1] * u);
    OUT.forEach(function (p) { fx.lineTo(cx - p[0] * u, top + p[1] * u); });
    OUT.slice().reverse().forEach(function (p) { fx.lineTo(cx + p[0] * u, top + p[1] * u); });
    fx.closePath();
    var body = fx.createLinearGradient(cx - u, 0, cx + u, 0);
    body.addColorStop(0, "rgba(40,120,220,0.10)"); body.addColorStop(0.5, "rgba(120,200,255,0.42)"); body.addColorStop(1, "rgba(40,120,220,0.10)");
    fx.save(); fx.shadowColor = "rgba(63,180,255,0.9)"; fx.shadowBlur = 24; fx.fillStyle = body; fx.fill(); fx.restore();
    var headFill = fx.createRadialGradient(cx, top + u * 0.45, 0, cx, top + u * 0.5, u * 0.5);
    headFill.addColorStop(0, "rgba(160,220,255,0.55)"); headFill.addColorStop(1, "rgba(40,120,220,0.12)");
    fx.fillStyle = headFill; fx.beginPath(); fx.ellipse(cx, top + u * 0.5, u * 0.36, u * 0.48, 0, 0, 6.283); fx.fill();
    var core = fx.createRadialGradient(cx, top + 2.0 * u, 0, cx, top + 2.0 * u, u * 0.5);      // pecho brillante
    core.addColorStop(0, "rgba(230,248,255,0.95)"); core.addColorStop(1, "rgba(63,180,255,0)");
    fx.fillStyle = core; fx.beginPath(); fx.arc(cx, top + 2.0 * u, u * 0.5, 0, 6.283); fx.fill();
    fx.strokeStyle = "rgba(150,215,255,0.85)"; fx.lineWidth = 1.2; fx.lineJoin = "round"; fx.lineCap = "round";
    fx.shadowColor = "rgba(63,180,255,0.8)"; fx.shadowBlur = 8;
    fx.beginPath(); fx.ellipse(cx, top + u * 0.5, u * 0.36, u * 0.48, 0, 0, 6.283); fx.stroke();       // cabeza
    function line(pts) { fx.beginPath(); fx.moveTo(cx + pts[0][0] * u, top + pts[0][1] * u);
      for (var k = 1; k < pts.length; k++) fx.lineTo(cx + pts[k][0] * u, top + pts[k][1] * u); fx.stroke(); }
    line([[-0.14, 0.98], [-0.16, 1.25], [-1.0, 1.45], [-1.05, 3.1], [-0.92, 4.3], [-0.78, 4.35], [-0.72, 3.2], [-0.62, 1.95],
          [-0.55, 3.0], [-0.6, 4.0], [-0.45, 6.2], [-0.42, 7.75], [-0.1, 7.75], [-0.08, 4.4], [0, 4.1]]);       // lado izq.
    line([[0.14, 0.98], [0.16, 1.25], [1.0, 1.45], [1.05, 3.1], [0.92, 4.3], [0.78, 4.35], [0.72, 3.2], [0.62, 1.95],
          [0.55, 3.0], [0.6, 4.0], [0.45, 6.2], [0.42, 7.75], [0.1, 7.75], [0.08, 4.4], [0, 4.1]]);             // lado der.
    fx.shadowBlur = 0; fx.strokeStyle = "rgba(120,200,255,0.18)";
    for (var y = 1.4; y < 7.6; y += 0.35) {                                                  // malla horizontal
      var half = y < 4.1 ? 0.6 + Math.sin((y - 1.4) / 2.7 * Math.PI) * 0.05 : 0.5;
      fx.beginPath(); fx.moveTo(cx - half * u, top + y * u); fx.lineTo(cx + half * u, top + y * u); fx.stroke();
    }
    fx.fillStyle = "rgba(220,242,255,0.95)";                                                   // articulaciones
    [[0, 1.3], [-1.0, 1.45], [1.0, 1.45], [-1.0, 3.0], [1.0, 3.0], [0, 2.4], [0, 4.1], [-0.28, 5.9], [0.28, 5.9]].forEach(function (p) {
      fx.beginPath(); fx.arc(cx + p[0] * u, top + p[1] * u, 2, 0, 6.283); fx.fill(); });
    var sy = top + ((reduce ? 0.4 : (t / 3500) % 1) * 8) * u;                                  // escaneo
    var g = fx.createLinearGradient(0, sy - 14, 0, sy + 2);
    g.addColorStop(0, "rgba(63,180,255,0)"); g.addColorStop(1, "rgba(150,215,255,0.55)");
    fx.fillStyle = g; fx.fillRect(cx - 1.3 * u, sy - 14, 2.6 * u, 16);
    for (var r = 0; r < 3; r++) {                                                              // plataforma
      fx.strokeStyle = "rgba(63,180,255," + (0.6 - r * 0.17) + ")";
      fx.beginPath(); fx.ellipse(cx, top + 7.9 * u, u * (0.9 + r * 0.45), u * (0.16 + r * 0.07), 0, 0, 6.283); fx.stroke();
    }
  }

  // ---------- medidores ----------
  var ATTN = { cobros: 1, vencidos: 2, agenda: 1, stock: 1, mensajes: 1 };
  function pnl(c) { var m = /\(([-+]\d+(?:\.\d+)?)%\)/.exec((c.lines || []).join(" ")); return m ? parseFloat(m[1]) : null; }
  var gaugeNodes = [];
  function renderGauges() {
    var box = $("hx-gauges"); clear(box); gaugeNodes = [];
    data.cards.forEach(function (c) {
      var n = parseFloat(String(c.value).replace(/[^0-9.\-]/g, "")), level, note;
      if (c.id === "practica") {
        var p = pnl(c); level = p == null ? 0 : Math.min(1, Math.abs(p) / 10);
        note = p == null ? "sin dato" : (p >= 0 ? "+" : "") + p.toFixed(2) + "% simulado";
      } else if (ATTN[c.id]) { level = n > 0 ? 1 : 0; note = n > 0 ? (ATTN[c.id] === 2 ? "⚠ por atender ya" : "por atender") : "al día"; }
      else { level = 0.5; note = c.stale ? "⚠ dato viejo" : "informativo"; }
      var b = el("button", "hx-gauge"); b.type = "button";
      var cv = el("canvas"); cv.setAttribute("aria-hidden", "true");
      var txt = el("div", "hx-gauge-text");
      txt.appendChild(el("strong", "", show(c.value, c.sensitive)));
      txt.appendChild(el("span", "", String(c.title).replace(/^DEMO · /, "")));
      txt.appendChild(el("small", "", note));
      b.appendChild(cv); b.appendChild(txt);
      b.addEventListener("click", function () {
        fetch("/api/open", { method: "POST", credentials: "same-origin", headers: { "X-Jarvis-UI": "1", "Content-Type": "application/json" },
                             body: JSON.stringify({ target: c.id }) }).catch(function () {});
      });
      box.appendChild(b);
      gaugeNodes.push({ cv: cv, level: level, alert: ATTN[c.id] === 2 && n > 0 || c.stale, neg: c.id === "practica" && pnl(c) < 0 });
    });
  }
  function gauge(g, t) {
    var S = g.cv.clientWidth || 84, dpr = Math.min(2, devicePixelRatio || 1);
    if (g.cv.width !== S * dpr) { g.cv.width = S * dpr; g.cv.height = S * dpr; }
    var c = g.cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, S, S);
    var cx = S / 2, cy = S / 2, R = S * 0.38;
    c.strokeStyle = "rgba(63,180,255,0.15)"; c.lineWidth = 6; c.beginPath(); c.arc(cx, cy, R, 0, 6.283); c.stroke();
    for (var k = 0; k < 36; k++) {                                         // escala
      var a = k / 36 * 6.283; c.strokeStyle = "rgba(63,180,255," + (k % 3 ? 0.25 : 0.55) + ")"; c.lineWidth = 1;
      c.beginPath(); c.moveTo(cx + Math.cos(a) * (R + 7), cy + Math.sin(a) * (R + 7));
      c.lineTo(cx + Math.cos(a) * (R + (k % 3 ? 10 : 13)), cy + Math.sin(a) * (R + (k % 3 ? 10 : 13))); c.stroke();
    }
    var on = g.alert && !reduce ? 0.55 + 0.45 * Math.abs(Math.sin(t / 400)) : 1;
    c.save(); c.shadowColor = "rgba(63,180,255,0.8)"; c.shadowBlur = 10; c.lineCap = "round";
    c.strokeStyle = g.neg ? "rgba(226,84,106," + on + ")" : "rgba(80,175,255," + on + ")"; c.lineWidth = 6;
    if (g.level > 0) { c.beginPath(); c.arc(cx, cy, R, -Math.PI / 2, -Math.PI / 2 + g.level * 6.283); c.stroke(); }
    c.restore();
    var spin = reduce ? 0 : t / 2500;
    c.strokeStyle = "rgba(160,215,255,0.5)"; c.lineWidth = 1.5;
    c.beginPath(); c.arc(cx, cy, R - 9, spin, spin + 1.2); c.stroke();
    c.beginPath(); c.arc(cx, cy, R - 9, spin + Math.PI, spin + Math.PI + 1.2); c.stroke();
  }

  function renderAll() { renderJobs(); renderGantt(); renderGauges(); renderStatus(); }
  document.addEventListener("jarvis:hud", function (e) {
    var d = e.detail || {}; data = { cards: d.cards || [], jobs: Array.isArray(d.jobs) ? d.jobs : null, demo: !!d.demo }; renderAll();
  });
  document.addEventListener("jarvis:health", function (e) { health = e.detail; renderStatus(); });
  var rv = $("hud-reveal"); if (rv) rv.addEventListener("change", renderAll);
  renderStatus();

  var last = 0;
  function loop(t) {
    if (!document.hidden && t - last > 45) { last = t; figure(t); gaugeNodes.forEach(function (g) { gauge(g, t); }); }
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
})();
