// Inicio: el núcleo es la pantalla principal. «Paneles» muestra u oculta la conversación y los detalles.
// El núcleo se aviva mientras el micrófono graba (el botón Hablar lleva la clase «recording»).
(function () {
  "use strict";
  var b = document.getElementById("paneles"), talk = document.getElementById("talk"), est = document.getElementById("estado");
  function set(on) { document.body.classList.toggle("ver-paneles", on); b.setAttribute("aria-pressed", String(on));
    try { sessionStorage.setItem("jarvis-paneles", on ? "1" : "0"); } catch (e) {} }
  var saved = null; try { saved = sessionStorage.getItem("jarvis-paneles"); } catch (e) {}
  set(saved === "1");
  b.onclick = function () { set(!document.body.classList.contains("ver-paneles")); };
  if (talk && "MutationObserver" in window) new MutationObserver(function () {
    var on = talk.classList.contains("recording");
    if (window.JarvisNucleo) window.JarvisNucleo.escuchar(on);
    if (est) est.textContent = on ? "ESCUCHANDO" : "EN LÍNEA";
  }).observe(talk, { attributes: true, attributeFilter: ["class"] });
})();
