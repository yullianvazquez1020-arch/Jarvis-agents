/* One local intro per browser session; no loop, no overlap with listening or speech. */
(function () {
  'use strict';
  var audio=null, timer=0, done=false, started=false, settings=null;
  function remembered(){try{return sessionStorage.getItem('jarvis-arranque')==='1';}catch(_){return false;}}
  function listening(){var t=document.getElementById('talk');return !!(t&&t.classList.contains('recording'));}
  function cleanup(){clearTimeout(timer);removeEventListener('pointerdown',attempt);removeEventListener('keydown',attempt);
    if(audio){audio.onended=null;audio.onerror=null;audio.pause();audio.removeAttribute('src');audio.load();audio=null;}}
  function finish(greeting){if(done)return;done=true;cleanup();
    if(greeting){try{sessionStorage.setItem('jarvis-arranque','1');}catch(_){}}
    if(greeting && settings && settings.greeting && window.JarvisAudioOwner===true && !listening()){
      fetch('/api/greet',{method:'POST',credentials:'same-origin',headers:{'X-Jarvis-UI':'1','Content-Type':'application/json'},body:'{}'}).catch(function(){});
    }
  }
  window.JarvisStopIntro=function(){finish(false);};
  function attempt(){
    if(done||started||!settings||window.JarvisAudioOwner!==true||document.hidden)return;
    if(listening()||remembered()){finish(false);return;}
    if(!settings.sound){finish(true);return;}
    started=true;audio=new Audio('/api/startup-sound');audio.volume=.35;audio.loop=false;
    audio.onplaying=function(){try{sessionStorage.setItem('jarvis-arranque','1');}catch(_){}
      timer=setTimeout(function(){finish(true);},4000);};
    audio.onended=function(){finish(true);};audio.onerror=function(){finish(true);};
    var p=audio.play();if(p&&p.catch)p.catch(function(){if(done)return;started=false;cleanup();
      addEventListener('pointerdown',attempt);addEventListener('keydown',attempt);});
  }
  addEventListener('jarvis-audio-owner',function(e){if(e.detail)attempt();else if(started)finish(false);});
  addEventListener('pagehide',function(){finish(false);});
  document.addEventListener('visibilitychange',function(){if(document.hidden&&started)finish(false);});
  fetch('/api/state',{credentials:'same-origin'}).then(function(r){if(!r.ok)throw Error('No session');return r.json();})
    .then(function(s){settings=s.startup||{};attempt();}).catch(function(){finish(false);});
})();
