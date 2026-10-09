"""Regression: repeated playing events must retain only one animation clock."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class VoiceSyncLifecycle(unittest.TestCase):
    def test_replay_cancels_clock_and_ignores_obsolete_decoder(self):
        script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('desktop/ui/app.js','utf8');
const chunk=src.slice(src.indexOf('  var voice = (function ()'),src.indexOf('  window.JarvisVoiceSync'));
let seq=0;const frames=new Map(),pending=[],messages=[];
const ctx={window:{JarvisLipsync:require('./desktop/ui/lipsync.js'),BroadcastChannel:true},location:{search:''},
 performance:{timeOrigin:1000,now:()=>100},Date,
 BroadcastChannel:class{postMessage(m){messages.push(m)}},
 requestAnimationFrame:f=>{frames.set(++seq,f);return seq},cancelAnimationFrame:id=>frames.delete(id),
 setInterval:()=>1,clearInterval:()=>{},fetch:()=>new Promise((ok,bad)=>pending.push({ok,bad}))};
vm.createContext(ctx);vm.runInContext(chunk,ctx);
function audio(){const handlers={};return {paused:false,ended:false,readyState:4,currentTime:0,playbackRate:1,
 addEventListener:(k,f)=>(handlers[k]??=[]).push(f),removeEventListener:(k,f)=>handlers[k]=handlers[k].filter(x=>x!==f),
 emit:k=>(handlers[k]||[]).forEach(f=>f())}}
(async()=>{const a=audio();ctx.voice.attach(a,'same');a.emit('playing');a.emit('playing');assert.equal(frames.size,1);
ctx.voice.detach(a);assert.equal(frames.size,0);
const b=audio();ctx.voice.attach(b,'same');b.emit('playing');assert.equal(frames.size,1);
messages.length=0;pending[0].bad(new Error('old decode failed'));await new Promise(r=>setImmediate(r));
assert.equal(messages.filter(m=>m.k==='stop').length,0);
ctx.voice.detach(b);assert.equal(frames.size,0);
})().catch(e=>{console.error(e);process.exit(1)});
'''
        subprocess.run(['node','-e',script],cwd=ROOT,check=True)
