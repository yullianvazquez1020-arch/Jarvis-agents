/* Manual owner gesture bridge. No clicks, no keyboard, no autonomous agent. */
(() => {
  'use strict';
  const handsButton = document.getElementById('hands');
  if (!handsButton) return;
  const button = document.createElement('button');
  button.type = 'button'; button.textContent = 'Mover mouse de Mac · prueba 60 s';
  button.setAttribute('aria-pressed', 'false');
  handsButton.parentNode.appendChild(button);
  const status = document.createElement('p'); status.setAttribute('role', 'status');
  status.textContent = 'Mouse de macOS apagado. Prueba sin clics; solo pantalla principal. Escape detiene.';
  handsButton.parentNode.insertAdjacentElement('afterend', status);
  let lease = '', pending = false, busy = false, generation = 0, seq = 0, lastSample = 0;
  window.JarvisHandMouseActive = false;

  async function post(action, data, keepalive = false) {
    const response = await fetch('/api/hand-mouse/' + action, {
      method: 'POST', headers: {'Content-Type':'application/json', 'X-Jarvis-UI':'1'},
      credentials: 'same-origin', body: JSON.stringify(data), keepalive
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'No se pudo comunicar con el control local');
    return result;
  }
  function stopped(text) {
    generation++; pending = false; lease = ''; busy = false;
    window.JarvisHandMouseActive = false;
    button.textContent = 'Mover mouse de Mac · prueba 60 s'; button.setAttribute('aria-pressed','false');
    status.textContent = text;
  }
  function stop(text = 'Mouse detenido. Sin clics ni escritura.') {
    const old = lease;
    stopped(text);
    if (old) post('stop', {lease:old}, true).catch(() => {});
  }
  button.onclick = async () => {
    if (lease || pending) { stop(); return; }
    if (!window.JarvisHands?.running) { status.textContent = 'Primero activa la cámara y comprueba que detecta tu mano.'; return; }
    const ticket = ++generation;
    pending = true; button.textContent = 'Cancelar prueba de mouse';
    try {
      const result = await post('arm', {confirm:'SOLO_MOVER_60S'});
      if (ticket !== generation) { post('stop', {lease:result.lease}, true).catch(() => {}); return; }
      pending = false; lease = result.lease; seq = 0; lastSample = 0;
      window.JarvisHandMouseActive = true;
      button.textContent = 'Detener mouse de Mac'; button.setAttribute('aria-pressed','true');
      status.textContent = `Solo mover · ${result.width}×${result.height} · máximo 60 s. Escape o borde de pantalla detienen.`;
    } catch (error) { if (ticket === generation) stopped(error.message); }
  };
  async function tick() {
    if (!lease || busy) return;
    const h = window.JarvisHands;
    if (document.hidden || !h?.running) { stop('Mouse detenido: cámara apagada o pestaña oculta.'); return; }
    const age = performance.now() - (h.updatedAt || 0);
    if (!h.seen || !h.landmarks || age > 300 || h.updatedAt === lastSample) return;
    const point = h.landmarks[8];
    if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) return;
    const ticket = generation;
    lastSample = h.updatedAt; busy = true;
    try {
      const result = await post('frame', {lease, seq:++seq,
        x:Math.max(0,Math.min(1,(point.x-.1)/.8)), y:Math.max(0,Math.min(1,(point.y-.1)/.8)),
        captured_ms:Date.now()-Math.max(0,age)});
      if (ticket !== generation) return;
      if (!result.active) stop(result.reason);
      else status.textContent = `Mouse de Mac activo · ${result.remaining} s · SIN CLICS. Escape detiene.`;
    } catch (error) { if (ticket === generation) stop(error.message); }
    finally { if (ticket === generation) busy = false; }
  }
  setInterval(tick, 100);
  // Update expiry/Escape status even when no hand is visible.
  setInterval(async () => {
    if (!lease) return;
    const ticket = generation;
    try {
      const r = await fetch('/api/hand-mouse/status', {credentials:'same-origin'});
      if (!r.ok) throw new Error('Sesión local vencida');
      const s = await r.json();
      if (ticket === generation && !s.active) stop(s.reason);
    } catch (error) { if (ticket === generation) stop(error.message); }
  }, 1000);
  addEventListener('keydown', event => { if (event.key === 'Escape') stop(); });
  addEventListener('pagehide', () => stop());
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
})();
