/* Dedicated classic worker: both WASM startup and inference stay off the UI.
   A classic worker also permits the WASM loader's importScripts calls. */
"use strict";
const VISION = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.17";
const MODEL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";
let detector = null, initializing = false, vision = null, files = null;
let backend = "CPU", numHands = 2, fallbackReason = "";
async function build(delegate) {
  return vision.HandLandmarker.createFromOptions(files, {
    canvas: new OffscreenCanvas(320, 240),
    baseOptions: { modelAssetPath: MODEL, delegate },
    runningMode: "VIDEO", numHands,
    minHandDetectionConfidence: 0.6, minTrackingConfidence: 0.5
  });
}
self.onmessage = async function (event) {
  const message = event.data || {};
  if (message.type === "init") {
    if (initializing || detector) return;
    initializing = true;
    numHands = message.numHands === 1 ? 1 : 2;
    try {
      if (typeof OffscreenCanvas === "undefined") throw new Error("Este navegador no permite el detector aislado. La cámara queda apagada.");
      vision = await import(VISION + "/vision_bundle.mjs");
      files = await vision.FilesetResolver.forVisionTasks(VISION + "/wasm");
      if (message.delegate !== "CPU") {
        try { detector = await build("GPU"); backend = "GPU"; }
        catch (_) { fallbackReason = "GPU no disponible; usando CPU"; }
      }
      if (!detector) { detector = await build("CPU"); backend = "CPU"; }
      self.postMessage({ type: "ready", backend, numHands, fallbackReason });
    } catch (error) {
      self.postMessage({ type: "error", message: error.message || "No arrancó el detector aislado" });
    }
    return;
  }
  if (message.type !== "frame") return;
  try {
    if (!detector) throw new Error("El detector no está listo");
    const began = performance.now();
    const result = detector.detectForVideo(message.bitmap, message.timestamp);
    self.postMessage({ type: "result", id: message.id, landmarks: result.landmarks, handedness: result.handedness,
      detectorMs: Math.max(0, performance.now() - began), backend, fallbackReason });
  } catch (error) {
    if (backend === "GPU") {
      // A lost GPU context must not leave old landmarks controlling the pointer.
      try {
        try { detector.close(); } catch (_) {}
        detector = null;
        backend = "CPU";
        detector = await build("CPU");
        fallbackReason = "GPU interrumpida; usando CPU";
        self.postMessage({ type: "result", id: message.id, landmarks: [], handedness: [], backend, fallbackReason });
      } catch (fallbackError) {
        self.postMessage({ type: "error", message: fallbackError.message || "No se pudo recuperar el detector" });
      }
    } else self.postMessage({ type: "error", message: error.message || "Falló la detección" });
  } finally {
    if (message.bitmap) message.bitmap.close();
  }
};
