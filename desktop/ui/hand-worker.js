/* Dedicated classic worker: both WASM startup and inference stay off the UI.
   A classic worker also permits the WASM loader's importScripts calls. */
"use strict";
const VISION = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.17";
const MODEL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";
let detector = null;
let initializing = false;
self.onmessage = async function (event) {
  const message = event.data || {};
  if (message.type === "init") {
    if (initializing || detector) return;
    initializing = true;
    try {
      if (typeof OffscreenCanvas === "undefined") throw new Error("Este navegador no permite el detector aislado. La cámara queda apagada.");
      const vision = await import(VISION + "/vision_bundle.mjs");
      const files = await vision.FilesetResolver.forVisionTasks(VISION + "/wasm");
      detector = await vision.HandLandmarker.createFromOptions(files, {
        canvas: new OffscreenCanvas(320, 240),
        baseOptions: { modelAssetPath: MODEL, delegate: "CPU" },
        runningMode: "VIDEO", numHands: 1,
        minHandDetectionConfidence: 0.6, minTrackingConfidence: 0.5
      });
      self.postMessage({ type: "ready" });
    } catch (error) {
      self.postMessage({ type: "error", message: error.message || "No arrancó el detector aislado" });
    }
    return;
  }
  if (message.type !== "frame") return;
  try {
    if (!detector) throw new Error("El detector no está listo");
    const result = detector.detectForVideo(message.bitmap, message.timestamp);
    self.postMessage({ type: "result", id: message.id, landmarks: result.landmarks });
  } catch (error) {
    self.postMessage({ type: "error", message: error.message || "Falló la detección" });
  } finally {
    if (message.bitmap) message.bitmap.close();
  }
};
