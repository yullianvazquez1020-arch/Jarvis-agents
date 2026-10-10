/* Jarvis desktop, screen 1. Everything from the server is rendered with textContent (never as HTML).
   This page never sees the device token or any key: it only talks to the local companion (same origin). */
(function () {
  "use strict";
  var W = window.JarvisWav, M = window.JarvisMask;
  var $ = function (id) { return document.getElementById(id); };
  var windowId = rid();
  var isOwner = false, seq = 0, current = null, rec = null, audioEl = null, state = { prefs: {} };
  var revealed = false, lastReply = "", lastPanel = null;
  var PANEL_NAMES = { agenda: 1, cobros: 1, practica: 1, estado: 1, brief: 1, caja: 1 };
  var HUD_NAMES = { cobros: 1, vencidos: 1, agenda: 1, balances: 1, stock: 1, mensajes: 1, practica: 1 };
  var clockFmt = new Intl.DateTimeFormat("es-PR", { timeZone: "America/Puerto_Rico", hour: "2-digit", minute: "2-digit",
                                                   weekday: "short", day: "numeric", month: "short" });

  function rid() {
    var a = new Uint8Array(12); (window.crypto || window.msCrypto).getRandomValues(a);
    return Array.prototype.map.call(a, function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
  }
  function api(method, path, body, raw) {
    var opt = { method: method, credentials: "same-origin", headers: { "X-Jarvis-UI": "1" } };
    if (raw) { opt.body = raw; opt.headers["Content-Type"] = "audio/wav"; }
    else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
    return fetch(path, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) { var e = new Error(j.error || ("error " + r.status)); e.status = r.status; throw e; }
        return j;
      });
    });
  }
  function discreet() { return !!(state.prefs && state.prefs.discreet); }
  function show(text) { return discreet() && !revealed ? M.mask(text) : String(text == null ? "" : text); }

  // ---------- top bar ----------
  function setText(id, text, cls) { var el = $(id); el.textContent = text; el.className = cls || ""; }
  function renderHealth(h) {
    if (!h) return;
    $("dot").setAttribute("data-s", h.state);
    $("dot").title = { ok: "Servidor responde", slow: "Servidor con retraso", down: "Sin red", error: "Error del servidor",
                       unpaired: "Sin emparejar", demo: "Modo DEMO", unknown: "Sin comprobar" }[h.state] || h.state;
    var i = h.info || {};
    setText("st-version", i.jarvis_version ? String(i.jarvis_version) : "—");
    setText("st-storage", i.storage ? String(i.storage).split(" ")[0] : "—");
    setText("st-ai", i.ai_configured === undefined ? "—" : (i.ai_configured ? "sí" : "no"), i.ai_configured ? "ok" : "warn");
    setText("st-mode", !i.crypto_mode ? "—" : (i.crypto_mode === "real" ? "REAL" : "PRACTICE"), i.crypto_mode === "real" ? "bad" : "ok");
    setText("st-cb", i.coinbase_connected === undefined ? "—" : (i.coinbase_connected ? "conectado" : "no"));
    setText("st-real", i.real_trading_active === undefined ? "—" : (i.real_trading_active ? "ACTIVO" : "apagado"),
            i.real_trading_active ? "bad" : "ok");
  }
  function tick() { $("st-clock").textContent = clockFmt.format(new Date()); }
  function setState(s, detail) { $("state").textContent = s + (detail ? " — " + detail : ""); }
  function setOwner(own) {
    isOwner = own;
    window.JarvisAudioOwner=own;
    window.dispatchEvent(new CustomEvent("jarvis-audio-owner",{detail:own}));
    $("chip-role").textContent = own ? "Esta ventana: voz y audio" : "Esta ventana: solo muestra";
    $("owner-note").hidden = own; $("talk").disabled = !own;
  }
  function micUi(on) {
    $("mic-dot").textContent = on ? "● micrófono capturando" : "● micrófono apagado";
    $("mic-dot").className = "mic" + (on ? " on" : ""); $("st-mic").textContent = on ? "capturando" : "apagado";
    $("st-mic").className = on ? "bad" : "";
  }

  function loadState() {
    return api("GET", "/api/state").then(function (s) {
      state = s; renderHealth(s.server);
      $("chip-demo").hidden = !s.demo;
      $("pair").hidden = s.demo || !s.server_configured || s.paired;
      $("processing").textContent = s.processing + (s.stt.problem ? " · " + s.stt.problem : "") +
        (s.tts.problem ? " · " + s.tts.problem : "");
      $("review").checked = !!s.prefs.review; $("discreet").checked = !!s.prefs.discreet; $("rate").value = s.prefs.rate;
      if (s.pairing && s.pairing.code && s.pairing.status === "pending") showCode(s.pairing.code);
      if (!window.isSecureContext) setState("error", "este navegador no permite el micrófono aquí; abre http://127.0.0.1 o localhost");
    });
  }

  // ---------- events (long poll; works in Safari without extra APIs) ----------
  function poll() {
    api("GET", "/api/events?since=" + seq + "&window=" + windowId).then(function (r) {
      setOwner(!!r.owner); r.events.forEach(handle); seq = r.seq; poll();
    }).catch(function (e) {
      $("dot").setAttribute("data-s", "down");
      setState("sin conexión con el panel", e.status === 401 ? "abre de nuevo el enlace de la terminal" : "");
      setTimeout(poll, 3000);
    });
  }
  function handle(e) {
    if (e.type === "state") setState(e.state, e.detail || "");
    else if (e.type === "health") renderHealth(e.health);
    else if (e.type === "transcript.final" && e.turn === current) $("transcript").value = e.text;
    else if (e.type === "reply.text") {
      lastReply = e.text; revealed = false; renderReply();
      $("reply-meta").textContent = e.llm ? "Consultó a la IA (usa tokens)" : "Respuesta local, sin tokens";
    }
    else if (e.type === "panel.open" && e.data) renderPanel(e.data);
    else if (e.type === "alert") addAlert(e);
    else if (e.type === "audio.play" && isOwner) play(e.id);
    else if (e.type === "audio.stop") stopAudio();
    else if (e.type === "mic.off") stopMic(true);
    else if (e.type === "mic.on") setState("micrófono listo", "pulsa Hablar o Espacio");
    else if (e.type === "turn.done" || e.type === "turn.error" || e.type === "turn.cancelled") {
      if (e.turn === current) { current = null; $("cancel").disabled = true; }
      if (e.type === "turn.done" && $("convo").checked && isOwner && state.prefs.mic) {
        setTimeout(function () { if (!audioEl || audioEl.paused) startMic(); }, 600);
      }
    }
    else if (e.type === "pairing") { loadState(); $("pair-msg").textContent = pairMsg(e); }
    else if (e.type === "prefs") { state.prefs = e.prefs; $("rate").value = e.prefs.rate; $("discreet").checked = e.prefs.discreet;
      renderReply(); if (lastPanel) renderPanel(lastPanel); }
  }
  function pairMsg(e) {
    return { approved: "Listo: este equipo quedó emparejado (solo lectura).", expired: "El código venció; empieza otra vez.",
             error: "No se pudo emparejar: " + (e.detail || ""), removed: "Emparejamiento borrado o vencido: empareja de nuevo." }[e.status] || "";
  }

  // ---------- reply and detail (masked in discreet mode until "Mostrar") ----------
  function renderReply() {
    $("reply").textContent = show(lastReply);
    $("reveal").hidden = !(discreet() && M.hasSensitive(lastReply + (lastPanel ? (lastPanel.lines || []).join(" ") : "")));
    $("reveal").textContent = revealed ? "Ocultar" : "Mostrar";
  }
  function renderPanel(p) {
    var name = String(p.panel || "");
    if (!PANEL_NAMES[name] && !(name.indexOf("hud:") === 0 && HUD_NAMES[name.slice(4)])) return;
    lastPanel = p;
    $("panel-title").textContent = p.title || name;
    $("panel-badge").hidden = !p.demo; $("panel-badge").textContent = p.demo ? "DEMO · no son tus datos" : "";
    $("panel-asof").textContent = p.as_of ? "Dato del " + String(p.as_of).slice(0, 16).replace("T", " ") : "";
    var ul = $("panel-lines"); while (ul.firstChild) ul.removeChild(ul.firstChild);
    (p.lines || []).forEach(function (t) { var li = document.createElement("li"); li.textContent = show(t); ul.appendChild(li); });
    Array.prototype.forEach.call(document.querySelectorAll(".tabs button"), function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-panel") === name ? "true" : "false");
    });
    renderReply();
    try { sessionStorage.setItem("jarvis-panel", PANEL_NAMES[name] ? name : ""); } catch (err) { /* private mode */ }
  }
  function openPanel(name) { api("POST", "/api/open", { target: name }).catch(function (e) { setState("error", e.message); }); }

  // ---------- alerts strip: once, no popups ----------
  function addAlert(a) {
    var ol = $("alert-list");
    if (ol.firstChild && ol.firstChild.className === "small") ol.removeChild(ol.firstChild);
    var li = document.createElement("li"), k = document.createElement("div"), t = document.createElement("div");
    k.className = "k"; k.textContent = (a.kind || "aviso") + (a.when ? " · " + String(a.when).slice(0, 16) : "") + (a.repeat ? " · repetido" : "");
    t.textContent = show(a.text); li.appendChild(k); li.appendChild(t);
    ol.insertBefore(li, ol.firstChild);
    while (ol.children.length > 12) ol.removeChild(ol.lastChild);
  }

  // ---------- audio out ----------
  function play(id) {
    stopAudio(); audioEl = new Audio("/voice/audio/" + id);
    audioEl.onended = function () { setState("listo"); };
    setState("hablando");
    voice.attach(audioEl, id);
    audioEl.addEventListener("playing",function(){if(window.JarvisAmbience)window.JarvisAmbience.duck(true);});
    audioEl.addEventListener("ended",function(){if(window.JarvisAmbience)window.JarvisAmbience.duck(false);});
    audioEl.play().catch(function () { setState("listo", "toca la página una vez para permitir el audio"); });
  }
  addEventListener("pointerdown", function () {
    if (audioEl && audioEl.paused && audioEl.currentTime===0) audioEl.play().catch(function(){});
  });
  function stopAudio() {
    if(window.JarvisAmbience)window.JarvisAmbience.duck(false);
    if (audioEl) { voice.detach(audioEl); audioEl.pause(); audioEl.src = ""; audioEl = null; }
  }

  // ---------- boca del avatar: envolvente y reloj del audio que suena aquí (ventana /avatar) ----------
  // Se lee el mismo archivo otra vez para calcular la envolvente; la reproducción no pasa por Web Audio,
  // así que un AudioContext suspendido (Safari sin gesto) nunca silencia la voz.
  var voice = (function () {
    var L = window.JarvisLipsync, bc = null, el = null, id = "", timer = 0, ctx = null, raf = 0, generation = 0;
    var measure = /[?&]medir=1\b/.test(location.search), log = [];
    try { if (L && "BroadcastChannel" in window) bc = new BroadcastChannel(L.CHANNEL); } catch (err) { bc = null; }
    function now() { return (performance.timeOrigin || Date.now() - performance.now()) + performance.now(); }
    function post(msg) { if (bc) { try { bc.postMessage(msg); } catch (err) { /* ventana cerrada */ } } }
    function clock() {
      if (!el) return;
      var playing = !el.paused && !el.ended && el.readyState >= 2;
      post({ k: "clock", id: id, t: el.currentTime || 0, at: now(), rate: el.playbackRate || 1, playing: playing });
      if (el.ended) { clearInterval(timer); timer = 0; }
    }
    function frame() {
      raf = 0;                         // reloj en cada cuadro mientras suena; si esta ventana está oculta,
      if (!el || el.paused || el.ended) return;   // el intervalo de 250 ms sigue enviándolo
      clock();
      if (measure && log.length < 20000) log.push([now(), el.currentTime || 0, 1]);
      raf = requestAnimationFrame(frame);
    }
    function startFrames() {
      if (raf) cancelAnimationFrame(raf);
      raf = 0; frame();
    }
    function decoder() {
      if (ctx) return ctx;
      var Off = window.OfflineAudioContext || window.webkitOfflineAudioContext;
      var Ctx = window.AudioContext || window.webkitAudioContext;
      ctx = Off ? new Off(1, 1, 22050) : (Ctx ? new Ctx() : null);
      return ctx;
    }
    function analyse(audioId, ticket) {
      if (!bc) return;
      var started = now();
      fetch("/voice/audio/" + audioId, { credentials: "same-origin" }).then(function (r) {
        if (!r.ok) throw new Error("audio " + r.status);
        return r.arrayBuffer();
      }).then(function (buf) {
        var c = decoder(); if (!c) throw new Error("sin Web Audio");
        return new Promise(function (ok, bad) { c.decodeAudioData(buf, ok, bad); });   // forma con callbacks: Safari antiguo
      }).then(function (audio) {
        if (ticket !== generation || !el || audioId !== id) return;
        var env = L.envelope(audio.getChannelData(0), audio.sampleRate, L.FPS);
        post(L.message(audioId, env)); clock();
        if (measure) log.push(["env", now() - started, env.values.length]);
      }).catch(function (err) {
        if (ticket !== generation || !el) return;
        post({ k: "stop", id: audioId, why: "sin envolvente: " + (err && err.name || "error") });
      });
    }
    var EVENTS = ["playing", "pause", "seeked", "ratechange", "ended", "waiting"];
    return {
      attach: function (audio, audioId) {
        generation++; el = audio; id = String(audioId); log = measure ? [] : log;
        EVENTS.forEach(function (n) { audio.addEventListener(n, clock); });
        audio.addEventListener("playing", startFrames);
        clearInterval(timer); timer = setInterval(clock, 250);
        analyse(id, generation);
      },
      detach: function (audio) {
        generation++;
        if (raf) cancelAnimationFrame(raf);
        raf = 0;
        EVENTS.forEach(function (n) { audio.removeEventListener(n, clock); });
        audio.removeEventListener("playing", startFrames);
        clearInterval(timer); timer = 0; post({ k: "stop", id: id }); el = null;
      },
      log: function () { return measure ? log.slice() : []; }
    };
  })();
  window.JarvisVoiceSync = { log: voice.log };

  // ---------- microphone ----------
  function startMic() {
    if (!isOwner || rec) return;
    if (state.stt && state.stt.problem) { setState("listo", state.stt.problem); $("transcript").focus(); return; }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { setState("error", "este navegador no da acceso al micrófono"); return; }
    stopAudio();                                   // never listen while Jarvis is speaking (no echo loop)
    if (!state.prefs.mic) api("POST", "/api/prefs", { mic: true });
    navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } })
      .then(function (stream) {
        var Ctx = window.AudioContext || window.webkitAudioContext, ctx = new Ctx();
        var src = ctx.createMediaStreamSource(stream), node = ctx.createScriptProcessor(4096, 1, 1);
        var chunks = [], det = new W.Detector({ silenceMs: 1200, maxMs: 30000 });
        rec = { stream: stream, ctx: ctx, node: node, src: src, chunks: chunks, rate: ctx.sampleRate };
        node.onaudioprocess = function (ev) {
          if (!rec) return;
          var data = new Float32Array(ev.inputBuffer.getChannelData(0)); chunks.push(data);
          var r = det.push(data, data.length / rec.rate * 1000);
          if (r === "silence-end" || r === "max") stopMic(false);
          else if (r === "no-speech") { stopMic(true); setState("listo", "no te escuché"); }
        };
        src.connect(node); node.connect(ctx.destination);
        micUi(true); $("talk").classList.add("recording"); $("talk").firstChild.nodeValue = "Detener ";
        setState("escuchando");
      })
      .catch(function () { setState("error", "permiso de micrófono denegado"); });
  }
  function stopMic(discard) {
    var r = rec; if (!r) return; rec = null;
    try { r.node.disconnect(); r.src.disconnect(); } catch (err) { /* already closed */ }
    r.stream.getTracks().forEach(function (t) { t.stop(); });   // the indicator goes off immediately
    r.ctx.close(); micUi(false); $("talk").classList.remove("recording"); $("talk").firstChild.nodeValue = "Hablar ";
    if (discard) { setState("listo"); return; }
    var n = 0; r.chunks.forEach(function (c) { n += c.length; });
    var all = new Float32Array(n), o = 0; r.chunks.forEach(function (c) { all.set(c, o); o += c.length; });
    var wav = W.encodeWav(W.downsample(all, r.rate, W.OUT_RATE));
    setState("transcribiendo");
    api("POST", "/voice/transcribe", undefined, wav).then(function (t) {
      $("transcript").value = t.text;
      if (!t.text) { setState("listo", "no entendí nada"); return; }
      if (!$("review").checked) send(t.text, "voice"); else setState("listo", "revisa el texto y pulsa Enviar");
    }).catch(function (e) { setState("error", e.message); });
  }

  // ---------- turns ----------
  function send(text, source) {
    text = String(text || "").trim(); if (!text || current) return;
    current = rid() + rid().slice(0, 4);
    $("cancel").disabled = false; lastReply = ""; renderReply();
    api("POST", "/conversation/turns", { request_id: current, text: text, source: source || "text" })
      .catch(function (e) { setState("error", e.message); current = null; $("cancel").disabled = true; });
  }

  // ---------- wiring ----------
  function showCode(code) { $("pair-code").hidden = false; $("pair-code").textContent = code;
    $("pair-msg").textContent = "En tu chat privado de Telegram con Jarvis escribe: /emparejar " + code; }

  $("talk").onclick = function () { rec ? stopMic(false) : startMic(); };
  $("send").onclick = function () { send($("transcript").value, "text"); };
  $("cancel").onclick = function () { if (current) api("POST", "/conversation/turns/" + current + "/cancel", {}).then(function (r) {
    $("reply-meta").textContent = r.note; }); };
  $("repeat").onclick = function () { send("repite", "text"); };
  $("stop").onclick = function () { stopAudio(); api("POST", "/api/audio/stop", {}); };
  $("mic-off").onclick = function () { stopMic(true); api("POST", "/api/prefs", { mic: false }); };
  $("claim").onclick = function () { api("POST", "/api/audio/claim", { window: windowId }).then(function () { setOwner(true); }); };
  $("review").onchange = function () { api("POST", "/api/prefs", { review: this.checked }); };
  $("discreet").onchange = function () { revealed = false; api("POST", "/api/prefs", { discreet: this.checked }); };
  $("rate").onchange = function () { api("POST", "/api/prefs", { rate: parseFloat(this.value) }); };
  $("reveal").onclick = function () { revealed = !revealed; renderReply(); if (lastPanel) renderPanel(lastPanel); };
  $("alert-silence").onclick = function () { stopAudio(); api("POST", "/api/alerts/silence", {}); };
  $("alert-repeat").onclick = function () { api("POST", "/api/alerts/repeat", {}); };
  $("pair-start").onclick = function () { api("POST", "/api/pair/start", {}).then(function (r) { showCode(r.code); })
    .catch(function (e) { $("pair-msg").textContent = e.message; }); };
  Array.prototype.forEach.call(document.querySelectorAll(".tabs button"), function (b) {
    b.onclick = function () { openPanel(b.getAttribute("data-panel")); };
  });
  $("transcript").onkeydown = function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("send").click(); } };
  document.addEventListener("keydown", function (e) {
    var tag = (document.activeElement && document.activeElement.tagName) || "";
    if (e.key === "Escape") { stopAudio(); if (rec) stopMic(true); }
    else if ((e.key === " " || e.code === "Space") && tag !== "TEXTAREA" && tag !== "INPUT" && tag !== "BUTTON") {
      e.preventDefault(); $("talk").click();
    }
  });

  tick(); setInterval(tick, 15000);
  api("POST", "/api/window/hello", { window: windowId }).then(function (r) { setOwner(r.owner); })
    .then(loadState).then(function () {
      var last = null; try { last = sessionStorage.getItem("jarvis-panel"); } catch (err) { /* ignore */ }
      if (last && PANEL_NAMES[last]) openPanel(last);
      setState("listo"); poll();
      if (isOwner && state.startup && state.startup.audio && !state.tts.problem) {
        api("POST", "/conversation/turns", {request_id:rid(),text:"estado del sistema",source:"text"})
          .catch(function(e){setState("listo",e.message);});
      }
    }).catch(function (e) { setState("error", e.message); });
})();
