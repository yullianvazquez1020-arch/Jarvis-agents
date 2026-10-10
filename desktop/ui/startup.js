/* Explicit local startup settings. No camera frames, models or music downloads. */
(function () {
  'use strict';
  function saved(key, fallback) {
    try { const value=localStorage.getItem(key); return value===null?fallback:value==='true'; }
    catch (_) { return fallback; }
  }
  function save(key, value) { try { localStorage.setItem(key,String(value)); } catch (_) {} }
  const hands=window.JarvisHands;
  let context=null, gain=null, nodes=[], enabled=false, speaking=false;
  let musicButton=null;
  function volume() {
    if(gain && context) gain.gain.setTargetAtTime(speaking?.002:.014,context.currentTime,.18);
  }
  function stopMusic() {
    nodes.forEach(node=>{try { node.stop(); node.disconnect(); } catch (_) {}}); nodes=[];
    if(context) context.close().catch(()=>{}); context=null;gain=null;
  }
  async function startMusic() {
    if(!enabled || document.hidden || window.JarvisAudioOwner!==true) return;
    const Audio=window.AudioContext||window.webkitAudioContext;
    if(!Audio){musicButton.textContent='Música no disponible';return;}
    if(!context){
      context=new Audio();gain=context.createGain();gain.gain.value=.014;gain.connect(context.destination);
      // Original quiet ambient chord, synthesized locally with two oscillators.
      [130.81,196].forEach((frequency,i)=>{const oscillator=context.createOscillator();oscillator.type='sine';oscillator.frequency.value=frequency;
        oscillator.detune.value=i?3:-3;oscillator.connect(gain);oscillator.start();nodes.push(oscillator);});
      volume();
    }
    try { await context.resume(); } catch (_) {}
    if(!context || !enabled)return;
    musicButton.textContent=context.state==='running'?'Silenciar música':'Activar audio · permiso del navegador';
    musicButton.setAttribute('aria-pressed',String(enabled));
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
    musicButton=document.createElement('button');musicButton.type='button';musicButton.textContent='Activar música';
    (document.querySelector('footer')||document.body).appendChild(musicButton);
    enabled=saved('jarvis-startup-music',!!settings.audio);
    musicButton.onclick=function(){
      if(context && context.state!=='running' && enabled){startMusic();return;}
      enabled=!enabled;save('jarvis-startup-music',enabled);
      if(enabled)startMusic();else{stopMusic();musicButton.textContent='Activar música';musicButton.setAttribute('aria-pressed','false');}
    };
    if(enabled)startMusic();
    addEventListener('pointerdown',function(){if(enabled && (!context||context.state!=='running'))startMusic();});
    document.addEventListener('visibilitychange',function(){if(document.hidden && context)context.suspend().catch(()=>{});else if(enabled && window.JarvisAudioOwner===true)startMusic();});
    }
    addEventListener('jarvis-audio-owner',function(event){if(event.detail)initializeMusic();else stopMusic();});
    initializeMusic();
  }).catch(()=>{});
  addEventListener('pagehide',stopMusic);
})();
