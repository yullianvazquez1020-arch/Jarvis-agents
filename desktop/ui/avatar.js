(function () {
  "use strict";
  var $=function(id){return document.getElementById(id);},face=false,animationId=0;
  var visual=window.JarvisVisual.create($("c"),{scene:"silhouette",onQuality:function(tier,requested){$("performance").textContent=(requested==="auto"?"AUTO · ":"")+({light:"LIGERO",detail:"DETALLE",eco:"AHORRO"}[tier]);},onMotion:function(paused){
    $("motion").textContent=paused?"Activar animación":"Pausar animación";
    $("motion").setAttribute("aria-pressed",String(paused));
  }});
  function faceLabel(){ $("style").textContent=face?"Ver partículas":"Ver rostro";$("style").setAttribute("aria-pressed",String(face)); }
  $("style").onclick=function(){face=!face;visual.setScene(face?"face":"silhouette");faceLabel();};
  $("smile").onclick=function(){face=true;visual.setScene("face");visual.setActivity(0,.8);faceLabel();};
  $("motion").onclick=function(){visual.toggleMotion();};
  $("quality").onchange=function(){visual.setQuality(this.value);};
  $("speak").onclick=function(){
    var id=++animationId,text=$("phrase").value.slice(0,1000).toLowerCase(),timeline=[],duration=0;
    var shapes={a:1,e:.7,i:.35,o:.9,u:.6,m:.05,rest:.15};
    for(var ch of text){var base=ch.normalize("NFD")[0],mouth="aeiou".includes(base)?base:"mbp".includes(base)?"m":"rest";
      timeline.push({at:duration,value:shapes[mouth]});duration+=mouth==="rest"?60:140;}
    var start=Date.now(),index=0;
    function run(){
      if(id!==animationId)return;
      var elapsed=Date.now()-start;
      if(!timeline.length||elapsed>duration){visual.setActivity(0,0);return;}
      while(index+1<timeline.length&&timeline[index+1].at<=elapsed)index++;
      visual.setActivity(timeline[index].value,0);setTimeout(run,60);
    }
    run();
  };
  $("fullscreen").onclick=function(){
    var exit=document.exitFullscreen||document.webkitExitFullscreen;
    if((document.fullscreenElement||document.webkitFullscreenElement)&&exit){exit.call(document);return;}
    var fn=document.documentElement.requestFullscreen||document.documentElement.webkitRequestFullscreen;
    if(!fn){$("status").textContent="Usa pantalla completa desde el menú del navegador.";return;}
    var result=fn.call(document.documentElement);
    if(result&&result.catch)result.catch(function(){$("status").textContent="Usa pantalla completa desde el menú del navegador.";});
  };
  async function pulse(){
    if(location.protocol==="file:"){$("status").textContent="Vista previa sin conexión. Animación aproximada, sin audio.";return;}
    try{
      var r=await fetch("/api/state",{credentials:"same-origin"});if(!r.ok)throw new Error("sin sesión");
      var s=await r.json(),labels={ok:"conectado",demo:"demostración",down:"sin conexión",slow:"con retraso",error:"error",unpaired:"sin emparejar",unknown:"sin comprobar"};
      $("status").textContent=(s.demo?"DEMO · ":"")+"Servidor: "+(labels[(s.server||{}).state]||"sin comprobar")+" · Animación aproximada, sin audio ni acceso al micrófono.";
    }catch(e){$("status").textContent="Sin conexión comprobada al escritorio. Animación sin audio.";}
    setTimeout(pulse,5000);
  }
  pulse();
})();
