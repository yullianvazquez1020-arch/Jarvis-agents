// Jarvis · Torre de Aincrad: 100 pisos, cada uno un negocio. Cifras DEMO.
(function () {
  "use strict";
  var stage = document.getElementById("stage") || document.body;
  var box = document.createElement("aside"); box.className = "neg pisos"; box.id = "pisos"; box.setAttribute("aria-label", "Pisos de la torre");
  stage.appendChild(box);
  fetch("/api/negocios", {credentials: "same-origin"}).then(function (r) { return r.json(); }).then(function (t) {
    var h = document.createElement("h2"); h.textContent = "AINCRAD · " + t.conquistados + "/" + t.total_pisos + " pisos · Mando: " + t.controlador; box.appendChild(h);
    h.tabIndex = 0; h.setAttribute("role", "button"); h.title = "Plegar/desplegar lista";                // lista plegable para no tapar la torre
    var tog = function () { box.classList.toggle("plegado"); }; h.addEventListener("click", tog);
    h.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); tog(); } });
    var d = document.createElement("div"); d.className = "demo"; d.textContent = t.etiqueta; box.appendChild(d);
    var ol = document.createElement("ol");
    t.pisos.forEach(function (p) {
      var li = document.createElement("li"); if (!/^libre-/.test(p.id)) li.className = "on";
      var b = document.createElement("b"); b.textContent = p.piso; li.appendChild(b);
      var s = document.createElement("span"); s.textContent = p.nombre + " · " + p.estado; li.appendChild(s);
      li.dataset.piso = p.piso;
      li.addEventListener("click", function () { mark(p.piso); dispatchEvent(new CustomEvent("jarvis-piso-lista", {detail: p.piso})); });
      ol.appendChild(li);
    });
    box.appendChild(ol);
    function mark(n) { Array.prototype.forEach.call(ol.children, function (li) { li.classList.toggle("sel", +li.dataset.piso === n); }); }
    addEventListener("jarvis-piso", function (e) { mark(e.detail); var li = ol.querySelector('[data-piso="' + e.detail + '"]'); if (li) li.scrollIntoView({block: "nearest"}); });
  }).catch(function () { box.textContent = "Torre sin datos"; });
})();
