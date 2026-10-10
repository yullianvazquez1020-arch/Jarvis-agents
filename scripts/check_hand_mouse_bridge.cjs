/* Browser bridge checks with fake HTTP and no physical pointer. */
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict'), path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../desktop/ui/hand-mouse.js'),'utf8');
const flush = async () => { for(let i=0;i<30;i++) await Promise.resolve(); };
function setup() {
  const elements=[], listeners={}, intervals=[], calls=[];
  const parent={appendChild(){},insertAdjacentElement(){}};
  const h={running:true,seen:true,updatedAt:990,landmarks:Array.from({length:21},()=>({x:.5,y:.5}))};
  let deferred=null;
  const context={
    document:{hidden:false,getElementById:()=>({parentNode:parent}),createElement:()=>{const e={setAttribute(){}};elements.push(e);return e;},addEventListener:(name,cb)=>listeners[name]=cb},
    window:{JarvisHands:h},performance:{now:()=>1000},Date,
    setInterval:(cb,ms)=>intervals.push({cb,ms}),addEventListener:(name,cb)=>listeners[name]=cb,
    fetch:async(url,options)=>{
      const body=options?.body?JSON.parse(options.body):null;calls.push({url,body,options});
      if(url.endsWith('/arm')&&deferred) await deferred.promise;
      return {ok:true,json:async()=>url.endsWith('/arm')?{lease:'test-grant',width:3840,height:1080}: {active:true,remaining:59}};
    }
  };
  vm.runInNewContext(source,context);
  return {context,h,calls,listeners,button:elements[0],intervals,
    defer:()=>{let resolve;const promise=new Promise(r=>resolve=r);deferred={promise,resolve};return resolve;}};
}
(async()=>{
  let t=setup();t.h.running=false;await t.button.onclick();assert.equal(t.calls.length,0);
  t=setup();await t.button.onclick();
  assert.equal(t.calls[0].body.confirm,'SOLO_MOVER_60S');
  assert.equal(t.context.window.JarvisHandMouseActive,true);
  const tick=t.intervals.find(i=>i.ms===100).cb;
  await tick();assert.equal(t.calls[1].url,'/api/hand-mouse/frame');
  assert.deepEqual(Object.keys(t.calls[1].body).sort(),['captured_ms','lease','seq','x','y']);
  await tick();assert.equal(t.calls.length,2); // no duplicate sample
  t.h.updatedAt=100;await tick();assert.equal(t.calls.length,2); // no stale sample
  t.listeners.keydown({key:'Escape'});await flush();
  assert.equal(t.context.window.JarvisHandMouseActive,false);
  assert.equal(t.calls[2].url,'/api/hand-mouse/stop');
  await tick();assert.equal(t.calls.length,3);
  t=setup();const release=t.defer();const arming=t.button.onclick();
  t.listeners.pagehide();release();await arming;await flush();
  assert.equal(t.context.window.JarvisHandMouseActive,false);
  assert.equal(t.calls.at(-1).url,'/api/hand-mouse/stop');
  t=setup();await t.button.onclick();t.context.document.hidden=true;t.listeners.visibilitychange();await flush();
  assert.equal(t.context.window.JarvisHandMouseActive,false);
  assert.equal(t.calls.at(-1).url,'/api/hand-mouse/stop');
  console.log('PASS: explicit activation, one fresh sample, no clicks, Escape, hidden tab and late activation cancellation.');
})().catch(error=>{console.error(error);process.exitCode=1;});
