/* Regression tests run the actual UI controller with fake devices and timers. */
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const path = require('node:path');
const root = path.join(__dirname, '..');
function harness(options = {}) {
  const els = {}, timers = new Map(), requests = [], pending = [];
  const listeners = {}, audios = [], contexts = [];
  let serial = 0, captures = 0;
  function element(id) {
    return els[id] ||= { checked: false, value: '', classList: {add(){},remove(){}}, firstChild: {nodeValue:''},
      setAttribute(){}, focus(){}, addEventListener(){}, children:[], appendChild(el){this.children.push(el)} };
  }
  const win = { crypto: require('node:crypto').webcrypto, JarvisWav:require('../desktop/ui/wav.js'),
    JarvisMask:{mask:x=>x,hasSensitive:()=>false}, dispatchEvent(){}, isSecureContext:true };
  const doc = { createElement:()=>({}), hidden:false, getElementById:element, querySelectorAll:()=>[], addEventListener(){}, activeElement:null };
  const state = {prefs:{mic:true,review:false,rate:1},stt:{problem:''},tts:{problem:''},startup:{},server:{state:'ok'}};
  const context = {window:win,document:doc,location:{search:''},console,Intl,Date,Uint8Array,Float32Array,Promise,Math,
    CustomEvent: function(){}, performance:{now:()=>0},
    sessionStorage:{getItem:()=>null,setItem(){}},localStorage:{getItem:key=>key==='jarvis-mic-device'?(options.savedDevice||null):null,setItem(){}},
    setTimeout(fn){timers.set(++serial,fn);return serial},clearTimeout(id){timers.delete(id)},setInterval(){},clearInterval(){},
    addEventListener(name,fn){(listeners[name] ||= []).push(fn);},requestAnimationFrame(){},cancelAnimationFrame(){},
    navigator:{mediaDevices:{enumerateDevices: options.devices ? ()=>Promise.resolve(options.devices) : undefined, getUserMedia(){captures++;return new Promise(resolve=>pending.push(resolve));}}},
    fetch(url,opt){requests.push([url,opt]);if(url.startsWith('/api/events'))return new Promise(()=>{});
      if(url.startsWith('/voice/transcribe') && options.transcribe) return Promise.resolve(options.transcribe(url,opt)).then(data=>({ok:true,json:()=>Promise.resolve(data)}));
      const data = url==='/api/state'?state:url==='/api/window/hello'?{owner:true}:{};
      return Promise.resolve({ok:true,json:()=>Promise.resolve(data)});},
    Audio: function(){audios.push(this);this.paused=false;this.currentTime=0;this.addEventListener=()=>{};this.removeEventListener=()=>{};
      this.play=()=>options.play?options.play(this):Promise.resolve();this.pause=()=>{this.paused=true};}
  };
  win.AudioContext = function(){contexts.push(this);this.state=options.contextState || 'running';this.sampleRate=48000;
    this.createMediaStreamSource=()=>{if(options.failCaptureSetup)throw new Error('setup failed');return {connect(){},disconnect(){}};};
    this.createScriptProcessor=()=>({connect(){},disconnect(){}});this.close=()=>{this.state='closed';};
    this.resume=()=>{if(options.resume)return options.resume(this);this.state='running';return Promise.resolve();};};
  let src=fs.readFileSync(path.join(root,'desktop/ui/app.js'),'utf8');
  src=src.replace(/\}\)\(\);\s*$/,`window.test = {startMic,stopMic,handle,setOwner,resumeConversation,
    send,flushPhrase,interruptWith,queues:()=>({stt:sttQueue.length,text:textQueue.length}),audio:()=>audioEl,recording:()=>rec,setCurrent:x=>{current=x},setPaused:x=>{conversationPaused=x}};})();`);
  vm.runInNewContext(src,context);
  return {win,els,state,pending,requests,audios,contexts,gesture(){(listeners.pointerdown||[]).forEach(fn=>fn());},
    captures:()=>captures,flush(){const jobs=[...timers.values()];timers.clear();jobs.forEach(fn=>fn())}};
}
function stream(){const track={readyState:"live",enabled:true,stop(){this.stopped=true;this.readyState="ended";}};return {track,getTracks:()=>[track],getAudioTracks:()=>[track]};}
async function settle(){for(let i=0;i<15;i++)await Promise.resolve();}

function phrase(h, overlap=false) {
  const rec=h.win.test.recording(); rec.detector.heard=true;
  rec.phrase.frames=[new Float32Array(24000).fill(.1)];rec.duringOutput=overlap;
  h.win.test.flushPhrase(rec);return rec;
}
async function ready(options={}) {
  const h=harness(options);await settle();h.flush();h.pending.shift()(stream());await settle();return h;
}
(async()=>{
  const h=await ready({transcribe:()=>({text:'Jarvis, hazme una monografía del sol'})});
  const rec=phrase(h);await settle();
  assert.equal(h.win.test.recording(),rec,'same microphone/context survives transcription and model request');
  assert.equal(h.captures(),1,'no device reacquisition between phrases');
  assert.equal(h.requests.filter(r=>r[0]==='/conversation/turns').length,1);
  h.win.test.handle({type:'audio.play',id:'answer',turn:'answer-turn'});
  assert.equal(h.win.test.recording(),rec,'microphone stays active while TTS plays');
  h.win.test.audio().onended();await settle();
  assert(h.requests.some(r=>r[0]==='/api/voice/follow'),'follow-up clock renewed at audio end');

  const q=await ready({transcribe:()=>({text:'Amplía la introducción'})});
  q.win.test.setCurrent('busy-turn');phrase(q);await settle();
  assert.equal(q.win.test.queues().text,1,'new phrase waits while previous query is processing');
  assert.equal(q.requests.filter(r=>r[0]==='/conversation/turns').length,0);
  q.win.test.handle({type:'turn.done',turn:'busy-turn'});await settle();
  assert.equal(q.requests.filter(r=>r[0]==='/conversation/turns').length,1,'queued instruction submitted once after completion');

  const echo=await ready({transcribe:()=>({text:'',reason:'playback_echo'})});
  echo.win.test.handle({type:'audio.play',id:'echo',turn:'echo-turn'});phrase(echo,true);await settle();
  assert(echo.requests.some(r=>r[0]==='/voice/transcribe?interrupt=1'),'overlapping speech requires wake-word verification');
  assert.equal(echo.requests.filter(r=>r[0].includes('/cancel')).length,0,'filtered echo never cancels the answer');
  assert(echo.win.test.audio(),'filtered echo leaves answer playing');

  const interrupt=await ready({transcribe:()=>({text:'Jarvis, cambia de tema'})});
  interrupt.win.test.setCurrent('old-turn');interrupt.win.test.handle({type:'audio.play',id:'old',turn:'old-turn'});
  phrase(interrupt,true);await settle();
  assert(interrupt.requests.some(r=>r[0]==='/conversation/turns/old-turn/cancel'),'wake-addressed interruption cancels old output');
  assert.equal(interrupt.requests.filter(r=>r[0]==='/conversation/turns').length,1);
  interrupt.win.test.handle({type:'audio.play',id:'late',turn:'old-turn'});
  assert.equal(interrupt.win.test.audio(),null,'late audio from interrupted turn is suppressed');

  let resolve;
  const muted=await ready({transcribe:()=>new Promise(r=>{resolve=r})});phrase(muted);
  muted.els['mic-off'].onclick();resolve({text:'Jarvis, escribe un informe'});await settle();
  assert.equal(muted.win.test.recording(),null,'explicit mute closes capture');
  assert.equal(muted.requests.filter(r=>r[0]==='/conversation/turns').length,0,'late transcript cannot override mute');
  const once=await ready({transcribe:()=>({text:'Jarvis, escribe un informe'})});
  once.els.convo.checked=false;phrase(once);await settle();
  assert.equal(once.win.test.recording(),null,'single-shot mode closes capture after one phrase');
  assert.equal(once.requests.filter(r=>r[0]==='/conversation/turns').length,1,'single-shot transcript is still submitted');

  let finishStt, sttCalls=0;
  const bounded=await ready({transcribe:()=>{sttCalls++;return new Promise(r=>{finishStt=r});}});
  phrase(bounded);phrase(bounded);phrase(bounded);phrase(bounded);await settle();
  assert.equal(sttCalls,1,'only one browser transcription request runs at a time');
  assert.equal(bounded.win.test.queues().stt,2,'pending audio queue is bounded');
  bounded.els['mic-off'].onclick();finishStt({text:'ignored'});await settle();
  assert.equal(sttCalls,1,'muting discards queued audio before further transcription');
  console.log('Continuous capture, queued follow-ups, playback wake gate, interruption and explicit mute: OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
