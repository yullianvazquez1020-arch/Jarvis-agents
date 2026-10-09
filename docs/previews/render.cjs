/* Optional developer preview exporter. Uses @napi-rs/canvas, never needed by the Mac companion. */
const fs=require('fs'),path=require('path'),vm=require('vm');
const {createCanvas}=require('@napi-rs/canvas');
const source=fs.readFileSync(path.join(__dirname,'../../desktop/ui/visuals.js'),'utf8');
for(const scene of ['orbit','atlas','silhouette']){
  const canvas=createCanvas(1200,645),frames=[];
  canvas.getBoundingClientRect=()=>({width:1200,height:645});
  const window={matchMedia:()=>({matches:true,addEventListener(){}}),devicePixelRatio:1,performance,
    requestAnimationFrame:fn=>(frames.push(fn),frames.length),cancelAnimationFrame(){},addEventListener(){},removeEventListener(){}};
  vm.runInNewContext(source,{window,document:{hidden:false,addEventListener(){},removeEventListener(){}}});
  const engine=window.JarvisVisual.create(canvas,{scene});engine.setQuality('detail');
  engine.setModules(['cobros','vencidos','agenda','balances','stock','mensajes','practica'].map(id=>({id})));
  frames.shift()(100);
  const output=createCanvas(1200,645),context=output.getContext('2d');context.fillStyle='#030e19';
  context.fillRect(0,0,1200,645);context.drawImage(canvas,0,0);
  fs.writeFileSync(path.join(__dirname,scene+'.png'),output.toBuffer('image/png'));
}
