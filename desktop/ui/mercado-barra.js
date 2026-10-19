/* Jarvis · barra de trading. Solo LEE lo que mercado.js ya trajo de /api/panels/practica.
   No pide nada a la red, no manda órdenes y no inventa un número: lo que no está, dice "—".

   Por qué es un archivo aparte: mercado.js ya funciona y está probado. Lo llama al terminar de
   cargar (una línea allí) y envuelve la llamada, así que si algo falla aquí, la curva y la tabla
   siguen como estaban. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var money = new Intl.NumberFormat("es-PR", { style: "currency", currency: "USD" });
  var css = getComputedStyle(document.documentElement);
  var tok = function (n) { return css.getPropertyValue(n).trim(); };

  function num(v) { return typeof v === "number" && isFinite(v) ? v : null; }

  /* Flecha SIEMPRE: el color no puede ser el único aviso (verde y rojo son justo el par que
     peor distingue un daltónico). El signo lo pone cada formateador, no esto: ponerlo en los
     dos sitios daba "++2.31 %". */
  function signo(v, texto) {
    var n = num(v);
    if (n == null) return { txt: "—", cls: "" };
    var flecha = n > 0 ? "▲ " : n < 0 ? "▼ " : "";
    return { txt: flecha + texto(n), cls: n > 0 ? "up" : n < 0 ? "down" : "" };
  }
  function pinta(id, v, texto) {
    var e = $(id); if (!e) return;
    var s = signo(v, texto);
    e.textContent = s.txt; e.className = e.className.replace(/\b(up|down)\b/g, "").trim();
    if (s.cls) e.className = (e.className + " " + s.cls).trim();
  }
  var pct = function (v) { return (v > 0 ? "+" : "") + v.toFixed(2) + " %"; };
  var dinero = function (v) { return (v > 0 ? "+" : "") + money.format(v); };

  /* Lo de hoy: contra el primer registro de HOY, no contra el inicio de la práctica. */
  function deHoy(pts) {
    if (!pts || pts.length < 2) return null;
    var hoy = new Date().toDateString(), prim = null, ult = null;
    pts.forEach(function (p) {
      var t = new Date(p.t || p.ts || p.time || 0);
      if (isNaN(t) || t.toDateString() !== hoy) return;
      if (prim == null) prim = num(p.v);
      var v = num(p.v); if (v != null) ult = v;
    });
    if (prim == null || ult == null || !prim) return null;
    return { abs: ult - prim, pct: (ult / prim - 1) * 100 };
  }

  function dias(pts) {
    if (!pts || !pts.length) return null;
    var t = new Date(pts[0].t || pts[0].ts || pts[0].time || 0);
    if (isNaN(t)) return null;
    return Math.max(1, Math.round((Date.now() - t) / 86400000));
  }

  /* Una sola serie: sin leyenda, línea de 2 px, punto final de 8 px (marks-and-anatomy). */
  function spark(pts) {
    var cv = $("tb-spark"); if (!cv) return;
    var w = cv.clientWidth, h = cv.clientHeight, dpr = Math.min(2, devicePixelRatio || 1);
    if (!w || !h) return;
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    var c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, w, h);
    var vs = (pts || []).map(function (p) { return num(p.v); }).filter(function (v) { return v != null; });
    if (vs.length < 2) return;
    var min = Math.min.apply(null, vs), max = Math.max.apply(null, vs), span = (max - min) || 1;
    var pad = 6, x = function (i) { return pad + i * (w - pad * 2) / (vs.length - 1); };
    var y = function (v) { return h - pad - (v - min) / span * (h - pad * 2); };
    c.strokeStyle = tok("--rule") || "rgba(255,255,255,.09)"; c.lineWidth = 1;
    c.beginPath(); c.moveTo(0, y(vs[0])); c.lineTo(w, y(vs[0])); c.stroke();   // capital inicial
    c.strokeStyle = tok("--series") || "#2f8fe6"; c.lineWidth = 2;
    c.lineJoin = "round"; c.lineCap = "round";
    c.beginPath(); vs.forEach(function (v, i) { i ? c.lineTo(x(i), y(v)) : c.moveTo(x(i), y(v)); }); c.stroke();
    c.fillStyle = tok("--series") || "#2f8fe6";
    c.beginPath(); c.arc(x(vs.length - 1), y(vs[vs.length - 1]), 4, 0, Math.PI * 2); c.fill();
  }

  function pintarTodo(ch) {
    var s = (ch && ch.summary) || {}, pts = (ch && ch.equity) || [], prods = (ch && ch.products) || [];

    var eq = num(s.equity);
    $("tb-equity").textContent = eq == null ? "—" : money.format(eq);
    $("tb-cap").textContent = eq == null ? "—" : money.format(eq);

    var hoy = deHoy(pts);
    if (hoy) {
      pinta("tb-delta", hoy.abs, function (v) { return dinero(v) + " (" + pct(hoy.pct) + ")"; });
      pinta("tb-hoy", hoy.abs, dinero);
    } else {
      $("tb-delta").textContent = "—"; $("tb-hoy").textContent = "sin registro de hoy";
    }

    pinta("tb-acum", s.pnl_total, function (v) {
      return dinero(v) + (num(s.pnl_pct) == null ? "" : " (" + pct(s.pnl_pct) + ")"); });
    pinta("tb-pnl", s.pnl_total, dinero);

    var ops = num(s.closed_trades);
    $("tb-ops").textContent = ops == null ? "—" : String(ops);
    $("tb-win").textContent = num(s.win_rate_pct) == null ? "—" : s.win_rate_pct.toFixed(0) + "%";
    $("tb-fees").textContent = num(s.fees_share_pct) == null ? "—" : s.fees_share_pct.toFixed(0) + "%";
    $("tb-dd").textContent = num(s.max_drawdown_pct) == null ? "—" : s.max_drawdown_pct.toFixed(2) + "%";
    $("tb-ddnow").textContent = num(s.drawdown_now_pct) == null ? "—" :
      "ahora " + s.drawdown_now_pct.toFixed(2) + "% bajo el máximo";

    var d = dias(pts);
    $("tb-dias").textContent = (num(s.pnl_pct) == null ? "" : pct(s.pnl_pct) + " · ") +
      (ops == null ? "0" : ops) + " cerradas" + (d == null ? "" : " · día " + d);

    /* Mejor y peor de las 24 h, de lo que vigila. Dato real: change_24h_pct por activo. */
    var con = prods.filter(function (m) { return num(m.change_24h_pct) != null; });
    if (con.length) {
      var orden = con.slice().sort(function (a, b) { return b.change_24h_pct - a.change_24h_pct; });
      var mejor = orden[0], peor = orden[orden.length - 1];
      var fila = function (id, m) {
        var e = $(id), s2 = signo(m.change_24h_pct, pct);
        e.textContent = m.product.split("-")[0] + "  " + s2.txt;
        e.className = s2.cls;
      };
      fila("tb-best", mejor); fila("tb-worst", peor);
      var suben = con.filter(function (m) { return m.change_24h_pct > 0; }).length;
      $("tb-breadth").textContent = Math.round(suben / con.length * 100) + "%";
      $("tb-breadth-note").textContent = suben + " de " + con.length + " en alza · " +
        con.map(function (m) { return m.product.split("-")[0]; }).join(" · ");
    } else {
      $("tb-best").textContent = "—"; $("tb-worst").textContent = "—";
      $("tb-breadth").textContent = "—";
      $("tb-breadth-note").textContent = "sin lectura de 24 h todavía";
    }

    $("tb-spark-note").textContent = pts.length < 2 ? "la curva aparece tras la primera revisión" :
      pts.length + " registros · la línea fina es el capital inicial";
    spark(pts);
  }

  /* mercado.js llama a window.JarvisBarra.pintar() cuando termina de cargar: una linea alli,
     en vez de que esto ande mirando el DOM a ver si cambio. */
  /* Si algo de la barra falla, la curva y la tabla de abajo siguen funcionando: esto es
     decoración sobre una página que ya servía. El fallo se ve en la consola, no en pantalla. */
  window.JarvisBarra = { pintar: function (ch) {
    try { pintarTodo(ch); } catch (e) { if (window.console) console.error("barra:", e); }
  } };
})();
