/* Paneles HUD de negocio alrededor del núcleo. Solo datos reales de /api/paneles-negocio.
   Refresca cada 45 s FUERA del bucle de render; solo anima ~0.9 s tras cada cambio. Sin librerías. */
(function () {
  "use strict";
  var REFRESCO = 45000, ANIM = 900, root, data = null, prev = {}, t0 = 0, foco = null, manual = false, raf = 0;
  function api(p) { return fetch(p, { credentials: "same-origin", headers: { "X-Jarvis-UI": "1" } }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); }
  function el(tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
  function money(n, u) { return u === "USD" || !u ? "$" + Math.round(n).toLocaleString("en-US") : Math.round(n).toLocaleString("en-US") + " " + u; }
  function hora(s) { var d = new Date(s); return isNaN(d) ? "" : d.toLocaleTimeString("es-PR", { timeZone: "America/Puerto_Rico", hour: "2-digit", minute: "2-digit" }); }

  function chart(cv, serie, k, bars) {
    var dpr = Math.min(3, window.devicePixelRatio || 1);
    var w = cv.clientWidth || 300, h = cv.clientHeight || 64, c = cv.getContext("2d");
    var pw = Math.round(w * dpr), ph = Math.round(h * dpr);
    if (cv.width !== pw) cv.width = pw;
    if (cv.height !== ph) cv.height = ph;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.shadowBlur = 0;
    c.clearRect(0, 0, w, h);
    if (!serie.length) { c.fillStyle = "#ffb35c"; c.font = "12px Helvetica Neue,Arial"; c.fillText("No data", 4, 32); return; }
    var mx = Math.max.apply(null, serie.concat([1])), mn = bars ? 0 : Math.min.apply(null, serie), n = serie.length;
    var vis = n;
    c.strokeStyle = "rgba(80,200,255,.18)"; c.lineWidth = 1;
    for (var g = 1; g < 4; g++) { c.beginPath(); c.moveTo(0, h * g / 4); c.lineTo(w, h * g / 4); c.stroke(); }
    if (bars) {
      var bw = w / n;
      for (var i = 0; i < vis; i++) { var bh = (h - 6) * serie[i] / mx * k; c.fillStyle = serie[i] ? "#4cc8ff" : "rgba(80,200,255,.15)"; c.fillRect(i * bw + 1, h - Math.max(2, bh), bw - 2, Math.max(2, bh)); }
    } else {
      c.strokeStyle = "#7fe6ff"; c.lineWidth = 1.5; c.shadowColor = "#3cb4ff"; c.shadowBlur = 4; c.save(); c.beginPath(); c.rect(0, 0, w * k, h); c.clip(); c.beginPath();
      for (var j = 0; j < vis; j++) { var x = n > 1 ? w * j / (n - 1) : 0, y = h - 6 - (h - 12) * (serie[j] - mn) / ((mx - mn) || 1); j ? c.lineTo(x, y) : c.moveTo(x, y); }
      c.stroke(); c.restore();
    }
  }
  function panelNegocio(n) {
    var p = el("div", "pn"); p.dataset.id = n.id;
    var t = el("div", "t"); t.appendChild(el("span", "", n.nombre.toUpperCase()));
    t.appendChild(el("span", "", n.progreso != null ? Math.round(n.progreso * 100) + "%" : "")); p.appendChild(t);
    var sd = !n.datos; p.appendChild(el("div", "e" + (sd ? " sd" : ""), sd ? n.estado + " — fuente: " + n.fuente : n.estado + (n.as_of ? " · " + n.as_of.slice(0, 10) : "")));
    if (n.progreso != null) { var b = el("div", "bar"), i = el("i"); i.dataset.p = n.progreso; i.dataset.d = prev[n.id] || 0; b.appendChild(i); p.appendChild(b); }
    if (n.meta && n.real != null) p.appendChild(el("div", "l", money(n.real, n.unidad) + " de " + money(n.meta, n.unidad)));
    (n.hitos || []).slice(0, 3).forEach(function (h) { p.appendChild(el("div", "h " + (h.ok ? "ok" : "no"), (h.ok ? "◆ " : "◇ ") + h.t)); });
    (n.lineas || []).slice(0, 2).forEach(function (l) { p.appendChild(el("div", "l", l)); });
    if (n.serie && n.serie.length > 1) { var cv = el("canvas"); cv.dataset.s = JSON.stringify(n.serie); p.appendChild(cv); }
    return p;
  }
  function render() {
    if (!data) return;
    cancelAnimationFrame(raf); raf = 0;
    root.textContent = "";
    var izq = el("div", "col izq"), der = el("div", "col der");
    data.negocios.forEach(function (n, i) { (i < Math.ceil((data.negocios.length + 2) / 2) ? izq : der).appendChild(panelNegocio(n)); });
    var a = data.actividad, pa = el("div", "pn"); pa.dataset.id = "actividad";
    var ta = el("div", "t"); ta.appendChild(el("span", "", "ACTIVIDAD DEL AGENTE · 24 H")); ta.appendChild(el("span", "", a.datos ? String(a.total) : "")); pa.appendChild(ta);
    var cv = el("canvas"); cv.dataset.s = JSON.stringify(a.datos ? a.por_hora : []); cv.dataset.b = "1"; pa.appendChild(cv);
    if (!a.datos) pa.appendChild(el("div", "e sd", "sin datos · audit.jsonl vacío"));
    a.ultimas.slice(0, 3).forEach(function (u) { pa.appendChild(el("div", "l", hora(u.at) + "  " + u.agente + " · " + u.accion + " · " + u.veredicto)); });
    der.appendChild(pa);
    var ev = data.evidencia, pe = el("div", "pn"); pe.dataset.id = "evidencia";
    var te = el("div", "t"); te.appendChild(el("span", "", "EVIDENCIA")); te.appendChild(el("span", "", ev.total_capturas ? ev.total_capturas + " capturas" : "")); pe.appendChild(te);
    if (ev.ultimo_move) pe.appendChild(el("div", "l", "Puntero " + (ev.ultimo_move.ok ? "movido" : "falló") + " " + hora(ev.ultimo_move.at) + " · accesibilidad " + (ev.ultimo_move.accesibilidad ? "sí" : "no")));
    if (ev.capturas.length) { var im = el("img"); im.src = "/api/evidencia/" + ev.capturas[0].nombre; im.style.cssText = "width:100%;max-height:90px;object-fit:cover;margin-top:5px;opacity:.85"; pe.appendChild(im); }
    if (ev.estado !== "ok") pe.appendChild(el("div", "e sd", "sin datos · sin capturas ni movimientos"));
    der.appendChild(pe);
    root.appendChild(izq); root.appendChild(der);
    if (data.ejemplo) root.appendChild(el("div", "ej", "EJEMPLO · datos de prueba del box, no son de Yullian"));
    resaltar(foco); t0 = -1; anim();
  }
  function paso(now) {          // también lo usa el grabador de video con paso fijo
    if (t0 < 0) t0 = now;
    var k = Math.min(1, (now - t0) / ANIM), e = 1 - Math.pow(1 - k, 3);
    root.querySelectorAll(".bar i").forEach(function (i) { var d = +i.dataset.d, p = +i.dataset.p; i.style.width = ((d + (p - d) * e) * 100) + "%"; });
    root.querySelectorAll("canvas").forEach(function (cv) { chart(cv, cv._series || (cv._series = JSON.parse(cv.dataset.s)), e, cv.dataset.b); });
    if (k >= 1) data.negocios.forEach(function (n) { if (n.progreso != null) prev[n.id] = n.progreso; });
    return k < 1;
  }
  function anim() { if (manual) return; raf = requestAnimationFrame(function (now) { raf = 0; if (paso(now)) anim(); }); }
  window.addEventListener("resize", function () {
    if (!data || manual) return;
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(function () { raf = 0; paso(t0 + ANIM); });
  });
  function resaltar(id) {
    foco = id; root.querySelectorAll(".pn").forEach(function (p) { p.classList.toggle("foco", p.dataset.id === id); });
  }
  function voz(texto) {      // Jarvis habla de un negocio -> se ilumina su panel
    var t = String(texto || "").toLowerCase(), hit = null;
    (data ? data.negocios : []).forEach(function (n) { if (!hit && n.alias.some(function (a) { return t.indexOf(a) >= 0; })) hit = n.id; });
    if (hit) resaltar(hit);
  }
  function cargar() { return api("/api/paneles-negocio").then(function (d) { data = d; render(); }).catch(function () {}); }
  function pollVoz() {
    api("/api/voz").then(function (v) { var ls = (v.lineas || []).filter(function (x) { return x.quien === "jarvis"; }); if (ls.length) voz(ls[ls.length - 1].texto); }).catch(function () {});
  }
  function init() {
    root = document.getElementById("hud-negocio") || document.body.appendChild(Object.assign(document.createElement("div"), { id: "hud-negocio" }));
    if (window.JarvisPanelesManual) { manual = true; return; }
    cargar(); setInterval(cargar, REFRESCO); setInterval(pollVoz, 2500);
  }
  window.JarvisPaneles = { cargarDatos: function (d) { data = d; render(); }, paso: paso, voz: voz, resaltar: resaltar };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
