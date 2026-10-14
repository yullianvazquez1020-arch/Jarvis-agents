// Mecanismo azul: núcleo con anillos segmentados que giran en sentidos opuestos, marcas de medición y rayos.
// Decorativo. No lee datos ni llama a ningún servidor. Lo usan el núcleo del HUD y el emblema junto a «JARVIS».
(function () {
  "use strict";
  var reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  var BLUE = "63,180,255", ICE = "190,230,255";

  function ring(ctx, cx, cy, r, w, parts, gap, rot, alpha) {
    var step = Math.PI * 2 / parts;
    ctx.lineWidth = w; ctx.strokeStyle = "rgba(" + BLUE + "," + alpha + ")";
    for (var i = 0; i < parts; i++) {
      var a = rot + i * step;
      ctx.beginPath(); ctx.arc(cx, cy, r, a + gap / 2, a + step - gap / 2); ctx.stroke();
    }
  }

  // Cristal tallado propio (no es ninguna gema conocida): bipirámide alargada con facetas, en azules.
  function crystal(ctx, x, y, size, tilt, state, t, i) {
    var lit = state === 2 ? 0.55 + 0.45 * Math.abs(Math.sin(t * 3 + i)) : state === 1 ? 0.9 : 0.35;
    var h = size * 1.7, w = size * 0.62, top = { x: 0, y: -h }, bot = { x: 0, y: h * 0.55 };
    ctx.save(); ctx.translate(x, y); ctx.rotate(tilt);
    var glow = ctx.createRadialGradient(0, 0, 0, 0, 0, size * 2.6);
    glow.addColorStop(0, "rgba(" + BLUE + "," + (0.35 * lit) + ")"); glow.addColorStop(1, "rgba(" + BLUE + ",0)");
    ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(0, 0, size * 2.6, 0, 6.283); ctx.fill();
    var faces = [[top, { x: -w, y: -h * 0.15 }, { x: 0, y: 0 }], [top, { x: 0, y: 0 }, { x: w, y: -h * 0.15 }],
                 [{ x: -w, y: -h * 0.15 }, bot, { x: 0, y: 0 }], [{ x: 0, y: 0 }, bot, { x: w, y: -h * 0.15 }]];
    var tones = ["rgba(210,238,255," + (0.55 * lit + 0.2) + ")", "rgba(90,170,245," + (0.6 * lit + 0.2) + ")",
                 "rgba(40,110,210," + (0.6 * lit + 0.2) + ")", "rgba(20,70,160," + (0.6 * lit + 0.25) + ")"];
    faces.forEach(function (f, k) {
      ctx.fillStyle = tones[k]; ctx.beginPath(); ctx.moveTo(f[0].x, f[0].y); ctx.lineTo(f[1].x, f[1].y); ctx.lineTo(f[2].x, f[2].y);
      ctx.closePath(); ctx.fill();
    });
    ctx.strokeStyle = "rgba(220,242,255," + (0.5 + 0.4 * lit) + ")"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(top.x, top.y); ctx.lineTo(-w, -h * 0.15); ctx.lineTo(bot.x, bot.y); ctx.lineTo(w, -h * 0.15);
    ctx.closePath(); ctx.moveTo(top.x, top.y); ctx.lineTo(0, 0); ctx.lineTo(bot.x, bot.y); ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255," + (0.8 * lit) + ")"; ctx.beginPath(); ctx.arc(-w * 0.3, -h * 0.45, size * 0.12, 0, 6.283); ctx.fill();
    ctx.restore();
  }

  // Cristales en órbita inclinada alrededor del núcleo. Los de atrás se dibujan antes que el reactor.
  function orbit(gems, R, t) {
    var n = gems.length;
    return gems.map(function (g, i) {
      var a = t * 0.25 + i / n * 6.283, depth = Math.sin(a);
      return { x: Math.cos(a) * R * 1.55, y: depth * R * 0.42 + Math.sin(t * 1.4 + i) * R * 0.03 - R * 0.05,
               depth: depth, scale: 0.75 + 0.25 * (depth + 1) / 2, state: g.state || 0, i: i };
    });
  }
  function drawCrystals(ctx, cx, cy, R, t, list, front) {
    list.filter(function (p) { return front ? p.depth >= 0 : p.depth < 0; }).forEach(function (p) {
      ctx.globalAlpha = front ? 1 : 0.55;
      crystal(ctx, cx + p.x, cy + p.y, R * 0.115 * p.scale, Math.sin(t + p.i) * 0.25, p.state, t, p.i);
      ctx.globalAlpha = 1;
    });
  }

  function draw(ctx, cx, cy, R, t, detail, gems) {
    detail = detail !== false;
    var flock = gems && gems.length ? orbit(gems, R, t) : null;
    if (flock) {
      ctx.strokeStyle = "rgba(" + BLUE + ",0.14)"; ctx.lineWidth = 1;          // trayectoria de la órbita
      ctx.beginPath(); ctx.ellipse(cx, cy - R * 0.05, R * 1.55, R * 0.42, 0, 0, 6.283); ctx.stroke();
      drawCrystals(ctx, cx, cy, R, t, flock, false);
    }
    // resplandor del núcleo, con un pulso suave de energía
    var pulse = 0.85 + 0.15 * Math.sin(t * 2.2);
    var g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 0.55);
    g.addColorStop(0, "rgba(235,248,255," + (0.95 * pulse) + ")"); g.addColorStop(0.25, "rgba(" + ICE + ",0.55)");
    g.addColorStop(0.6, "rgba(" + BLUE + ",0.18)"); g.addColorStop(1, "rgba(" + BLUE + ",0)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, R * 0.55, 0, 6.283); ctx.fill();
    ctx.save(); ctx.lineCap = "butt";
    // aro del núcleo y dientes finos (más detalle)
    ctx.strokeStyle = "rgba(" + ICE + ",0.8)"; ctx.lineWidth = Math.max(1, R * 0.012);
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.17, 0, 6.283); ctx.stroke();
    if (detail) ring(ctx, cx, cy, R * 0.21, R * 0.03, 40, 0.07, t * 0.6, 0.55);
    // anillo interior: 10 bloques gruesos (bobinas), giro contrario
    ring(ctx, cx, cy, R * 0.42, R * 0.1, 10, 0.12, -t * 0.35, 0.85);
    if (detail) {                                                         // filo claro de cada bobina
      ring(ctx, cx, cy, R * 0.475, R * 0.008, 10, 0.12, -t * 0.35, 0.9);
      ring(ctx, cx, cy, R * 0.365, R * 0.008, 10, 0.12, -t * 0.35, 0.6);
    }
    // rayos que unen el núcleo con las bobinas
    ctx.strokeStyle = "rgba(" + ICE + ",0.35)"; ctx.lineWidth = Math.max(1, R * 0.012);
    for (var s = 0; s < 8; s++) {
      var a = s / 8 * 6.283 - t * 0.35;
      ctx.beginPath(); ctx.moveTo(cx + Math.cos(a) * R * 0.16, cy + Math.sin(a) * R * 0.16);
      ctx.lineTo(cx + Math.cos(a) * R * 0.36, cy + Math.sin(a) * R * 0.36); ctx.stroke();
    }
    // anillo medio: 24 segmentos finos, giro lento
    ring(ctx, cx, cy, R * 0.62, R * 0.035, 24, 0.06, t * 0.18, 0.75);
    if (detail) {
      // marcas de medición: 72, cada sexta más larga
      ctx.strokeStyle = "rgba(" + BLUE + ",0.55)";
      for (var k = 0; k < 72; k++) {
        var b = k / 72 * 6.283, long = k % 6 === 0, r1 = R * 0.74, r2 = R * (long ? 0.84 : 0.79);
        ctx.lineWidth = long ? 1.5 : 1;
        ctx.beginPath(); ctx.moveTo(cx + Math.cos(b) * r1, cy + Math.sin(b) * r1);
        ctx.lineTo(cx + Math.cos(b) * r2, cy + Math.sin(b) * r2); ctx.stroke();
      }
      // círculos guía finos
      ctx.strokeStyle = "rgba(" + BLUE + ",0.18)"; ctx.lineWidth = 1;
      [0.53, 0.70, 1.0].forEach(function (k) { ctx.beginPath(); ctx.arc(cx, cy, R * k, 0, 6.283); ctx.stroke(); });
      // anillo exterior: 3 arcos largos que barren, con remates
      ring(ctx, cx, cy, R * 0.93, R * 0.018, 3, 0.9, -t * 0.12, 0.6);
      for (var e = 0; e < 3; e++) {
        var ea = -t * 0.12 + e * 2.094 + 0.45;
        ctx.fillStyle = "rgba(" + ICE + ",0.8)";
        ctx.fillRect(cx + Math.cos(ea) * R * 0.93 - 2, cy + Math.sin(ea) * R * 0.93 - 2, 4, 4);
      }
      // cursor que recorre la escala
      var c = t * 0.5;
      ctx.fillStyle = "rgba(" + ICE + ",0.95)";
      ctx.beginPath(); ctx.arc(cx + Math.cos(c) * R * 0.86, cy + Math.sin(c) * R * 0.86, Math.max(1.5, R * 0.018), 0, 6.283); ctx.fill();
    }
    ctx.restore();
    if (flock) drawCrystals(ctx, cx, cy, R, t, flock, true);
  }

  // Emblema junto a cada «JARVIS» de las barras.
  function emblems() {
    var list = [];
    document.querySelectorAll(".brand").forEach(function (brand) {
      var cv = document.createElement("canvas");
      cv.className = "emblem"; cv.width = 56; cv.height = 56; cv.setAttribute("aria-hidden", "true");
      brand.insertBefore(cv, brand.firstChild);
      list.push(cv);
    });
    if (!list.length) return;
    var last = 0;
    function loop(time) {
      if (!document.hidden && time - last > 50) {
        last = time;
        list.forEach(function (cv) {
          var c = cv.getContext("2d"); c.clearRect(0, 0, 56, 56); draw(c, 28, 28, 26, reduce ? 0 : time / 1000, false);
        });
      }
      if (!reduce) requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
  }

  function metal(ctx, x0, y0, x1, y1) {
    var g = ctx.createLinearGradient(x0, y0, x1, y1);
    g.addColorStop(0, "#d7e3ee"); g.addColorStop(0.18, "#5d7186"); g.addColorStop(0.42, "#1b2633");
    g.addColorStop(0.62, "#8fa3b7"); g.addColorStop(0.82, "#26323f"); g.addColorStop(1, "#b9c8d6");
    return g;
  }

  // ---------- Núcleo: reactor de arco (HUD) ----------
  // Disco blanco, anillo de energía, diez segmentos trapezoidales, triángulo central y bisel con pernos.
  // Geometría propia. No es un logo. Las marcas de afuera giran; el triángulo no.
  function reactor(ctx, cx, cy, R, t, gems) {
    var flock = gems && gems.length ? orbit(gems, R, t) : null;
    if (flock) drawCrystals(ctx, cx, cy, R, t, flock, false);
    var hablando = false;
    var fig = document.querySelector(".hx-figure");
    if (fig) hablando = fig.getAttribute("data-voz") === "hablando";
    var pulse = hablando ? (0.72 + 0.28 * Math.abs(Math.sin(t * 9))) : (0.9 + 0.1 * Math.sin(t * 2.2));
    var spin = reduce ? 0 : Math.sin(t * 0.35) * 0.04;

    var halo = ctx.createRadialGradient(cx, cy, R * 0.2, cx, cy, R * 1.35);
    halo.addColorStop(0, "rgba(210,245,255," + (0.55 * pulse) + ")");
    halo.addColorStop(0.45, "rgba(" + BLUE + "," + (0.28 * pulse) + ")");
    halo.addColorStop(1, "rgba(" + BLUE + ",0)");
    ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(cx, cy, R * 1.35, 0, 6.283); ctx.fill();

    ctx.save();
    ctx.strokeStyle = "rgba(" + BLUE + ",0.45)";
    for (var k = 0; k < 96; k++) {
      var b = k / 96 * 6.283 + t * 0.04, long = k % 8 === 0;
      ctx.lineWidth = long ? 1.6 : 0.7;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(b) * R * 1.02, cy + Math.sin(b) * R * 1.02);
      ctx.lineTo(cx + Math.cos(b) * R * (long ? 1.12 : 1.07), cy + Math.sin(b) * R * (long ? 1.12 : 1.07));
      ctx.stroke();
    }
    ctx.restore();

    var plate = ctx.createRadialGradient(cx, cy, R * 0.1, cx, cy, R);
    plate.addColorStop(0, "#071424"); plate.addColorStop(1, "#02060c");
    ctx.fillStyle = plate; ctx.beginPath(); ctx.arc(cx, cy, R * 0.98, 0, 6.283); ctx.fill();

    ctx.lineWidth = R * 0.09; ctx.strokeStyle = metal(ctx, cx - R, cy - R, cx + R, cy + R);
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.93, 0, 6.283); ctx.stroke();
    ctx.lineWidth = 1.2; ctx.strokeStyle = "rgba(230,242,255,0.7)";
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.975, 0, 6.283); ctx.stroke();
    ctx.strokeStyle = "rgba(0,0,0,0.75)"; ctx.beginPath(); ctx.arc(cx, cy, R * 0.885, 0, 6.283); ctx.stroke();
    for (var s = 0; s < 10; s++) {
      var ba = (s + 0.5) / 10 * 6.283, bx = cx + Math.cos(ba) * R * 0.93, by = cy + Math.sin(ba) * R * 0.93, br = R * 0.028;
      var bg = ctx.createRadialGradient(bx - br * 0.4, by - br * 0.4, 0, bx, by, br);
      bg.addColorStop(0, "#f4f8fb"); bg.addColorStop(0.45, "#7d91a3"); bg.addColorStop(1, "#121920");
      ctx.fillStyle = bg; ctx.beginPath(); ctx.arc(bx, by, br, 0, 6.283); ctx.fill();
    }

    ctx.save();
    ctx.translate(cx, cy); ctx.rotate(spin);
    ctx.shadowColor = "rgba(160,220,255,0.95)"; ctx.shadowBlur = R * 0.12;
    for (var i = 0; i < 10; i++) {
      ctx.save(); ctx.rotate(i / 10 * 6.283);
      ctx.beginPath();
      ctx.moveTo(R * 0.52, -R * 0.05); ctx.lineTo(R * 0.8, -R * 0.12);
      ctx.lineTo(R * 0.8, R * 0.12); ctx.lineTo(R * 0.52, R * 0.05); ctx.closePath();
      var cg = ctx.createLinearGradient(R * 0.52, 0, R * 0.8, 0);
      cg.addColorStop(0, "rgba(230,250,255," + pulse + ")");
      cg.addColorStop(0.45, "rgba(90,190,255," + (0.85 * pulse) + ")");
      cg.addColorStop(1, "rgba(20,90,170," + (0.55 * pulse) + ")");
      ctx.fillStyle = cg; ctx.fill();
      ctx.shadowBlur = 0; ctx.strokeStyle = "rgba(4,16,32,0.55)"; ctx.lineWidth = Math.max(1, R * 0.007);
      for (var w = 0; w < 7; w++) {
        var x = R * (0.56 + w * 0.032), hh = R * (0.055 + w * 0.007);
        ctx.beginPath(); ctx.moveTo(x, -hh); ctx.lineTo(x, hh); ctx.stroke();
      }
      ctx.restore();
    }
    ctx.restore();

    var breathe = 1 + (hablando ? 0.07 : 0.03) * Math.sin(t * (hablando ? 6 : 2.2));
    var cr = R * 0.4 * breathe;
    ctx.save(); ctx.shadowColor = "rgba(180,230,255,1)"; ctx.shadowBlur = R * 0.2;
    ctx.lineWidth = R * 0.018; ctx.strokeStyle = "rgba(220,245,255," + pulse + ")";
    ctx.beginPath(); ctx.arc(cx, cy, cr * 1.08, 0, 6.283); ctx.stroke(); ctx.restore();

    var core = ctx.createRadialGradient(cx - cr * 0.2, cy - cr * 0.25, 0, cx, cy, cr);
    core.addColorStop(0, "rgba(255,255,255," + pulse + ")");
    core.addColorStop(0.28, "rgba(225,248,255,0.98)");
    core.addColorStop(0.7, "rgba(80,190,255,0.9)");
    core.addColorStop(1, "rgba(20,90,180,0.15)");
    ctx.fillStyle = core; ctx.beginPath(); ctx.arc(cx, cy, cr, 0, 6.283); ctx.fill();

    ctx.save(); ctx.shadowColor = "rgba(255,255,255,0.95)"; ctx.shadowBlur = cr * 0.35;
    ctx.beginPath();
    for (var p = 0; p < 3; p++) {
      var ta = -1.5708 + p * 2.0944;
      var tx = cx + Math.cos(ta) * cr * 0.62, ty = cy + Math.sin(ta) * cr * 0.62;
      if (p === 0) ctx.moveTo(tx, ty); else ctx.lineTo(tx, ty);
    }
    ctx.closePath();
    ctx.fillStyle = "rgba(255,255,255," + (0.95 * pulse) + ")"; ctx.fill();
    ctx.lineWidth = Math.max(1.5, cr * 0.04); ctx.strokeStyle = "rgba(255,255,255,0.95)"; ctx.stroke();
    ctx.restore();

    if (flock) drawCrystals(ctx, cx, cy, R, t, flock, true);
  }

  window.JarvisMecanismo = { draw: draw, reactor: reactor };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", emblems); else emblems();
})();
