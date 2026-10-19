/* Jarvis HUD, screen 2: read-only cards. Clicking a card only asks the main window to show its detail. */
(function () {
  "use strict";
  var M = window.JarvisMask, $ = function (id) { return document.getElementById(id); };
  var cards = [], seq = 0, windowId = "hud-" + Math.random().toString(16).slice(2);
  var clockFmt = new Intl.DateTimeFormat("es-PR", { timeZone: "America/Puerto_Rico", hour: "2-digit", minute: "2-digit" });

  function api(method, path, body) {
    var opt = { method: method, credentials: "same-origin", headers: { "X-Jarvis-UI": "1" } };
    if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
    return fetch(path, opt).then(function (r) { return r.json().then(function (j) {
      if (!r.ok) throw new Error(j.error || ("error " + r.status)); return j; }); });
  }
  function show(t, sensitive) { return sensitive && !$("hud-reveal").checked ? M.mask(t) : String(t == null ? "" : t); }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

  function render() {
    renderNodes();
    var g = $("grid"); while (g.firstChild) g.removeChild(g.firstChild);
    cards.forEach(function (c) {
      var b = el("button", "card" + (c.stale ? " stale" : "") + (c.demo ? " demo" : ""));
      b.type = "button"; b.setAttribute("aria-label", c.title);
      b.appendChild(el("div", "t", c.title));
      b.appendChild(el("div", "v", show(c.value, c.sensitive)));
      var ul = el("ul"); (c.lines || []).slice(0, 5).forEach(function (l) { ul.appendChild(el("li", "", show(l, c.sensitive))); });
      b.appendChild(ul);
      var when = c.as_of ? "Dato del " + String(c.as_of).slice(0, 16).replace("T", " ") : (c.demo ? "Ejemplo" : "");
      if (c.stale) when += " · STALE DATA (over 3 days)";
      b.appendChild(el("div", "when", when));
      b.onclick = function () { api("POST", "/api/open", { target: c.id }); };
      g.appendChild(b);
    });
  }
  function load() {
    return api("GET", "/api/hud").then(function (r) {
      cards = r.cards || []; $("hud-demo").hidden = !r.demo; render();
      document.dispatchEvent(new CustomEvent("jarvis:hud", { detail: r }));   // hudx.js dibuja barras, línea de tiempo y medidores
      $("deck-caption").textContent = r.demo ? "DEMO · sample data, no real connection" : "Desktop data · tap a module to open its detail";
      $("hud-updated").textContent = "Actualizado " + clockFmt.format(new Date());
    }).catch(function (e) { cards = []; render(); document.dispatchEvent(new CustomEvent("jarvis:hud", {detail:{cards:[],jobs:null}})); $("hud-updated").textContent = "Error: " + e.message; deckHealth({state:"down"}); });
  }
  function poll() {   // keeps this window registered (not the audio one) and follows server health
    api("GET", "/api/events?since=" + seq + "&window=" + windowId).then(function (r) {
      r.events.forEach(function (e) {
        if (e.type === "health" && e.health) deckHealth(e.health);
        if (e.type === "voz" && e.voz) takeVoz(e.voz);
      });
      seq = r.seq; poll();
    }).catch(function () { setTimeout(poll, 3000); });
  }
  function tick() { $("hud-clock").textContent = "PR " + clockFmt.format(new Date()); }
  function takeVoz(v) {
    if (!v || !v.estado) return;
    document.dispatchEvent(new CustomEvent("jarvis:voz", { detail: v }));
  }
  function pullVoz() { api("GET", "/api/voz").then(takeVoz).catch(function () {}); }

  function deckHealth(h) {
    document.dispatchEvent(new CustomEvent("jarvis:health", { detail: h }));
    $("dot").setAttribute("data-s", h.state);
    $("deck-state").textContent = {ok:"Servidor conectado",demo:"Demo",slow:"Con retraso",down:"Offline",error:"Error",unpaired:"Sin emparejar",unknown:"Sin comprobar"}[h.state] || "Sin comprobar";
  }
  var V2 = document.body.classList.contains("hud-v2");   // HUD v2: los módulos van en la franja de arriba, no alrededor del núcleo
  function renderNodes() {
    lastFrame = 0;
    var parent = $("deck-nodes"); parent.textContent = "";
    if (V2) return;
    cards.slice(0, 8).forEach(function (c, i) {
      var angle = (i / Math.min(cards.length, 8)) * Math.PI * 2 - Math.PI / 2;
      var b = el("button", "deck-node"); b.type = "button";
      b.style.left = (50 + Math.cos(angle) * 36) + "%";
      b.style.top = (50 + Math.sin(angle) * 37) + "%";
      b.appendChild(el("span", "deck-node-title", c.title));
      b.appendChild(el("small", "", c.demo ? "Ejemplo" : c.stale ? "Dato antiguo" : "Abrir detalle"));
      b.onclick = function () { api("POST", "/api/open", {target:c.id}).catch(function () { $("deck-caption").textContent = "No pude abrir el detalle. Revisa la ventana principal."; }); };
      parent.appendChild(b);
    });
  }
  // Un cristal por módulo. Brillo: 0 nada pendiente, 1 algo por atender, 2 vencido o dato viejo (pulsa).
  // El número sigue escrito en su tarjeta: el brillo nunca es el único aviso.
  var ATTENTION = { cobros: 1, vencidos: 2, agenda: 1, stock: 1, mensajes: 1 };
  function gemState(c) {
    if (c.stale) return 2;
    var n = parseFloat(String(c.value == null ? "" : c.value).replace(/[^0-9.\-]/g, ""));
    if (!ATTENTION[c.id] || !(n > 0)) return 0;
    return ATTENTION[c.id];
  }
  var canvas = $("deck-canvas"), ctx = canvas.getContext("2d"), lastFrame = 0;
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)"), paused = reduced.matches;
  function motionLabel() { $("deck-motion").textContent = paused ? "Resume animation" : "Pause animation"; $("deck-motion").setAttribute("aria-pressed", String(paused)); }
  function draw(time) {
    requestAnimationFrame(draw);
    if (document.hidden || (time - lastFrame < 40) || (paused && lastFrame)) return;
    lastFrame = time;
    var w = canvas.clientWidth, h = canvas.clientHeight, dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    if (canvas.width !== Math.round(w*dpr) || canvas.height !== Math.round(h*dpr)) { canvas.width=Math.round(w*dpr); canvas.height=Math.round(h*dpr); }
    ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,w,h);
    var cx=w/2, cy=h/2, radius=Math.min(w,h)*0.22, t=paused?0:time/1800;
    if (window.JarvisMecanismo) {   // núcleo azul: bobinas, escala y anillos que giran (mecanismo.js)
      if (V2 && window.JarvisMecanismo.reactor)   // HUD v2: reactor con volumen, del alto disponible
        window.JarvisMecanismo.reactor(ctx, cx, cy, Math.min(w * 0.3, h * 0.36), paused ? 0 : time / 1000, cards.slice(0, 8).map(gemState));
      else
        window.JarvisMecanismo.draw(ctx, cx, cy, Math.max(radius * 1.9, 150), paused ? 0 : time / 1000, true, cards.slice(0, 8).map(gemState));
    } else {
      ctx.beginPath(); ctx.strokeStyle="rgba(63,180,255,0.7)"; ctx.lineWidth=2; ctx.arc(cx,cy,radius,0,Math.PI*2); ctx.stroke();
    }
    if (!V2) cards.slice(0,8).forEach(function(c,i) {
      var a=i/Math.min(cards.length,8)*Math.PI*2-Math.PI/2, nx=cx+Math.cos(a)*w*.36, ny=cy+Math.sin(a)*h*.37;
      ctx.strokeStyle="rgba(54,208,241,0.3)"; ctx.beginPath();ctx.moveTo(cx+Math.cos(a)*radius,cy+Math.sin(a)*radius);ctx.lineTo(nx,ny);ctx.stroke();
      var f=(t*.3+i*.17)%1;ctx.fillStyle="#79e7ff";ctx.beginPath();ctx.arc(cx+(nx-cx)*f,cy+(ny-cy)*f,2,0,Math.PI*2);ctx.fill();
    });
  }
  $("deck-motion").onclick=function(){paused=!paused;lastFrame=0;motionLabel();};
  window.addEventListener("resize",function(){lastFrame=0;});
  $("deck-fullscreen").onclick=function(){var fn=document.documentElement.requestFullscreen || document.documentElement.webkitRequestFullscreen;
    if(fn){var p=fn.call(document.documentElement);if(p&&p.catch)p.catch(function(){$("deck-caption").textContent="Use full screen from the browser menu.";});}
    else $("deck-caption").textContent="Use full screen from the browser menu.";};
  motionLabel(); requestAnimationFrame(draw);

  $("hud-refresh").onclick = load;
  $("hud-reveal").onchange = render;
  tick(); setInterval(tick, 15000);
  api("GET", "/api/state").then(function (s) { if (s.server) deckHealth(s.server); }).catch(function(){deckHealth({state:"down"});});
  load(); setInterval(load, 300000); poll(); pullVoz(); setInterval(pullVoz, 2000);
})();
