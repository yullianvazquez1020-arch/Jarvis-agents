/* Local visual atlas. Proposals only: no provider, money or message endpoints. */
(() => {
  'use strict';
  const root = document.getElementById('portfolio');
  if (!root) return;
  const ideas = [
    {name:'Servicio local', color:'#54ffbd', cost:'$0–50', task:'Preparar una ficha de mantenimiento para ISLAFIX y una plantilla de cotización con costos pendientes.', goal:'Validar una necesidad y conseguir una cotización solicitada en 30 días.', metric:'Solicitudes, horas invertidas y cobros vinculados a trabajos.', approval:'Servicios ofrecidos, costos y cada contacto antes de enviarlo.'},
    {name:'Producto digital', color:'#ffd878', cost:'$0–30', task:'Preparar una plantilla original de inventario para contratistas y una muestra gratuita.', goal:'Conseguir 3 evaluaciones voluntarias y probar una venta en 30 días.', metric:'Evaluaciones reales, ventas, devoluciones y comisiones.', approval:'Contenido final, licencia, precio y publicación.'},
    {name:'Contenido educativo', color:'#36a8ff', cost:'$0–20', task:'Redactar cuatro guiones originales de mantenimiento, basados en experiencia verificable.', goal:'Publicar hasta 4 piezas aprobadas y medir consultas calificadas durante 30 días.', metric:'Piezas publicadas, consultas y horas; seguidores no equivalen a ingresos.', approval:'Guiones, imágenes, plataforma y cada publicación.'},
    {name:'Tienda por validar', color:'#ffad38', cost:'$0–100', task:'Comparar una categoría de consumibles y preparar costos unitarios, envío y devoluciones.', goal:'Validar demanda antes de comprar inventario durante 30 días.', metric:'Interés documentado, margen estimado y ventas cobradas si se aprueban.', approval:'Proveedor, plataforma, compra y publicación; Amazon permanece bloqueado.'},
    {name:'Afiliados', color:'#65eeff', cost:'$0–20', task:'Preparar una comparación honesta de herramientas que el dueño conozca y revisar requisitos del programa.', goal:'Evaluar un programa y una pieza aprobada en 30 días, sin tráfico artificial.', metric:'Clics y comisiones confirmadas por el programa, separados de estimaciones.', approval:'Programa, divulgación de afiliación, enlaces y publicación.'}
  ];
  const canvas = document.getElementById('atlas'), ctx = canvas.getContext('2d');

  // Match CSS size and Retina density, bounded for the 8 GB Mac.
  function resizeDisplay() {
    if (typeof canvas.getBoundingClientRect !== 'function') return;
    const width = canvas.getBoundingClientRect().width;
    if (!(width > 0)) return;
    const density = Math.min(2, window.devicePixelRatio || 1);
    const scale = Math.min(2.5, width * density / 1100, Math.sqrt(3200000 / (1100 * 650)));
    const bw = Math.round(1100 * scale), bh = Math.round(650 * scale);
    if (canvas.width === bw && canvas.height === bh) return;
    canvas.width = bw; canvas.height = bh;
    ctx.setTransform(bw / 1100, 0, 0, bh / 650, 0, 0);
  }
  resizeDisplay();
  if ('ResizeObserver' in window) new ResizeObserver(() => { resizeDisplay(); last = 0; }).observe(canvas);
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
      m.fillStyle=i%3?'#61d6d6':'#36a8ff';m.beginPath();m.arc(xx,yy,2.5,0,7);m.fill();
    }
    for(let i=0;i<14;i++){const angle=i*2.4+phase*.15;m.fillStyle='#36a8ff';m.fillRect(148+Math.cos(angle)*65,88+Math.sin(angle)*28,3,3);}
    // Paired lobes and irregular cortical folds, decorative rather than biometric.
    for(const side of [-1,1])for(let fold=0;fold<12;fold++){
      b.beginPath();b.strokeStyle=ideas[fold%5].color+'88';
      for(let j=0;j<=70;j++){
        const angle=j*Math.PI/35, wobble=1+.075*Math.sin(angle*9+fold*.7);
        const xx=150+side*(5+(36+30*Math.cos(angle))*(1-fold*.025)*wobble);
        const yy=88+Math.sin(angle)*(65-fold*2)*wobble;
        j?b.lineTo(xx,yy):b.moveTo(xx,yy);
      }b.stroke();
    }
    b.strokeStyle='#8be8ff99';b.beginPath();b.moveTo(148,130);b.lineTo(140,166);b.lineTo(159,164);b.stroke();
    for(let i=0;i<10;i++){b.fillStyle=ideas[i%5].color;b.beginPath();b.arc(150+Math.sin(i*3+phase*.5)*68,88+Math.cos(i*1.4+phase*.4)*43,2,0,7);b.fill();}
    const amp=window.JarvisAvatar?.telemetry?.().amplitude||0;
    a.strokeStyle='#6bf5ad';a.beginPath();a.moveTo(0,60);a.lineTo(300,60);a.stroke();
    a.fillStyle='#6bf5ad';a.fillRect(12,60-amp*48,276,amp*48);
  }
  // Explicit read-only refresh. No new server route, model call or background polling.
  const connect=document.getElementById('atlas-connect');
  if(connect)connect.onclick=async()=>{
    connect.disabled=true;
    const status=document.getElementById('atlas-live-status'),output=document.getElementById('atlas-live');
    output.replaceChildren();status.textContent='Consultando conexión…';
    try{
      const stateResponse=await fetch('/api/state',{credentials:'same-origin'});
      if(!stateResponse.ok)throw new Error('estado no disponible');
      const state=await stateResponse.json();
      if(state.demo||!state.paired||!state.server_configured){status.textContent='Sin datos reales: panel DEMO o equipo sin emparejar';return;}
      const results=await Promise.allSettled(['estado','agenda','cobros'].map(async name=>{
        const response=await fetch('/api/panels/'+name,{credentials:'same-origin'});
        if(!response.ok)throw new Error(name+' no disponible');
        const panel=await response.json();if(panel.demo)throw new Error('datos DEMO');return panel;
      }));
      let loaded=0;
      for(const result of results){
        if(result.status!=='fulfilled')continue;
        const panel=result.value;add('h3',panel.title||panel.panel,output);
        for(const line of (panel.lines||[]).slice(0,12))add('p',String(line),output);
        add('small','Actualizado: '+(panel.as_of||'fecha no informada'),output);loaded++;
      }
      status.textContent=loaded?'ISLAFIX · '+loaded+' fuentes consultadas. Otras especialidades siguen propuestas.':'Servidor sin datos disponibles';
    }catch(error){status.textContent='Sin conexión verificable. No se muestran cifras inventadas.';}
    finally{connect.disabled=false;}
  };
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
  // Refresh real read-only reports while this observatory is visible. No model or actions.
  if (connect && typeof setInterval === 'function') {
    const refresh = () => { if (!document.hidden && visible && !connect.disabled) connect.onclick(); };
    setInterval(refresh, 60000);
    if (typeof setTimeout === 'function') setTimeout(refresh, 1200);
  }
  function line(points,color,width=1){ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke();}
  function ellipse(x,y,rx,ry,color,width=1){ctx.beginPath();ctx.ellipse(x,y,rx,ry,0,0,Math.PI*2);ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke();}
  function dot(x,y,r,color){ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();}
  function label(text,x,y,color='#6d99ad'){ctx.fillStyle=color;ctx.font='11px ui-monospace, monospace';ctx.fillText(text,x,y);}
  function nebula(){
    for(let i=0;i<7;i++){
      const cx=180+i*125,cy=280+Math.sin(i*1.8+phase*.03)*115;
      const g=ctx.createRadialGradient(cx,cy,5,cx,cy,220);
      g.addColorStop(0,ideas[i%5].color+'60');g.addColorStop(1,'#04091800');ctx.fillStyle=g;ctx.fillRect(cx-220,cy-220,440,440);
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
  // A 90-second journey: verdant world, nebula, distant galaxy. Artistic only.
  function tower() {
    const journey=phase/30, world=Math.floor(journey)%3, blend=(journey%1);
    const names=['MUNDO VERDE','NEBULOSA ÁMBAR','GALAXIA AZUL'];
    nebula();
    if(world===0){
      for(let layer=0;layer<4;layer++){
        const pts=[[0,650]];
        for(let i=0;i<=44;i++){const xx=i*25, yy=405+layer*43+Math.sin(i*.43+layer*2+phase*.012)*34+Math.cos(i*.91)*16;pts.push([xx,yy]);}
        pts.push([1100,650]);ctx.beginPath();pts.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.fillStyle=['#153b43','#145052','#123c38','#092a2c'][layer];ctx.fill();
      }
    }
    // Travel accelerates through the last third of each destination.
    const transit=Math.max(0,(blend-.7)/.3), cx=550+Math.sin(phase*.13)*12, lift=Math.sin(phase*.19)*7;
    if(transit>0)for(let i=0;i<70;i++){
      const angle=i*2.399963,rr=70+(i*31)%450;
      line([[550+Math.cos(angle)*rr,325+Math.sin(angle)*rr*.7],[550+Math.cos(angle)*(rr+transit*90),325+Math.sin(angle)*(rr+transit*90)*.7]],'#86eaff55');
    }
    ctx.save();ctx.translate(cx,300+lift);
    // Cyan spherical lattice encloses the whole citadel.
    for(let ring=0;ring<9;ring++)ellipse(0,0,285,40+ring*29,'#53dfff38',.7);
    for(let ring=0;ring<9;ring++)ellipse(0,0,35+ring*31,275,'#53dfff32',.7);
    for(let i=0;i<76;i++){
      const angle=i*2.399963+phase*.035, yy=-255+i*510/75, radius=Math.sqrt(Math.max(0,1-(yy/275)**2))*285;
      const xx=Math.cos(angle)*radius;
      dot(xx,yy, i%7===0?3:1.4,'#8befff');
      if(i%3===0)line([[xx,yy],[Math.cos(angle+.35)*radius,yy+12]],'#66ddff44');
    }
    // Shaded stacked terraces with masonry, windows and defensive towers.
    const tiers=quality==='rich'?18:12;
    for(let k=0;k<tiers;k++){
      const u=k/(tiers-1), y=205-u*385, rr=205-u*153, hh=385/tiers;
      const shade=ctx.createLinearGradient(-rr,y,rr,y);shade.addColorStop(0,'#162344');shade.addColorStop(.45,'#647aa3');shade.addColorStop(1,'#10152e');
      ctx.fillStyle=shade;ctx.fillRect(-rr,y-hh,rr*2,hh);
      ctx.fillStyle='#30446f';ctx.beginPath();ctx.ellipse(0,y-hh,rr,rr*.13,0,0,Math.PI*2);ctx.fill();
      ellipse(0,y-hh,rr,rr*.13,'#ede2b6',1.1);ellipse(0,y,rr,rr*.13,'#85dbea66',.65);
      const count=quality==='rich'?28:18;
      for(let j=0;j<count;j++){
        const xx=-rr+(j+.5)*rr*2/count;
        ctx.fillStyle=j%4===0?'#8ddcff':'#ffd789';ctx.fillRect(xx,y-hh*.63,2,5);
        if(j%4===0){ctx.strokeStyle='#201d1c88';ctx.strokeRect(xx-3,y-hh+3,7,hh-4);}
      }
      if(k%3===0)for(let side of [-1,1]){
        const xx=side*rr*.84;ctx.fillStyle='#547c80';ctx.fillRect(xx-7,y-hh-23,14,27);
        ctx.beginPath();ctx.moveTo(xx-11,y-hh-23);ctx.lineTo(xx,y-hh-43);ctx.lineTo(xx+11,y-hh-23);ctx.fillStyle='#3a6269';ctx.fill();dot(xx,y-hh-32,1.5,'#c7faff');
      }
    }
    // Inverted floating foundation and luminous propulsion core.
    for(let k=0;k<7;k++){
      const y=210+k*9,rr=195-k*25;
      line([[-rr,y],[0,y+23],[rr,y]],'#d7aa7077',2);
    }
    dot(0,279,7,'#baffff');ellipse(0,280,42,8,'#6cddff88');
    ctx.fillStyle='#d7b675';ctx.fillRect(-9,-219,18,43);line([[-14,-219],[0,-250],[14,-219]],'#e8c983',2);
    ctx.restore();
    for(let i=0;i<3;i++){
      const angle=phase*.12+i*Math.PI*2/3,xx=cx+Math.cos(angle)*325,yy=290+Math.sin(angle)*190;
      ellipse(xx,yy,11,11,'#d5faff88');dot(xx,yy,3,'#ffe6a0');
      line([[xx-18,yy],[xx+18,yy]],'#78dfff55');
    }
    for(let i=0;i<5;i++){const y=490-i*83,col=ideas[i].color;line([[cx+205-i*37,y],[885,y]],col+'66');label(`${i*20+1}–${(i+1)*20}`,895,y,col);}
    label('CIUDADELA ÓRBITA / 100 PISOS RESERVADOS',30,40,'#c9f5ff');
    label(names[world]+(transit>0?' · VIAJE EN CURSO':' · ÓRBITA ESTABLE'),30,61,'#e0c28c');
    label('CICLO VISUAL · 30 SEGUNDOS POR DESTINO',30,81);
  }
  function galaxy(){
    nebula();const cx=535,cy=320,rotation=phase*.018,count=quality==='rich'?1800:1000;
    // Deterministic scatter: three curved arms rather than random visual flicker.
    for(let i=0;i<count;i++){
      const u=(i+.5)/count,r=30+Math.sqrt(u)*390,arm=i%3;
      const noise=Math.sin(i*127.1)*Math.cos(i*31.7);
      const angle=arm*Math.PI*2/3+r*.0105+rotation+noise*(.10+.25*u);
      const spread=r+Math.sin(i*93.7)*24*Math.sqrt(u);
      const xx=cx+Math.cos(angle)*spread,yy=cy+Math.sin(angle)*spread*.52;
      const hue=i%9===0?'#ffe4b0':i%4===0?'#469dff':'#a9e8ff';
      dot(xx,yy,i%37===0?2.1:i%7===0?1.1:.65,hue+(i%7===0?'d0':'75'));
      if(i%38===0){const glow=ctx.createRadialGradient(xx,yy,0,xx,yy,14);glow.addColorStop(0,'#469dff40');glow.addColorStop(1,'#768dff00');ctx.fillStyle=glow;ctx.fillRect(xx-14,yy-14,28,28);}
    }
    for(let i=0;i<200;i++){
      const a=i*2.399963+rotation,r=82*Math.pow((i+.5)/200,1.7);
      dot(cx+Math.cos(a)*r,cy+Math.sin(a)*r*.55,.7,i%4===0?'#ffe2aacc':'#dceeff88');
    }
    // Dark dust lanes separate the bright arms; central elliptical bulge.
    for(let arm=0;arm<3;arm++){
      const pts=[];for(let j=0;j<100;j++){const r=65+j*3.2,a=arm*Math.PI*2/3+r*.0105+rotation+.12;pts.push([cx+Math.cos(a)*r,cy+Math.sin(a)*r*.52]);}line(pts,'#03091866',5);
    }
    const g=ctx.createRadialGradient(cx,cy,1,cx,cy,82);g.addColorStop(0,'#fff8e8ee');g.addColorStop(.18,'#ffe3a999');g.addColorStop(.5,'#49baff36');g.addColorStop(1,'#49baff00');ctx.save();ctx.translate(cx,cy);ctx.scale(1,.64);ctx.fillStyle=g;ctx.translate(-cx,-cy);ctx.fillRect(cx-82,cy-82,164,164);ctx.restore();
    ideas.forEach((item,i)=>{const a=i*Math.PI*.4-.6,xx=cx+Math.cos(a)*370,yy=cy+Math.sin(a)*240;line([[cx,cy],[xx,yy]],item.color+'35');ellipse(xx,yy,i===selected?16:9,i===selected?16:9,item.color);dot(xx,yy,3,item.color);label(`0${i+1} ${item.name}`,xx-60,yy+30,item.color);});
    label('GALAXIA ÓRBITA / BRAZOS ESPIRALES',30,40,'#c8efff');label('ESCENA ARTÍSTICA · SECTORES PROPUESTOS',30,61);
  }
  function cell(){const cx=535,cy=320;for(let ring=0;ring<3;ring++){const pts=[];for(let i=0;i<=180;i++){const a=i*Math.PI/90,r=220+ring*8+Math.sin(a*7+phase*.3)*8;pts.push([cx+Math.cos(a)*r*1.5,cy+Math.sin(a)*r]);}line(pts,ring===1?'#65d9cbaa':'#42859755');}
    for(let i=0;i<5;i++){const a=i*Math.PI*.4-1.4,xx=cx+Math.cos(a)*215,yy=cy+Math.sin(a)*135,col=ideas[i].color;line([[cx,cy],[xx,yy]],col+'55');ellipse(xx,yy,i===selected?70:55,40,col,2);for(let j=0;j<12;j++)dot(xx+Math.cos(j*2.4+phase*.1)*34,yy+Math.sin(j*2.4)*21,1.5,col);label(`0${i+1} / ${ideas[i].name}`,xx-55,yy+60,col);}
    ellipse(cx,cy,65,54,'#8bddff');label('JARVIS',cx-24,cy+4,'#e0faff');label('MEMBRANA / LÍMITES Y APROBACIONES',60,70);
  }
  function frame(now){requestAnimationFrame(frame);if(document.hidden||!visible)return;gesture(now);telemetry(now);const fps=quality==='rich'?24:window.JarvisHandMouseActive?10:15;if(now-last<1000/fps)return;const elapsed=last?Math.min(.2,(now-last)/1000):1/fps;last=now;if(!paused)phase+=elapsed;ctx.fillStyle='#020b15';ctx.fillRect(0,0,1100,650);

  // Deterministic deep-space field; no extra animation loop or asset downloads.
  for(let star=0;star<720;star++){
    const sx=(star*197.31)%1100,sy=(star*97.93)%650;
    ctx.globalAlpha=.3+.55*(.5+.5*Math.sin(phase*.7+star));
    ctx.fillStyle=star%13===0?'#ffcf79':star%5===0?'#54caff':'#e6f7ff';
    const size=star%23===0?1.8:star%7===0?1:.65;ctx.fillRect(sx,sy,size,size);
  }
  ctx.globalAlpha=1;
  for(let meteor=0;meteor<3;meteor++){
    const travel=(phase*.16+meteor*.37)%1;
    const mx=travel*(1100+360)-180,my=meteor*216+travel*220-100;
    const tail=ctx.createLinearGradient(mx-100,my-42,mx,my);
    tail.addColorStop(0,'#39baff00');tail.addColorStop(.8,'#58ceff80');tail.addColorStop(1,'#fff4d9');
    ctx.strokeStyle=tail;ctx.lineWidth=meteor===0?1.8:1;ctx.beginPath();
    ctx.moveTo(mx-100,my-42);ctx.lineTo(mx,my);ctx.stroke();
    ctx.fillStyle='#f3fbff';ctx.fillRect(mx-1,my-1,2,2);
  }
    ctx.strokeStyle='#27516b20';ctx.lineWidth=1;for(let xx=0;xx<1100;xx+=55)line([[xx,0],[xx,650]],'#27516b15');for(let yy=0;yy<650;yy+=50)line([[0,yy],[1100,yy]],'#27516b15');
    ({tower,galaxy,cell})[mode]();science();label(paused?'UNIVERSO PAUSADO':quality==='rich'?'DETALLE / 24 FPS MÁX':window.JarvisHandMouseActive?'GESTOS PRIORITARIOS / 10 FPS MÁX':'LIGERO / 15 FPS MÁX',30,625);label('REVENUE / SIN DATOS',840,625);
  }
  if('IntersectionObserver' in window)new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;}).observe(canvas);
  select(0);requestAnimationFrame(frame);
})();
