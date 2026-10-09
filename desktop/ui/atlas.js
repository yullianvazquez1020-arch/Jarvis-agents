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
  let last = 0, phase = 0, visible = true, position = null;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const cursor = document.createElement('div'); cursor.className = 'atlas-cursor'; cursor.hidden = true; cursor.setAttribute('aria-hidden','true'); root.appendChild(cursor);
  function add(tag, text, parent, cls) { const e = document.createElement(tag); e.textContent = text; if(cls)e.className=cls; parent.appendChild(e); return e; }
  function select(index) {
    selected = index;
    [...list.children].forEach((b,i) => b.setAttribute('aria-pressed',String(i===index)));
    detail.replaceChildren(); const item = ideas[index];
    add('small',`PISO ${String(index+1).padStart(2,'0')} / PROPUESTA`,detail);
    add('h2',item.name,detail); add('p',`Arranque estimado: ${item.cost}. No gastado.`,detail,'atlas-estimate');
    for (const [title, text] of [['Preparación de Jarvis',item.task],['Meta propuesta · 30 días',item.goal],['Cómo medir',item.metric],['Aprobación del dueño',item.approval]]) {add('h3',title,detail);add('p',text,detail);}
    add('p','Cobrado no es ganancia. Sin datos conectados no se calcula rendimiento ni se decide cerrar o ampliar la prueba.',detail,'atlas-disclaimer');
  }
  ideas.forEach((item,i)=> {const b=add('button',`${String(i+1).padStart(2,'0')} / ${item.name}`,list);b.type='button'; b.dataset.floor=String(i);b.style.setProperty('--floor-color',item.color);b.onclick=()=>select(i);});
  tabs.forEach(button => button.onclick = () => {mode=button.dataset.atlas;tabs.forEach(b=>b.setAttribute('aria-pressed',String(b===button)));document.getElementById('atlas-view-name').textContent={tower:'TORRE / UN PISO POR PRUEBA',galaxy:'GALAXIA / MERCADOS POR EXPLORAR',cell:'MEMBRANA / ÁREAS DEL PORTAFOLIO'}[mode];});
  handButton.onclick = () => {navigation=!navigation;handButton.setAttribute('aria-pressed',String(navigation));if(!navigation){cursor.hidden=true;hovered=null;latched=null;position=null;}handStatus.textContent=navigation?'Activa la cámara con «Activar mano». Señala con el índice y mantén 1,2 segundos sobre una vista o piso. Escape detiene la navegación.':'Navegación por mano apagada. No controla el cursor del sistema.';};
  addEventListener('keydown',e=>{if(e.key==='Escape'&&navigation)handButton.click();});
  const safeTargets = [...tabs,...list.children];
  function gesture(now) {
    const h=window.JarvisHands;
    if(!navigation || document.hidden || !h?.seen || !h.landmarks || now-(h.updatedAt||0)>350){cursor.hidden=true;hovered=null;latched=null;position=null;return;}
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
  function tower() {
    const cx=510;
    for(let floor=4;floor>=0;floor--){const y=480-floor*82,r=210-floor*27,col=ideas[floor].color;
      ctx.fillStyle=floor===selected?'#12313d':'#081c2b';ctx.beginPath();ctx.ellipse(cx,y,r,35,0,0,Math.PI*2);ctx.fill();
      for(let k=0;k<5;k++)ellipse(cx,y+k*4,r-k*2,35,col+(k?'35':'bb'),floor===selected?2:1);
      for(let j=0;j<20;j++){const a=j*Math.PI/10+phase*.05;const xx=cx+Math.cos(a)*(r-18),yy=y+Math.sin(a)*25;if(Math.sin(a)>0){line([[xx,yy-20],[xx,yy]],col+'60');dot(xx,yy-20,1.3,col);}}
      line([[cx+r,y],[790,y-25],[835,y-25]],col+'55');label(`0${floor+1} / ${ideas[floor].name.toUpperCase()}`,840,y-22,floor===selected?col:'#7295a7');
    }
    line([[cx,85],[cx,548]],'#89ddec45');ellipse(cx,563,285,42,'#4acbd430');ellipse(cx,563,310,52,'#4acbd415');
    for(let i=0;i<100;i++){const a=i*2.399+phase*.1,rr=30+((i*37)%240);dot(cx+Math.cos(a)*rr,545+(i%7)*5,1,'#63c9d355');}
    label('FLOOR ACCESS / SELECT IN DIRECTORY',60,70);label('00 / OWNER APPROVAL',390,608,'#d0b887');
  }
  function galaxy(){const cx=515,cy=315;for(let i=0;i<1200;i++){const a=i*2.399963+phase*.025,r=15+Math.sqrt(i/1200)*360,arm=i%5;const twist=a*.025+r*.009+arm*Math.PI*.4;const xx=cx+Math.cos(twist)*r,yy=cy+Math.sin(twist)*r*.60;dot(xx,yy,i%19===0?1.9:.8,ideas[arm].color+(arm===selected?'bb':'45'));}
    const g=ctx.createRadialGradient(cx,cy,1,cx,cy,70);g.addColorStop(0,'#fff4cbbb');g.addColorStop(.3,'#e1a55044');g.addColorStop(1,'#ffad0000');ctx.fillStyle=g;ctx.fillRect(cx-70,cy-70,140,140);
    ideas.forEach((item,i)=>{const a=i*Math.PI*.4-.6,xx=cx+Math.cos(a)*310,yy=cy+Math.sin(a)*210;line([[cx,cy],[xx,yy]],item.color+'40');ellipse(xx,yy,i===selected?20:12,i===selected?20:12,item.color);dot(xx,yy,4,item.color);label(`0${i+1} ${item.name}`,xx-45,yy+36,item.color);});label('RELACIONES CONCEPTUALES / NO TRÁFICO REAL',60,70);
  }
  function cell(){const cx=535,cy=320;for(let ring=0;ring<3;ring++){const pts=[];for(let i=0;i<=180;i++){const a=i*Math.PI/90,r=220+ring*8+Math.sin(a*7+phase*.3)*8;pts.push([cx+Math.cos(a)*r*1.5,cy+Math.sin(a)*r]);}line(pts,ring===1?'#65d9cbaa':'#42859755');}
    for(let i=0;i<5;i++){const a=i*Math.PI*.4-1.4,xx=cx+Math.cos(a)*215,yy=cy+Math.sin(a)*135,col=ideas[i].color;line([[cx,cy],[xx,yy]],col+'55');ellipse(xx,yy,i===selected?70:55,40,col,2);for(let j=0;j<12;j++)dot(xx+Math.cos(j*2.4+phase*.1)*34,yy+Math.sin(j*2.4)*21,1.5,col);label(`0${i+1} / ${ideas[i].name}`,xx-55,yy+60,col);}
    ellipse(cx,cy,65,54,'#dabdff');label('JARVIS',cx-24,cy+4,'#ecddff');label('MEMBRANA / LÍMITES Y APROBACIONES',60,70);
  }
  function frame(now){requestAnimationFrame(frame);if(document.hidden||!visible)return;gesture(now);if(now-last<1000/24)return;last=now;if(!reduced.matches)phase+=1/24;ctx.fillStyle='#020b15';ctx.fillRect(0,0,1100,650);
    for(let i=0;i<140;i++){const xx=(i*197.3)%1100,yy=(i*97.9)%650;dot(xx,yy,i%9===0?1:.5,'#739fc344');}
    ctx.strokeStyle='#27516b20';ctx.lineWidth=1;for(let xx=0;xx<1100;xx+=55)line([[xx,0],[xx,650]],'#27516b15');for(let yy=0;yy<650;yy+=50)line([[0,yy],[1100,yy]],'#27516b15');
    ({tower,galaxy,cell})[mode]();label('LOCAL RENDER / 24 FPS MAX',30,625);label('REVENUE / SIN DATOS',840,625);
  }
  if('IntersectionObserver' in window)new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;}).observe(root);
  select(0);requestAnimationFrame(frame);
})();
