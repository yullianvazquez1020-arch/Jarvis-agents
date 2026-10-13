"""Hub de links propio. Jarvis lo sirve en /hub. No usa Linktree."""
import os
import re
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

KEY = 'jarvis:funnel'
HELP = ('/hub — tu página de links\n'
        '/hub set NOMBRE https://...\n'
        '/hub quitar NOMBRE\n'
        '/hub titulo TEXTO\n'
        '/hub bio TEXTO')
SLUG = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$')
PIXEL = re.compile(r'^\d{5,20}$')
GA4 = re.compile(r'^G-[A-Z0-9]{4,20}$')


def empty():
    return {
        'title': 'AINCRAD',
        'bio': 'Organiza tu remodelación. Un kit práctico en español.',
        'links': [],
    }


def slugify(name):
    raw = re.sub(r'[^a-z0-9]+', '-', str(name).strip().lower()).strip('-')
    if not SLUG.match(raw):
        raise ValueError('Nombre inválido. Usa letras o números.')
    return raw


def https_url(value):
    u = urlsplit(str(value).strip())
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.fragment:
        raise ValueError('El enlace tiene que ser HTTPS, sin usuario ni contraseña.')
    return u.geturl()


def load():
    d = core.kv_get(KEY, empty())
    if not isinstance(d, dict):
        d = empty()
    d.setdefault('title', 'AINCRAD')
    d.setdefault('bio', '')
    d.setdefault('links', [])
    return d


def save(d):
    core.kv_set(KEY, d)


def tracking():
    pixel = os.getenv('META_PIXEL_ID', '').strip()
    ga = os.getenv('GA4_MEASUREMENT_ID', '').strip()
    return {
        'pixel': pixel if PIXEL.match(pixel) else '',
        'ga4': ga if GA4.match(ga) else '',
    }


def page(data=None, host=''):
    d = data if data is not None else load()
    title = escape(str(d.get('title') or 'AINCRAD')[:80])
    bio = escape(str(d.get('bio') or '')[:280])
    rows = []
    for link in d.get('links') or []:
        if not isinstance(link, dict):
            continue
        try:
            url = https_url(link.get('url', ''))
            slug = slugify(link.get('slug') or link.get('name'))
        except ValueError:
            continue
        name = escape(str(link.get('name') or slug)[:60])
        rows.append(
            f'<a class="go" href="/hub/go/{slug}">{name}</a>'
        )
    body = '\n'.join(rows) or '<p class="empty">Los enlaces salen aquí en cuanto los guardas.</p>'
    ids = tracking()
    scripts = []
    if ids['ga4']:
        gid = ids['ga4']
        scripts.append(
            f'<script async src="https://www.googletagmanager.com/gtag/js?id={gid}"></script>'
            f'<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}'
            f'gtag("js",new Date());gtag("config","{gid}");</script>'
        )
    if ids['pixel']:
        pid = ids['pixel']
        scripts.append(
            "<script>!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?"
            "n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;"
            "n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;"
            "t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,"
            "document,'script','https://connect.facebook.net/en_US/fbevents.js');"
            f'fbq("init","{pid}");fbq("track","PageView");</script>'
        )
    return f'''<!doctype html>
<html lang="es">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
  body {{ margin:0; background:#0c0c0c; color:#f4f1ea; font:16px/1.4 Georgia, serif; }}
  main {{ max-width:420px; margin:0 auto; padding:48px 20px 64px; }}
  h1 {{ font-size:32px; letter-spacing:.12em; margin:0 0 8px; }}
  p {{ color:#c8c2b4; margin:0 0 28px; }}
  a.go {{ display:block; margin:0 0 12px; padding:16px 18px; border:1px solid #3a3428;
          color:#f4f1ea; text-decoration:none; text-align:center; letter-spacing:.04em; }}
  a.go:hover {{ border-color:#d6b25e; color:#d6b25e; }}
  .empty {{ color:#8a8478; }}
</style>
{''.join(scripts)}
<main>
  <h1>{title}</h1>
  <p>{bio}</p>
  {body}
</main>
'''


def summary():
    d = load()
    host = os.getenv('PUBLIC_HOST', '').strip()
    url = f'https://{host}/hub' if host else '/hub'
    lines = [f'Hub propio: {url}', d['title'], d['bio'] or '(sin bio)', f"Enlaces: {len(d['links'])}"]
    for link in d['links']:
        lines.append(f"• {link['name']} → {link['url']}  ({link.get('clicks', 0)} clics)")
    if not d['links']:
        lines.append('Todavía no hay enlaces. Ejemplo: /hub set Kit https://tu-producto')
    lines.append(HELP)
    return '\n'.join(lines)


def reply(arg):
    text = (arg or '').strip()
    action, _, rest = text.partition(' ')
    action = action.lower()
    with core._data_lock:
        d = load()
        if not action:
            return summary()
        if action == 'titulo':
            if not rest.strip() or len(rest.strip()) > 80:
                raise ValueError('Título de 1 a 80 caracteres.')
            d['title'] = rest.strip()
            save(d)
            return 'Título guardado.\n' + summary()
        if action == 'bio':
            if len(rest.strip()) > 280:
                raise ValueError('Bio de hasta 280 caracteres.')
            d['bio'] = rest.strip()
            save(d)
            return 'Bio guardada.\n' + summary()
        if action == 'set':
            name, _, url = rest.partition(' ')
            if not url:
                raise ValueError('Usa /hub set NOMBRE https://...')
            slug = slugify(name)
            url = https_url(url)
            label = name.strip()[:60]
            found = False
            for link in d['links']:
                if link['slug'] == slug:
                    link['name'] = label
                    link['url'] = url
                    found = True
            if not found:
                if len(d['links']) >= 8:
                    raise ValueError('Máximo 8 enlaces.')
                d['links'].append({'slug': slug, 'name': label, 'url': url, 'clicks': 0})
            save(d)
            return 'Enlace guardado.\n' + summary()
        if action == 'quitar':
            slug = slugify(rest)
            before = len(d['links'])
            d['links'] = [x for x in d['links'] if x['slug'] != slug]
            if len(d['links']) == before:
                raise ValueError('Ese enlace no está.')
            save(d)
            return 'Enlace quitado.\n' + summary()
        raise ValueError(HELP)


def record_click(slug):
    with core._data_lock:
        d = load()
        for link in d['links']:
            if link['slug'] == slug:
                link['clicks'] = int(link.get('clicks') or 0) + 1
                save(d)
                return link['url']
    return None


def install(j):
    global core
    core = j
    from fastapi.responses import HTMLResponse, RedirectResponse

    @j.app.get('/hub')
    async def hub_page():
        return HTMLResponse(page())

    @j.app.get('/hub/go/{slug}')
    async def hub_go(slug: str):
        try:
            slugify(slug)
        except ValueError:
            raise j.HTTPException(404, 'No está')
        url = record_click(slug)
        if not url:
            raise j.HTTPException(404, 'No está')
        return RedirectResponse(url, status_code=302)

    old = j._extensions.command

    async def command(chat_id, cmd, arg):
        if cmd != '/hub':
            return await old(chat_id, cmd, arg)
        if str(chat_id) != str(j.TG_OWNER):
            return
        try:
            text = reply(arg)
        except ValueError as e:
            text = str(e)
        await j._tg_safe_send(chat_id, text)

    j._extensions.command = command
    j._extensions.COMMANDS.add('/hub')
    j.HELP_TEXT += '\n' + HELP
    j._funnel = __import__(__name__)
