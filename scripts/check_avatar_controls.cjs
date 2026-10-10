const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const els = {};
const nativeCanvas=process.env.AVATAR_NATIVE_CANVAS?require(process.env.AVATAR_NATIVE_CANVAS).createCanvas(960,540):null;
const ctx = nativeCanvas?nativeCanvas.getContext('2d'):new Proxy({}, {get: (o,k) => (k==='createRadialGradient'||k==='createLinearGradient') ? ()=>({addColorStop(){}}) : ()=>{},set:()=>true});
const document = {hidden:false,getElementById(id){return els[id] ||= {textContent:'',value:'Hola',setAttribute(k,v){this[k]=v;},getContext(){return ctx;}};}};
const box = {document, window:{JarvisHands:{seen:true,x:0,y:0}},location:{search:'',protocol:'file:'},performance:{timeOrigin:0,now:()=>1000},Date,Math,matchMedia:()=>({matches:false}),requestAnimationFrame(){},setTimeout(){}};
vm.createContext(box);
vm.runInContext(fs.readFileSync('desktop/ui/avatar.js','utf8'),box);
const read = code => vm.runInContext(code,box);
read('loop(100)');
els.motion.onclick();
read('loop(200)');const frozen=read('t');
read('loop(300)');assert.equal(read('t'),frozen,'pause freezes phase even when a hand is detected');
els.style.onclick();assert.equal(els.style.textContent,'Ver núcleo');
els.smile.onclick();assert.equal(read('smile'),1);
read('loop(400)');assert.equal(read('smile'),1,'smile persists during pause');
els.smile.onclick();assert.equal(read('smile'),0);
els.speak.onclick();read('viseme="a";loop(500)');assert.equal(read('talk'),1,'mouth test works while ambience paused');
read('talking=false;window.JarvisHands.seen=false;for(let n=600;n<4000;n+=50)loop(n)');assert.equal(read('talk'),0,'paused mouth returns to rest after the test');
els.motion.onclick();read('loop(4100)');assert.ok(read('t')>frozen,'resume continues phase');
assert.match(els['animation-status'].textContent,/activa/);
console.log('PASS: pause with hand, core/rings toggle, luminous greeting, audio pulse during pause, resume');

const beforeHidden=read('t');read('avatarVisible=false;loop(4200)');assert.equal(read('t'),beforeHidden,'off-screen body skips rendering');read('avatarVisible=true;lastFrame=0;loop(4300)');assert.ok(read('t')>beforeHidden,'body resumes on return');console.log('PASS: off-screen rendering suspension and resume');

if(nativeCanvas){read('particleMode=true;paused=false;loop(5000)');fs.writeFileSync('/tmp/avatar-anatomy.png',nativeCanvas.toBuffer('image/png'));}
