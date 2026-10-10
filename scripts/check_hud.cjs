/* Behavioral HUD checks without a browser, network, or private business data. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Element {
 constructor(){this.children=[];this.style={};this.checked=false;this.attributes={};this._text='';}
 set textContent(v){this._text=String(v);this.children=[];}get textContent(){return this._text+this.children.map(c=>c.textContent).join(' ');}
 appendChild(e){this.children.push(e);return e;}setAttribute(k,v){this.attributes[k]=v;}
}
async function scenario(payload){
 const nodes={},get=id=>nodes[id]||(nodes[id]=new Element());let fail=false;
 const document={getElementById:get,createElement:()=>new Element(),documentElement:{}};
 const window={JarvisMask:require('../desktop/ui/mask.js'),JarvisReactor:{create:()=>({toggle(){}})}};
 const fetch=async url=>{if(url.startsWith('/api/events'))return new Promise(()=>{});if(fail)throw new Error('offline');return {ok:true,json:async()=>url==='/api/hud'?payload:{server:{state:'ok',latency_ms:0,age_s:0,info:{real_trading_active:false}},windows:0,paired:true}};};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../desktop/ui/hud.js'),'utf8'),{window,document,fetch,Intl,Date,setInterval(){},setTimeout(){}});
 await new Promise(setImmediate);return {get,async disconnect(){fail=true;get('hud-refresh').onclick();await new Promise(setImmediate);}};
}
(async()=>{
 let s=await scenario({cards:[]});assert.equal(s.get('metric-jobs').textContent,'sin dato');assert.equal(s.get('job-list').textContent,'sin dato');
 assert.equal(s.get('metric-latency').textContent,'0');assert.equal(s.get('metric-windows').textContent,'0');assert.equal(s.get('sec-storage').textContent,'sin dato');
 s=await scenario({cards:[],jobs:[],jobs_count:0});assert.equal(s.get('metric-jobs').textContent,'0');assert.match(s.get('job-list').textContent,/Sin trabajos abiertos/);
 s=await scenario({cards:[],jobs:[{title:'Trabajo $900',status:'in_progress',created:'2026-10-01',due_date:'2026-10-10'},{title:'Otro',status:'toString',created:'2026-02-30',due_date:null}],jobs_count:2});
 assert.match(s.get('job-list').textContent,/En proceso/);assert.match(s.get('job-list').textContent,/sin dato/);assert.doesNotMatch(s.get('job-list').textContent,/900|function/);
 assert.match(s.get('timeline').textContent,/2026-10-01/);assert.doesNotMatch(s.get('timeline').textContent,/2026-02-30/);
 s.get('hud-reveal').checked=true;s.get('hud-reveal').onchange();assert.match(s.get('job-list').textContent,/900/);
 await s.disconnect();assert.equal(s.get('metric-jobs').textContent,'sin dato');assert.equal(s.get('metric-latency').textContent,'sin dato');assert.equal(s.get('timeline').textContent,'sin dato');
 console.log('HUD: known stages, missing values, zero values, dates, privacy and offline clearing OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
