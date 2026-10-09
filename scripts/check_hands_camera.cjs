/* Deterministic camera lifecycle checks; no physical camera or network. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../desktop/ui/hands.js'), 'utf8')
  .replace('import(VISION)', 'Promise.resolve(vision)');
const flush = async () => { for (let i = 0; i < 40; i++) await Promise.resolve(); };
function setup({ devices, failDetect = false, pending = false } = {}) {
  const calls = [], streams = [], frames = [], events = {}, elements = {};
  const container = { appendChild() {}, insertBefore() {} };
  function element() {
    return { value: '', textContent: '', options: [], parentNode: container,
      classList: { add() {}, remove() {} }, setAttribute() {},
      appendChild(o) { this.options.push(o); }, remove(i) { this.options.splice(i, 1); } };
  }
  for (const id of ['hand-video', 'hand-status', 'hands']) elements[id] = element();
  const video = elements['hand-video'];
  Object.assign(video, { readyState: 4, currentTime: 1, play: async () => {} });
  let chooser, resolveStream;
  const cameraList = devices || [{ kind: 'videoinput', deviceId: 'mac', label: 'FaceTime HD' }, { kind: 'videoinput', deviceId: 'brio', label: 'Logitech BRIO' }];
  function makeStream() {
    const track = { label: 'Logitech BRIO', stopped: false, stop() { this.stopped = true; } };
    const s = { getTracks: () => [track], getVideoTracks: () => [track] };
    streams.push(s); return s;
  }
  const context = {
    document: { hidden: false, getElementById: id => elements[id], createElement: tag => {
      const e = element(); if (tag === 'select') chooser = e; return e;
    } },
    navigator: { mediaDevices: {
      enumerateDevices: async () => typeof cameraList === 'function' ? cameraList() : cameraList,
      getUserMedia: async constraints => { calls.push(constraints); return pending ? new Promise(r => { resolveStream = () => r(makeStream()); }) : makeStream(); }
    } },
    vision: { FilesetResolver: { forVisionTasks: async () => ({}) }, HandLandmarker: { createFromOptions: async () => ({
      detectForVideo: () => { if (failDetect) throw new Error('detector failed'); return { landmarks: [] }; }
    }) } },
    window: {}, performance: { now: () => 1000 }, requestAnimationFrame: f => frames.push(f),
    addEventListener: (type, f) => { events[type] = f; }
  };
  vm.runInNewContext(source, context);
  return { context, calls, streams, frames, elements, chooser, events, resolve: () => resolveStream() };
}
(async () => {
  let t = setup(); t.elements.hands.onclick(); await flush();
  assert.equal(t.calls.length, 1);
  assert.equal(t.calls[0].video.deviceId.exact, 'brio');
  assert.equal(t.calls[0].audio, false);
  assert.equal(t.context.window.JarvisHands.running, true);
  assert.match(t.elements['hand-status'].textContent, /Logitech BRIO/);
  t.chooser.value = 'mac'; t.chooser.onchange();
  assert.equal(t.streams[0].getTracks()[0].stopped, true);
  t.elements.hands.onclick(); await flush();
  assert.equal(t.calls[1].video.deviceId.exact, 'mac');
  t.events.keydown({key:'Escape'});
  assert.equal(t.context.window.JarvisHands.running, false);
  assert.equal(t.streams[1].getTracks()[0].stopped, true);

  let enumerations = 0;
  t = setup({ devices: () => ++enumerations === 1 ? [{kind:'videoinput', deviceId:'', label:''}] : [{kind:'videoinput', deviceId:'brio', label:'Logitech BRIO'}] });
  t.elements.hands.onclick(); await flush();
  assert.equal(t.calls.length, 2);
  assert.equal(t.streams[0].getTracks()[0].stopped, true);
  assert.equal(t.calls[1].video.deviceId.exact, 'brio');
  t.events.pagehide();
  assert.equal(t.streams[1].getTracks()[0].stopped, true);

  t = setup({ devices: [{ kind:'videoinput', deviceId:'mac', label:'FaceTime HD' }] });
  t.elements.hands.onclick(); await flush();
  assert.equal(t.calls.length, 0); // Never silently substitute the built-in camera.
  assert.match(t.elements['hand-status'].textContent, /No aparece la Brio/);

  t = setup({ pending: true }); t.elements.hands.onclick(); await flush();
  t.elements.hands.onclick(); t.resolve(); await flush();
  assert.equal(t.streams[0].getTracks()[0].stopped, true);
  assert.equal(t.context.window.JarvisHands.running, false);

  t = setup({ failDetect: true }); t.elements.hands.onclick(); await flush();
  t.frames.shift()();
  assert.match(t.elements['hand-status'].textContent, /Falló la detección: detector failed/);
  assert.equal(t.streams[0].getTracks()[0].stopped, true);
  assert.equal(t.context.window.JarvisHands.running, false);
  console.log('PASS: Brio exacta, audio apagado, selección explícita, Escape, ausencia de Brio, cancelación y error visible.');
})().catch(e => { console.error(e); process.exitCode = 1; });
