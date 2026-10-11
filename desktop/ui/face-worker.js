/* Dedicated classic worker for Face Landmarker. Inference stays off the UI thread. */
"use strict";
const VISION = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.17";
const MODEL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
let detector = null, initializing = false, vision = null, files = null;
let backend = "CPU", fallbackReason = "";
async function build(delegate) {
  return vision.FaceLandmarker.createFromOptions(files, {
    baseOptions: { modelAssetPath: MODEL, delegate },
    runningMode: "VIDEO",
    numFaces: 2,
    minFaceDetectionConfidence: 0.5,
    minFacePresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
    outputFaceBlendshapes: true,
    outputFacialTransformationMatrixes: false
  });
}
self.onmessage = async function (event) {
  const message = event.data || {};
  if (message.type === "init") {
    if (initializing || detector) return;
    initializing = true;
    try {
      vision = await import(VISION + "/vision_bundle.mjs");
      files = await vision.FilesetResolver.forVisionTasks(VISION + "/wasm");
      if (message.delegate !== "CPU") {
        try { detector = await build("GPU"); backend = "GPU"; }
        catch (_) { fallbackReason = "GPU no disponible; usando CPU"; }
      }
      if (!detector) { detector = await build("CPU"); backend = "CPU"; }
      self.postMessage({ type: "ready", backend, fallbackReason });
    } catch (error) {
      self.postMessage({ type: "error", message: error.message || "No arrancó el detector facial" });
    }
    return;
  }
  if (message.type !== "frame") return;
  try {
    if (!detector) throw new Error("El detector facial no está listo");
    const began = performance.now();
    const result = detector.detectForVideo(message.bitmap, message.timestamp);
    self.postMessage({
      type: "result",
      id: message.id,
      faceLandmarks: result.faceLandmarks || [],
      faceBlendshapes: result.faceBlendshapes || [],
      detectorMs: Math.max(0, performance.now() - began),
      backend,
      fallbackReason
    });
  } catch (error) {
    if (backend === "GPU") {
      try {
        try { detector.close(); } catch (_) {}
        detector = null;
        backend = "CPU";
        detector = await build("CPU");
        fallbackReason = "GPU interrumpida; usando CPU";
        self.postMessage({ type: "result", id: message.id, faceLandmarks: [], faceBlendshapes: [], backend, fallbackReason });
      } catch (fallbackError) {
        self.postMessage({ type: "error", message: fallbackError.message || "No se pudo recuperar el detector facial" });
      }
    } else self.postMessage({ type: "error", message: error.message || "Falló la detección facial" });
  } finally {
    if (message.bitmap) message.bitmap.close();
  }
};
