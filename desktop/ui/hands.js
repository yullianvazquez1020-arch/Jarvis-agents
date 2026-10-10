/* MediaPipe Hand Landmarker. Se descarga al pulsar el botón.
   Los cuadros de la cámara no se envían a Jarvis ni a Render. */
(function () {
  "use strict";
  var video = document.getElementById("hand-video");
  var status = document.getElementById("hand-status");
  var button = document.getElementById("hands");
  var stream = null;
  var worker = null;
  var rejectReady = null;
  var watchdog = null;
  var busy = false;
  var frameId = 0;
  var capture = document.createElement("canvas");
  capture.width = 320;
  capture.height = 240;
  var captureContext = capture.getContext("2d");
  var running = false;
  var loading = false;
  var generation = 0;
  var lastDetection = 0;
  var lastVideoTime = -1;
  var state = { x: 0, y: 0, open: 0, seen: false, landmarks: null, updatedAt: 0, running: false, camera: "", hands: [], count: 0 };
  var primaryWrist = null, primaryLabel = "", inferenceMs = 50;
  var selector = document.createElement("select");
  selector.id = "hand-camera";
  selector.setAttribute("aria-label", "Cámara para la mano");
  var automatic = document.createElement("option");
  automatic.value = "";
  automatic.textContent = "Logitech Brio (automática)";
  selector.appendChild(automatic);
  if (button) button.parentNode.appendChild(selector);
  if (video && status) status.parentNode.insertBefore(video, status);
  var savedCamera = "";
  try { savedCamera = localStorage.getItem("jarvis-hand-camera-v1") || ""; } catch (_) {}
  selector.onchange = function () {
    savedCamera = selector.value;
    try { localStorage.setItem("jarvis-hand-camera-v1", savedCamera); } catch (_) {}
    stop(); say("Cámara seleccionada. Pulsa Activar mano."); };

  function release(s) { if (s) s.getTracks().forEach(function (t) { t.stop(); }); }

  async function cameraStream(ticket) {
    var selected = selector.value || savedCamera;
    var devices = await navigator.mediaDevices.enumerateDevices();
    if (ticket !== generation) throw new Error("Inicio cancelado");
    // Labels may require a camera permission first. Release that temporary stream.
    if (!devices.some(function (d) { return d.kind === "videoinput" && d.label; })) {
      var permission = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      release(permission);
      if (ticket !== generation) throw new Error("Inicio cancelado");
      devices = await navigator.mediaDevices.enumerateDevices();
    }
    if (ticket !== generation) throw new Error("Inicio cancelado");
    var cameras = devices.filter(function (d) { return d.kind === "videoinput"; });
    while (selector.options.length > 1) selector.remove(1);
    cameras.forEach(function (d, i) {
      var option = document.createElement("option");
      option.value = d.deviceId;
      option.textContent = d.label || "Cámara " + (i + 1);
      selector.appendChild(option);
    });
    selector.value = selected;
    var chosen = cameras.find(function (d) { return selected ? d.deviceId === selected : /brio/i.test(d.label); });
    if (!chosen) throw new Error("No aparece la Brio o la cámara elegida. Revisa el USB o elige otra cámara.");
    var s = await navigator.mediaDevices.getUserMedia({
      video: { deviceId: { exact: chosen.deviceId }, width: { ideal: 320 }, height: { ideal: 240 }, frameRate: { ideal: 24, max: 30 } },
      audio: false
    });
    if (ticket !== generation) { release(s); throw new Error("Inicio cancelado"); }
    state.camera = s.getVideoTracks()[0].label || chosen.label;
    return s;
  }

  function say(text) { if (status) status.textContent = text; }

  function decay() {
    state.seen = false;
    state.landmarks = null;
    state.hands = []; state.count = 0;
    state.x *= 0.85;
    state.y *= 0.85;
    state.open *= 0.85;
  }

  function apply(landmarks) {
    var wrist = landmarks[0];
    var tip = landmarks[12];
    var screenX = 1 - wrist.x;
    state.x = Math.max(-1, Math.min(1, (screenX - 0.5) * 2));
    state.y = Math.max(-1, Math.min(1, (wrist.y - 0.5) * 2));
    state.open = Math.max(0, Math.min(1, (Math.hypot(tip.x - wrist.x, tip.y - wrist.y) - 0.12) / 0.28));
    state.seen = true;
    state.updatedAt = performance.now();
    state.landmarks = landmarks.map(function (p) { return { x: 1 - p.x, y: p.y }; });
  }

  function applyResult(message) {
    var candidates = (message.landmarks || []).map(function (points, index) {
      var category = message.handedness && message.handedness[index] && message.handedness[index][0];
      return {points:points, label:category ? category.categoryName : ""};
    }).filter(function (item) { return item.points.length === 21 && item.points.every(function(p) { return Number.isFinite(p.x) && Number.isFinite(p.y); }); });
    if (!candidates.length) { decay(); return; }
    var selected = null, distance = Infinity;
    candidates.forEach(function(item) {
      if (window.JarvisHandMouseActive && primaryLabel && item.label !== primaryLabel) return;
      var d = primaryWrist ? Math.hypot(item.points[0].x-primaryWrist.x,item.points[0].y-primaryWrist.y) : 0;
      if (d < distance) { distance = d; selected = item; }
    });
    // An unseen second hand must never inherit the active pointer or a held drag.
    if (!selected || (window.JarvisHandMouseActive && primaryWrist && distance > .3)) { decay(); return; }
    primaryWrist = {x:selected.points[0].x,y:selected.points[0].y};
    primaryLabel = selected.label;
    apply(selected.points);
    state.hands = candidates.map(function(item) { return {label:item.label, active:item===selected, landmarks:item.points.map(function(p) { return {x:1-p.x,y:p.y}; })}; });
    state.count = state.hands.length;
  }

  function fail(message) { stop(); say(message); }

  function startWorker(ticket) {
    return new Promise(function (resolve, reject) {
      rejectReady = reject;
      worker = new Worker("/ui/hand-worker.js");
      worker.onmessage = function (event) {
        if (ticket !== generation) return;
        var message = event.data || {};
        if (message.type === "ready") {
          clearTimeout(watchdog);
          watchdog = null;
          rejectReady = null;
          resolve();
        } else if (message.type === "error") {
          fail("Detector detenido: " + message.message);
        } else if (message.type === "result" && busy && message.id === frameId) {
          clearTimeout(watchdog);
          watchdog = null;
          busy = false;
          inferenceMs = inferenceMs*.7 + Math.max(1,performance.now()-lastDetection)*.3;
          if (document.hidden || performance.now() - lastDetection > 350) decay();
          else applyResult(message);
        }
      };
      worker.onerror = function (event) {
        if (ticket !== generation) return;
        if (event.preventDefault) event.preventDefault();
        fail("No arrancó el detector aislado: " + (event.message || "error del navegador"));
      };
      watchdog = setTimeout(function () {
        if (ticket === generation) fail("La carga del detector superó 40 segundos. Se detuvo; puedes volver a intentarlo.");
      }, 40000);
      worker.postMessage({ type: "init" });
    });
  }

  function loop(ticket) {
    if (!running || ticket !== generation) return;
    requestAnimationFrame(function () { loop(ticket); });
    if (document.hidden) { decay(); return; }
    if (state.seen && performance.now() - state.updatedAt > 350) decay();
    // Faster sampling only during the explicit mouse trial; still one frame in flight.
    const detectionInterval = Math.max(window.JarvisHandMouseActive ? 45 : 100, Math.min(200,inferenceMs*1.1));
    if (busy || performance.now() - lastDetection < detectionInterval) return;
    if (!worker || !video || video.readyState < 2) return;
    if (video.currentTime === lastVideoTime) return;
    lastVideoTime = video.currentTime;
    lastDetection = performance.now();
    busy = true; // One frame only; never build a queue of images.
    var id = ++frameId;
    watchdog = setTimeout(function () {
      if (ticket === generation) fail("El detector tardó demasiado y se detuvo para proteger el panel.");
    }, 2500);
    try {
      captureContext.drawImage(video, 0, 0, 320, 240);
      createImageBitmap(capture).then(function (bitmap) {
        if (ticket !== generation || !running) { bitmap.close(); return; }
        try {
          worker.postMessage({ type: "frame", id: id, timestamp: lastDetection, bitmap: bitmap }, [bitmap]);
        } catch (error) {
          bitmap.close();
          fail("No pude entregar el cuadro al detector: " + error.message);
        }
      }).catch(function (error) {
        if (ticket === generation) fail("No pude preparar el cuadro: " + error.message);
      });
    } catch (error) { fail("No pude leer la vista previa: " + error.message); }
  }

  function stop() {
    generation++;
    primaryWrist = null; primaryLabel = ""; inferenceMs = 50;
    clearTimeout(watchdog);
    watchdog = null;
    if (worker) { worker.terminate(); worker = null; }
    if (rejectReady) { var reject = rejectReady; rejectReady = null; reject(new Error("Inicio cancelado")); }
    busy = false;
    loading = false;
    running = false;
    state.running = false;
    state.camera = "";
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    stream = null;
    if (video) { video.srcObject = null; video.classList.remove("preview-active"); }
    lastVideoTime = -1;
    decay();
    if (button) {
      button.textContent = "Activar mano";
      button.setAttribute("aria-pressed", "false");
    }
    say("Cámara apagada. Ningún cuadro salió de esta página.");
  }

  function start() {
    if (loading || running) return;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      say("Este navegador no entregó la cámara.");
      return;
    }
    if (typeof Worker === "undefined" || typeof createImageBitmap === "undefined" || !captureContext) {
      say("Este navegador no permite el detector aislado. No se iniciará en el hilo del avatar.");
      return;
    }
    loading = true;
    if (button) { button.textContent = "Cancelar mano"; button.setAttribute("aria-pressed", "true"); }
    var ticket = ++generation;
    say("Cargando detector aislado… Puedes cancelar. La cámara aún está apagada.");
    var ready = startWorker(ticket);

    ready.then(function () {
      if (ticket !== generation) throw new Error("Inicio cancelado");
      return cameraStream(ticket);
    }).then(function (s) {
      if (ticket !== generation) { s.getTracks().forEach(function (t) { t.stop(); }); throw new Error("Inicio cancelado"); }
      stream = s;
      video.srcObject = s;
      video.classList.add("preview-active");
      return video.play();
    }).then(function () {
      if (ticket !== generation) return;
      loading = false;
      running = true;
      state.running = true;
      stream.getVideoTracks()[0].onended = function () { stop(); say("La cámara se desconectó. Pulsa Activar mano para reconectar."); };
      if (button) {
        button.textContent = "Apagar mano";
        button.setAttribute("aria-pressed", "true");
      }
      say("Cámara: " + state.camera + ". Detector aislado, máximo 5 análisis/s; muestra una mano. Vista previa local, sin envío.");
      requestAnimationFrame(function () { loop(ticket); });
    }).catch(function (err) {
      if (ticket !== generation) return;
      stop();
      say("No pude iniciar la mano: " + (err && err.message ? err.message : "permiso o red"));
    });
  }

  window.JarvisHands = state;
  addEventListener("pagehide", stop);
  addEventListener("keydown", function (e) { if (e.key === "Escape") stop(); });
  if (button) button.onclick = function () { running || loading ? stop() : start(); };
  say("Mano apagada.");
})();
