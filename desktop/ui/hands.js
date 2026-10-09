/* MediaPipe Hand Landmarker. Se descarga al pulsar el botón.
   Los cuadros de la cámara no se envían a Jarvis ni a Render. */
(function () {
  "use strict";
  var VISION = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.17";
  var MODEL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";
  var video = document.getElementById("hand-video");
  var status = document.getElementById("hand-status");
  var button = document.getElementById("hands");
  var stream = null;
  var landmarker = null;
  var running = false;
  var loading = false;
  var generation = 0;
  var lastDetection = 0;
  var lastVideoTime = -1;
  var state = { x: 0, y: 0, open: 0, seen: false, landmarks: null, updatedAt: 0 };

  function say(text) { if (status) status.textContent = text; }

  function decay() {
    state.seen = false;
    state.landmarks = null;
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

  function loop() {
    if (!running) return;
    requestAnimationFrame(loop);
    if (document.hidden) { decay(); return; }
    if (performance.now() - lastDetection < 1000 / 15) return;
    if (!landmarker || !video || video.readyState < 2) return;
    if (video.currentTime === lastVideoTime) return;
    lastVideoTime = video.currentTime;
    lastDetection = performance.now();
    var result;
    try {
      result = landmarker.detectForVideo(video, performance.now());
    } catch (e) {
      decay();
      return;
    }
    var hands = result && result.landmarks;
    if (!hands || !hands.length) decay();
    else apply(hands[0]);
  }

  function stop() {
    generation++;
    loading = false;
    running = false;
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    stream = null;
    if (video) video.srcObject = null;
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
    loading = true;
    var ticket = ++generation;
    say("Cargando MediaPipe…");
    var ready = landmarker ? Promise.resolve() : import(VISION).then(function (vision) {
      return vision.FilesetResolver.forVisionTasks(VISION + "/wasm").then(function (files) {
        return vision.HandLandmarker.createFromOptions(files, {
          baseOptions: { modelAssetPath: MODEL, delegate: "CPU" },
          runningMode: "VIDEO",
          numHands: 1,
          minHandDetectionConfidence: 0.6,
          minTrackingConfidence: 0.5
        });
      });
    }).then(function (created) { landmarker = created; });

    ready.then(function () {
      if (ticket !== generation) throw new Error("Inicio cancelado");
      return navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: "user" },
        audio: false
      });
    }).then(function (s) {
      if (ticket !== generation) { s.getTracks().forEach(function (t) { t.stop(); }); throw new Error("Inicio cancelado"); }
      stream = s;
      video.srcObject = s;
      return video.play();
    }).then(function () {
      if (ticket !== generation) return;
      loading = false;
      running = true;
      if (button) {
        button.textContent = "Apagar mano";
        button.setAttribute("aria-pressed", "true");
      }
      say("MediaPipe activo, 21 puntos, CPU. La imagen no se envía.");
      requestAnimationFrame(loop);
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
