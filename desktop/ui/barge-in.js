/* Jarvis: interrumpirlo mientras habla.

   Hasta ahora el panel apagaba el micrófono al empezar a hablar, para no oírse a sí mismo
   (app.js: play() llamaba a stopMic). Por eso no se dejaba interrumpir.

   Aquí el micrófono se queda escuchando MIENTRAS habla, con tres frenos para que Jarvis no se
   corte a sí mismo, que es el riesgo real:
     1. El navegador ya cancela el eco (getUserMedia pide echoCancellation), así que su propia
        voz llega muy baja.
     2. Un periodo de gracia al empezar: los primeros milisegundos no cuentan.
     3. Hay que superar el umbral de forma SOSTENIDA, no en un golpe suelto: una tos, un clic
        del teclado o un portazo no lo callan.

   Si aun así se corta solo, se sube el umbral sin tocar código:
       localStorage.setItem("jarvis-barge-umbral", "0.30")
   y se apaga del todo con:
       localStorage.setItem("jarvis-barge", "0")

   No graba nada, no manda nada y no toca la red: solo mide el volumen y, si oye al dueño,
   detiene el audio y abre el micrófono de verdad. */
(function () {
  "use strict";

  var POR_DEFECTO = { umbral: 0.18, gracia: 450, sostenido: 180 };

  function ajuste(clave, def, min, max) {
    var v;
    try { v = parseFloat(localStorage.getItem(clave)); } catch (e) { v = NaN; }
    return isFinite(v) && v >= min && v <= max ? v : def;
  }
  function encendido() {
    try { return localStorage.getItem("jarvis-barge") !== "0"; } catch (e) { return true; }
  }

  /* El cerebro, aislado a propósito: sin micrófono, sin DOM y sin navegador, para poder
     probarlo de verdad en vez de a ojo. Devuelve true cuando hay que cortar. */
  function Decisor(op) {
    op = op || {};
    this.umbral = op.umbral != null ? op.umbral : ajuste("jarvis-barge-umbral", POR_DEFECTO.umbral, 0.02, 0.9);
    this.gracia = op.gracia != null ? op.gracia : POR_DEFECTO.gracia;
    this.sostenido = op.sostenido != null ? op.sostenido : POR_DEFECTO.sostenido;
    this.inicio = null;      // cuándo empezó a sonar Jarvis
    this.desde = null;       // cuándo empezó la voz que supera el umbral
  }
  Decisor.prototype.empezar = function (ahora) { this.inicio = ahora; this.desde = null; };
  Decisor.prototype.push = function (nivel, ahora) {
    if (this.inicio == null) return false;
    if (ahora - this.inicio < this.gracia) { this.desde = null; return false; }
    if (!(nivel > this.umbral)) { this.desde = null; return false; }
    if (this.desde == null) { this.desde = ahora; return false; }
    return ahora - this.desde >= this.sostenido;
  };

  if (typeof module !== "undefined" && module.exports) { module.exports = { Decisor: Decisor }; return; }

  // ---------- la parte que toca el navegador ----------
  var ctx = null, nodo = null, fuente = null, decisor = null, mirando = false;
  var ultimo = 0;   // ultimo nivel medido: con Jarvis hablando dice cuanto mide su propia voz

  function soltar() {
    mirando = false;
    try { if (nodo) nodo.disconnect(); if (fuente) fuente.disconnect(); } catch (e) { /* ya cerrado */ }
    nodo = fuente = null;
    if (ctx) { try { ctx.close(); } catch (e) { /* ya cerrado */ } ctx = null; }
  }

  function vigilar() {
    if (!encendido() || mirando) return;
    var api = window.JarvisMicAPI;
    if (!api) return;
    var stream = api.warmStream();
    if (!stream) return;                                   // sin permiso todavía: no hay nada que hacer
    var pistas = stream.getAudioTracks();
    if (!pistas.length || pistas[0].readyState !== "live") return;
    try {
      pistas.forEach(function (t) { t.enabled = true; });   // en conversación quedan mudas entre turnos
      var Ctx = window.AudioContext || window.webkitAudioContext;
      ctx = new Ctx();
      fuente = ctx.createMediaStreamSource(stream);
      nodo = ctx.createScriptProcessor(1024, 1, 1);
    } catch (e) { soltar(); return; }

    decisor = new Decisor();
    decisor.empezar(performance.now());
    mirando = true;

    nodo.onaudioprocess = function (ev) {
      if (!mirando) return;
      var d = ev.inputBuffer.getChannelData(0), e = 0;
      for (var i = 0; i < d.length; i++) e += d[i] * d[i];
      var nivel = Math.min(1, Math.sqrt(e / d.length) * 8);   // misma escala que el medidor del panel
      ultimo = nivel;
      if (!decisor.push(nivel, performance.now())) return;
      soltar();
      try { api.stopAudio(); } catch (err) { /* ya estaba parado */ }
      try { api.startMic(); } catch (err) { /* el panel dirá por qué */ }
      window.dispatchEvent(new CustomEvent("jarvis-interrumpido"));
    };
    fuente.connect(nodo); nodo.connect(ctx.destination);
  }

  // nivel(): con Jarvis hablando, cuanto mide su propia voz por los altavoces. El umbral va
  // por encima de eso y por debajo de lo que mide la voz del dueno.
  window.JarvisBargeIn = { watch: vigilar, stop: soltar, Decisor: Decisor,
                           nivel: function () { return ultimo; },
                           mirando: function () { return mirando; } };
})();
