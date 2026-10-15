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
      setAttribute(){}, focus(){}, addEventListener(){}, children:[] };
  }
  const win = { crypto: require('node:crypto').webcrypto, JarvisWav:require('../desktop/ui/wav.js'),
    JarvisMask:{mask:x=>x,hasSensitive:()=>false}, dispatchEvent(){}, isSecureContext:true };
  const doc = { hidden:false, getElementById:element, querySelectorAll:()=>[], addEventListener(){}, activeElement:null };
  const state = {prefs:{mic:true,review:false,rate:1},stt:{problem:''},tts:{problem:''},startup:{},server:{state:'ok'}};
  const context = {window:win,document:doc,location:{search:''},console,Intl,Date,Uint8Array,Float32Array,Promise,Math,
    CustomEvent: function(){}, performance:{now:()=>0},
    sessionStorage:{getItem:()=>null,setItem(){}},localStorage:{getItem:()=>null,setItem(){}},
    setTimeout(fn){timers.set(++serial,fn);return serial},clearTimeout(id){timers.delete(id)},setInterval(){},clearInterval(){},
    addEventListener(name,fn){(listeners[name] ||= []).push(fn);},requestAnimationFrame(){},cancelAnimationFrame(){},
    navigator:{mediaDevices:{getUserMedia(){captures++;return new Promise(resolve=>pending.push(resolve));}}},
    fetch(url,opt){requests.push([url,opt]);if(url.startsWith('/api/events'))return new Promise(()=>{});
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
    audio:()=>audioEl,recording:()=>rec,setCurrent:x=>{current=x},setPaused:x=>{conversationPaused=x}};})();`);
  vm.runInNewContext(src,context);
  return {win,els,state,pending,requests,audios,contexts,gesture(){(listeners.pointerdown||[]).forEach(fn=>fn());},
    captures:()=>captures,flush(){const jobs=[...timers.values()];timers.clear();jobs.forEach(fn=>fn())}};
}
function stream(){const track={readyState:"live",enabled:true,stop(){this.stopped=true;this.readyState="ended";}};return {track,getTracks:()=>[track],getAudioTracks:()=>[track]};}
async function settle(){for(let i=0;i<15;i++)await Promise.resolve();}
(async()=>{
  const h=harness();await settle();
  h.flush();assert.equal(h.captures(),1,'hands-free startup requests microphone');
  h.win.test.startMic();assert.equal(h.captures(),1,'only one permission request in flight');
  h.win.test.stopMic(true);let stopped=0;
  h.pending.shift()({getTracks:()=>[{stop(){stopped++}}]});await settle();
  assert.equal(stopped,1,'late microphone grant must be released');assert.equal(h.win.test.recording(),null);
  h.win.test.setCurrent('turn-1');
  h.win.test.handle({type:'audio.play',id:'a1',turn:'turn-1'});
  h.win.test.handle({type:'turn.done',turn:'turn-1'});h.flush();
  assert.equal(h.captures(),1,'must not listen while response is playing');
  h.win.test.audio().onended();h.flush();
  assert.equal(h.captures(),2,'listening resumes after long response finishes');
  h.els['mic-off'].onclick();h.flush();
  h.pending.shift()({getTracks:()=>[{stop(){stopped++}}]});await settle();
  assert.equal(h.win.test.recording(),null,'mic-off cancels pending capture');
  h.win.test.resumeConversation();h.flush();assert.equal(h.captures(),2,'mic-off remains off');
  h.state.prefs.mic=true;h.win.test.setPaused(false);h.win.test.startMic();
  h.win.test.setOwner(false);h.pending.shift()({getTracks:()=>[{stop(){stopped++}}]});await settle();
  assert.equal(stopped,3,'ownership loss releases pending stream');
  h.win.test.setOwner(true);h.flush();
  assert.equal(h.captures(),4,'regaining ownership resumes hands-free capture');
  for (const type of ['turn.error','turn.cancelled','turn.done']) {
    h.win.test.stopMic(true);h.win.test.setCurrent(type);
    h.win.test.handle({type,turn:type});h.flush();
  }
  assert.equal(h.captures(),7,'every completed or failed turn re-arms listening');
  h.win.test.setPaused(true);h.win.test.stopMic(true);
  h.win.test.handle({type:'turn.error',turn:'late'});h.flush();
  assert.equal(h.captures(),7,'late errors cannot override an explicit pause');
  const failed=harness({play:()=>Promise.reject(Object.assign(new Error('unsupported'),{name:'NotSupportedError'}))});
  await settle();failed.win.test.setCurrent('failed');
  failed.win.test.handle({type:'audio.play',turn:'failed',id:'broken'});
  failed.win.test.handle({type:'turn.done',turn:'failed'});await settle();failed.flush();
  assert.equal(failed.win.test.audio(),null,'failed playback releases the audio lock');
  assert.equal(failed.captures(),1,'failed playback re-arms listening');

  let rejectOld;
  const race=harness({play:a=>race.audios.length===1?new Promise((ok,bad)=>{rejectOld=bad;}):Promise.resolve()});
  await settle();race.win.test.handle({type:'audio.play',turn:'old',id:'old'});
  const oldEnd=race.audios[0].onended, oldError=race.audios[0].onerror;
  race.win.test.handle({type:'audio.play',turn:'new',id:'new'});
  oldEnd();oldError();rejectOld(new Error('late failure'));await settle();
  assert.equal(race.win.test.audio(),race.audios[1],'old callbacks cannot stop newer audio');

  let blocked=true;
  const permission=harness({play:a=>{a.paused=blocked;return blocked?Promise.reject(Object.assign(new Error(),{name:'NotAllowedError'})):Promise.resolve();}});
  await settle();permission.win.test.handle({type:'audio.play',turn:'permission',id:'p'});await settle();permission.flush();
  assert.equal(permission.captures(),0,'permission block is not mistaken for working audio or microphone');
  assert.match(permission.els.state.textContent,/Touch the page/);
  blocked=false;permission.gesture();await settle();permission.win.test.audio().onended();permission.flush();
  assert.equal(permission.captures(),1,'after permission gesture and playback, hands-free listening resumes');

  const suspended=harness({contextState:'suspended'});await settle();suspended.flush();
  const mic=stream();suspended.pending.shift()(mic);await settle();
  assert.equal(suspended.contexts[0].state,'running','suspended capture is resumed');
  assert.match(suspended.els.state.textContent,/ESCUCHANDO/);
  mic.track.onended();suspended.flush();
  assert.equal(suspended.captures(),2,'device disconnect retries capture');
  suspended.win.test.setPaused(true);suspended.win.test.stopMic(true);mic.track.onended();suspended.flush();
  assert.equal(suspended.captures(),2,'obsolete track event cannot override pause');

  const denied=harness({contextState:'suspended',resume:()=>Promise.reject(new Error('blocked'))});
  await settle();denied.flush();const deniedMic=stream();denied.pending.shift()(deniedMic);await settle();
  assert.equal(denied.win.test.recording(),null,'failed context startup releases capture');
  assert.equal(deniedMic.track.stopped,true,'failed context startup stops the actual microphone');
  assert.match(denied.els.state.textContent,/Press Talk/);
  const setup=harness({failCaptureSetup:true});await settle();setup.flush();
  const setupMic=stream();setup.pending.shift()(setupMic);await settle();
  assert.equal(setupMic.track.stopped,true,'partial setup releases microphone tracks');
  assert.equal(setup.contexts[0].state,'closed','partial setup closes audio context');
  const warm=harness();await settle();warm.flush();const warmDevice=stream();warm.pending.shift()(warmDevice);await settle();
  warm.win.test.stopMic(true);assert.equal(warmDevice.track.enabled,false,'device muted between turns');
  assert.notEqual(warmDevice.track.stopped,true,'conversation keeps device permission warm');
  warm.win.test.startMic();await settle();assert.equal(warm.captures(),1,'no repeated device acquisition between turns');
  assert.equal(warmDevice.track.enabled,true,'device enabled only for capture');
  warm.els['mic-off'].onclick();assert.equal(warmDevice.track.stopped,true,'explicit mic off releases hardware');
  console.log('Conversation lifecycle: recovery, permissions, capture and stale-event checks passed');
})().catch(err=>{console.error(err);process.exitCode=1});
