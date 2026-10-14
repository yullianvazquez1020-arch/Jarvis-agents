// Jarvis · arranque: sonido de encendido ORIGINAL (o el archivo propio del dueño vía JARVIS_STARTUP_SOUND)
// y después el saludo de Alan. Una vez por sesión del navegador, solo si "audio al arrancar" está encendido.
// Si Chrome bloquea el autoplay, espera al primer clic/tecla (o abre Chrome con
// --autoplay-policy=no-user-gesture-required).
(function () {
  "use strict";
  if (sessionStorage.getItem("jarvis-arranque") === "1") return;
  function greet() {
    fetch("/api/greet", {method: "POST", credentials: "same-origin",
      headers: {"X-Jarvis-UI": "1", "Content-Type": "application/json"}, body: "{}"}).catch(function () {});
  }
  function go() {
    var a = new Audio("/api/startup-sound"); a.volume = 0.8;
    var p = a.play();
    if (!p || !p.then) { sessionStorage.setItem("jarvis-arranque", "1"); a.onended = greet; return; }
    p.then(function () { sessionStorage.setItem("jarvis-arranque", "1"); a.onended = greet; })
     .catch(function () {                                   // autoplay bloqueado: al primer gesto
       function once() { removeEventListener("pointerdown", once); removeEventListener("keydown", once); go(); }
       addEventListener("pointerdown", once); addEventListener("keydown", once);
     });
  }
  fetch("/api/state", {credentials: "same-origin"}).then(function (r) { return r.json(); }).then(function (s) {
    var on = localStorage.getItem("jarvis-startup-music");
    var enabled = on === null ? !!(s.startup && s.startup.audio) : on === "true";
    if (enabled) go();
  }).catch(function () {});
})();
