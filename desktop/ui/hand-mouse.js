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
  let clickMode = false, mode = 'move';
  window.JarvisHandMouseActive = false;
  const profileKey = 'jarvis-hand-profile-v1';
  let profile = {span:.8, cx:.5, cy:.5};
  try {
    const saved = JSON.parse(localStorage.getItem(profileKey) || 'null');
    if (saved && [.5,.65,.8,1].includes(saved.span) &&
        Number.isFinite(saved.cx) && Number.isFinite(saved.cy) &&
        saved.cx>=.2 && saved.cx<=.8 && saved.cy>=.2 && saved.cy<=.8) profile = saved;
  } catch (_) {}
  function saveProfile() { try { localStorage.setItem(profileKey, JSON.stringify(profile)); } catch (_) {} }
  function extra(label) {
    const e = document.createElement('button'); e.type='button'; e.textContent=label;
    handsButton.parentNode.appendChild(e); return e;
  }
  const scrollButton = extra('Desplazar con dos dedos · 60 s');
  const dragButton = extra('Arrastrar con pinza · 60 s');
  const calibrate = extra('Calibrar centro');
  const resetProfile = extra('Restablecer calibración');
  const sensitivity = document.createElement('select');
  sensitivity.setAttribute('aria-label','Recorrido de la mano');
  for (const [value,label] of [[.5,'Recorrido corto'],[.65,'Recorrido medio'],[.8,'Recorrido normal'],[1,'Recorrido amplio']]) {
    const option=document.createElement('option');option.value=String(value);option.textContent=label;
    sensitivity.appendChild(option);
  }
  sensitivity.value=String(profile.span);handsButton.parentNode.appendChild(sensitivity);
  sensitivity.onchange=()=>{stop('Calibración guardada. Activa el modo deseado.');profile.span=Number(sensitivity.value);saveProfile();};
  calibrate.onclick=()=>{
    stop('Calibración: muestra el índice en el centro cómodo de tu alcance.');
    const h=window.JarvisHands,p=h?.landmarks?.[8];
    if(!h?.seen || performance.now()-h.updatedAt>300 || !p || !Number.isFinite(p.x) || !Number.isFinite(p.y)) return;
    profile.cx=Math.max(.2,Math.min(.8,p.x));profile.cy=Math.max(.2,Math.min(.8,p.y));saveProfile();
    status.textContent='Centro guardado. Activa el mouse; puedes elegir un recorrido más corto.';
  };
  resetProfile.onclick=()=>{stop('Calibración restablecida.');profile={span:.8,cx:.5,cy:.5};sensitivity.value='.8';saveProfile();};
  const cursor = document.createElement('span');cursor.className='hand-cursor-status';cursor.textContent='Pausado';
  handsButton.parentNode.appendChild(cursor);
  // In-page indicator follows the physical pointer while it is inside this window.
  addEventListener('mousemove',event=>{cursor.style.left=Math.min(innerWidth-160,event.clientX+18)+'px';cursor.style.top=Math.max(8,event.clientY+18)+'px';});


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
    clickMode = false; mode='move'; cursor.textContent='Pausado';
    clickButton.textContent = 'Mover + clic con pinza · 60 s'; clickButton.setAttribute('aria-pressed','false');
    status.textContent = text;
  }
  function stop(text = 'Mouse detenido.') {
    const old = lease;
    stopped(text);
    if (old) post('stop', {lease:old}, true).catch(() => {});
  }
  async function activate(requestedMode) {
    const withClick = requestedMode === 'click' || requestedMode === 'drag';
    if (lease || pending) { stop(); return; }
    if (!window.JarvisHands?.running) { status.textContent = 'Primero activa la cámara y comprueba que detecta tu mano.'; return; }
    if (withClick && requestedMode === 'click' && !window.confirm('Activar clic izquierdo real por 60 segundos: abre los dedos, apunta y junta pulgar e índice durante medio segundo. Prueba sobre una zona vacía, lejos de botones de envío o compra. Escape detiene. ¿Activar?')) return;
    if(requestedMode==='drag' && !window.confirm('Arrastre real por 60 segundos. Abre los dedos, apunta, mantén la pinza medio segundo y mueve la mano. Abre para soltar. Escape y pérdida de mano sueltan el objeto. ¿Activar?')) return;
    if(requestedMode==='scroll' && !window.confirm('Desplazamiento real por 60 segundos. Extiende índice y medio; recoge los otros dedos. Escape detiene. ¿Activar?')) return;
    mode=requestedMode; clickMode = withClick;
    const ticket = ++generation;
    pending = true; button.textContent = 'Cancelar prueba de mouse';
    try {
      const result = await post('arm', {confirm:{move:'SOLO_MOVER_60S',click:'MOVER_Y_CLIC_60S',scroll:'DESPLAZAR_60S',drag:'ARRASTRAR_60S'}[mode]});
      if (ticket !== generation) { post('stop', {lease:result.lease}, true).catch(() => {}); return; }
      pending = false; lease = result.lease; seq = 0; lastSample = 0;
      window.JarvisHandMouseActive = true;
      button.textContent = 'Detener mouse de Mac'; button.setAttribute('aria-pressed','true');
      clickButton.textContent = 'Detener mouse de Mac'; clickButton.setAttribute('aria-pressed', withClick ? 'true' : 'false');
      status.textContent = `${{move:'Solo mover',click:'Abre los dedos; pinza sostenida hace clic',drag:'Pinza sostenida toma; abre para soltar',scroll:'Extiende índice y medio y muévelos verticalmente'}[mode]} · ${result.width}×${result.height} · máximo 60 s. Escape o borde de pantalla detienen.`;
    } catch (error) { if (ticket === generation) stopped(error.message); }
  }
  button.onclick = () => activate('move');
  clickButton.onclick = () => activate('click');
  scrollButton.onclick=()=>activate('scroll');
  dragButton.onclick=()=>activate('drag');
  function twoFingers(points) {
    if(!points || points.length!==21 || !points.every(p=>p && Number.isFinite(p.x) && Number.isFinite(p.y))) return false;
    const d=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
    const extended=(tip,pip)=>d(points[tip],points[0])>d(points[pip],points[0])*1.2;
    return extended(8,6) && extended(12,10) && !extended(16,14) && !extended(20,18);
  }
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
    if (!valid && !clickMode && mode!=='scroll') return;
    const payload = {lease, seq:++seq,
      x:valid ? Math.max(0,Math.min(1,(point.x-profile.cx)/profile.span+.5)) : .5,
      y:valid ? Math.max(0,Math.min(1,(point.y-profile.cy)/profile.span+.5)) : .5,
      captured_ms:Date.now()-(valid ? Math.max(0,age) : 0)};
    if(mode==='scroll') payload.two_fingers=Boolean(valid && twoFingers(h.landmarks));
    if (clickMode) payload.pinch_ratio = valid ? ratio : null;
    const ticket = generation;
    lastSample = h.updatedAt; busy = true;
    try {
      const result = await post('frame', payload);
      if (ticket !== generation) return;
      if (!result.active) stop(result.reason);
      else { cursor.textContent=result.dragging?'Arrastrando':mode==='scroll'?'Desplazar':ratio!==null && ratio<.6?'Pinza':'Listo'; status.textContent = `Mouse de Mac activo · ${result.remaining} s · ${clickMode ? result.gesture || 'Pinza activa' : mode==='scroll' ? result.gesture : 'SIN CLICS'}. Escape detiene.`; }
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
