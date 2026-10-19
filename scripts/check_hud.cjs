/* HUD v2 behavior: missing data, real stages, privacy, invalid dates and disconnects. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Element {
 constructor(){this.children=[];this.style={};this.checked=false;this.attributes={};this._text='';this.listeners={};this.classList={contains:()=>true};}
 set textContent(v){this._text=String(v);this.children=[];}get textContent(){return this._text+this.children.map(c=>c.textContent).join(' ');}
 get firstChild(){return this.children[0];}removeChild(e){this.children.splice(this.children.indexOf(e),1);}
 appendChild(e){this.children.push(e);return e;}setAttribute(k,v){this.attributes[k]=v;}addEventListener(k,f){(this.listeners[k]||=[]).push(f);}
 getContext(){return {};}
}
async function scenario(payload){
 const nodes={},get=id=>nodes[id]||(nodes[id]=new Element());let fail=false;const listeners={};
 const document={getElementById:get,createElement:()=>new Element(),documentElement:{},body:new Element(),hidden:false,
 addEventListener:(k,f)=>(listeners[k]||=[]).push(f),dispatchEvent:e=>(listeners[e.type]||[]).forEach(f=>f(e))};
 const matchMedia=()=>({matches:true});
 const window={JarvisMask:require('../desktop/ui/mask.js'),matchMedia,addEventListener(){}};
 const fetch=async url=>{if(url.startsWith('/api/events'))return new Promise(()=>{});if(fail)throw new Error('offline');return {ok:true,json:async()=>url==='/api/hud'?payload:{server:{state:'ok',latency_ms:0,info:{real_trading_active:false}},windows:0,paired:true}};};
 const context=vm.createContext({window,document,fetch,matchMedia,Intl,Date,setInterval(){},setTimeout(){},requestAnimationFrame(){},CustomEvent:class{constructor(type,opt){this.type=type;this.detail=opt.detail;}}});
 for(const file of ['hudx.js','hud.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../desktop/ui',file),'utf8'),context);
 await new Promise(setImmediate);return {get, reveal(){get('hud-reveal').checked=true;get('hud-reveal').onchange();(get('hud-reveal').listeners.change||[]).forEach(f=>f());},async disconnect(){fail=true;get('hud-refresh').onclick();await new Promise(setImmediate);}};
}
(async()=>{
 let s=await scenario({cards:[]});assert.equal(s.get('hx-jobs').textContent,'no data');assert.match(s.get('hx-assist').textContent,/0 ms/);assert.match(s.get('hx-secure').textContent,/Off/);
 s=await scenario({cards:[],jobs:[],jobs_count:0});assert.match(s.get('hx-jobs').textContent,/No hay trabajos abiertos/);
 s=await scenario({cards:[],jobs:[{title:'Trabajo $900',status:'in_progress',stage:'En progreso',progress:50,start:'2026-10-01',due:'2026-10-10'},{title:'Otro',stage:'Cotización',progress:10,start:null,due:'2026-02-30'}]});
 assert.match(s.get('hx-jobs').textContent,/En progreso/);assert.doesNotMatch(s.get('hx-jobs').textContent,/900|function/);
 assert.equal(s.get('hx-gantt').children.filter(e=>e.className==='hx-row').length,1);
 s.reveal();assert.match(s.get('hx-jobs').textContent,/900/);
 await s.disconnect();assert.equal(s.get('hx-jobs').textContent,'no data');assert.match(s.get('hx-assist').textContent,/Offline/);assert.equal(s.get('hx-gauges').children.length,0);
 console.log('HUD v2: real stages, missing and zero values, privacy, dates and offline clearing OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
