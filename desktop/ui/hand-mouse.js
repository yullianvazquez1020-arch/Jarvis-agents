/* Manual owner gesture bridge. Explicit opt-in pinch click; no keyboard or autonomous agent. */
(() => {
  'use strict';
  const handsButton = document.getElementById('hands');
  if (!handsButton) return;
  const button = document.createElement('button');
  button.type = 'button'; button.textContent = 'Mover mouse de Mac · prueba 60 s';
  button.setAttribute('aria-pressed', 'false');
  handsButton.parentNode.appendChild(button);
  const clickButton = document.createElement('button');
  clickButton.type = 'button'; clickButton.textContent = 'Mover + clic con pinza · 60 s';
  clickButton.setAttribute('aria-pressed', 'false');
  handsButton.parentNode.appendChild(clickButton);
  const status = document.createElement('p'); status.setAttribute('role', 'status');
  status.textContent = 'Mouse de macOS apagado. Prueba sin clics; solo pantalla principal. Escape detiene.';
  handsButton.parentNode.insertAdjacentElement('afterend', status);
  const practice = document.createElement('button');
  practice.type = 'button'; practice.textContent = 'Probar clic · 0';
  let practiceClicks = 0;
  practice.onclick = () => { practice.textContent = 'Probar clic · ' + (++practiceClicks); };
  status.insertAdjacentElement('afterend', practice);
  let lease = '', pending = false, busy = false, generation = 0, seq = 0, lastSample = 0;
  let clickMode = false;
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
    clickMode = false;
    clickButton.textContent = 'Mover + clic con pinza · 60 s'; clickButton.setAttribute('aria-pressed','false');
    status.textContent = text;
  }
  function stop(text = 'Mouse detenido.') {
    const old = lease;
    stopped(text);
    if (old) post('stop', {lease:old}, true).catch(() => {});
  }
  async function activate(withClick) {
    if (lease || pending) { stop(); return; }
    if (!window.JarvisHands?.running) { status.textContent = 'Primero activa la cámara y comprueba que detecta tu mano.'; return; }
    if (withClick && !window.confirm('Activar clic izquierdo real por 60 segundos: abre los dedos, apunta y junta pulgar e índice durante medio segundo. Prueba sobre una zona vacía, lejos de botones de envío o compra. Escape detiene. ¿Activar?')) return;
    clickMode = withClick;
    const ticket = ++generation;
    pending = true; button.textContent = 'Cancelar prueba de mouse';
    try {
      const result = await post('arm', {confirm:withClick ? 'MOVER_Y_CLIC_60S' : 'SOLO_MOVER_60S'});
      if (ticket !== generation) { post('stop', {lease:result.lease}, true).catch(() => {}); return; }
      pending = false; lease = result.lease; seq = 0; lastSample = 0;
      window.JarvisHandMouseActive = true;
      button.textContent = 'Detener mouse de Mac'; button.setAttribute('aria-pressed','true');
      clickButton.textContent = 'Detener mouse de Mac'; clickButton.setAttribute('aria-pressed', withClick ? 'true' : 'false');
      status.textContent = `${withClick ? 'Abre pulgar e índice primero; pinza sostenida hace clic' : 'Solo mover'} · ${result.width}×${result.height} · máximo 60 s. Escape o borde de pantalla detienen.`;
    } catch (error) { if (ticket === generation) stopped(error.message); }
  }
  button.onclick = () => activate(false);
  clickButton.onclick = () => activate(true);
  async function tick() {
    if (!lease || busy) return;
    const h = window.JarvisHands;
    if (document.hidden || !h?.running) { stop('Mouse detenido: cámara apagada o pestaña oculta.'); return; }
    const age = performance.now() - (h.updatedAt || 0);
    if (h.updatedAt === lastSample && h.seen && age <= 300) return;
    let point = h.landmarks?.[8], ratio = null;
    let valid = h.seen && age >= 0 && age <= 300 && point && Number.isFinite(point.x) && Number.isFinite(point.y);
    if (clickMode && valid) {
      const pts = [4,5,17].map(i => h.landmarks[i]);
      if (pts.every(p => p && Number.isFinite(p.x) && Number.isFinite(p.y))) {
        const palm = Math.hypot(pts[1].x-pts[2].x, pts[1].y-pts[2].y);
        if (palm > .01) ratio = Math.hypot(point.x-pts[0].x, point.y-pts[0].y)/palm;
      }
      valid = Number.isFinite(ratio);
    }
    if (!valid && !clickMode) return;
    const payload = {lease, seq:++seq,
      x:valid ? Math.max(0,Math.min(1,(point.x-.1)/.8)) : .5,
      y:valid ? Math.max(0,Math.min(1,(point.y-.1)/.8)) : .5,
      captured_ms:Date.now()-(valid ? Math.max(0,age) : 0)};
    if (clickMode) payload.pinch_ratio = valid ? ratio : null;
    const ticket = generation;
    lastSample = h.updatedAt; busy = true;
    try {
      const result = await post('frame', payload);
      if (ticket !== generation) return;
      if (!result.active) stop(result.reason);
      else status.textContent = `Mouse de Mac activo · ${result.remaining} s · ${clickMode ? result.gesture || 'Pinza activa' : 'SIN CLICS'}. Escape detiene.`;
    } catch (error) { if (ticket === generation) stop(error.message); }
    finally { if (ticket === generation) busy = false; }
  }
  setInterval(tick, 40);
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
