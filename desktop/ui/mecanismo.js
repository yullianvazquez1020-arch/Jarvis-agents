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
      var hidden = document.body.classList.contains("nucleo-home") && !document.body.classList.contains("ver-paneles");
      if (!document.hidden && !hidden && time - last > 50) {
        last = time;
        list.forEach(function (cv) {
          var c = cv.getContext("2d"); c.clearRect(0, 0, 56, 56); draw(c, 28, 28, 26, reduce ? 0 : time / 1000, false);
        });
      }
      if (!reduce) requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
  }

  // ---------- Reactor con volumen (HUD grande) ----------
  // Pieza mecánica propia: bisel metálico con tornillos, 10 bobinas de acero azulado con su enrollado, luz que se
  // escapa entre bobinas, aro de energía y núcleo de vidrio con malla. Las escalas de afuera giran; el metal no.
  function metal(ctx, x0, y0, x1, y1) {
    var g = ctx.createLinearGradient(x0, y0, x1, y1);
    g.addColorStop(0, "#d7e3ee"); g.addColorStop(0.18, "#5d7186"); g.addColorStop(0.42, "#1b2633");
    g.addColorStop(0.62, "#8fa3b7"); g.addColorStop(0.82, "#26323f"); g.addColorStop(1, "#b9c8d6");
    return g;
  }
  function rrect(ctx, x, y, w, h, r) {
    ctx.beginPath(); ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h); ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r); ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y); ctx.closePath();
  }
  function reactor(ctx, cx, cy, R, t, gems) {
    var flock = gems && gems.length ? orbit(gems, R, t) : null;
    if (flock) {
      ctx.strokeStyle = "rgba(" + BLUE + ",0.16)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.ellipse(cx, cy - R * 0.05, R * 1.55, R * 0.42, 0, 0, 6.283); ctx.stroke();
      drawCrystals(ctx, cx, cy, R, t, flock, false);
    }
    var pulse = 0.88 + 0.12 * Math.sin(t * 2.4);
    // halo de energía detrás de la pieza
    var halo = ctx.createRadialGradient(cx, cy, R * 0.3, cx, cy, R * 1.25);
    halo.addColorStop(0, "rgba(" + BLUE + "," + (0.35 * pulse) + ")"); halo.addColorStop(1, "rgba(" + BLUE + ",0)");
    ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(cx, cy, R * 1.25, 0, 6.283); ctx.fill();
    // escalas exteriores (HUD) que giran
    ctx.save();
    ctx.strokeStyle = "rgba(" + BLUE + ",0.5)";
    for (var k = 0; k < 120; k++) {
      var b = k / 120 * 6.283 + t * 0.05, long = k % 10 === 0, r1 = R * 1.06, r2 = R * (long ? 1.14 : 1.1);
      ctx.lineWidth = long ? 1.6 : 0.8; ctx.beginPath();
      ctx.moveTo(cx + Math.cos(b) * r1, cy + Math.sin(b) * r1); ctx.lineTo(cx + Math.cos(b) * r2, cy + Math.sin(b) * r2); ctx.stroke();
    }
    ring(ctx, cx, cy, R * 1.2, R * 0.012, 4, 0.7, -t * 0.1, 0.55);
    ring(ctx, cx, cy, R * 1.0, R * 0.008, 60, 0.05, t * 0.08, 0.35);
    ctx.restore();
    // placa de fondo
    var plate = ctx.createRadialGradient(cx, cy, R * 0.2, cx, cy, R * 0.95);
    plate.addColorStop(0, "#0d2238"); plate.addColorStop(1, "#03080f");
    ctx.fillStyle = plate; ctx.beginPath(); ctx.arc(cx, cy, R * 0.95, 0, 6.283); ctx.fill();
    // bisel metálico con tornillos
    ctx.lineWidth = R * 0.085; ctx.strokeStyle = metal(ctx, cx - R, cy - R, cx + R, cy + R);
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.9, 0, 6.283); ctx.stroke();
    ctx.lineWidth = 1; ctx.strokeStyle = "rgba(220,235,250,0.55)";
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.945, 0, 6.283); ctx.stroke();
    ctx.strokeStyle = "rgba(0,0,0,0.7)"; ctx.beginPath(); ctx.arc(cx, cy, R * 0.855, 0, 6.283); ctx.stroke();
    for (var s = 0; s < 12; s++) {
      var a = s / 12 * 6.283 + 0.13, bx = cx + Math.cos(a) * R * 0.9, by = cy + Math.sin(a) * R * 0.9, br = R * 0.022;
      var bg = ctx.createRadialGradient(bx - br * 0.4, by - br * 0.4, 0, bx, by, br);
      bg.addColorStop(0, "#f2f7fb"); bg.addColorStop(0.5, "#6f8396"); bg.addColorStop(1, "#141d27");
      ctx.fillStyle = bg; ctx.beginPath(); ctx.arc(bx, by, br, 0, 6.283); ctx.fill();
      ctx.strokeStyle = "rgba(10,15,20,0.9)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(bx - br * 0.6, by); ctx.lineTo(bx + br * 0.6, by); ctx.stroke();
    }
    // canal de las bobinas con luz que se escapa
    ctx.lineWidth = R * 0.24; ctx.strokeStyle = "#05101c";
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.67, 0, 6.283); ctx.stroke();
    ctx.save(); ctx.shadowColor = "rgba(" + BLUE + ",1)"; ctx.shadowBlur = R * 0.12;
    ctx.lineWidth = R * 0.2; ctx.strokeStyle = "rgba(90,190,255," + (0.55 * pulse) + ")";
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.67, 0, 6.283); ctx.stroke(); ctx.restore();
    // 10 bobinas de acero azulado con enrollado
    for (var c = 0; c < 10; c++) {
      var ang = c / 10 * 6.283 + 0.314;
      ctx.save(); ctx.translate(cx + Math.cos(ang) * R * 0.67, cy + Math.sin(ang) * R * 0.67); ctx.rotate(ang + Math.PI / 2);
      var w = R * 0.29, h = R * 0.2;
      var body = ctx.createLinearGradient(0, -h / 2, 0, h / 2);
      body.addColorStop(0, "#9fb6cc"); body.addColorStop(0.35, "#3d5a78"); body.addColorStop(0.7, "#1a2b3f"); body.addColorStop(1, "#5b7896");
      rrect(ctx, -w / 2, -h / 2, w, h, R * 0.025); ctx.fillStyle = body; ctx.fill();
      ctx.strokeStyle = "rgba(170,220,255,0.6)"; ctx.lineWidth = 1; ctx.stroke();
      for (var wv = 1; wv < 13; wv++) {                                   // enrollado
        var xx = -w / 2 + w * wv / 13;
        ctx.strokeStyle = wv % 2 ? "rgba(200,230,255,0.55)" : "rgba(8,16,26,0.8)"; ctx.lineWidth = Math.max(1, R * 0.006);
        ctx.beginPath(); ctx.moveTo(xx, -h / 2 + 2); ctx.lineTo(xx + R * 0.01, h / 2 - 2); ctx.stroke();
      }
      ctx.fillStyle = "rgba(255,255,255,0.18)"; ctx.fillRect(-w / 2 + 2, -h / 2 + 2, w - 4, h * 0.18);   // brillo
      ctx.restore();
    }
    // aro interior metálico
    ctx.lineWidth = R * 0.05; ctx.strokeStyle = metal(ctx, cx + R * 0.5, cy - R * 0.5, cx - R * 0.5, cy + R * 0.5);
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.5, 0, 6.283); ctx.stroke();
    // aro de energía
    ctx.save(); ctx.shadowColor = "rgba(" + BLUE + ",1)"; ctx.shadowBlur = R * 0.18;
    ctx.lineWidth = R * 0.035; ctx.strokeStyle = "rgba(150,220,255," + pulse + ")";
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.44, 0, 6.283); ctx.stroke(); ctx.restore();
    // núcleo de vidrio con malla
    var core = ctx.createRadialGradient(cx - R * 0.08, cy - R * 0.08, 0, cx, cy, R * 0.41);
    core.addColorStop(0, "rgba(255,255,255," + pulse + ")"); core.addColorStop(0.35, "rgba(200,240,255,0.95)");
    core.addColorStop(0.75, "rgba(80,180,255,0.85)"); core.addColorStop(1, "rgba(20,80,160,0.9)");
    ctx.fillStyle = core; ctx.beginPath(); ctx.arc(cx, cy, R * 0.41, 0, 6.283); ctx.fill();
    ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, R * 0.41, 0, 6.283); ctx.clip();
    ctx.fillStyle = "rgba(10,60,120,0.22)"; var step = R * 0.035;
    for (var yy = -R * 0.42; yy < R * 0.42; yy += step * 0.87) {
      var off = Math.round(yy / (step * 0.87)) % 2 ? step / 2 : 0;
      for (var xh = -R * 0.42 + off; xh < R * 0.42; xh += step) { ctx.beginPath(); ctx.arc(cx + xh, cy + yy, step * 0.28, 0, 6.283); ctx.fill(); }
    }
    ctx.strokeStyle = "rgba(255,255,255,0.35)"; ctx.lineWidth = 1;
    [0.16, 0.28, 0.36].forEach(function (k) { ctx.beginPath(); ctx.arc(cx, cy, R * k, 0, 6.283); ctx.stroke(); });
    var shine = ctx.createLinearGradient(cx - R * 0.4, cy - R * 0.4, cx, cy);                     // reflejo del vidrio
    shine.addColorStop(0, "rgba(255,255,255,0.35)"); shine.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = shine; ctx.beginPath(); ctx.ellipse(cx - R * 0.12, cy - R * 0.16, R * 0.22, R * 0.11, -0.6, 0, 6.283); ctx.fill();
    ctx.restore();
    // cursor que recorre la escala
    var cu = t * 0.4;
    ctx.fillStyle = "rgba(" + ICE + ",0.95)";
    ctx.beginPath(); ctx.arc(cx + Math.cos(cu) * R * 1.17, cy + Math.sin(cu) * R * 1.17, Math.max(2, R * 0.016), 0, 6.283); ctx.fill();
    if (flock) drawCrystals(ctx, cx, cy, R, t, flock, true);
  }

  window.JarvisMecanismo = { draw: draw, reactor: reactor };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", emblems); else emblems();
})();
