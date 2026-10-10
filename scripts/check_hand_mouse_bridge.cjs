/* Browser bridge checks with fake HTTP and no physical pointer. */
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict'), path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../desktop/ui/hand-mouse.js'),'utf8');
const flush = async () => { for(let i=0;i<30;i++) await Promise.resolve(); };
function setup(savedProfile=null) {
  const elements=[], listeners={}, intervals=[], calls=[];
  const parent={appendChild(){},insertAdjacentElement(){}};
  const h={running:true,seen:true,updatedAt:990,landmarks:Array.from({length:21},()=>({x:.5,y:.5}))};
  let deferred=null; const storage=new Map(savedProfile ? [["jarvis-hand-profile-v1",JSON.stringify(savedProfile)]] : []);
  const context={
    document:{hidden:false,getElementById:()=>({parentNode:parent}),createElement:()=>{const e={style:{},appendChild(){},setAttribute(){},insertAdjacentElement(){}};elements.push(e);return e;},addEventListener:(name,cb)=>listeners[name]=cb},
    localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
    window:{JarvisHands:h,confirm:()=>true},performance:{now:()=>1000},Date,
    setInterval:(cb,ms)=>intervals.push({cb,ms}),addEventListener:(name,cb)=>listeners[name]=cb,
    fetch:async(url,options)=>{
      const body=options?.body?JSON.parse(options.body):null;calls.push({url,body,options});
      if(url.endsWith('/arm')&&deferred) await deferred.promise;
      return {ok:true,json:async()=>url.endsWith('/arm')?{lease:'test-grant',width:3840,height:1080}: {active:true,remaining:59}};
    }
  };
  vm.runInNewContext(source,context);
  return {context,h,calls,listeners,elements,storage,button:elements[0],clickButton:elements[1],practice:elements[3],intervals,
    defer:()=>{let resolve;const promise=new Promise(r=>resolve=r);deferred={promise,resolve};return resolve;}};
}
(async()=>{
  let t=setup();t.practice.onclick();assert.equal(t.practice.textContent,'Probar clic · 1');assert.equal(t.calls.length,0);t.h.running=false;await t.button.onclick();assert.equal(t.calls.length,0);
  t=setup();await t.button.onclick();
  assert.equal(t.calls[0].body.confirm,'SOLO_MOVER_60S');
  assert.equal(t.context.window.JarvisHandMouseActive,true);
  const tick=t.intervals.find(i=>i.ms===40).cb;
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
  t=setup();t.context.window.confirm=()=>false;await t.clickButton.onclick();
  assert.equal(t.calls.length,0); // declining explicit click opt-in does not arm
  t=setup();await t.clickButton.onclick();
  assert.equal(t.calls[0].body.confirm,'MOVER_Y_CLIC_60S');
  const clickTick=t.intervals.find(i=>i.ms===40).cb;
  t.h.landmarks[5]={x:.4,y:.5};t.h.landmarks[17]={x:.6,y:.5};
  t.h.landmarks[4]={x:.7,y:.5};
  await clickTick();
  assert.ok(Math.abs(t.calls.at(-1).body.pinch_ratio-1)<1e-9);
  assert.deepEqual(Object.keys(t.calls.at(-1).body).sort(),['captured_ms','lease','pinch_ratio','seq','x','y']);
  const before=t.calls.length;await clickTick();assert.equal(t.calls.length,before);
  t.h.updatedAt=991;t.h.landmarks[4]={x:.51,y:.5};await clickTick();
  assert.ok(Math.abs(t.calls.at(-1).body.pinch_ratio-.05)<1e-9);
  t.h.seen=false;await clickTick();assert.equal(t.calls.at(-1).body.pinch_ratio,null);
  t.h.seen=true;t.h.updatedAt=100;await clickTick();assert.equal(t.calls.at(-1).body.pinch_ratio,null);
  t.h.updatedAt=992;t.h.landmarks[17]={x:.4,y:.5};await clickTick();
  assert.equal(t.calls.at(-1).body.pinch_ratio,null); // degenerate palm never creates pinch
  t.listeners.keydown({key:'Escape'});await flush();
  assert.equal(t.calls.at(-1).url,'/api/hand-mouse/stop');
  const stoppedCount=t.calls.length;await clickTick();assert.equal(t.calls.length,stoppedCount);
  t=setup();const releaseClick=t.defer();const armingClick=t.clickButton.onclick();
  t.listeners.pagehide();releaseClick();await armingClick;await flush();
  assert.equal(t.context.window.JarvisHandMouseActive,false);
  assert.equal(t.calls.at(-1).url,'/api/hand-mouse/stop');
  t=setup();await t.elements[4].onclick();assert.equal(t.calls[0].body.confirm,'DESPLAZAR_60S');
  t.h.landmarks[0]={x:.5,y:.8};
  for(const i of [6,10,14,18]) t.h.landmarks[i]={x:.5,y:.6};
  for(const i of [8,12]) t.h.landmarks[i]={x:.5,y:.2};
  for(const i of [16,20]) t.h.landmarks[i]={x:.5,y:.7};
  await t.intervals[0].cb();assert.equal(t.calls.at(-1).body.two_fingers,true);
  assert.equal('pinch_ratio' in t.calls.at(-1).body,false);
  t.h.seen=false;await t.intervals[0].cb();assert.equal(t.calls.at(-1).body.two_fingers,false);
  t=setup();await t.elements[5].onclick();assert.equal(t.calls[0].body.confirm,'ARRASTRAR_60S');
  t.listeners.keydown({key:'Escape'});await flush();assert.equal(t.calls.at(-1).url,'/api/hand-mouse/stop');
  t=setup({span:.5,cx:.5,cy:.5});assert.equal(t.calls.length,0); // saved profile does not activate
  await t.button.onclick();t.h.landmarks[8]={x:.6,y:.5};await t.intervals[0].cb();
  assert.ok(Math.abs(t.calls.at(-1).body.x-.7)<1e-9);
  t.elements[6].onclick();assert.equal(t.context.window.JarvisHandMouseActive,false);
  assert.equal(JSON.parse(t.storage.get('jarvis-hand-profile-v1')).cx,.6);
  t=setup({span:0,cx:999,cy:null});await t.button.onclick();await t.intervals[0].cb();
  assert.equal(t.calls.at(-1).body.x,.5); // invalid persisted calibration ignored
  console.log('PASS: scroll/drag isolation, loss of hand, saved calibration without autoactivation; move-only isolation, explicit click consent, measured ratio, tracking loss, Escape, hidden tab and late activation cancellation.');
})().catch(error=>{console.error(error);process.exitCode=1;});
