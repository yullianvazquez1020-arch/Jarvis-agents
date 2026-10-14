// Jarvis · arranque: sonido de encendido del traje (original, o JARVIS_STARTUP_SOUND del dueño) y luego Alan.
// JARVIS_STARTUP_SOUND=off lo quita; VOICE_STARTUP_GREETING controla el saludo.
// Una vez por sesión del navegador. Si Chrome bloquea el autoplay, espera al primer clic/tecla
// (o abre Chrome con --autoplay-policy=no-user-gesture-required).
(function () {
  "use strict";
  if (sessionStorage.getItem("jarvis-arranque") === "1") return;
  function greet() {
    fetch("/api/greet", {method: "POST", credentials: "same-origin",
      headers: {"X-Jarvis-UI": "1", "Content-Type": "application/json"}, body: "{}"}).catch(function () {});
  }
  function whenAllowed(fn) {
    function once() { removeEventListener("pointerdown", once); removeEventListener("keydown", once); fn(); }
    addEventListener("pointerdown", once); addEventListener("keydown", once);
  }
  function sound(then) {
    var a = new Audio("/api/startup-sound"); a.volume = 0.8; a.onended = then;
    var p = a.play();
    if (p && p.catch) p.catch(function () { whenAllowed(function () { sound(then); }); });
  }
  fetch("/api/state", {credentials: "same-origin"}).then(function (r) { return r.json(); }).then(function (s) {
    var st = s.startup || {};
    if (!st.greeting && !st.sound) return;
    sessionStorage.setItem("jarvis-arranque", "1");
    var after = st.greeting ? greet : function () {};
    if (st.sound) sound(after); else after();
  }).catch(function () {});
})();
