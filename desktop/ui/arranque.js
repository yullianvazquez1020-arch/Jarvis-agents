/* Arranque: música + saludo corto, una vez por sesión del navegador. El micrófono espera a que termine. */
(function () {
  'use strict';
  var FULL = 0.35, LOW = 0.10, GREET_AFTER_MS = 3000, FADE_MS = 1500;
  var audio = null, done = false, started = false, greeted = false, heard = false;
  var settings = null, poll = 0, safety = 0, greetAt = 0;
  window.JarvisIntroBusy = true;                       // app.js no abre el micrófono mientras esto sea true

  function remembered() { try { return sessionStorage.getItem('jarvis-arranque') === '1'; } catch (_) { return false; } }
  function mark() { try { sessionStorage.setItem('jarvis-arranque', '1'); } catch (_) {} }
  function release() {
    if (!window.JarvisIntroBusy) return;
    window.JarvisIntroBusy = false;
    dispatchEvent(new Event('jarvis-intro-done'));
  }
  function stopMusic(ms) {
    if (!audio) return;
    var a = audio; audio = null;
    var steps = Math.max(1, Math.round((ms || 0) / 50)), v = a.volume, n = 0;
    var t = setInterval(function () {
      n++; a.volume = Math.max(0, v - v * n / steps);
      if (n >= steps) { clearInterval(t); a.pause(); a.removeAttribute('src'); a.load(); }
    }, 50);
  }
  function finish(ms) {
    if (done) return;
    done = true; clearInterval(poll); clearTimeout(safety);
    stopMusic(ms); release();
  }
  window.JarvisStopIntro = function () { finish(400); };
  // app.js llama duck(true) cuando suena una voz y duck(false) al pararla.
  window.JarvisAmbience = { duck: function (on) {
    if (!audio) return;
    if (on) audio.volume = LOW; else if (greeted) finish(FADE_MS); else audio.volume = FULL;
  } };

  function greet() {
    if (greeted || done) return;
    greeted = true; greetAt = Date.now(); mark();
    if (audio) audio.volume = LOW;
    if (!(settings && settings.greeting) || window.JarvisAudioOwner !== true) { finish(FADE_MS); return; }
    fetch('/api/greet', { method: 'POST', credentials: 'same-origin',
      headers: { 'X-Jarvis-UI': '1', 'Content-Type': 'application/json' }, body: '{}' })
      .catch(function () { finish(800); });
    // Vale para voz en el navegador y para voz por los altavoces de la Mac: el servidor dice si está hablando.
    poll = setInterval(function () {
      fetch('/api/state', { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (s) {
        if (s.speaking) heard = true;
        else if (heard || Date.now() - greetAt > 6000) finish(FADE_MS);
      }).catch(function () {});
    }, 300);
  }

  function attempt() {
    if (done || started || !settings || window.JarvisAudioOwner !== true || document.hidden) return;
    if (remembered()) { finish(0); return; }
    started = true;
    safety = setTimeout(function () { finish(800); }, 20000);     // nunca deja el micrófono esperando más de 20 s
    if (!settings.sound) { greet(); return; }
    audio = new Audio('/api/startup-sound'); audio.volume = FULL; audio.loop = false;
    audio.onplaying = function () { mark(); setTimeout(greet, GREET_AFTER_MS); };
    audio.onended = function () { audio = null; greet(); };
    audio.onerror = function () { audio = null; greet(); };
    var p = audio.play();
    if (p && p.catch) p.catch(function () { audio = null; greet(); });   // el navegador bloqueó la música: saluda igual
  }

  addEventListener('jarvis-audio-owner', function (e) { if (e.detail) attempt(); else finish(0); });
  addEventListener('pagehide', function () { finish(0); });
  document.addEventListener('visibilitychange', function () { if (document.hidden) { if (started) finish(0); } else attempt(); });
  setTimeout(function () { if (!started) finish(0); }, 25000);   // ventana sin audio: suelta el micrófono igual
  fetch('/api/state', { credentials: 'same-origin' }).then(function (r) { if (!r.ok) throw Error('No session'); return r.json(); })
    .then(function (s) { settings = s.startup || {}; attempt(); }).catch(function () { finish(0); });
})();
