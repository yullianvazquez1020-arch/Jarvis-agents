#!/usr/bin/env python3
"""Supervised Safari companion. Python 3.9+, standard library, no shell commands from AI."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'desktop'))
from browser_control import encoded, public_url, snapshot, proposal
from jarvis_client import JarvisClient, TokenStore, ServerError

APPLE_SCRIPT='''on run argv
 tell application "Safari"
  if item 1 of argv is "open" then
   make new document with properties {URL:item 2 of argv}
   activate
   return id of front window as text
  end if
  set targetWindow to window id (item 2 of argv as integer)
  if (count of tabs of targetWindow) is not 1 then error "La ventana dedicada debe tener una sola pestaña"
  if item 1 of argv is "url" then return URL of tab 1 of targetWindow
  return do JavaScript (item 3 of argv) in tab 1 of targetWindow
 end tell
end run'''

# Fixed JavaScript: values and instructions are JSON data, never executable model code.
DOM='''
const privateField=/password|passwd|contrase|secret|token|credential|one.time|otp|tarjeta|card.number|cvv/i;
const clean=s=>String(s||'').replace(/\\s+/g,' ').trim().slice(0,160);
const candidates=Array.from(document.querySelectorAll('a,button,input,textarea,select,[role="button"]'));
const nodes=candidates.filter(e=>{
 if(e.tagName==='A'){
  try{const u=new URL(e.href);
   if(u.protocol!=='https:' || u.username || u.password || (u.port && u.port!=='443') ||
    /bank|banco|paypal|stripe|checkout|coinbase|venmo|zelle|wallet|payment|payout|billing|athmovil/i.test(u.hostname+u.pathname) ||
    Array.from(u.searchParams.keys()).some(k=>/token|key|secret|password|signature|credential|auth|session|code/i.test(k)))return false;
  }catch(_){return false;}
 }
 const r=e.getBoundingClientRect(),style=getComputedStyle(e);
 return r.width>0 && r.height>0 && style.visibility!=='hidden' && style.display!=='none' && !e.disabled &&
 !['password','hidden','file'].includes(e.type) &&
 !privateField.test([e.name,e.autocomplete,e.getAttribute('aria-label'),e.labels?Array.from(e.labels).map(l=>l.innerText).join(' '):''].join(' '));
}).slice(0,80);
const state={url:location.href,title:clean(document.title),elements:nodes.map((e,id)=>({
 id,tag:e.tagName.toLowerCase(),type:e.type||'',
 label:clean(e.getAttribute('aria-label')||(e.labels&&e.labels.length?Array.from(e.labels).map(l=>l.innerText).join(' '):'')||e.innerText||e.placeholder||e.name),
 href:e.tagName==='A'?e.href:''
}))};
'''

class Safari:
    def __init__(self,url):
        if sys.platform!='darwin':raise RuntimeError('Este conector se ejecuta en tu Mac')
        self.window=self._call('open',public_url(url)).strip()
        if not self.window.isdigit():raise RuntimeError('No se pudo identificar la ventana de Safari')

    def _call(self,*args):
        p=subprocess.run(['/usr/bin/osascript','-e',APPLE_SCRIPT,*args],capture_output=True,text=True,timeout=25)
        if p.returncode:
            # AppleScript errors may contain page text; do not forward them to the cloud.
            raise RuntimeError('Safari no permitió la acción. Revisa Automatización y «Permitir JavaScript desde eventos de Apple», o si cerraste/cambiaste la ventana dedicada.')
        return p.stdout.strip()

    def current_url(self):return public_url(self._call('url',self.window))

    def observe(self):
        self.current_url()
        result=self._call('js',self.window,'(()=>{'+DOM+'return JSON.stringify(state);})()')
        return snapshot(json.loads(result))

    def act(self,action,page):
        action=proposal(action,page)
        self.current_url()
        js='(()=>{'+DOM+'const expected='+encoded(page)+';const action='+encoded(action)+''';
if(JSON.stringify(state)!==JSON.stringify(expected))throw new Error('Página cambió; revisa otra vez');
const e=nodes[action.target];
if(action.action==='click'){e.click();}
else if(action.action==='fill'){
 const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
 Object.getOwnPropertyDescriptor(proto,'value').set.call(e,action.text);
 e.dispatchEvent(new Event('input',{bubbles:true}));
 e.dispatchEvent(new Event('change',{bubbles:true}));
}else{throw new Error('Acción inválida');}
return 'hecho';})()'''
        return self._call('js',self.window,js)

def stopped():return (Path.home()/'.jarvis-control'/'STOP').exists()

def approve_and_execute(browser,action,page,ask=input,clock=time.monotonic):
    action=proposal(action,page)
    if action['action']=='done':return 'done'
    if stopped():raise RuntimeError('STOP está activo')
    print('Página y acción que se ejecutarán:')
    print(encoded({'url':page['url'],'element':next(n for n in page['elements'] if n['id']==action['target']),'proposal':action}))
    print('Un clic puede enviar/publicar; un campo puede guardar automáticamente. Revisa también Safari.')
    code=secrets.token_hex(3);started=clock()
    if ask('Escribe '+code+' para ejecutar UNA vez, o Enter para cancelar: ').strip()!=code:return 'cancelled'
    if clock()-started>90 or stopped():raise RuntimeError('Confirmación vencida o STOP activo')
    if browser.observe()!=page:raise RuntimeError('La página cambió; pide una propuesta nueva')
    if clock()-started>90 or stopped():raise RuntimeError('Confirmación vencida o STOP activo')
    # No retry: if a timeout follows execution, outcome is unknown and must be inspected.
    browser.act(action,page)
    return 'executed'

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--url',required=True)
    ap.add_argument('--server',default='https://jarvis-agents.onrender.com')
    args=ap.parse_args()
    if not sys.stdin.isatty():raise RuntimeError('Abre este conector desde tu Terminal para revisar las acciones')
    tokens=TokenStore(Path.home()/'.jarvis-desktop')
    client=JarvisClient(args.server,tokens.load,timeout=75)
    client.status()  # Verify pairing before opening Safari; never prints or sends token in URLs.
    browser=Safari(args.url)
    print('Safari listo en una ventana dedicada. Inicia sesión personalmente allí si hace falta.')
    print('Escribe la tarea para proponer UN paso. /ver muestra controles locales. /salir termina.')
    print('Al pedir un paso compartes URL, título y etiquetas de controles con Jarvis; nunca se leen valores de campos ni contraseñas.')
    while True:
        try:
            task=input('Jarvis navegador> ').strip()
            if task=='/salir':break
            if not task:continue
            if stopped():raise RuntimeError('STOP activo')
            page=browser.observe()
            if task=='/ver':print(encoded(page));continue
            result=client._call('POST','/browser/v1/propose',{'task':task,'page':page})
            action=proposal(result.get('proposal'),page)
            if action['action']=='done':print(encoded(action));continue
            outcome=approve_and_execute(browser,action,page)
            print('Paso ejecutado. Revisa Safari antes de pedir el siguiente.' if outcome=='executed' else 'Cancelado; no se ejecutó el paso.')
        except (ValueError,RuntimeError,ServerError,subprocess.TimeoutExpired) as e:
            print('Detenido: '+encoded(str(e))+'. Si hubo un intento de ejecución, revisa Safari antes de repetir.')
        except (EOFError,KeyboardInterrupt):break

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,ServerError,subprocess.TimeoutExpired) as e:
        print(encoded(str(e)));sys.exit(1)
