// Cielo de galaxia (decorativo) y ajuste de la barra de abajo. No lee datos ni llama a ningún servidor.
(function () {
  "use strict";
  var reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // La barra de abajo puede ocupar una o dos filas: el contenido se corre según su alto real.
  // Igual con la barra de arriba: los paneles llenan el alto que queda entre las dos.
  var foot = document.querySelector(".foot"), top = document.querySelector("body > header");
  function fitFoot() {
    var root = document.documentElement.style;
    if (foot) root.setProperty("--foot-h", Math.ceil(foot.getBoundingClientRect().height) + "px");
    if (top) root.setProperty("--top-h", Math.ceil(top.getBoundingClientRect().height) + "px");
  }
  if ("ResizeObserver" in window) {
    var ro = new ResizeObserver(fitFoot);
    if (foot) ro.observe(foot);
    if (top) ro.observe(top);
  }
  addEventListener("resize", fitFoot); fitFoot();

  var sky = document.createElement("canvas");
  sky.className = "sky"; sky.setAttribute("aria-hidden", "true");
  document.body.insertBefore(sky, document.body.firstChild);
  var c = sky.getContext("2d"), stars = [], meteor = null, lowPower = (navigator.hardwareConcurrency || 4) <= 4;

  function size() {
    var dpr = Math.min(lowPower ? 1 : 2, devicePixelRatio || 1);
    sky.width = innerWidth * dpr; sky.height = innerHeight * dpr; c.setTransform(dpr, 0, 0, dpr, 0, 0);
    var n = Math.round(innerWidth * innerHeight / (lowPower ? 6500 : 3800));
    stars = [];
    for (var i = 0; i < n; i++) {
      var big = Math.random() < 0.06, roll = Math.random();
      stars.push({ x: Math.random() * innerWidth, y: Math.random() * innerHeight,
                   r: big ? 1.1 + Math.random() * 0.9 : 0.3 + Math.random() * 0.7, p: Math.random() * 6.28,
                   s: 0.4 + Math.random() * 1.6, c: roll < 0.18 ? "150,200,255" : roll < 0.26 ? "255,230,200" : "255,255,255" });
    }
  }
  function draw(t) {
    c.clearRect(0, 0, innerWidth, innerHeight);
    for (var i = 0; i < stars.length; i++) {
      var st = stars[i], a = reduce ? 0.7 : 0.35 + 0.65 * Math.abs(Math.sin(st.p + t / 1000 * st.s * 0.6));
      c.fillStyle = "rgba(" + st.c + "," + a.toFixed(3) + ")";
      c.beginPath(); c.arc(st.x, st.y, st.r, 0, 6.283); c.fill();
      if (st.r > 1.2) { c.fillStyle = "rgba(" + st.c + "," + (a * 0.12).toFixed(3) + ")"; c.beginPath(); c.arc(st.x, st.y, st.r * 4, 0, 6.283); c.fill(); }
    }
    if (!reduce) {
      if (!meteor && Math.random() < 0.0012) meteor = { x: Math.random() * innerWidth * 0.8, y: Math.random() * innerHeight * 0.4, born: t };
      if (meteor) {
        var k = (t - meteor.born) / 900;
        if (k > 1) meteor = null;
        else {
          var hx = meteor.x + k * 320, hy = meteor.y + k * 140, g = c.createLinearGradient(hx - 120, hy - 52, hx, hy);
          g.addColorStop(0, "rgba(160,210,255,0)"); g.addColorStop(1, "rgba(220,240,255," + (0.8 * (1 - k)).toFixed(3) + ")");
          c.strokeStyle = g; c.lineWidth = 1.5; c.beginPath(); c.moveTo(hx - 120, hy - 52); c.lineTo(hx, hy); c.stroke();
        }
      }
    }
  }
  var last = 0;
  function loop(t) {
    if (!document.hidden && t - last > (lowPower ? 66 : 33)) { draw(t); last = t; }   // ~15 fps en la Mac 2015, ~30 en la otra
    requestAnimationFrame(loop);
  }
  size(); addEventListener("resize", size);
  if (reduce) draw(0); else requestAnimationFrame(loop);
})();
