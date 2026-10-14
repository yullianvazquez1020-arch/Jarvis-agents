/* Explicit local startup settings. No camera frames, models or music downloads.
   Música de inicio: encendida por defecto (respeta un "off" guardado). Usa el archivo propio del dueño
   (/api/startup-music → ~/.jarvis-desktop/musica/inicio.*) y si no existe, el acorde sintetizado. */
(function () {
  'use strict';
  function saved(key, fallback) {
    try { const value=localStorage.getItem(key); return value===null?fallback:value==='true'; }
    catch (_) { return fallback; }
  }
  function save(key, value) { try { localStorage.setItem(key,String(value)); } catch (_) {} }
  const hands=window.JarvisHands;
  const FILE_VOLUME=.35, FILE_DUCKED=.06;
  let context=null, gain=null, nodes=[], enabled=false, speaking=false;
  let musicButton=null, track=null, fileMissing=false, waitingGesture=false;
  function volume() {
    if(gain && context) gain.gain.setTargetAtTime(speaking?.002:.014,context.currentTime,.18);
    if(track) track.volume=speaking?FILE_DUCKED:FILE_VOLUME;
  }
  function label(playing) {
    if(!musicButton)return;
    musicButton.textContent=playing?'Silenciar música':(enabled?'Activar audio · permiso del navegador':'Activar música');
    musicButton.setAttribute('aria-pressed',String(enabled));
  }
  function whenAllowed() {   // mismo patrón que arranque.js: primer clic/tecla
    if(waitingGesture)return; waitingGesture=true;
    function once(){removeEventListener('pointerdown',once);removeEventListener('keydown',once);waitingGesture=false;if(enabled)startMusic();}
    addEventListener('pointerdown',once);addEventListener('keydown',once);
  }
  function stopMusic() {
    if(track){try { track.pause(); } catch (_) {}}
    nodes.forEach(node=>{try { node.stop(); node.disconnect(); } catch (_) {}}); nodes=[];
    if(context) context.close().catch(()=>{}); context=null;gain=null;
  }
  async function startChord() {
    const Audio=window.AudioContext||window.webkitAudioContext;
    if(!Audio){if(musicButton)musicButton.textContent='Música no disponible';return;}
    if(!context){
      context=new Audio();gain=context.createGain();gain.gain.value=.014;gain.connect(context.destination);
      // Original quiet ambient chord, synthesized locally with two oscillators.
      [130.81,196].forEach((frequency,i)=>{const oscillator=context.createOscillator();oscillator.type='sine';oscillator.frequency.value=frequency;
        oscillator.detune.value=i?3:-3;oscillator.connect(gain);oscillator.start();nodes.push(oscillator);});
      volume();
    }
    try { await context.resume(); } catch (_) {}
    if(!context || !enabled)return;
    label(context.state==='running');
    if(context.state!=='running')whenAllowed();
  }
  async function startMusic() {
    if(!enabled || document.hidden || window.JarvisAudioOwner!==true) return;
    if(!fileMissing){
      if(!track){
        track=new window.Audio('/api/startup-music');track.loop=true;track.preload='auto';
        track.addEventListener('error',function(){if(track && track.error){fileMissing=true;track=null;if(enabled)startChord();}});
      }
      volume();
      try { await track.play(); label(true); return; }
      catch (err) {
        if(fileMissing)return;               // el handler de error ya pasó al acorde
        if(err && err.name==='NotAllowedError'){label(false);whenAllowed();return;}
        fileMissing=true;track=null;          // 404 / formato no soportado → acorde
      }
    }
    return startChord();
  }
  window.JarvisAmbience={duck:function(value){speaking=value;volume();}};
  fetch('/api/state',{credentials:'same-origin'}).then(r=>{if(!r.ok)throw new Error('sin sesión');return r.json();}).then(state=>{
    const settings=state.startup||{};
    if(hands){
      const button=document.getElementById('hands');
      const label=document.createElement('label'),checkbox=document.createElement('input');
      checkbox.type='checkbox';checkbox.checked=saved('jarvis-auto-camera',!!settings.camera);
      label.appendChild(checkbox);label.appendChild(document.createTextNode(' Brio al abrir'));
      button.parentNode.appendChild(label);
      checkbox.onchange=function(){save('jarvis-auto-camera',checkbox.checked);checkbox.checked?hands.start():hands.stop();};
      if(checkbox.checked && !document.hidden)hands.start();
      return; // Only the conversation window produces background sound.
    }
    function initializeMusic() {
    if(window.JarvisAudioOwner!==true || musicButton)return;
    musicButton=document.createElement('button');musicButton.type='button';
    (document.querySelector('footer')||document.body).appendChild(musicButton);
    enabled=saved('jarvis-startup-music',true);   // encendida por defecto; respeta "off" guardado
    label(false);
    musicButton.onclick=function(){
      const playing=(track && !track.paused) || (context && context.state==='running');
      if(enabled && !playing){startMusic();return;}
      enabled=!enabled;save('jarvis-startup-music',enabled);
      if(enabled)startMusic();else{stopMusic();label(false);}
    };
    if(enabled)startMusic();
    document.addEventListener('visibilitychange',function(){
      if(document.hidden){if(track)track.pause();if(context)context.suspend().catch(()=>{});}
      else if(enabled && window.JarvisAudioOwner===true)startMusic();});
    }
    addEventListener('jarvis-audio-owner',function(event){if(event.detail)initializeMusic();else stopMusic();});
    initializeMusic();
  }).catch(()=>{});
  addEventListener('pagehide',stopMusic);
})();
