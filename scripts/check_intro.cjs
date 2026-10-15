/* Run real intro code against controlled audio promises, ownership and timers. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('desktop/ui/arranque.js','utf8');
const settle=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
async function harness({reject=false,owner=true,recording=false}={}){
 const events={},timers=new Map(),requests=[],sounds=[],memory=new Map();let id=0;
 const window={JarvisAudioOwner:owner};
 const document={hidden:false,getElementById:()=>({classList:{contains:()=>recording}}),addEventListener:(k,v)=>events[k]=v};
 function Audio(){sounds.push(this);this.play=()=>reject?Promise.reject(Error('gesture')):Promise.resolve();this.pause=()=>this.paused=true;this.removeAttribute=()=>{};this.load=()=>{};}
 const context={window,document,Audio,sessionStorage:{getItem:k=>memory.get(k),setItem:(k,v)=>memory.set(k,v)},
 addEventListener:(k,v)=>events[k]=v,removeEventListener:k=>delete events[k],setTimeout:(fn,ms)=>{timers.set(++id,{fn,ms});return id;},clearTimeout:k=>timers.delete(k),
 fetch:async url=>{requests.push(url);return {ok:true,json:async()=>({startup:{sound:true,greeting:true}})};}};
 vm.runInNewContext(source,context);await settle();
 return {window,events,timers,requests,sounds,memory,allow:()=>reject=false};
}
(async()=>{
 let h=await harness();assert.equal(h.sounds.length,1);assert.equal(h.sounds[0].loop,false);
 h.sounds[0].onplaying();const timer=[...h.timers.values()][0];assert.equal(timer.ms,4000);timer.fn();
 assert.equal(h.sounds[0].paused,true);assert.equal(h.requests.filter(x=>x==='/api/greet').length,1);
 h.window.JarvisStopIntro();assert.equal(h.requests.filter(x=>x==='/api/greet').length,1);
 h=await harness();h.sounds[0].onplaying();h.window.JarvisStopIntro();assert.equal(h.sounds[0].paused,true);assert.equal(h.timers.size,0);assert.ok(!h.requests.includes('/api/greet'));
 h=await harness({reject:true});assert.ok(h.events.pointerdown);h.window.JarvisStopIntro();assert.equal(h.events.pointerdown,undefined);assert.ok(!h.requests.includes('/api/greet'));
 h=await harness({reject:true});h.allow();h.events.pointerdown();await settle();assert.equal(h.sounds.length,2);h.sounds[1].onended();assert.equal(h.requests.filter(x=>x==='/api/greet').length,1);
 h=await harness({owner:false});assert.equal(h.sounds.length,0);
 h=await harness({recording:true});assert.equal(h.sounds.length,0);
 h=await harness();h.events['jarvis-audio-owner']({detail:false});assert.equal(h.sounds[0].paused,true);
 console.log('PASS: intro bounded to 4s, no loop, microphone/ownership cancellation, autoplay rejection and retry, greeting exactly once.');
})().catch(e=>{console.error(e);process.exitCode=1;});
