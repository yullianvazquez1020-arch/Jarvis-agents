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

  /* Keep a short onset margin, not seconds of idle microphone audio. Once speech
     starts retain every sample, including pauses and the final silence. */
  function CaptureBuffer(rate, preRollMs) {
    this.limit = Math.ceil(rate * (preRollMs || 300) / 1000);
    this.frames = []; this.samples = 0; this.started = false;
  }
  CaptureBuffer.prototype.push = function (frame, speech) {
    if (speech) this.started = true;
    this.frames.push(frame); this.samples += frame.length;
    if (!this.started) {
      while (this.frames.length && this.samples > this.limit) {
        var excess = this.samples - this.limit, first = this.frames[0];
        if (first.length <= excess) { this.frames.shift(); this.samples -= first.length; }
        else { this.frames[0] = first.slice(excess); this.samples -= excess; }
      }
    }
  };
  CaptureBuffer.prototype.audio = function () {
    var out = new Float32Array(this.samples), offset = 0;
    this.frames.forEach(function (frame) { out.set(frame, offset); offset += frame.length; });
    return out;
  };

  /* End-of-phrase: speech starts when level > threshold; the phrase ends after silenceMs below it.
     Returns "speech" | "silence-end" | "no-speech" | "max" | null for each frame.
     Opcional (el panel lo activa; por defecto se comporta como antes):
       adaptive: el umbral sube con el ruido de fondo (noiseFactor veces el ruido medido, ruido máximo 0.04).
         Al abrir, calibrateMs mide el ruido (el nivel más bajo) sin aceptar voz; noise: medida de un turno anterior.
       minStartMs: hace falta sonido sostenido para empezar una frase; un clic o un golpe no la abren.
       minSpeechMs: una "frase" con menos voz que esto se descarta en silencio y no se transcribe. */
  function Detector(opts) {
    opts = opts || {};
    this.threshold = opts.threshold || 0.015; this.silenceMs = opts.silenceMs || 1200;
    this.noSpeechMs = opts.noSpeechMs || 8000; this.maxMs = opts.maxMs || 30000;
    this.adaptive = !!opts.adaptive; this.noiseFactor = opts.noiseFactor || 2.5;
    this.minStartMs = opts.minStartMs || 0; this.minSpeechMs = opts.minSpeechMs || 0;
    this.calibrateMs = opts.noise ? 0 : (opts.calibrateMs || 0);
    this.noise = Math.min(0.04, opts.noise || this.threshold / 2); this.calMin = Infinity;
    this.run = 0; this.speechMs = 0;
    this.t = 0; this.heard = false; this.quiet = 0;
  }
  Detector.prototype.level = function () {
    return this.adaptive ? Math.max(this.threshold, this.noise * this.noiseFactor) : this.threshold;
  };
  Detector.prototype.push = function (frame, ms) {
    this.t += ms;
    var r = rms(frame);
    if (this.adaptive && this.t <= this.calibrateMs) {      // calibración: solo mide el cuarto
      this.calMin = Math.min(this.calMin, r);
      if (this.t + ms > this.calibrateMs) this.noise = Math.min(0.04, Math.max(this.threshold / 2, this.calMin));
      return null;
    }
    var loud = r > this.level();
    if (this.adaptive && !this.heard && !loud) this.noise = Math.min(0.04, this.noise * 0.95 + r * 0.05);
    if (!this.heard) {
      this.run = loud ? this.run + ms : Math.max(0, this.run - ms / 2);
      if (this.run >= this.minStartMs && loud) { this.heard = true; this.quiet = 0; this.speechMs = this.run; }
    } else if (loud) { this.quiet = 0; this.speechMs += ms; }
    else this.quiet += ms;
    if (this.t >= this.maxMs) return "max";
    if (!this.heard && this.t >= this.noSpeechMs) return "no-speech";
    if (this.heard && this.quiet >= this.silenceMs) {
      if (this.speechMs < this.minSpeechMs) {            // fue un ruido corto: se olvida sin transcribir
        this.heard = false; this.quiet = 0; this.speechMs = 0; this.run = 0;
        return null;
      }
      return "silence-end";
    }
    return loud && this.heard ? "speech" : null;
  };

  // Keep a short lead-in until speech starts; never trim within a spoken phrase.
  function PhraseBuffer(rate, leadMs) {
    this.limit = Math.ceil(rate * (leadMs || 500) / 1000);
    this.frames = []; this.samples = 0;
  }
  PhraseBuffer.prototype.push = function (frame, heard) {
    this.frames.push(frame); this.samples += frame.length;
    if (!heard) {
      while (this.frames.length > 1 && this.samples - this.frames[0].length >= this.limit) {
        this.samples -= this.frames.shift().length;
      }
    }
  };

  var api = { PhraseBuffer: PhraseBuffer, downsample: downsample, encodeWav: encodeWav, rms: rms, Detector: Detector, OUT_RATE: OUT_RATE };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.JarvisWav = api;
})(this);
