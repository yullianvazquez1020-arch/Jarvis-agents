/* Mechanical display artwork. No decorative motion is presented as measured activity. */
(function(root){"use strict";
function create(canvas,onMotion){
 var ctx=canvas.getContext('2d'),cache=document.createElement('canvas'),bg=cache.getContext('2d');
 var media=root.matchMedia('(prefers-reduced-motion: reduce)'),paused=media.matches,id=null,dirty=true,last=0,time=0;
 var width=0,height=0,ratio=1;
 function ring(c,r,stroke,lw){c.beginPath();c.arc(0,0,r,0,Math.PI*2);c.strokeStyle=stroke;c.lineWidth=lw;c.stroke();}
 function disc(c,r,fill){c.beginPath();c.arc(0,0,r,0,Math.PI*2);c.fillStyle=fill;c.fill();}
 function metal(c,a,b){var g=c.createLinearGradient(-a,-b,a,b);g.addColorStop(0,'#132630');g.addColorStop(.28,'#75939d');g.addColorStop(.43,'#c5d8d9');g.addColorStop(.53,'#3c6575');g.addColorStop(.78,'#101d26');g.addColorStop(1,'#607e8b');return g;}
 function build(){
  var box=canvas.getBoundingClientRect();width=Math.max(1,box.width);height=Math.max(1,box.height);
  ratio=Math.min(root.devicePixelRatio||1,1.25,1400/width,1400/height);
  canvas.width=cache.width=Math.round(width*ratio);canvas.height=cache.height=Math.round(height*ratio);
  bg.setTransform(ratio,0,0,ratio,0,0);bg.clearRect(0,0,width,height);
  var r=Math.min(width,height)*.445;bg.save();bg.translate(width/2,height/2);bg.scale(r/250,r/250);
  var halo=bg.createRadialGradient(0,0,90,0,0,270);halo.addColorStop(0,'rgba(52,177,218,.15)');halo.addColorStop(.73,'rgba(45,126,157,.11)');halo.addColorStop(1,'rgba(0,0,0,0)');bg.fillStyle=halo;bg.fillRect(-270,-270,540,540);
  bg.save();bg.translate(6,11);disc(bg,241,'#00070d');bg.restore();
  disc(bg,240,metal(bg,240,120));disc(bg,228,'#031019');ring(bg,235,'#85a4b1',1);ring(bg,225,'#264a59',4);
  for(var i=0;i<16;i++){
   bg.save();bg.rotate(i*Math.PI/8);
   bg.fillStyle=metal(bg,30,225);bg.fillRect(-21,-228,42,64);bg.strokeStyle='#08151b';bg.lineWidth=2;bg.strokeRect(-21,-228,42,64);
   bg.fillStyle='#050e15';bg.fillRect(-17,-217,34,49);
   var copper=bg.createLinearGradient(-15,0,15,0);copper.addColorStop(0,'#69453c');copper.addColorStop(.32,'#e0b399');copper.addColorStop(.5,'#a1745e');copper.addColorStop(.8,'#e2b294');copper.addColorStop(1,'#654330');
   for(var n=0;n<14;n++){bg.fillStyle=copper;bg.fillRect(-15,-214+n*3,30,1.7);}
   bg.fillStyle='#64cfe8';bg.fillRect(-4,-166,8,10);bg.fillStyle='#193c4a';bg.fillRect(-10,-239,20,7);
   for(var side of [-1,1]){bg.beginPath();bg.arc(side*23,-194,6,0,Math.PI*2);bg.fillStyle='#101d25';bg.fill();bg.strokeStyle='#7895a0';bg.lineWidth=1.5;bg.stroke();bg.beginPath();bg.moveTo(side*23-2,-194);bg.lineTo(side*23+2,-194);bg.stroke();}
   bg.rotate(Math.PI/16);bg.fillStyle='#145472';bg.fillRect(-10,-225,20,45);bg.fillStyle='#8aedff';bg.fillRect(-5,-219,10,32);bg.fillStyle='#f1fcff';bg.fillRect(-3,-219,3,32);bg.restore();
  }
  disc(bg,169,metal(bg,160,80));ring(bg,172,'#a6d4df',3);ring(bg,165,'#1b4155',3);disc(bg,149,'#071b27');
  for(var j=0;j<32;j++){bg.save();bg.rotate(j*Math.PI/16);bg.fillStyle=j%2?'#88c9d9':'#21495f';bg.fillRect(-4,-157,8,19);bg.restore();}
  disc(bg,133,metal(bg,170,40));ring(bg,133,'#061821',4);ring(bg,125,'#b7e3e9',2);disc(bg,116,'#092536');
  for(var k=0;k<12;k++){bg.save();bg.rotate(k*Math.PI/6);bg.fillStyle='#06131f';bg.fillRect(-10,-123,20,30);bg.fillStyle='#478da4';bg.fillRect(-6,-119,12,22);bg.fillStyle='#a9ecfa';bg.fillRect(-3,-118,3,19);bg.restore();}
  disc(bg,94,metal(bg,90,10));ring(bg,90,'#b0f6ff',3);disc(bg,80,'#103145');ring(bg,78,'#36a7c8',6);ring(bg,70,'#c6f9ff',3);
  var core=bg.createRadialGradient(-17,-12,1,0,0,66);core.addColorStop(0,'#f1ffff');core.addColorStop(.55,'#a8e9ef');core.addColorStop(1,'#176b86');disc(bg,66,core);
  bg.save();bg.beginPath();bg.arc(0,0,63,0,Math.PI*2);bg.clip();bg.fillStyle='#397d9155';
  for(var row=-12;row<=12;row++)for(var col=-12;col<=12;col++){bg.beginPath();bg.arc(col*7+(row%2)*3.5,row*6,1.7,0,Math.PI*2);bg.fill();}bg.restore();ring(bg,64,'#ecffff',1);
  // Foreground clamps make the rings read as hardware with depth.
  for(var q=0;q<4;q++){bg.save();bg.rotate(q*Math.PI/2+.35);bg.fillStyle=metal(bg,25,180);bg.beginPath();bg.moveTo(-14,-183);bg.lineTo(13,-183);bg.lineTo(20,-139);bg.lineTo(9,-92);bg.lineTo(-9,-92);bg.lineTo(-19,-139);bg.closePath();bg.fill();bg.strokeStyle='#9cb9c2';bg.lineWidth=1;bg.stroke();bg.beginPath();bg.arc(0,-167,9,0,Math.PI*2);bg.fillStyle='#102833';bg.fill();bg.stroke();bg.restore();}
  bg.restore();dirty=false;
 }
 function frame(now){id=null;if(document.hidden)return;
  if(dirty)build();
  if(last===0||now-last>=1000/24||paused){if(!paused&&last)time+=Math.min(now-last,80)/1000;last=now;
   ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(cache,0,0);
   ctx.setTransform(ratio,0,0,ratio,0,0);ctx.save();ctx.translate(width/2,height/2);var r=Math.min(width,height)*.445;ctx.scale(r/250,r/250);
   ctx.rotate(time*.065);ctx.strokeStyle='#bcf5ff';ctx.lineWidth=1.6;ctx.globalAlpha=.65;
   for(var i=0;i<6;i++){ctx.beginPath();ctx.arc(0,0,103,i*Math.PI/3,i*Math.PI/3+.47);ctx.stroke();}
   ring(ctx,246,'#36657a',.7);ctx.restore();ctx.globalAlpha=1;
  }
  if(!paused)id=root.requestAnimationFrame(frame);
 }
 function schedule(){if(!document.hidden&&id===null)id=root.requestAnimationFrame(frame);}
 function motion(v){paused=v;last=0;if(id!==null)root.cancelAnimationFrame(id);id=null;schedule();if(onMotion)onMotion(paused);}
 root.addEventListener('resize',function(){dirty=true;last=0;schedule();});
 document.addEventListener('visibilitychange',function(){if(id!==null)root.cancelAnimationFrame(id);id=null;last=0;if(!document.hidden)schedule();});
 var change=function(e){motion(e.matches);};if(media.addEventListener)media.addEventListener('change',change);else if(media.addListener)media.addListener(change);
 schedule();if(onMotion)onMotion(paused);return {toggle:function(){motion(!paused);}};
}
root.JarvisReactor={create:create};
})(window);
