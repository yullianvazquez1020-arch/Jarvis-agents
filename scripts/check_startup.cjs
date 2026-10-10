/* Startup policies with browser doubles, no microphone, camera or audio hardware. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('desktop/ui/startup.js','utf8');
async function setup({hands=false,owner=true,hidden=false,audio=true,camera=true}={}) {
  const events={},elements=[],requests=[],store=new Map();let starts=0,stops=0,oscillators=0,closed=0;
  let canPlay=false;const gains=[];
  const parent={appendChild(e){elements.push(e);}};
  const document={hidden,body:parent,querySelector:()=>parent,addEventListener:(name,fn)=>events[name]=fn,
    getElementById:()=>({parentNode:parent}),createTextNode:text=>({textContent:text}),
    createElement:()=>({textContent:'',appendChild(e){elements.push(e);},setAttribute(){}})};
  class AudioContext {
    constructor(){this.state='suspended';this.currentTime=0;this.destination={};}
    createGain(){const g={gain:{value:0,setTargetAtTime:value=>gains.push(value)},connect(){}};return g;}
    createOscillator(){oscillators++;return {frequency:{value:0},detune:{value:0},connect(){},start(){},stop(){stops++;},disconnect(){}};}
    async resume(){if(canPlay)this.state='running';}
    async suspend(){this.state='suspended';}
    async close(){closed++;}
  }
  const window={JarvisAudioOwner:owner,AudioContext};
  if(hands)window.JarvisHands={start(){starts++;},stop(){stops++;}};
  const context={window,document,localStorage:{getItem:k=>store.has(k)?store.get(k):null,setItem:(k,v)=>store.set(k,v)},
    fetch:async url=>{requests.push(url);return {ok:true,json:async()=>({startup:{audio,camera}})};},
    addEventListener:(name,fn)=>events[name]=fn};
  vm.runInNewContext(source,context);
  const flush=async()=>{for(let i=0;i<15;i++)await Promise.resolve();};await flush();
  return {events,elements,requests,window,document,gains,flush,enableAudio(){canPlay=true;},counts:()=>({starts,stops,oscillators,closed})};
}
(async()=>{
  let t=await setup({hands:true});assert.equal(t.counts().starts,1);assert.equal(t.counts().oscillators,0);
  const camera=t.elements.find(e=>e.type==='checkbox');camera.checked=false;camera.onchange();assert.equal(t.counts().stops,1);
  t=await setup({hands:true,hidden:true});assert.equal(t.counts().starts,0);
  t=await setup({hands:true,camera:false});assert.equal(t.counts().starts,0);
  t=await setup({owner:false});assert.equal(t.counts().oscillators,0);
  t=await setup({owner:null});assert.equal(t.counts().oscillators,0);
  t.window.JarvisAudioOwner=true;t.events['jarvis-audio-owner']({detail:true});await t.flush();assert.equal(t.counts().oscillators,2);
  t=await setup();assert.equal(t.counts().oscillators,2);
  assert.match(t.elements.find(e=>e.type==='button').textContent,/permiso del navegador/);
  t.enableAudio();t.events.pointerdown();await t.flush();assert.equal(t.counts().oscillators,2,'resume reuses two oscillators');
  t.window.JarvisAmbience.duck(true);assert.equal(t.gains.at(-1),.002);
  t.window.JarvisAmbience.duck(false);assert.equal(t.gains.at(-1),.014);
  t.events.pagehide();assert.equal(t.counts().stops,2);assert.equal(t.counts().closed,1);
  assert.deepEqual(t.requests,['/api/state']);
  console.log('PASS: camera startup opt-in, hidden-page guard, no audio in follower window, browser permission, bounded local music, voice ducking and cleanup.');
})().catch(error=>{console.error(error);process.exitCode=1;});
