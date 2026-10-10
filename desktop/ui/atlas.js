/* Local visual atlas. Proposals only: no provider, money or message endpoints. */
(() => {
  'use strict';
  const root = document.getElementById('portfolio');
  if (!root) return;
  const ideas = [
    {name:'Servicio local', color:'#50d5bd', cost:'$0–50', task:'Preparar una ficha de mantenimiento para ISLAFIX y una plantilla de cotización con costos pendientes.', goal:'Validar una necesidad y conseguir una cotización solicitada en 30 días.', metric:'Solicitudes, horas invertidas y cobros vinculados a trabajos.', approval:'Servicios ofrecidos, costos y cada contacto antes de enviarlo.'},
    {name:'Producto digital', color:'#efbc64', cost:'$0–30', task:'Preparar una plantilla original de inventario para contratistas y una muestra gratuita.', goal:'Conseguir 3 evaluaciones voluntarias y probar una venta en 30 días.', metric:'Evaluaciones reales, ventas, devoluciones y comisiones.', approval:'Contenido final, licencia, precio y publicación.'},
    {name:'Contenido educativo', color:'#bb8cff', cost:'$0–20', task:'Redactar cuatro guiones originales de mantenimiento, basados en experiencia verificable.', goal:'Publicar hasta 4 piezas aprobadas y medir consultas calificadas durante 30 días.', metric:'Piezas publicadas, consultas y horas; seguidores no equivalen a ingresos.', approval:'Guiones, imágenes, plataforma y cada publicación.'},
    {name:'Tienda por validar', color:'#ff7cae', cost:'$0–100', task:'Comparar una categoría de consumibles y preparar costos unitarios, envío y devoluciones.', goal:'Validar demanda antes de comprar inventario durante 30 días.', metric:'Interés documentado, margen estimado y ventas cobradas si se aprueban.', approval:'Proveedor, plataforma, compra y publicación; Amazon permanece bloqueado.'},
    {name:'Afiliados', color:'#68c7ff', cost:'$0–20', task:'Preparar una comparación honesta de herramientas que el dueño conozca y revisar requisitos del programa.', goal:'Evaluar un programa y una pieza aprobada en 30 días, sin tráfico artificial.', metric:'Clics y comisiones confirmadas por el programa, separados de estimaciones.', approval:'Programa, divulgación de afiliación, enlaces y publicación.'}
  ];
  const canvas = document.getElementById('atlas'), ctx = canvas.getContext('2d');
  const list = document.getElementById('atlas-list'), detail = document.getElementById('atlas-detail');
  const tabs = [...root.querySelectorAll('[data-atlas]')];
  const handButton = document.getElementById('hand-navigation'), handStatus = document.getElementById('atlas-hand-status');
  let selected = 0, mode = 'tower', navigation = false, hovered = null, since = 0, latched = null;
  let last = 0, phase = 0, visible = true, position = null, paused = false, quality = 'eco';
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  paused = reduced.matches;
  const motionButton=document.getElementById('atlas-motion');
  function motionLabel(){motionButton.textContent=paused?'Reanudar universo':'Pausar universo';motionButton.setAttribute('aria-pressed',String(paused));}
  motionButton.onclick=()=>{paused=!paused;motionLabel();};motionLabel();
  document.getElementById('atlas-quality').onchange=e=>{quality=e.target.value==='rich'?'rich':'eco';};
  const mini = ['membrane','brain','audio'].map(id=>document.getElementById(id+'-mini').getContext('2d'));
  let lastStatus=0;
  function telemetry(now){
    if(now-lastStatus<300)return;lastStatus=now;
    const hand=window.JarvisHands,voice=window.JarvisAvatar?.telemetry?.();
    document.getElementById('observatory-hand').textContent=hand?.seen?'Mano detectada · '+(hand.landmarks?.length||0)+' puntos':hand?.running?'Cámara activa · buscando mano':'Cámara apagada';
    document.getElementById('observatory-voice').textContent=voice?.audioActive?'Audio reproducido · amplitud RMS':'Sin audio reproducido';
  }
  function science(){
    mini.forEach((c,i)=>c.clearRect(0,0,300,i===2?70:180));
    const m=mini[0],b=mini[1],a=mini[2];
    for(let i=0;i<40;i++){
      const angle=i*Math.PI/20,xx=150+Math.cos(angle)*112,yy=90+Math.sin(angle)*51;
      m.strokeStyle='#63dcd788';m.beginPath();m.moveTo(xx,yy);m.lineTo(150+Math.cos(angle)*95,90+Math.sin(angle)*39);m.stroke();
      m.fillStyle=i%3?'#61d6d6':'#b58cff';m.beginPath();m.arc(xx,yy,2.5,0,7);m.fill();
    }
    for(let i=0;i<14;i++){const angle=i*2.4+phase*.15;m.fillStyle='#bb8cff';m.fillRect(148+Math.cos(angle)*65,88+Math.sin(angle)*28,3,3);}
    for(let k=0;k<14;k++){
      b.beginPath();b.strokeStyle=ideas[k%5].color+'88';
      for(let j=0;j<=80;j++){const angle=j*Math.PI/40,rr=1+.08*Math.sin(angle*11+k);const xx=150+Math.cos(angle)*(87-k*2)*rr,yy=88+Math.sin(angle)*(61-k)*rr; j?b.lineTo(xx,yy):b.moveTo(xx,yy);}b.stroke();
    }
    for(let i=0;i<10;i++){b.fillStyle=ideas[i%5].color;b.beginPath();b.arc(150+Math.sin(i*3+phase*.5)*68,88+Math.cos(i*1.4+phase*.4)*43,2,0,7);b.fill();}
    const amp=window.JarvisAvatar?.telemetry?.().amplitude||0;
    a.strokeStyle='#6bf5ad';a.beginPath();a.moveTo(0,60);a.lineTo(300,60);a.stroke();
    a.fillStyle='#6bf5ad';a.fillRect(12,60-amp*48,276,amp*48);
  }
  const cursor = document.createElement('div'); cursor.className = 'atlas-cursor'; cursor.hidden = true; cursor.setAttribute('aria-hidden','true'); root.appendChild(cursor);
  function add(tag, text, parent, cls) { const e = document.createElement(tag); e.textContent = text; if(cls)e.className=cls; parent.appendChild(e); return e; }
  function select(index) {
    selected = index;
    [...list.children].forEach((b,i) => b.setAttribute('aria-pressed',String(i===index)));
    detail.replaceChildren(); const item = ideas[index];
    add('small',`SECTOR ${index+1} · PISOS ${index*20+1}–${(index+1)*20} / PROPUESTA`,detail);
    add('h2',item.name,detail); add('p',`Arranque estimado: ${item.cost}. No gastado.`,detail,'atlas-estimate');
    for (const [title, text] of [['Preparación de Jarvis',item.task],['Meta propuesta · 30 días',item.goal],['Cómo medir',item.metric],['Aprobación del dueño',item.approval]]) {add('h3',title,detail);add('p',text,detail);}
    add('p','Cobrado no es ganancia. Sin datos conectados no se calcula rendimiento ni se decide cerrar o ampliar la prueba.',detail,'atlas-disclaimer');
  }
  ideas.forEach((item,i)=> {const b=add('button',`${i*20+1}–${(i+1)*20} / ${item.name}`,list);b.type='button'; b.dataset.floor=String(i);b.style.setProperty('--floor-color',item.color);b.onclick=()=>select(i);});
  tabs.forEach(button => button.onclick = () => {mode=button.dataset.atlas;tabs.forEach(b=>b.setAttribute('aria-pressed',String(b===button)));document.getElementById('atlas-view-name').textContent={tower:'CIUDAD ORBITAL / 100 PISOS RESERVADOS',galaxy:'GALAXIA / MERCADOS POR EXPLORAR',cell:'MEMBRANA / ÁREAS DEL PORTAFOLIO'}[mode];});
  handButton.onclick = () => {navigation=!navigation;handButton.setAttribute('aria-pressed',String(navigation));if(!navigation){cursor.hidden=true;hovered=null;latched=null;position=null;}handStatus.textContent=navigation?'Activa la cámara con «Activar mano». Señala con el índice y mantén 1,2 segundos sobre una vista o piso. Escape detiene la navegación.':'Navegación por mano apagada. No controla el cursor del sistema.';};
  addEventListener('keydown',e=>{if(e.key==='Escape'&&navigation)handButton.click();});
  const safeTargets = [...tabs,...list.children];
  function gesture(now) {
    const h=window.JarvisHands;
    if(window.JarvisHandMouseActive || !navigation || document.hidden || !h?.seen || !h.landmarks || now-(h.updatedAt||0)>350){cursor.hidden=true;hovered=null;latched=null;position=null;return;}
    const p=h.landmarks[8]; if(!p || !Number.isFinite(p.x)||!Number.isFinite(p.y)) return;
    const tx=Math.max(0,Math.min(1,(p.x-.1)/.8))*innerWidth,ty=Math.max(0,Math.min(1,(p.y-.1)/.8))*innerHeight;
    position=position?{x:position.x+(tx-position.x)*.28,y:position.y+(ty-position.y)*.28}:{x:tx,y:ty};
    cursor.hidden=false;cursor.style.left=`${position.x}px`;cursor.style.top=`${position.y}px`;
    const target=safeTargets.find(el=>{const r=el.getBoundingClientRect();return position.x>=r.left&&position.x<=r.right&&position.y>=r.top&&position.y<=r.bottom;});
    if(target!==hovered){hovered=target;since=now;latched=null;}
    cursor.style.setProperty('--dwell',`${target?Math.min(100,(now-since)/12):0}%`);
    if(target&&target!==latched&&now-since>=1200){latched=target;target.click();handStatus.textContent=`Seleccionado: ${target.textContent}. Solo navegación local.`;}
  }
  function line(points,color,width=1){ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke();}
  function ellipse(x,y,rx,ry,color,width=1){ctx.beginPath();ctx.ellipse(x,y,rx,ry,0,0,Math.PI*2);ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke();}
  function dot(x,y,r,color){ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();}
  function label(text,x,y,color='#6d99ad'){ctx.fillStyle=color;ctx.font='11px ui-monospace, monospace';ctx.fillText(text,x,y);}
  function nebula(){
    for(let i=0;i<7;i++){
      const cx=180+i*125,cy=280+Math.sin(i*1.8+phase*.03)*115;
      const g=ctx.createRadialGradient(cx,cy,5,cx,cy,220);
      g.addColorStop(0,ideas[i%5].color+'42');g.addColorStop(1,'#04091800');ctx.fillStyle=g;ctx.fillRect(cx-220,cy-220,440,440);
    }
    for(const [cx,cy] of [[145,475],[925,135]]){
      for(let k=0;k<9;k++)ellipse(cx,cy,18+k*4,28+k*5,ideas[(k+2)%5].color+'48');
      dot(cx,cy,17,'#01060d');
      const angle=phase*.6;dot(cx+Math.cos(angle)*43,cy+Math.sin(angle)*63,3,'#bffaff');
    }
  }
  function dragon(cx,cy,size,color,angle){
    ctx.save();ctx.translate(cx,cy);ctx.rotate(angle);ctx.scale(size,size);
    const flap=Math.sin(phase*3+cx)*7;
    ctx.fillStyle=color+'a0';ctx.strokeStyle=color;ctx.lineWidth=.8;
    // Two articulated wings, long tail, neck, horns and rider; all procedural.
    for(const side of [-1,1]){
      ctx.beginPath();ctx.moveTo(0,1);ctx.lineTo(-12,-22-flap*side);
      ctx.lineTo(-31,-32-flap*side);ctx.quadraticCurveTo(-25,-15,-30,-8);
      ctx.quadraticCurveTo(-18,-16,-17,-2);ctx.quadraticCurveTo(-8,-8,0,4);ctx.fill();ctx.stroke();
      ctx.beginPath();ctx.moveTo(1,1);ctx.lineTo(13,-25+flap*side);
      ctx.lineTo(30,-29+flap*side);ctx.quadraticCurveTo(24,-15,29,-9);
      ctx.quadraticCurveTo(17,-15,15,-2);ctx.lineTo(2,5);ctx.fill();ctx.stroke();
    }
    ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(-9,3);ctx.bezierCurveTo(-24,4,-25,18,-39,10);ctx.bezierCurveTo(-25,23,-16,8,-6,8);ctx.lineTo(7,7);ctx.quadraticCurveTo(16,3,15,-5);ctx.lineTo(24,-6);ctx.lineTo(19,-10);ctx.lineTo(14,-10);ctx.lineTo(10,-17);ctx.lineTo(9,-8);ctx.quadraticCurveTo(9,1,3,2);ctx.closePath();ctx.fill();
    line([[-3,6],[-8,13],[-3,12]],color);line([[5,6],[9,12],[14,11]],color);
    ctx.fillStyle='#e5ffff';ctx.beginPath();ctx.arc(17,-8,1,0,7);ctx.fill();
    ctx.fillStyle='#d9f2ee';ctx.beginPath();ctx.arc(2,-7,2,0,7);ctx.fill();ctx.fillRect(0,-5,3,7);ctx.restore();
  }
  function tower() {
    nebula();const cx=550;
    for(let floor=0;floor<100;floor++){
      const sector=Math.floor(floor/20),y=530-floor*4.25,r=228-floor*1.86,col=ideas[sector].color;
      if(floor%20===0){ctx.fillStyle=col+'12';ctx.beginPath();ctx.ellipse(cx,y,r,22,0,0,Math.PI*2);ctx.fill();}
      ellipse(cx,y,r,7+r*.055,col+(sector===selected?'b0':'40'),floor%20===0?2:.65);
      if(floor%4===0)for(let j=0;j<12;j++){
        const angle=j*Math.PI/6+phase*.035;
        if(Math.sin(angle)>0)dot(cx+Math.cos(angle)*r,y+Math.sin(angle)*(7+r*.055)-3,1.1,col);
      }
    }
    for(let side of [-1,1])line([[cx+side*228,530],[cx+side*44,109],[cx,53]],'#98e7ed88');
    line([[cx,53],[cx,550]],'#b7dfff65');
    // Balconies, bridges and spires give the reserved sectors a city silhouette.
    for(let k=0;k<5;k++){
      const y=500-k*85,rr=210-k*37,col=ideas[k].color;
      for(let j=-3;j<=3;j++){
        const xx=cx+j*rr/4,hh=18+(j*j%3)*8;
        line([[xx-4,y],[xx-4,y-hh],[xx,y-hh-13],[xx+4,y-hh],[xx+4,y]],col+'b0');
        dot(xx,y-hh-13,1.5,'#d3ffff');
      }
    }
    line([[cx-190,552],[cx,622],[cx+190,552]],'#6fdfff55');
    for(let i=0;i<5;i++){
      const y=492-i*85,col=ideas[i].color;
      line([[cx+205-i*37,y],[870,y],[887,y-12]],col+'77');label(`${i*20+1}–${(i+1)*20}`,895,y-10,col);
    }
    const count=quality==='rich'?15:7;
    for(let i=0;i<count;i++){
      const angle=i*2.4+phase*(.07+(i%3)*.012);
      dragon(cx+Math.cos(angle)*(270+i%3*60),305+Math.sin(angle)*210,.6+i%3*.2,ideas[i%5].color,Math.sin(angle)*.2);
    }
    label('CIUDAD ORBITAL / SECTORES RESERVADOS',30,40,'#afeced');
    label('DRAGONES Y PORTALES · AMBIENTACIÓN ARTÍSTICA',30,60);
  }
  function galaxy(){const cx=515,cy=315;for(let i=0;i<1200;i++){const a=i*2.399963+phase*.025,r=15+Math.sqrt(i/1200)*360,arm=i%5;const twist=a*.025+r*.009+arm*Math.PI*.4;const xx=cx+Math.cos(twist)*r,yy=cy+Math.sin(twist)*r*.60;dot(xx,yy,i%19===0?1.9:.8,ideas[arm].color+(arm===selected?'bb':'45'));}
    const g=ctx.createRadialGradient(cx,cy,1,cx,cy,70);g.addColorStop(0,'#fff4cbbb');g.addColorStop(.3,'#e1a55044');g.addColorStop(1,'#ffad0000');ctx.fillStyle=g;ctx.fillRect(cx-70,cy-70,140,140);
    ideas.forEach((item,i)=>{const a=i*Math.PI*.4-.6,xx=cx+Math.cos(a)*310,yy=cy+Math.sin(a)*210;line([[cx,cy],[xx,yy]],item.color+'40');ellipse(xx,yy,i===selected?20:12,i===selected?20:12,item.color);dot(xx,yy,4,item.color);label(`0${i+1} ${item.name}`,xx-45,yy+36,item.color);});label('RELACIONES CONCEPTUALES / NO TRÁFICO REAL',60,70);
  }
  function cell(){const cx=535,cy=320;for(let ring=0;ring<3;ring++){const pts=[];for(let i=0;i<=180;i++){const a=i*Math.PI/90,r=220+ring*8+Math.sin(a*7+phase*.3)*8;pts.push([cx+Math.cos(a)*r*1.5,cy+Math.sin(a)*r]);}line(pts,ring===1?'#65d9cbaa':'#42859755');}
    for(let i=0;i<5;i++){const a=i*Math.PI*.4-1.4,xx=cx+Math.cos(a)*215,yy=cy+Math.sin(a)*135,col=ideas[i].color;line([[cx,cy],[xx,yy]],col+'55');ellipse(xx,yy,i===selected?70:55,40,col,2);for(let j=0;j<12;j++)dot(xx+Math.cos(j*2.4+phase*.1)*34,yy+Math.sin(j*2.4)*21,1.5,col);label(`0${i+1} / ${ideas[i].name}`,xx-55,yy+60,col);}
    ellipse(cx,cy,65,54,'#dabdff');label('JARVIS',cx-24,cy+4,'#ecddff');label('MEMBRANA / LÍMITES Y APROBACIONES',60,70);
  }
  function frame(now){requestAnimationFrame(frame);if(document.hidden||!visible)return;gesture(now);telemetry(now);if(now-last<1000/(quality==='rich'?24:15))return;last=now;if(!paused)phase+=1/(quality==='rich'?24:15);ctx.fillStyle='#020b15';ctx.fillRect(0,0,1100,650);
    for(let i=0;i<420;i++){const xx=(i*197.3)%1100,yy=(i*97.9)%650;dot(xx,yy,i%9===0?1:.5,i%11===0?'#b6ddefaa':'#739fc355');}
    ctx.strokeStyle='#27516b20';ctx.lineWidth=1;for(let xx=0;xx<1100;xx+=55)line([[xx,0],[xx,650]],'#27516b15');for(let yy=0;yy<650;yy+=50)line([[0,yy],[1100,yy]],'#27516b15');
    ({tower,galaxy,cell})[mode]();science();label(paused?'UNIVERSO PAUSADO':quality==='rich'?'DETALLE / 24 FPS MÁX':'LIGERO / 15 FPS MÁX',30,625);label('REVENUE / SIN DATOS',840,625);
  }
  if('IntersectionObserver' in window)new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;}).observe(canvas);
  select(0);requestAnimationFrame(frame);
})();
