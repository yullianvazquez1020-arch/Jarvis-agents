/* Decorative Canvas 2D scenes. Geometry never represents AI activity, balances or agent links. */
(function (root) {
  "use strict";
  var TAU = Math.PI * 2, COLORS = ["#66e4f5", "#f6c76e", "#8b9dff", "#49cfae", "#ef87c2", "#61adff", "#d9a4fb", "#ade087"];
  function create(canvas, options) {
    options = options || {};
    var ctx = canvas.getContext("2d"), scene = options.scene || "orbit", quality = "light", requestedQuality = "auto";
    var media = root.matchMedia("(prefers-reduced-motion: reduce)"), paused = media.matches;
    var modules = [], raf = null, last = -1, elapsed = 0, dirty = true, disposed = false;
    var activity = 0, expression = 0, w = 1, h = 1, averageCost = 0, averageGap = 42, samples = 0, cooldown = 0;
    var cyan = [], gold = [], bodies = {};
    for(var c=0;c<32;c++){cyan.push("rgba(82,211,245,"+(.2+c/31*.78)+")");gold.push("rgba(255,190,102,"+(.3+c/31*.65)+")");}
    // Reuse deterministic geometry: no random allocations or all-pairs connections per frame.
    var points = [];
    for (var i = 0; i < 3200; i++) {
      var y = 1 - 2 * (i + .5) / 3200, a = i * 2.399963229728653;
      points.push({x: Math.cos(a) * Math.sqrt(1-y*y), y:y, z:Math.sin(a) * Math.sqrt(1-y*y), a:a});
    }
    function nodePositions() {
      return modules.map(function (_, i) {
        var side = i % 2, row = Math.floor(i / 2), rows = Math.ceil(modules.length / 2);
        return {x: side ? (w < 640 ? .8 : .84) : (w < 640 ? .2 : .16), y: rows===1 ? .45 : .20 + row * .57/(rows-1)};
      });
    }
    function line(x1,y1,x2,y2,color) {ctx.strokeStyle=color;ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();}
    function glow(cx,cy,r,color) {
      var g=ctx.createRadialGradient(cx,cy,0,cx,cy,r);g.addColorStop(0,color);g.addColorStop(1,"rgba(0,0,0,0)");
      ctx.fillStyle=g;ctx.fillRect(cx-r,cy-r,r*2,r*2);
    }
    function backdrop(t) {
      ctx.lineWidth=1;ctx.strokeStyle="rgba(67,137,174,.08)";ctx.beginPath();
      for(var x=24;x<w;x+=48){ctx.moveTo(x,0);ctx.lineTo(x,h);}
      for(var y=24;y<h;y+=48){ctx.moveTo(0,y);ctx.lineTo(w,y);}ctx.stroke();
      // Sparse ambient dust, deterministic and clearly decorative.
      ctx.fillStyle="rgba(118,199,226,.26)";
      for(var j=0;j<32;j++){var xx=((j*.6180339)%1)*w, yy=((j*.4142135+t*.005)%1)*h;ctx.fillRect(xx,yy,1,1);}
      ctx.strokeStyle="rgba(98,178,211,.4)";ctx.beginPath();
      [[20,20,1,1],[w-20,20,-1,1],[20,h-20,1,-1],[w-20,h-20,-1,-1]].forEach(function(p){ctx.moveTo(p[0]+p[2]*26,p[1]);ctx.lineTo(p[0],p[1]);ctx.lineTo(p[0],p[1]+p[3]*26);});ctx.stroke();
    }
    function orbit(t) {
      var cx=w/2,cy=h*.45,r=Math.min(w*.19,h*.285),rotation=t*.12;
      glow(cx,cy,r*1.8,"rgba(27,125,186,.22)");
      // Curved orbital paths, not a fabricated telemetry graph.
      for(var k=0;k<6;k++) {
        ctx.strokeStyle="rgba(57,175,213,"+(.05+k*.012)+")";ctx.beginPath();
        ctx.ellipse(cx,cy,r*(1.45+k*.15),r*(.47+k*.04),-.5+k*.22,0,TAU);ctx.stroke();
      }
      var count=quality==="detail"?2800:quality==="eco"?700:1400, stride=3200/count;
      ctx.globalCompositeOperation="lighter";
      for(var i=0;i<count;i++) {
        var p=points[Math.floor(i*stride)],px=p.x*Math.cos(rotation)+p.z*Math.sin(rotation),z=p.z*Math.cos(rotation)-p.x*Math.sin(rotation);
        var perspective=1+z*.10, depth=(z+1)/2;
        ctx.fillStyle=(i%17===0?gold:cyan)[Math.min(31,Math.floor(depth*31))];
        ctx.fillRect(cx+px*r*perspective,cy+p.y*r*perspective,depth> .6?1.5:1,depth>.6?1.5:1);
      }
      ctx.globalCompositeOperation="source-over";
      var halo=ctx.createRadialGradient(cx,cy,r*.94,cx,cy,r*1.27);
      halo.addColorStop(0,"rgba(248,199,106,0)");halo.addColorStop(.22,"rgba(248,199,106,.22)");halo.addColorStop(.55,"rgba(248,199,106,.07)");halo.addColorStop(1,"rgba(248,199,106,0)");
      ctx.fillStyle=halo;ctx.fillRect(cx-r*1.27,cy-r*1.27,r*2.54,r*2.54);
      // Gold corona: staggered segments and a halo rather than a flat disk.
      ctx.shadowBlur=quality==="detail"?15:8;ctx.shadowColor="#f8c567";
      for(var j=0;j<3;j++){ctx.lineWidth=j===0?2:1;ctx.strokeStyle=j===0?"rgba(255,215,126,.78)":"rgba(247,204,117,.21)";
        ctx.beginPath();ctx.arc(cx,cy,r*(1.06+j*.025),0,TAU);ctx.stroke();}ctx.shadowBlur=0;
      ctx.lineWidth=2;ctx.strokeStyle="rgba(136,233,255,.6)";
      for(var n=0;n<12;n++){var a=n*TAU/12+t*.018;ctx.beginPath();ctx.arc(cx,cy,r*1.16,a,a+.06);ctx.stroke();}
      nodePositions().forEach(function(p,i){var nx=p.x*w,ny=p.y*h,side=nx<cx?-1:1,ex=cx+side*r*1.13;
        ctx.lineWidth=1;ctx.strokeStyle="rgba(100,218,237,.24)";ctx.beginPath();ctx.moveTo(ex,cy+(ny-cy)*.4);ctx.bezierCurveTo(ex+side*30,ny,nx-side*30,ny,nx,ny);ctx.stroke();
        ctx.strokeStyle=modules[i].stale?"#e4ba70":"#72d9e7";ctx.beginPath();ctx.arc(nx,ny,5,0,TAU);ctx.stroke();
      });
    }
    function atlas(t) {
      var count=quality==="detail"?3200:quality==="eco"?900:2000,groups=Math.max(1,modules.length);
      var positions=nodePositions(),centers=[];
      var washes=["rgba(53,216,239,.15)","rgba(247,164,66,.18)","rgba(115,115,247,.16)","rgba(52,215,163,.15)","rgba(230,88,172,.16)","rgba(73,147,255,.15)","rgba(170,97,232,.16)","rgba(163,224,115,.15)"];
      var rx=Math.min(w*.105,150),ry=Math.min(h*.155,105);
      // The colored clusters are module navigation, not real neurons or measured connections.
      for(var g=0;g<groups;g++){
        var a=g/groups*TAU-.5;
        centers.push({x:w*.5+Math.cos(a)*Math.min(w*.11,170),y:h*.46+Math.sin(a)*h*.16});
      }
      ctx.globalCompositeOperation="lighter";
      centers.forEach(function(c,g){glow(c.x,c.y,Math.max(rx,ry)*1.5,washes[g%washes.length]);});
      for(var g=0;g<groups;g++) {
        var center=centers[g],cx=center.x,cy=center.y,previous=null;
        ctx.fillStyle=COLORS[g%COLORS.length];ctx.strokeStyle=COLORS[g%COLORS.length];
        for(var i=g;i<count;i+=groups) {
          var seed=points[Math.floor(i*3200/count)],phase=seed.a+t*.06;
          var radial=Math.sqrt((i%173)/173),px=cx+Math.cos(phase)*rx*radial,py=cy+seed.y*ry*radial;
          ctx.globalAlpha=.48+(seed.z+1)*.25;
          ctx.fillRect(px,py,2,2);
          if(i%13===0){if(previous){ctx.globalAlpha=.10;ctx.beginPath();ctx.moveTo(previous.x,previous.y);ctx.lineTo(px,py);ctx.stroke();}previous={x:px,y:py};}
        }
        ctx.globalAlpha=.24;
        if(positions[g]){ctx.beginPath();ctx.moveTo(cx,cy);ctx.quadraticCurveTo(w*.5,positions[g].y*h,positions[g].x*w,positions[g].y*h);ctx.stroke();}
      }
      ctx.globalCompositeOperation="source-over";ctx.globalAlpha=1;
    }
    function silhouette(t) {
      var scale=Math.min(w/960,h/720),cx=w/2,cy=h*.44;
      var face=scene==="face",yaw=Math.sin(t*.18)*.18;
      glow(cx,cy,260*scale,"rgba(20,108,170,.3)");
      glow(cx,cy-75*scale,115*scale,"rgba(255,132,42,.44)");
      ctx.globalCompositeOperation="lighter";
      ctx.save();ctx.translate(cx,cy);ctx.scale(scale,scale);
      // Lathed contours give the reference's volumetric head, neck and shoulders.
      var cols=quality==="detail"?64:quality==="eco"?24:40,rows=face?42:76,key=String(cols)+":"+String(rows);
      if(!bodies[key]){
        var body=[];
        for(var row=0;row<rows;row++){
          var yy=face?-130+row*6:-180+row*7,head=yy<35,neck=yy>=35&&yy<88;
          var rx=head?88*Math.sqrt(Math.max(0,1-Math.pow((yy+75)/112,2))):neck?28:28+190*(1-Math.exp(-(yy-88)/62));
          var rz=head?rx*.76:neck?26:rx*.35,contour=[];
          for(var col=0;col<cols;col++){
            var a=col/cols*TAU,z=Math.sin(a)*rz,xx=Math.cos(a)*rx;
            if(head&&z>0)z+=18*Math.exp(-Math.pow(xx/24,2)-Math.pow((yy+67)/38,2));
            contour.push({x:xx,y:yy,z:z,depth:(Math.sin(a)+1)/2,warm:head&&Math.abs(xx)<rx*.7&&z>0});
          }body.push(contour);
        }bodies[key]=body;
      }
      var co=Math.cos(yaw),si=Math.sin(yaw);
      bodies[key].forEach(function(contour){
        ctx.strokeStyle="rgba(54,176,226,.25)";ctx.beginPath();
        contour.forEach(function(p,col){
          var breath=1+Math.sin(t*1.2+p.y*.025)*.012;
          var px=(p.x*co+p.z*si)*breath,pz=p.z*co-p.x*si,py=p.y-pz*.16;
          if(col===0)ctx.moveTo(px,py);else ctx.lineTo(px,py);
          ctx.fillStyle=(p.warm?gold:cyan)[Math.min(31,Math.floor(p.depth*31))];
          var size=1.1+p.depth*.4+activity*.4;ctx.fillRect(px,py,size,size);
        });ctx.closePath();ctx.stroke();
      });
      ctx.strokeStyle="rgba(76,173,229,.16)";ctx.lineWidth=1;
      for(var k=0;k<7;k++){ctx.beginPath();ctx.ellipse(0,-70,104+k*17,131+k*14,0,Math.PI*1.02,Math.PI*1.98);ctx.stroke();}
      if(face){ctx.strokeStyle="#90e5fc";ctx.lineWidth=1.5;
        line(-42,-86,-20,-83,"#90e5fc");line(20,-83,42,-86,"#90e5fc");
        ctx.beginPath();ctx.ellipse(0,-24,18+expression*6,2+activity*8,0,0,TAU);ctx.stroke();}
      ctx.restore();ctx.globalCompositeOperation="source-over";
    }
    function paint() {
      var rect=canvas.getBoundingClientRect();w=Math.max(1,rect.width);h=Math.max(1,rect.height);
      var dpr=Math.min(root.devicePixelRatio||1,quality==="detail"?1.5:quality==="eco"?1:1.25);
      // Bound backing storage even on large Retina or TV displays.
      dpr=Math.min(dpr,1920/w,1080/h);
      var cw=Math.max(1,Math.round(w*dpr)),ch=Math.max(1,Math.round(h*dpr));
      if(canvas.width!==cw||canvas.height!==ch){canvas.width=cw;canvas.height=ch;}
      ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);ctx.globalAlpha=1;ctx.globalCompositeOperation="source-over";
      backdrop(elapsed);if(scene==="orbit")orbit(elapsed);else if(scene==="atlas")atlas(elapsed);else silhouette(elapsed);
      dirty=false;
    }
    function frame(now) {
      raf=null;if(disposed||document.hidden)return;
      var gap=last<0?42:now-last,delta=last<0?0:Math.min(gap,80),interval=quality==="detail"?33:quality==="eco"?55:42;
      if(dirty||(!paused&&(last<0||now-last>=interval))){if(!paused)elapsed+=delta/1000;last=now;
        var start=root.performance.now();paint();
        if(requestedQuality==="auto"&&!paused){
          var cost=root.performance.now()-start;averageCost=samples?averageCost*.9+cost*.1:cost;
          averageGap=averageGap*.9+Math.min(gap,150)*.1;samples++;if(cooldown>0)cooldown--;
          if(samples>16&&(averageCost>14||averageGap>90)&&quality!=="eco"){
            quality=quality==="detail"?"light":"eco";cooldown=180;samples=0;notifyQuality();
          }else if(samples>60&&cooldown===0&&averageCost<6&&averageGap<65&&quality!=="detail"){
            quality=quality==="eco"?"light":"detail";samples=0;cooldown=90;notifyQuality();
          }
        }}
      if(!paused)raf=root.requestAnimationFrame(frame);
    }
    function schedule() {dirty=true;if(!disposed&&!document.hidden&&raf===null)raf=root.requestAnimationFrame(frame);}
    function visibility(){last=-1;if(document.hidden){if(raf!==null)root.cancelAnimationFrame(raf);raf=null;}else schedule();}
    function motion(value){paused=value;last=-1;if(raf!==null){root.cancelAnimationFrame(raf);raf=null;}schedule();if(options.onMotion)options.onMotion(paused);}
    function preference(e){motion(e.matches);}
    document.addEventListener("visibilitychange",visibility);root.addEventListener("resize",schedule);
    if(media.addEventListener)media.addEventListener("change",preference);else if(media.addListener)media.addListener(preference);
    function notifyQuality(){if(options.onQuality)options.onQuality(quality,requestedQuality);}
    notifyQuality();schedule();if(options.onMotion)options.onMotion(paused);
    return {setScene:function(s){scene=s;schedule();},setQuality:function(q){requestedQuality=q==="detail"?"detail":q==="light"?"light":"auto";quality=requestedQuality==="auto"?"light":requestedQuality;samples=0;cooldown=0;averageGap=42;notifyQuality();schedule();},
      setModules:function(m){modules=m.slice(0,8);schedule();},getNodePositions:nodePositions,
      toggleMotion:function(){motion(!paused);},setActivity:function(a,e){activity=Math.max(0,Math.min(a||0,1));expression=e||0;},
      dispose:function(){disposed=true;if(raf!==null)root.cancelAnimationFrame(raf);document.removeEventListener("visibilitychange",visibility);root.removeEventListener("resize",schedule);if(media.removeEventListener)media.removeEventListener("change",preference);else if(media.removeListener)media.removeListener(preference);}};
  }
  root.JarvisVisual={create:create};
})(window);
