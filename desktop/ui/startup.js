/* Local camera preference only. Background music is disabled: intro lives in arranque.js. */
(function () {
  'use strict';
  function saved(key, fallback) {
    try { const value=localStorage.getItem(key); return value===null?fallback:value==='true'; }
    catch (_) { return fallback; }
  }
  const hands=window.JarvisHands;
  // Compatibility for existing speech controls; no audio context or music loop is created.
  window.JarvisAmbience={duck:function(value){if(value && window.JarvisStopIntro)window.JarvisStopIntro();}};
  fetch('/api/state',{credentials:'same-origin'}).then(r=>{if(!r.ok)throw new Error('No session');return r.json();}).then(state=>{
    if(!hands)return;
    const button=document.getElementById('hands');
    if(!button)return;
    const label=document.createElement('label'),checkbox=document.createElement('input');
    checkbox.type='checkbox';checkbox.checked=saved('jarvis-auto-camera',!!(state.startup||{}).camera);
    label.appendChild(checkbox);label.appendChild(document.createTextNode(' Camera on startup'));
    button.parentNode.appendChild(label);
    checkbox.onchange=function(){
      try{localStorage.setItem('jarvis-auto-camera',String(checkbox.checked));}catch(_){}
      checkbox.checked?hands.start():hands.stop();
    };
    if(checkbox.checked && !document.hidden)hands.start();
  }).catch(()=>{});
})();
