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
      b.onclick = function () { api("POST", "/api/open", { target: c.id }); };
      g.appendChild(b);
    });
  }
  function load() {
    return api("GET", "/api/hud").then(function (r) {
      cards = r.cards || []; $("hud-demo").hidden = !r.demo; render();
      $("hud-updated").textContent = "Actualizado " + clockFmt.format(new Date());
    }).catch(function (e) { $("hud-updated").textContent = "Error: " + e.message; $("dot").setAttribute("data-s", "down"); });
  }
  function poll() {   // keeps this window registered (not the audio one) and follows server health
    api("GET", "/api/events?since=" + seq + "&window=" + windowId).then(function (r) {
      r.events.forEach(function (e) { if (e.type === "health" && e.health) $("dot").setAttribute("data-s", e.health.state); });
      seq = r.seq; poll();
    }).catch(function () { setTimeout(poll, 3000); });
  }
  function tick() { $("hud-clock").textContent = "PR " + clockFmt.format(new Date()); }

  $("hud-refresh").onclick = load;
  $("hud-reveal").onchange = render;
  tick(); setInterval(tick, 15000);
  api("GET", "/api/state").then(function (s) { if (s.server) $("dot").setAttribute("data-s", s.server.state); });
  load(); setInterval(load, 300000); poll();
})();
