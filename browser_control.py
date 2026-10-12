"""Shared validation for browser proposals. No network, execution or credentials."""
import ipaddress
import json
import re
from urllib.parse import parse_qsl, urlsplit

PRIVATE = re.compile(r'password|passwd|contrase|secret|token|credential|one.time|otp|tarjeta|card.number|cvv', re.I)
FINANCE = re.compile(r'bank|banco|paypal|stripe|checkout|coinbase|venmo|zelle|wallet|payment|payout|billing|athmovil', re.I)

def public_url(value):
    if not isinstance(value,str) or not 1<=len(value)<=2000 or any(c.isspace() for c in value) or '\\' in value:
        raise ValueError('Enlace inválido')
    u=urlsplit(value);host=(u.hostname or '').lower().rstrip('.')
    if u.scheme!='https' or not host or '.' not in host or u.username or u.password or u.port not in (None,443):
        raise ValueError('Solo enlaces HTTPS públicos')
    if host.endswith(('.local','.internal','.localhost','.test','.invalid')) or FINANCE.search(host+u.path):
        raise ValueError('Sitio privado o financiero fuera del control del navegador')
    try:ipaddress.ip_address(host)
    except ValueError:pass
    else:raise ValueError('No se aceptan direcciones IP')
    if any(re.search(r'token|key|secret|password|signature|credential|auth|session|code',k,re.I) for k,_ in parse_qsl(u.query,keep_blank_values=True)):
        raise ValueError('No compartas enlaces con credenciales')
    return value

def snapshot(value):
    if not isinstance(value,dict):raise ValueError('Página inválida')
    url=public_url(value.get('url'))
    nodes=value.get('elements')
    if not isinstance(nodes,list) or len(nodes)>80:raise ValueError('Demasiados elementos')
    out=[];seen=set()
    for node in nodes:
        if not isinstance(node,dict):raise ValueError('Elemento inválido')
        n=node.get('id')
        if type(n)!=int or n<0 or n in seen:raise ValueError('Identificador inválido')
        seen.add(n)
        item={k:str(node.get(k,''))[:(2000 if k=='href' else 160)] for k in ('tag','type','label','href')}
        if item['type'] in ('password','hidden','file') or PRIVATE.search(item['label']):raise ValueError('Campo privado')
        if item['href']:public_url(item['href'])
        out.append({'id':n,**item})
    return {'url':url,'title':str(value.get('title',''))[:160],'elements':out}

def proposal(value,page):
    page=snapshot(page)
    if not isinstance(value,dict) or value.get('action') not in ('click','fill','done'):
        raise ValueError('Jarvis devolvió una acción no permitida')
    kind=value['action'];reason=str(value.get('reason',''))[:400]
    if kind=='done':return {'action':'done','reason':reason}
    target=value.get('target')
    if type(target)!=int:raise ValueError('Falta un elemento observado')
    node=next((n for n in page['elements'] if n['id']==target),None)
    if node is None:raise ValueError('El elemento no aparece en la página')
    if FINANCE.search(node['label']+' '+node['href']):raise ValueError('Acción financiera: hazla personalmente')
    if kind=='click' and node['href']:public_url(node['href'])
    out={'action':kind,'target':target,'reason':reason}
    if kind=='fill':
        if node['tag'] not in ('input','textarea') or node['type'] not in ('','text','search','email','url','tel','number','textarea'):
            raise ValueError('Ese campo no admite escritura')
        text=value.get('text')
        if not isinstance(text,str) or len(text)>4000 or any(ord(c)<32 and c not in '\n\t' for c in text):
            raise ValueError('Texto inválido')
        out['text']=text
    return out

def encoded(value):
    return json.dumps(value,ensure_ascii=True,separators=(',',':'))
