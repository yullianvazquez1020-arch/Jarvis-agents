// Jarvis / Ultron para el holograma: azul en normal; rojo-naranja angular con aviso o servidor caído (/api/state.mode).
(function () {
  "use strict";
  function set(m) { document.body.classList.toggle("ultron", m === "ultron"); document.body.classList.toggle("jarvis", m !== "ultron"); }
  var q = new URLSearchParams(location.search).get("modo");
  if (q) { set(q); return; }
  function poll() {
    fetch("/api/state", {credentials: "same-origin"}).then(function (r) { return r.json(); })
      .then(function (j) { set(j.mode); }).catch(function () { set("ultron"); });
  }
  poll(); setInterval(poll, 10000);
})();
