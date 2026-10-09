"""Render budgets and lifecycle of the decorative desktop scenes, without a browser or network."""
import shutil
import subprocess
import unittest
from pathlib import Path


class DesktopVisuals(unittest.TestCase):
    def test_adaptive_budget_and_animation_lifecycle(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node no está instalado")
        source = Path(__file__).resolve().parents[1] / "desktop/ui/visuals.js"
        script = r'''
const vm=require('vm'),fs=require('fs'),assert=require('assert');
const script=fs.readFileSync(process.argv[1],'utf8');
function setup(reduced=false){
  let frames=new Map(),next=0,time=0,cost=2,clock=0,phase=0,draws=0;
  const events={},preferences={},changes=[];
  const context=new Proxy({}, {get:(o,k)=>k==='createRadialGradient'?()=>({addColorStop(){}}):k==='fillRect'?()=>{draws++;}:()=>{},set:(o,k,v)=>(o[k]=v,true)});
  const canvas={width:0,height:0,getContext:()=>context,getBoundingClientRect:()=>({width:8192,height:4320})};
  const document={hidden:false,addEventListener:(n,f)=>events[n]=f,removeEventListener:n=>delete events[n]};
  const window={devicePixelRatio:3,performance:{now(){phase=1-phase;if(!phase)clock+=cost;return clock;}},
    matchMedia:()=>({matches:reduced,addEventListener:(n,f)=>preferences[n]=f,removeEventListener:n=>delete preferences[n]}),
    requestAnimationFrame:f=>{frames.set(++next,f);return next;},cancelAnimationFrame:id=>frames.delete(id),
    addEventListener:(n,f)=>events[n]=f,removeEventListener:n=>delete events[n]};
  vm.runInNewContext(script,{window,document});
  const engine=window.JarvisVisual.create(canvas,{onQuality:(q,r)=>changes.push([q,r])});
  function pump(n){for(let i=0;i<n;i++){time+=50;const batch=[...frames.values()];frames.clear();batch.forEach(f=>f(time));}}
  return {engine,canvas,document,changes,frames,events,preferences,pump,setCost:c=>cost=c,draws:()=>draws};
}
const a=setup();a.pump(64);assert.equal(a.changes.at(-1)[0],'detail');
a.setCost(25);a.pump(40);assert.equal(a.changes.at(-1)[0],'eco');
assert(a.canvas.width<=1920&&a.canvas.height<=1080,'large displays must have bounded backing storage');
a.engine.setQuality('detail');a.pump(80);assert.equal(a.changes.at(-1)[0],'detail','manual choice remains explicit');
a.document.hidden=true;a.events.visibilitychange();assert.equal(a.frames.size,0,'hidden tab cancels animation');
let before=a.draws();a.pump(5);assert.equal(a.draws(),before);
a.document.hidden=false;a.events.visibilitychange();a.pump(1);assert(a.draws()>before);
a.engine.toggleMotion();a.pump(1);before=a.draws();assert.equal(a.frames.size,0,'paused animation does not busy-loop');
a.engine.setActivity(1);a.pump(3);assert.equal(a.draws(),before,'phrase activity respects pause');
a.engine.setScene('atlas');a.engine.setModules(Array.from({length:20},(_,i)=>({id:String(i)})));a.pump(1);
assert.equal(a.engine.getNodePositions().length,8);assert.equal(a.frames.size,0);
a.engine.dispose();assert.equal(a.frames.size,0);assert(!a.events.visibilitychange);assert(!a.preferences.change);
const b=setup(true);b.pump(1);assert.equal(b.frames.size,0,'initial reduced motion renders one still');
b.preferences.change({matches:false});b.pump(2);assert.equal(b.frames.size,1);
b.preferences.change({matches:true});b.pump(1);assert.equal(b.frames.size,0);
for(const scene of ['orbit','atlas','silhouette','face']){b.engine.setScene(scene);b.pump(1);}
b.engine.dispose();
'''
        result = subprocess.run([node, "-e", script, str(source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
