/* Canvas/DOM unit checks; optionally render only the scene with an installed native canvas. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let native=null;if(process.env.ATLAS_NATIVE_CANVAS)native=require(process.env.ATLAS_NATIVE_CANVAS);
let frames=[],draws=0;const nodes={};
const noop=new Proxy({}, {get:(o,k)=>(k==='createRadialGradient'||k==='createLinearGradient')?()=>({addColorStop(){}}):()=>{draws++},set:()=>true});
function el(id='') { return {id,textContent:'',children:[],dataset:{},style:{setProperty(){}},attrs:{},appendChild(c){this.children.push(c)},replaceChildren(){this.children=[]},setAttribute(k,v){this.attrs[k]=v},getContext(){return this.canvas?this.canvas.getContext('2d'):noop},getBoundingClientRect(){return {left:0,right:1,top:0,bottom:1}},click(){this.onclick?.()}}; }
for(const id of ['portfolio','atlas','atlas-list','atlas-detail','hand-navigation','atlas-hand-status','atlas-motion','atlas-quality','membrane-mini','brain-mini','audio-mini','observatory-hand','observatory-voice','atlas-view-name','atlas-connect','atlas-live-status','atlas-live'])nodes[id]=el(id);
if(native){for(const id of ['atlas','membrane-mini','brain-mini','audio-mini'])nodes[id].canvas=native.createCanvas(id==='atlas'?1100:300,id==='atlas'?650:id==='audio-mini'?70:180)}
const tabs=['tower','galaxy','cell'].map(mode=>{const e=el();e.dataset.atlas=mode;return e});nodes.portfolio.querySelectorAll=()=>tabs;
const box={document:{hidden:false,getElementById:id=>nodes[id],createElement:()=>el()},window:{},matchMedia:()=>({matches:false}),requestAnimationFrame:cb=>frames.push(cb),addEventListener(){},innerWidth:1600,innerHeight:900,Math};
vm.runInNewContext(fs.readFileSync('desktop/ui/atlas.js','utf8'),box);
function frame(now){const f=frames.shift();assert.ok(f);f(now)}
frame(1000);assert.equal(nodes['atlas-list'].children.length,5);assert.match(nodes['observatory-hand'].textContent,/apagada/);
if(native)fs.writeFileSync('/tmp/observatory-scene.png',nodes.atlas.canvas.toBuffer('image/png'));
nodes['atlas-motion'].onclick();assert.equal(nodes['atlas-motion'].attrs['aria-pressed'],'true');
if(native){frame(1100);const a=nodes.atlas.canvas.toBuffer('image/png');frame(1300);assert.deepEqual(nodes.atlas.canvas.toBuffer('image/png'),a,'pause freezes art');}
for(const t of tabs){t.onclick();frame(1500+tabs.indexOf(t)*100)}
nodes['atlas-list'].children[4].onclick();assert.match(nodes['atlas-detail'].children[0].textContent,/81–100/);
box.window.JarvisHands={seen:true,running:true,landmarks:Array(21)};box.window.JarvisAvatar={telemetry:()=>({audioActive:true,amplitude:.4})};frame(2500);
assert.match(nodes['observatory-hand'].textContent,/21/);assert.match(nodes['observatory-voice'].textContent,/RMS/);
box.document.hidden=true;const count=draws;frame(2700);assert.equal(draws,count);
console.log('PASS: three views, five reserved sectors, pause, real-state labels, hidden-page stop. Canvas test, not browser layout.');

(async()=>{
  let calls=[];
  box.fetch=async path=>{calls.push(path);return {ok:true,json:async()=>path==='/api/state'?{demo:true,paired:false,server_configured:true}:{}};};
  await nodes['atlas-connect'].onclick();
  assert.deepEqual(calls,['/api/state']);assert.match(nodes['atlas-live-status'].textContent,/Sin datos reales/);
  calls=[];box.fetch=async path=>{calls.push(path);return {ok:true,json:async()=>path==='/api/state'?{demo:false,paired:true,server_configured:true}:{demo:false,panel:path.split('/').pop(),title:'ISLAFIX',lines:['Dato confirmado'],as_of:'2026-10-10'}};};
  await nodes['atlas-connect'].onclick();
  assert.equal(calls.length,4);assert.match(nodes['atlas-live-status'].textContent,/3 fuentes/);
  assert.ok(nodes['atlas-live'].children.some(n=>n.textContent==='Dato confirmado'));
  assert.equal(nodes['atlas-connect'].disabled,false);
  console.log('PASS: explicit read-only refresh; DEMO blocked; three real panels; no model or action requests.');
})().catch(e=>{console.error(e);process.exitCode=1;});
