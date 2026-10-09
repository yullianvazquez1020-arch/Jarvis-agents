/* Boca del avatar según el audio real: envolvente de amplitud (RMS) del mismo archivo que suena, alineada con el
   reloj del elemento <audio> de la ventana de conversación. Es amplitud, no fonemas. Sin dependencias.
   Navegador: window.JarvisLipsync. Node (pruebas): module.exports. */
(function (root) {
  "use strict";
  var FPS = 100;                 // una muestra cada 10 ms
  var ATTACK_MS = 18, RELEASE_MS = 45;
  var LOOKAHEAD_S = 0.01;        // compensa el retardo del suavizado y del cuadro de dibujo

  function percentile(sorted, p) {
    if (!sorted.length) return 0;
    var i = Math.min(sorted.length - 1, Math.max(0, Math.round((sorted.length - 1) * p)));
    return sorted[i];
  }

  /* samples: Float32Array de un canal; rate: Hz. -> {fps, duration, values: Array 0..1} */
  function envelope(samples, rate, fps) {
    fps = fps || FPS;
    if (!samples || !rate || rate <= 0) throw new Error("audio vacío");
    var step = Math.max(1, Math.round(rate / fps)), n = Math.ceil(samples.length / step), raw = new Array(n);
    for (var f = 0; f < n; f++) {
      var s = f * step, e = Math.min(samples.length, s + step), sum = 0;
      for (var i = s; i < e; i++) sum += samples[i] * samples[i];
      raw[f] = e > s ? Math.sqrt(sum / (e - s)) : 0;
    }
    var sorted = raw.slice().sort(function (a, b) { return a - b; });
    var floor = Math.max(0.004, percentile(sorted, 0.2));          // silencio y ruido de fondo
    var voiced = sorted.filter(function (v) { return v > floor * 1.5; });
    var ref = Math.max(floor * 2, percentile(voiced.length ? voiced : sorted, 0.95));
    var values = raw.map(function (v) {
      var x = (v - floor) / (ref - floor);
      x = x <= 0 ? 0 : x >= 1 ? 1 : x;
      return Math.round(Math.sqrt(x) * 1000) / 1000;               // sqrt: apertura más natural en voz baja
    });
    return { fps: fps, duration: samples.length / rate, values: values };
  }

  /* Nivel en el segundo t del audio (interpolado). Fuera del audio: 0. */
  function level(env, t) {
    if (!env || !env.values || !env.values.length || !(t >= 0)) return 0;
    var x = t * env.fps, i = Math.floor(x);
    if (i >= env.values.length) return 0;
    var a = env.values[i], b = i + 1 < env.values.length ? env.values[i + 1] : 0;
    return a + (b - a) * (x - i);
  }

  /* Posición actual del audio a partir del último mensaje de reloj: {t, at (ms de pared), rate, playing}. */
  function position(clock, nowMs) {
    if (!clock) return -1;
    if (!clock.playing) return clock.t;
    return clock.t + Math.max(0, nowMs - clock.at) / 1000 * (clock.rate || 1);
  }

  /* Reloj robusto: cada mensaje da una estimación del instante de pared en que el audio estaba en 0 s.
     Se usa la mediana de las últimas 9 (un mensaje tardío o un currentTime desigual no mueve la boca).
     Pausa, salto (>250 ms de diferencia), cambio de velocidad u otro audio reinician la estimación. */
  function ClockFilter() { this.id = null; this.rate = 1; this.offs = []; this.last = null; }
  ClockFilter.prototype.push = function (msg) {
    var rate = msg.rate || 1, off = msg.at - msg.t * 1000 / rate;
    if (msg.id !== this.id || rate !== this.rate || !msg.playing) this.offs = [];
    else if (this.offs.length && Math.abs(off - median(this.offs)) > 250) this.offs = [];
    this.id = msg.id; this.rate = rate; this.last = msg;
    if (msg.playing) { this.offs.push(off); if (this.offs.length > 9) this.offs.shift(); }
  };
  ClockFilter.prototype.position = function (nowMs) {
    var m = this.last;
    if (!m) return -1;
    if (!m.playing || !this.offs.length) return m.t;
    return Math.max(0, nowMs - median(this.offs)) / 1000 * this.rate;
  };
  function median(a) {
    var s = a.slice().sort(function (x, y) { return x - y; }), h = s.length >> 1;
    return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2;
  }

  /* Seguidor de envolvente: abre rápido, cierra un poco más lento (evita parpadeo de la boca). */
  function Follower(attackMs, releaseMs) { this.v = 0; this.a = attackMs || ATTACK_MS; this.r = releaseMs || RELEASE_MS; }
  Follower.prototype.step = function (target, dtMs) {
    var tau = target > this.v ? this.a : this.r;
    this.v += (target - this.v) * (1 - Math.exp(-Math.max(0, dtMs) / tau));
    return this.v;
  };

  /* Mensaje de envolvente compacto para BroadcastChannel (lista de números, no un objeto con funciones). */
  function message(id, env) {
    return { k: "env", id: String(id), fps: env.fps, duration: env.duration, values: env.values };
  }
  function valid(msg) {
    return !!msg && typeof msg === "object" && typeof msg.id === "string" && msg.id.length <= 64 &&
      (msg.k === "env" ? (msg.fps > 0 && msg.fps <= 200 && Array.isArray(msg.values) && msg.values.length <= 200 * 600)
        : msg.k === "clock" ? (typeof msg.t === "number" && typeof msg.at === "number")
        : msg.k === "stop");
  }

  var api = { envelope: envelope, level: level, position: position, ClockFilter: ClockFilter, Follower: Follower, message: message,
              valid: valid, FPS: FPS, LOOKAHEAD_S: LOOKAHEAD_S, CHANNEL: "jarvis-voz" };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.JarvisLipsync = api;
})(this);
