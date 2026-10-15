/* Regression tests run the actual UI controller with fake devices and timers. */
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const path = require('node:path');
const root = path.join(__dirname, '..');
function harness() {
  const els = {}, timers = new Map(), requests = [], pending = [];
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
    addEventListener(){},requestAnimationFrame(){},cancelAnimationFrame(){},
    navigator:{mediaDevices:{getUserMedia(){captures++;return new Promise(resolve=>pending.push(resolve));}}},
    fetch(url,opt){requests.push([url,opt]);if(url.startsWith('/api/events'))return new Promise(()=>{});
      const data = url==='/api/state'?state:url==='/api/window/hello'?{owner:true}:{};
      return Promise.resolve({ok:true,json:()=>Promise.resolve(data)});},
    Audio: function(){this.paused=false;this.addEventListener=()=>{};this.removeEventListener=()=>{};this.play=()=>Promise.resolve();this.pause=()=>{this.paused=true};}
  };
  win.AudioContext = function(){this.sampleRate=48000;this.createMediaStreamSource=()=>({connect(){},disconnect(){}});
    this.createScriptProcessor=()=>({connect(){},disconnect(){}});this.close=()=>{};};
  let src=fs.readFileSync(path.join(root,'desktop/ui/app.js'),'utf8');
  src=src.replace(/\}\)\(\);\s*$/,`window.test = {startMic,stopMic,handle,setOwner,resumeConversation,
    audio:()=>audioEl,recording:()=>rec,setCurrent:x=>{current=x},setPaused:x=>{conversationPaused=x}};})();`);
  vm.runInNewContext(src,context);
  return {win,els,state,pending,requests,captures:()=>captures,flush(){const jobs=[...timers.values()];timers.clear();jobs.forEach(fn=>fn())}};
}
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
  console.log('Conversation lifecycle: 12 checks passed');
})().catch(err=>{console.error(err);process.exitCode=1});
