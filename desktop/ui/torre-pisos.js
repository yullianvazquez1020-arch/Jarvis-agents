// Jarvis · Torre de Aincrad: 100 pisos, cada uno un negocio. Cifras DEMO.
(function () {
  "use strict";
  var stage = document.getElementById("stage") || document.body;
  var box = document.createElement("aside"); box.className = "neg pisos"; box.id = "pisos"; box.setAttribute("aria-label", "Pisos de la torre");
  stage.appendChild(box);
  fetch("/api/negocios", {credentials: "same-origin"}).then(function (r) { return r.json(); }).then(function (t) {
    var h = document.createElement("h2"); h.textContent = "AINCRAD · " + t.conquistados + "/" + t.total_pisos + " pisos · Mando: " + t.controlador; box.appendChild(h);
    var d = document.createElement("div"); d.className = "demo"; d.textContent = t.etiqueta; box.appendChild(d);
    var ol = document.createElement("ol");
    t.pisos.forEach(function (p) {
      var li = document.createElement("li"); if (!/^libre-/.test(p.id)) li.className = "on";
      var b = document.createElement("b"); b.textContent = p.piso; li.appendChild(b);
      var s = document.createElement("span"); s.textContent = p.nombre + " · " + p.estado; li.appendChild(s);
      ol.appendChild(li);
    });
    box.appendChild(ol);
  }).catch(function () { box.textContent = "Torre sin datos"; });
})();
