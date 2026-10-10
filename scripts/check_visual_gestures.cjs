/* Real classifier and atlas integration, simulated landmarks: no camera or OS pointer. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map(),listeners={};
const ctx=new Proxy({}, {get:(_,key)=>key==='createRadialGradient'||key==='createLinearGradient'?()=>({addColorStop(){}}):()=>{}});
function element(id){if(elements.has(id))return elements.get(id);const e={id,children:[],dataset:{},style:{setProperty(){}},width:1100,height:650,textContent:'',setAttribute(){},appendChild(c){this.children.push(c);},replaceChildren(){this.children=[];},getContext:()=>ctx,getBoundingClientRect:()=>({width:1100,left:5000,right:5100,top:5000,bottom:5100}),click(){this.onclick?.();}};elements.set(id,e);return e;}
const tabs=['tower','galaxy','cell'].map(m=>{const e=element(m);e.dataset.atlas=m;return e;});
element('portfolio').querySelectorAll=()=>tabs;
const w={devicePixelRatio:1};
let now=1000;
const context={window:w,document:{hidden:false,getElementById:element,createElement:()=>element('new-'+elements.size)},matchMedia:()=>({matches:false}),requestAnimationFrame(){},addEventListener:(name,fn)=>listeners[name]=fn,innerWidth:1100,innerHeight:650,performance:{now:()=>now},console};
vm.runInNewContext(fs.readFileSync('desktop/ui/gestures.js','utf8'),context);
function hand(count=0,cx=.4,pinch=false){const p=Array.from({length:21},()=>({x:cx,y:.7}));p[0]={x:cx,y:.9};p[5]={x:cx-.08,y:.7};p[17]={x:cx+.08,y:.7};[8,12,16,20].forEach((tip,i)=>{p[tip]={x:cx,y:i<count?.3:.8};p[tip-2]={x:cx,y:.6};});p[4]={x:cx+(pinch?.01:.15),y:p[8].y};return p;}
const G=w.JarvisGestures;
assert.equal(G.pose(hand(0)).command,'pause');assert.equal(G.pose(hand(4)).command,'resume');assert.equal(G.pose(hand(2)).command,'next');assert.equal(G.pose(hand(1)).command,null);
assert.equal(G.pose([]),null);const bad=hand();bad[7].x=NaN;assert.equal(G.pose(bad),null);
assert.ok(G.zoomDistance([{landmarks:hand(1,.3,true)},{landmarks:hand(1,.7,true)}])>.3);
assert.equal(G.zoomDistance([{landmarks:hand(1)}]),null);
vm.runInNewContext(fs.readFileSync('desktop/ui/atlas.js','utf8'),context);
// Access the real gesture consumer in this same script context.
const source=fs.readFileSync('desktop/ui/atlas.js','utf8').replace('select(0);requestAnimationFrame(frame);','select(0);window.testVisual={gesture,frame,values:()=>({zoom,paused,mode})};requestAnimationFrame(frame);');
vm.runInNewContext(source,context);
const api=w.testVisual;
w.JarvisHands={seen:true,landmarks:hand(2),updatedAt:now,hands:[]};element('hand-navigation').click();
function step(t){now=t;w.JarvisHands.updatedAt=t;api.gesture(t);}
step(1000);step(2000);assert.equal(api.values().mode,'galaxy');step(3100);assert.equal(api.values().mode,'galaxy'); // hold fires once
w.JarvisHands.landmarks=hand(0);step(3200);step(4200);assert.equal(api.values().paused,true);
w.JarvisHands.landmarks=hand(4);step(4300);step(5300);assert.equal(api.values().paused,false);
w.JarvisHands.hands=[{landmarks:hand(1,.4,true)},{landmarks:hand(1,.6,true)}];step(5400);
w.JarvisHands.hands=[{landmarks:hand(1,.2,true)},{landmarks:hand(1,.8,true)}];step(5500);assert.ok(api.values().zoom>1 && api.values().zoom<=2.5);
const fixed=api.values().zoom;w.JarvisHandMouseActive=true;step(5600);assert.equal(api.values().zoom,fixed);
w.JarvisHandMouseActive=false;w.JarvisHands.seen=false;step(5700);assert.equal(api.values().zoom,fixed);
listeners.keydown({key:'Escape'});w.JarvisHands.seen=true;step(5800);assert.equal(api.values().zoom,fixed);
element('atlas-reset-zoom').click();assert.equal(api.values().zoom,1);
console.log('PASS: pose validation, two pinch zoom, sustained command latch, tracking loss, native mouse exclusion, Escape and zoom reset.');
