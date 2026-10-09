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

  function openDetail(id) {return api("POST", "/api/open", {target:id}).catch(function(){ $("deck-caption").textContent="No pude abrir el detalle. Revisa la ventana principal."; });}
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
      if (c.stale) when += " · DATO VIEJO (más de 3 días)";
      b.appendChild(el("div", "when", when));
      b.onclick = function () { openDetail(c.id); };
      g.appendChild(b);
    });
  }
  function load() {
    return api("GET", "/api/hud").then(function (r) {
      cards = r.cards || []; $("hud-demo").hidden = !r.demo; render();
      $("deck-caption").textContent = r.demo ? "DEMO · datos de ejemplo, sin conexión real" : "Datos del escritorio · toca un módulo para abrir el detalle";
      $("hud-updated").textContent = "Actualizado " + clockFmt.format(new Date());
    }).catch(function (e) { $("hud-updated").textContent = "Error: " + e.message; deckHealth({state:"down"}); });
  }
  function poll() {   // keeps this window registered (not the audio one) and follows server health
    api("GET", "/api/events?since=" + seq + "&window=" + windowId).then(function (r) {
      r.events.forEach(function (e) { if (e.type === "health" && e.health) deckHealth(e.health); });
      seq = r.seq; poll();
    }).catch(function () { setTimeout(poll, 3000); });
  }
  function tick() { $("hud-clock").textContent = "PR " + clockFmt.format(new Date()); }

  function deckHealth(h) {
    $("dot").setAttribute("data-s", h.state);
    $("deck-state").textContent = {ok:"Servidor conectado",demo:"Demostración",slow:"Con retraso",down:"Sin conexión",error:"Error",unpaired:"Sin emparejar",unknown:"Sin comprobar"}[h.state] || "Sin comprobar";
  }
  function renderNodes() {
    if(visual)visual.setModules(cards);
    $("deck-count").textContent=String(cards.length).padStart(2,"0");
    var parent = $("deck-nodes"); parent.textContent = "";
    cards.slice(0, 8).forEach(function (c, i) {
      var small=$("deck-canvas").getBoundingClientRect().width<640;
      var rows=Math.ceil(Math.min(cards.length,8)/2);
      var position={x:i%2?(small ? .8 : .84):(small ? .2 : .16),y:rows===1 ? .45 : .20+Math.floor(i/2)*.57/(rows-1)};
      var b = el("button", "deck-node"); b.type = "button";
      b.style.left = (position.x*100) + "%";
      b.style.top = (position.y*100) + "%";
      b.appendChild(el("span", "deck-node-index", String(i+1).padStart(2,"0")));
      b.appendChild(el("span", "deck-node-title", c.title));
      b.appendChild(el("small", "", c.demo ? "Ejemplo" : c.stale ? "Dato antiguo" : "Abrir detalle"));
      b.onclick = function () { openDetail(c.id); };
      parent.appendChild(b);
    });
  }
  var view = "orbit";
  var visual = window.JarvisVisual.create($("deck-canvas"), {scene:view, onQuality:function(tier,requested){$("deck-performance").textContent=(requested==="auto"?"AUTO · ":"")+({light:"LIGERO",detail:"DETALLE",eco:"AHORRO"}[tier]);}, onMotion:function(paused){
    $("deck-motion").textContent = paused ? "Activar animación" : "Pausar animación";
    $("deck-motion").setAttribute("aria-pressed",String(paused));
  }});
  $("deck-motion").onclick=function(){visual.toggleMotion();};
  $("deck-view").onclick=function(){
    view=view==="orbit"?"atlas":"orbit";visual.setScene(view);
    $("deck-view").textContent=view==="orbit"?"Ver mapa":"Ver órbita";
    $("deck-view").setAttribute("aria-pressed",String(view==="atlas"));
    $("deck-view-name").textContent=view==="orbit"?"ÓRBITA":"MAPA DE MÓDULOS";
    $("deck-core").hidden=view==="atlas";
  };
  $("deck-quality").onchange=function(){visual.setQuality(this.value);};
  window.addEventListener("resize",renderNodes);
  $("deck-fullscreen").onclick=function(){
    var root=document.documentElement;
    var exit=document.exitFullscreen||document.webkitExitFullscreen;
    if((document.fullscreenElement||document.webkitFullscreenElement)&&exit){exit.call(document);return;}
    var fn=root.requestFullscreen||root.webkitRequestFullscreen;
    if(fn){var p=fn.call(root);if(p&&p.catch)p.catch(function(){$("deck-caption").textContent="Usa pantalla completa desde el menú del navegador.";});}
    else $("deck-caption").textContent="Usa pantalla completa desde el menú del navegador.";
  };

  $("hud-refresh").onclick = load;
  $("hud-reveal").onchange = render;
  tick(); setInterval(tick, 15000);
  api("GET", "/api/state").then(function (s) { if (s.server) deckHealth(s.server); }).catch(function(){deckHealth({state:"down"});});
  load(); setInterval(load, 300000); poll();
})();
