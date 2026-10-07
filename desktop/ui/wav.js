/* Microphone samples -> WAV PCM 16-bit mono 16 kHz, plus a simple energy-based end-of-phrase detector.
   No dependencies. Works in Safari (window.JarvisWav) and in Node for the tests (module.exports). */
(function (root) {
  "use strict";
  var OUT_RATE = 16000;

  function downsample(input, inRate, outRate) {
    outRate = outRate || OUT_RATE;
    if (inRate === outRate) return new Float32Array(input);
    if (inRate < outRate) throw new Error("sample rate too low");
    var ratio = inRate / outRate, len = Math.floor(input.length / ratio), out = new Float32Array(len);
    for (var i = 0; i < len; i++) {            // average each block (simple low-pass, good for speech)
      var start = Math.floor(i * ratio), end = Math.min(input.length, Math.floor((i + 1) * ratio)), sum = 0;
      for (var k = start; k < end; k++) sum += input[k];
      out[i] = end > start ? sum / (end - start) : 0;
    }
    return out;
  }

  function encodeWav(samples, rate) {
    rate = rate || OUT_RATE;
    var buf = new ArrayBuffer(44 + samples.length * 2), v = new DataView(buf);
    function str(o, s) { for (var i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); }
    str(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); str(8, "WAVE"); str(12, "fmt ");
    v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, rate, true);
    v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, "data");
    v.setUint32(40, samples.length * 2, true);
    for (var i = 0; i < samples.length; i++) {
      var s = Math.max(-1, Math.min(1, samples[i]));
      v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return buf;
  }

  function rms(frame) {
    var sum = 0;
    for (var i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
    return Math.sqrt(sum / Math.max(1, frame.length));
  }

  /* End-of-phrase: speech starts when level > threshold; the phrase ends after silenceMs below it.
     Returns "speech" | "silence-end" | "no-speech" | "max" | null for each frame. */
  function Detector(opts) {
    opts = opts || {};
    this.threshold = opts.threshold || 0.015; this.silenceMs = opts.silenceMs || 1200;
    this.noSpeechMs = opts.noSpeechMs || 8000; this.maxMs = opts.maxMs || 30000;
    this.t = 0; this.heard = false; this.quiet = 0;
  }
  Detector.prototype.push = function (frame, ms) {
    this.t += ms;
    var loud = rms(frame) > this.threshold;
    if (loud) { this.heard = true; this.quiet = 0; }
    else if (this.heard) this.quiet += ms;
    if (this.t >= this.maxMs) return "max";
    if (!this.heard && this.t >= this.noSpeechMs) return "no-speech";
    if (this.heard && this.quiet >= this.silenceMs) return "silence-end";
    return loud ? "speech" : null;
  };

  var api = { downsample: downsample, encodeWav: encodeWav, rms: rms, Detector: Detector, OUT_RATE: OUT_RATE };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.JarvisWav = api;
})(this);
