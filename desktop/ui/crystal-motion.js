/* Lightweight moving orbital geometry. Decorative motion is not activity telemetry. */
(function(){'use strict';
  var canvas=document.getElementById('crystal-motion');if(!canvas)return;
  var ctx=canvas.getContext('2d');if(!ctx)return;
  var w=0,h=0,scale=1,ox=0,oy=0,last=0,raf=0,amp=0,mic=0,micAt=0;
  var reduced=window.matchMedia('(prefers-reduced-motion: reduce)'), L=window.JarvisLipsync;
  var env=null,clock=null,playing=false,bc=null;
  function epoch(){return (performance.timeOrigin||Date.now()-performance.now())+performance.now();}
  function resize(){w=innerWidth;h=innerHeight;var d=Math.min(devicePixelRatio||1,1.5);canvas.width=Math.round(w*d);canvas.height=Math.round(h*d);ctx.setTransform(d,0,0,d,0,0);
    scale=Math.max(w/1916,h/821);ox=(w-1916*scale)/2;oy=(h-821*scale)/2;}
  // Projection of genuinely rotating rings onto the artwork's central axis.
  function point(a,r,tilt,spin){var x=Math.cos(a)*r,y=Math.sin(a)*r*Math.cos(tilt),z=Math.sin(a)*r*Math.sin(tilt);
    var xx=x*Math.cos(spin)-y*Math.sin(spin),yy=x*Math.sin(spin)+y*Math.cos(spin),p=1100/(1100+z);
    return {x:ox+(958+xx*p)*scale,y:oy+(365+yy*p)*scale,z:z};}
  // Depth-sorted faceted crystal: every vertex is projected each frame.
  function crystal(t){
    function project(v){
      var a=t*.23,c=Math.cos(a),s=Math.sin(a),x=v[0]*c+v[2]*s,z=-v[0]*s+v[2]*c;
      var tilt=.16*Math.sin(t*.18),y=v[1]*Math.cos(tilt)-z*Math.sin(tilt);
      z=v[1]*Math.sin(tilt)+z*Math.cos(tilt);var perspective=1000/(1000+z);
      return {x:ox+(958+x*perspective)*scale,y:oy+(365+y*perspective)*scale,z:z};
    }
    var verts=[[0,-210,0],[0,210,0]];
    for(var i=0;i<8;i++){var a=i*Math.PI/4;verts.push([Math.cos(a)*112,0,Math.sin(a)*112]);}
    var projected=verts.map(project), faces=[];
    for(var j=0;j<8;j++)for(var tip=0;tip<2;tip++){
      var ids=[tip,j+2,(j+1)%8+2],points=ids.map(function(id){return projected[id];});
      faces.push({points:points,depth:points.reduce(function(sum,p){return sum+p.z;},0)/3,index:j,tip:tip});
    }
    faces.sort(function(a,b){return b.depth-a.depth;});
    faces.forEach(function(face){var p=face.points;
      ctx.beginPath();ctx.moveTo(p[0].x,p[0].y);ctx.lineTo(p[1].x,p[1].y);ctx.lineTo(p[2].x,p[2].y);ctx.closePath();
      var light=Math.max(0,Math.min(1,(face.depth+140)/280));
      var g=ctx.createLinearGradient(p[0].x,p[0].y,p[1].x,p[1].y);
      g.addColorStop(0,'rgba(226,246,255,'+(.24+light*.4)+')');
      g.addColorStop(.5,'rgba(54,131,170,'+(.25+light*.3)+')');
      g.addColorStop(1,'rgba(190,228,249,'+(.12+amp*.3)+')');
      ctx.fillStyle=g;ctx.fill();ctx.strokeStyle='rgba(204,238,255,.65)';ctx.lineWidth=1*scale;ctx.stroke();
    });
    var aura=ctx.createRadialGradient(ox+958*scale,oy+365*scale,0,ox+958*scale,oy+365*scale,70*scale);
    aura.addColorStop(0,'rgba(255,248,217,'+(.7+amp*.3)+')');aura.addColorStop(.25,'rgba(248,201,119,.3)');aura.addColorStop(1,'rgba(110,211,255,0)');
    ctx.fillStyle=aura;ctx.fillRect(ox+888*scale,oy+295*scale,140*scale,140*scale);
  }
  function draw(t){ctx.clearRect(0,0,w,h);var target=performance.now()-micAt<250?mic:0;
    if(L&&env&&clock&&playing){target=Math.max(target,L.level(env,clock.position(epoch()))||0);}
    amp+=(target-amp)*.22;
    crystal(t);
    for(var ring=0;ring<3;ring++){
      var spin=t*(.10+ring*.035)*(ring%2?-1:1),r=245+ring*30,tilt=1.03+ring*.2;
      ctx.lineWidth=(ring===1?2:1)*scale;ctx.strokeStyle='rgba(172,220,248,'+(.18+amp*.2)+')';ctx.beginPath();
      for(var j=0;j<=96;j++){var q=point(j/96*Math.PI*2,r,tilt,spin);if(j)ctx.lineTo(q.x,q.y);else ctx.moveTo(q.x,q.y);}ctx.stroke();
      for(var k=0;k<8;k++){var p=point(k/8*Math.PI*2+t*(.4+ring*.1),r,tilt,spin);ctx.fillStyle=p.z>0?'rgba(157,221,255,.55)':'rgba(237,248,255,.95)';ctx.beginPath();ctx.arc(p.x,p.y,(1.4+amp*2)*scale,0,Math.PI*2);ctx.fill();}
    }
    // Actual audio level only: no fake sound wave while idle.
    var glow=ctx.createRadialGradient(ox+958*scale,oy+365*scale,0,ox+958*scale,oy+365*scale,105*scale);
    glow.addColorStop(0,'rgba(180,235,255,'+(amp*.6)+')');glow.addColorStop(1,'rgba(180,235,255,0)');ctx.fillStyle=glow;ctx.fillRect(ox+850*scale,oy+255*scale,220*scale,220*scale);
    if(amp>.015){ctx.strokeStyle='rgba(209,238,255,.85)';ctx.lineWidth=1.2;ctx.beginPath();for(var x=-140;x<=140;x+=3){var y=Math.sin(x*.11)*Math.cos(x*.027)*amp*25;var px=ox+(958+x)*scale,py=oy+(675+y)*scale;if(x===-140)ctx.moveTo(px,py);else ctx.lineTo(px,py);}ctx.stroke();}
  }
  function frame(now){raf=0;if(document.hidden)return;if(now-last>=1000/24){last=now;draw(now/1000);}if(!reduced.matches)raf=requestAnimationFrame(frame);}
  function start(){if(raf)cancelAnimationFrame(raf);raf=0;draw(performance.now()/1000);if(!document.hidden&&!reduced.matches)raf=requestAnimationFrame(frame);}
  addEventListener('jarvis-mic-level',function(e){mic=Math.min(1,Math.max(0,Number(e.detail)||0));micAt=performance.now();});
  try{if(L&&window.BroadcastChannel){bc=new BroadcastChannel(L.CHANNEL);bc.onmessage=function(e){var m=e.data;if(!L.valid(m))return;if(m.k==='env'){env=m;clock=new L.ClockFilter();}else if(m.k==='clock'&&env&&m.id===env.id){clock.push(m);playing=m.playing;}else if(m.k==='stop'){playing=false;env=null;clock=null;}};}}catch(_){}
  addEventListener('resize',function(){resize();start();});document.addEventListener('visibilitychange',start);
  if(reduced.addEventListener)reduced.addEventListener('change',start);else if(reduced.addListener)reduced.addListener(start);
  addEventListener('pagehide',function(){cancelAnimationFrame(raf);if(bc)bc.close();});resize();start();
})();
