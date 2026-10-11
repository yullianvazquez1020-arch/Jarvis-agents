/* Reconocimiento facial local con Logitech Brio. Cuadros no salen de la página. */
(function () {
  "use strict";
  var video = document.getElementById("face-video") || document.createElement("video");
  video.id = "face-video";
  video.muted = true;
  video.playsInline = true;
  video.setAttribute("aria-hidden", "true");
  var status = document.getElementById("face-status") || document.createElement("p");
  status.id = "face-status";
  status.setAttribute("role", "status");
  var button = document.getElementById("face") || document.createElement("button");
  button.id = "face";
  button.type = "button";
  button.textContent = "Activar rostro";
  var enrollBtn = document.getElementById("face-enroll") || document.createElement("button");
  enrollBtn.id = "face-enroll";
  enrollBtn.type = "button";
  enrollBtn.textContent = "Enrolar dueño";
  var stream = null;
  var worker = null;
  var rejectReady = null;
  var watchdog = null;
  var busy = false;
  var frameId = 0;
  var cameraChannel = typeof BroadcastChannel === "function" ? new BroadcastChannel("jarvis-camera-owner") : null;
  var cameraId = String(Math.random());
  if (cameraChannel) cameraChannel.onmessage = function (event) {
    if (event.data && event.data.type === "active" && event.data.id !== cameraId && (running || loading)) {
      stop(); say("La cámara está activa en otra ventana. Esta dejó el rostro libre.");
    }
  };
  var capture = document.createElement("canvas");
  capture.width = 320;
  capture.height = 240;
  var captureContext = capture.getContext("2d");
  var running = false;
  var loading = false;
  var generation = 0;
  var lastDetection = 0;
  var lastVideoTime = -1;
  var state = {
    present: false,
    recognized: false,
    confidence: 0,
    count: 0,
    landmarks: null,
    blendshapes: null,
    updatedAt: 0,
    running: false,
    camera: "",
    inferenceMs: 0,
    enrolled: false
  };
  var selector = document.createElement("select");
  selector.id = "face-camera";
  selector.setAttribute("aria-label", "Cámara para el rostro");
  var automatic = document.createElement("option");
  automatic.value = "";
  automatic.textContent = "Logitech Brio (automática)";
  selector.appendChild(automatic);

  function attachIfNeeded() {
    var container = document.querySelector(".stage") || document.body;
    if (!document.getElementById("face-video")) container.appendChild(video);
    if (!document.getElementById("face-status")) document.body.appendChild(status);
    var controls = document.querySelector(".stage + div") || document.body;
    if (!document.getElementById("face")) controls.appendChild(button);
    if (!document.getElementById("face-enroll")) controls.appendChild(enrollBtn);
    if (!document.getElementById("face-camera")) controls.appendChild(selector);
  }
  attachIfNeeded();

  var savedCamera = "";
  try { savedCamera = localStorage.getItem("jarvis-face-camera-v1") || ""; } catch (_) {}
  selector.onchange = function () {
    savedCamera = selector.value;
    try { localStorage.setItem("jarvis-face-camera-v1", savedCamera); } catch (_) {}
    stop(); say("Cámara seleccionada. Pulsa Activar rostro.");
  };

  function release(s) { if (s) s.getTracks().forEach(function (t) { t.stop(); }); }

  async function cameraStream(ticket) {
    var selected = selector.value || savedCamera;
    var devices = await navigator.mediaDevices.enumerateDevices();
    if (ticket !== generation) throw new Error("Inicio cancelado");
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
    if (!chosen) throw new Error("No aparece la Brio o la cámara elegida. Revisa el USB.");
    var s = await navigator.mediaDevices.getUserMedia({
      video: { deviceId: { exact: chosen.deviceId }, width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30, max: 30 } },
      audio: false
    });
    if (ticket !== generation) { release(s); throw new Error("Inicio cancelado"); }
    state.camera = s.getVideoTracks()[0].label || chosen.label;
    return s;
  }

  function say(text) { if (status) status.textContent = text; }

  function simpleSignature(landmarks) {
    if (!landmarks || landmarks.length < 20) return null;
    // Distances between key points as a simple embedding (nose, eyes, mouth).
    var pts = [landmarks[1], landmarks[33], landmarks[263], landmarks[61], landmarks[291], landmarks[13], landmarks[14]];
    var sig = [];
    for (var i = 0; i < pts.length; i++) {
      for (var j = i + 1; j < pts.length; j++) {
        var dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y;
        sig.push(Math.hypot(dx, dy));
      }
    }
    return sig;
  }

  function distance(a, b) {
    if (!a || !b || a.length !== b.length) return Infinity;
    var sum = 0;
    for (var i = 0; i < a.length; i++) sum += (a[i] - b[i]) * (a[i] - b[i]);
    return Math.sqrt(sum / a.length);
  }

  var enrolledSig = null;
  try {
    var raw = localStorage.getItem("jarvis-face-enrolled-v1");
    if (raw) enrolledSig = JSON.parse(raw);
    state.enrolled = !!enrolledSig;
  } catch (_) {}

  function applyResult(message) {
    var faces = message.faceLandmarks || [];
    state.count = faces.length;
    if (!faces.length) {
      state.present = false;
      state.recognized = false;
      state.confidence = 0;
      state.landmarks = null;
      state.blendshapes = null;
      return;
    }
    var primary = faces[0];
    state.present = true;
    state.landmarks = primary.map(function (p) { return { x: 1 - p.x, y: p.y, z: p.z || 0 }; });
    state.blendshapes = message.faceBlendshapes && message.faceBlendshapes[0] ? message.faceBlendshapes[0].categories : null;
    state.updatedAt = lastDetection;
    var sig = simpleSignature(primary);
    if (enrolledSig && sig) {
      var d = distance(sig, enrolledSig);
      state.confidence = Math.max(0, Math.min(1, 1 - d / 0.15));
      state.recognized = d < 0.08;
    } else {
      state.recognized = false;
      state.confidence = 0.5;
    }
    document.dispatchEvent(new CustomEvent("jarvis-face-frame", { detail: state }));
  }

  function fail(message) { stop(); say(message); }

  function startWorker(ticket) {
    return new Promise(function (resolve, reject) {
      rejectReady = reject;
      worker = new Worker("/ui/face-worker.js");
      worker.onmessage = function (event) {
        if (ticket !== generation) return;
        var message = event.data || {};
        if (message.type === "ready") {
          clearTimeout(watchdog);
          watchdog = null;
          rejectReady = null;
          state.backend = message.backend || "CPU";
          state.fallbackReason = message.fallbackReason || "";
          resolve();
        } else if (message.type === "error") {
          fail("Detector facial detenido: " + message.message);
        } else if (message.type === "result" && busy && message.id === frameId) {
          clearTimeout(watchdog);
          watchdog = null;
          busy = false;
          state.inferenceMs = Math.round(Math.max(1, performance.now() - lastDetection));
          state.backend = message.backend || state.backend;
          if (document.hidden || performance.now() - lastDetection > 400) {
            state.present = false;
            state.recognized = false;
          } else applyResult(message);
          say("Cámara: " + state.camera + " · " + state.count + " rostro(s) · " + (state.recognized ? "Dueño reconocido" : state.present ? "Presente" : "Sin rostro") + " · " + state.inferenceMs + " ms");
        }
      };
      worker.onerror = function (event) {
        if (ticket !== generation) return;
        if (event.preventDefault) event.preventDefault();
        fail("No arrancó el detector facial: " + (event.message || "error"));
      };
      watchdog = setTimeout(function () {
        if (ticket === generation) fail("La carga del detector facial superó 40 segundos.");
      }, 40000);
      worker.postMessage({ type: "init", delegate: "AUTO" });
    });
  }

  function loop(ticket) {
    if (!running || ticket !== generation) return;
    requestAnimationFrame(function () { loop(ticket); });
    if (document.hidden) { state.present = false; return; }
    if (busy || performance.now() - lastDetection < 1000 / 15) return;
    if (!worker || !video || video.readyState < 2) return;
    if (video.currentTime === lastVideoTime) return;
    lastVideoTime = video.currentTime;
    lastDetection = performance.now();
    busy = true;
    var id = ++frameId;
    watchdog = setTimeout(function () {
      if (ticket === generation) fail("El detector facial tardó demasiado.");
    }, 2500);
    try {
      captureContext.drawImage(video, 0, 0, 320, 240);
      createImageBitmap(capture).then(function (bitmap) {
        if (ticket !== generation || !running) { bitmap.close(); return; }
        try {
          worker.postMessage({ type: "frame", id: id, timestamp: lastDetection, bitmap: bitmap }, [bitmap]);
        } catch (error) {
          bitmap.close();
          fail("No pude entregar el cuadro: " + error.message);
        }
      }).catch(function (error) {
        if (ticket === generation) fail("No pude preparar el cuadro: " + error.message);
      });
    } catch (error) { fail("No pude leer la vista previa: " + error.message); }
  }

  function stop() {
    generation++;
    clearTimeout(watchdog);
    watchdog = null;
    if (worker) { worker.terminate(); worker = null; }
    if (rejectReady) { var reject = rejectReady; rejectReady = null; reject(new Error("Inicio cancelado")); }
    busy = false;
    loading = false;
    running = false;
    state.running = false;
    state.present = false;
    state.recognized = false;
    state.camera = "";
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    stream = null;
    if (video) { video.srcObject = null; }
    lastVideoTime = -1;
    if (button) {
      button.textContent = "Activar rostro";
      button.setAttribute("aria-pressed", "false");
    }
    say("Rostro apagado. Ningún cuadro salió de esta página.");
    document.dispatchEvent(new CustomEvent("jarvis-face-frame", { detail: state }));
  }

  function start() {
    if (loading || running) return;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      say("Este navegador no entregó la cámara.");
      return;
    }
    if (typeof Worker === "undefined" || typeof createImageBitmap === "undefined" || !captureContext) {
      say("Este navegador no permite el detector facial aislado.");
      return;
    }
    loading = true;
    if (button) { button.textContent = "Cancelar rostro"; button.setAttribute("aria-pressed", "true"); }
    var ticket = ++generation;
    say("Cargando detector facial… Puedes cancelar.");
    var ready = startWorker(ticket);

    ready.then(function () {
      if (ticket !== generation) throw new Error("Inicio cancelado");
      return cameraStream(ticket);
    }).then(function (s) {
      if (ticket !== generation) { s.getTracks().forEach(function (t) { t.stop(); }); throw new Error("Inicio cancelado"); }
      stream = s;
      video.srcObject = s;
      return video.play();
    }).then(function () {
      if (ticket !== generation) return;
      loading = false;
      running = true;
      state.running = true;
      if (cameraChannel) cameraChannel.postMessage({ type: "active", id: cameraId });
      stream.getVideoTracks()[0].onended = function () { stop(); say("La cámara se desconectó."); };
      if (button) {
        button.textContent = "Apagar rostro";
        button.setAttribute("aria-pressed", "true");
      }
      say("Cámara: " + state.camera + ". Detector facial local. " + (state.enrolled ? "Dueño enrolado." : "Pulsa Enrolar dueño para reconocer."));
      requestAnimationFrame(function () { loop(ticket); });
    }).catch(function (err) {
      if (ticket !== generation) return;
      stop();
      say("No pude iniciar el rostro: " + (err && err.message ? err.message : "permiso o red"));
    });
  }

  function enroll() {
    if (!state.present || !state.landmarks) {
      say("Muestra tu rostro a la Brio y espera detección antes de enrolar.");
      return;
    }
    var sig = simpleSignature(state.landmarks.map(function (p) { return { x: 1 - p.x, y: p.y }; })); // reverse the flip for consistency
    if (!sig) { say("No hay suficientes puntos para enrolar."); return; }
    enrolledSig = sig;
    state.enrolled = true;
    try { localStorage.setItem("jarvis-face-enrolled-v1", JSON.stringify(sig)); } catch (_) {}
    say("Dueño enrolado. El reconocimiento usará esta referencia local.");
  }

  state.start = start;
  state.stop = stop;
  state.enroll = enroll;
  window.JarvisFace = state;
  addEventListener("pagehide", stop);
  addEventListener("keydown", function (e) { if (e.key === "Escape") stop(); });
  if (button) button.onclick = function () { running || loading ? stop() : start(); };
  if (enrollBtn) enrollBtn.onclick = enroll;
  say("Rostro apagado. Usa la Brio para presencia y reconocimiento del dueño.");
})();
