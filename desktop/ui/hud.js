(function(){"use strict";
var $=function(id){return document.getElementById(id);},M=window.JarvisMask,cards=[],jobs=null,jobsCount=null,seq=0;
var windowId='hud-'+Math.random().toString(16).slice(2),clock=new Intl.DateTimeFormat('es-PR',{timeZone:'America/Puerto_Rico',hour:'2-digit',minute:'2-digit'});
var stages=['quote','confirmed','in_progress','delivered','invoiced'],names={quote:'Cotización',confirmed:'Confirmado',in_progress:'En proceso',delivered:'Entregado',invoiced:'Facturado'};
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
function show(value,sensitive){if(value==null||value==='')return 'sin dato';return sensitive&&!$('hud-reveal').checked?M.mask(String(value)):String(value);}
function api(method,path,body){var o={method:method,credentials:'same-origin',headers:{'X-Jarvis-UI':'1'}};if(body!==undefined){o.body=JSON.stringify(body);o.headers['Content-Type']='application/json';}return fetch(path,o).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json();});}
function number(id,n){$(id).textContent=typeof n==='number'&&Number.isFinite(n)&&n>=0?String(Math.round(n)):'sin dato';}
function open(id){api('POST','/api/open',{target:id}).catch(function(){$('deck-caption').textContent='No pude abrir el detalle. Revisa la ventana principal.';});}
function day(s){if(typeof s!=='string'||!/^\d{4}-\d{2}-\d{2}/.test(s))return null;var date=s.slice(0,10),n=Date.parse(date+'T12:00:00Z');return Number.isFinite(n)&&new Date(n).toISOString().slice(0,10)===date?n:null;}
function renderJobs(){
 var list=$('job-list'),timeline=$('timeline');list.textContent='';timeline.textContent='';number('metric-jobs',jobsCount);$('jobs-count').textContent=jobsCount==null?'sin dato':String(jobsCount);
 if(jobs===null){list.appendChild(el('p','empty','sin dato'));timeline.appendChild(el('p','empty','sin dato'));return;}
 if(!jobs.length){list.appendChild(el('p','empty','Sin trabajos abiertos'));timeline.appendChild(el('p','empty','Sin fechas de trabajos abiertos'));return;}
 var dates=[];jobs.forEach(function(j){[day(j.created),day(j.due_date)].forEach(function(d){if(d!==null)dates.push(d);});});var min=Math.min.apply(null,dates),max=Math.max.apply(null,dates);
 jobs.forEach(function(j){
  var row=el('div','job'),stage=stages.indexOf(j.status);row.appendChild(el('span','job-title',show(j.title,true)));
  row.appendChild(el('span','job-stage',(stage>=0?names[j.status]:'sin dato')));
  var track=el('div','stage-track');track.setAttribute('aria-label','Etapa: '+((stage>=0?names[j.status]:'sin dato')));
  stages.forEach(function(_,i){track.appendChild(el('i',stage>=i?'active':''));});row.appendChild(track);list.appendChild(row);
  var tr=el('div','timeline-row'),start=day(j.created),end=day(j.due_date);tr.appendChild(el('span','timeline-title',show(j.title,true)));
  tr.appendChild(el('span','timeline-dates','Registro: '+(start===null?'sin dato':j.created.slice(0,10))+' · Vence: '+(end===null?'sin dato':j.due_date.slice(0,10))));
  if(start!==null&&end!==null&&end>=start){var rail=el('div','timeline-track'),bar=el('div','timeline-bar'),span=Math.max(max-min,86400000);bar.style.marginLeft=((start-min)/span*100)+'%';bar.style.width=((end-start)/span*100)+'%';rail.appendChild(bar);tr.appendChild(rail);}
  timeline.appendChild(tr);
 });
 if(jobsCount>jobs.length)list.appendChild(el('p','caption','Mostrando '+jobs.length+' de '+jobsCount));
}
function render(){var grid=$('grid');grid.textContent='';cards.forEach(function(c){var b=el('button','card'+(c.stale?' stale':''));b.type='button';b.appendChild(el('div','t',(c.demo?'DEMO · ':'')+c.title));b.appendChild(el('div','v',show(c.value,c.sensitive)));b.appendChild(el('div','when',c.stale?'Dato antiguo':c.as_of?String(c.as_of).slice(0,16).replace('T',' '):'sin dato'));b.onclick=function(){open(c.id);};grid.appendChild(b);});if(!cards.length)grid.appendChild(el('p','empty','Módulos: sin dato'));renderJobs();}
function clearData(){cards=[];jobs=null;jobsCount=null;render();}
function load(){return api('GET','/api/hud').then(function(r){cards=Array.isArray(r.cards)?r.cards:[];jobs=Array.isArray(r.jobs)?r.jobs:null;jobsCount=Number.isInteger(r.jobs_count)&&r.jobs_count>=0?r.jobs_count:null;$('hud-demo').hidden=!r.demo;render();$('hud-updated').textContent='Consulta '+clock.format(new Date());$('deck-caption').textContent=r.demo?'DEMO · Datos de ejemplo. Trabajos: sin dato.':r.as_of?'Datos del '+String(r.as_of).slice(0,16).replace('T',' '):'Fecha de los datos: sin dato';}).catch(function(){clearData();health({state:'down'});$('hud-updated').textContent='sin dato';$('deck-caption').textContent='No se pudieron actualizar los datos. Pulsa Actualizar.';});}
function health(h){$('dot').setAttribute('data-s',h.state||'unknown');$('deck-state').textContent=({ok:'Conectado',slow:'Con retraso',demo:'DEMO',down:'Sin conexión',unpaired:'Sin emparejar',error:'Error'})[h.state]||'sin dato';var fresh=h.state==='ok'||h.state==='slow';number('metric-latency',fresh?h.latency_ms:null);number('metric-age',fresh?h.age_s:null);var info=fresh?(h.info||{}):{};$('sec-storage').textContent=show(info.storage);$('sec-real').textContent=info.real_trading_active===true?'Activadas':info.real_trading_active===false?'Apagadas':'sin dato';}
function state(){return api('GET','/api/state').then(function(s){health(s.server||{});number('metric-windows',s.windows);$('sec-paired').textContent=s.paired===true?'Sí':s.paired===false?'No':'sin dato';var t=s.tts;$('voice-state').textContent='Voz: '+(t&&t.engine&&t.engine!=='none'&&!t.problem?'motor local disponible':t?'no configurada':'sin dato');}).catch(function(){health({state:'down'});number('metric-windows',null);$('sec-paired').textContent='sin dato';$('voice-state').textContent='Voz: sin dato';});}
function poll(){api('GET','/api/events?since='+seq+'&window='+windowId).then(function(r){(r.events||[]).forEach(function(e){if(e.type==='health'&&e.health)health(e.health);});seq=r.seq;poll();}).catch(function(){health({state:'down'});setTimeout(poll,3000);});}
var reactor=window.JarvisReactor.create($('deck-canvas'),function(paused){$('deck-motion').textContent=paused?'Animar':'Pausar';$('deck-motion').setAttribute('aria-pressed',String(paused));});
$('deck-motion').onclick=reactor.toggle;$('hud-refresh').onclick=function(){load();state();};$('hud-reveal').onchange=render;
$('deck-fullscreen').onclick=function(){var root=document.documentElement,fn=root.requestFullscreen||root.webkitRequestFullscreen,exit=document.exitFullscreen||document.webkitExitFullscreen;if((document.fullscreenElement||document.webkitFullscreenElement)&&exit){exit.call(document);return;}if(fn){var p=fn.call(root);if(p&&p.catch)p.catch(function(){$('deck-caption').textContent='Usa pantalla completa desde el menú del navegador.';});}};
function tick(){$('hud-clock').textContent='PR '+clock.format(new Date());}tick();setInterval(tick,15000);load();state();poll();setInterval(load,60000);setInterval(state,15000);
})();
