"""Gumroad sales, kit files, price alerts, and X/Pinterest/TikTok drafts.
Publishing stays behind the owner's code. Coinbase approvals are not touched.
"""
import datetime as dt
import hashlib
import os
import re
import secrets
from urllib.parse import parse_qs, urlsplit
from xml.sax.saxutils import escape

import jarvis_aincrad

KEY = 'jarvis:evolve'
HELP = ('/precio · /precio alta NOMBRE URL · /precio quitar NOMBRE · '
        '/redes · /redes x TEXTO · /redes pinterest IMAGEN | TEXTO · /redes tiktok VIDEO | TEXTO · '
        '/confirmarredes ID CODIGO')
PRICE_HOSTS = ('amazon.com', 'amazon.es', 'amazon.com.mx', 'alibaba.com')
PLATFORMS = ('x', 'pinterest', 'tiktok')


def empty():
    return {'sales': [], 'prices': [], 'posts': [], '_seq': {'posts': 0}}


def load():
    d = core.kv_get(KEY, empty())
    if not isinstance(d, dict):
        d = empty()
    for k, v in empty().items():
        d.setdefault(k, v if not isinstance(v, list) else [])
    d.setdefault('_seq', {'posts': 0})
    return d


def save(d):
    core.kv_set(KEY, d)


PING_SECRET = '1FDa6qmTlLj5OreqR8GZ_goV0tK4AOubhUVe9aNhrEI'


def env(name):
    return os.getenv(name, '').strip()


def real_token(value):
    return bool(re.fullmatch(r'[A-Za-z0-9_-]{8,}', value or ''))


def ping_secret():
    raw = env('GUMROAD_PING_SECRET')
    return raw if real_token(raw) else PING_SECRET


def seller_expected():
    raw = env('GUMROAD_SELLER_ID')
    return raw if real_token(raw) else ''


def enabled(name):
    return env(name).lower() in ('1', 'true', 'yes')


def digest(code):
    return hashlib.sha256(str(code).encode()).hexdigest()


def https_url(value):
    u = urlsplit(str(value).strip())
    if u.scheme != 'https' or not u.hostname or u.username or u.password:
        raise ValueError('Enlace HTTPS válido requerido')
    return u.geturl()


def price_host_ok(value):
    host = (urlsplit(https_url(value)).hostname or '').lower()
    if re.fullmatch(r'\d+\.\d+\.\d+\.\d+', host):
        raise ValueError('Esa dirección no se consulta')
    if not any(host == h or host.endswith('.' + h) for h in PRICE_HOSTS):
        raise ValueError('Solo Amazon o Alibaba')
    return https_url(value)


def cents_to_usd(raw):
    text = str(raw).strip().replace(',', '')
    if not re.fullmatch(r'\d+(\.\d+)?', text):
        raise ValueError('Precio de Gumroad inválido')
    number = float(text)
    amount = round(number / 100, 2) if '.' not in text else round(number, 2)
    if not 0 < amount <= 100000:
        raise ValueError('Precio fuera de rango')
    return amount


def sale_from_payload(data):
    if not isinstance(data, dict):
        raise ValueError('Aviso inválido')
    sale_id = str(data.get('sale_id') or '').strip()[:80]
    if not re.fullmatch(r'[A-Za-z0-9_-]{4,80}', sale_id):
        raise ValueError('sale_id inválido')
    seller = str(data.get('seller_id') or '').strip()
    expected = seller_expected()
    if expected and not secrets.compare_digest(seller, expected):
        raise ValueError('Vendedor no coincide')
    email = jarvis_aincrad.valid_email(data.get('email'))
    product = ' '.join(str(data.get('product_name') or 'Gumroad').split())[:120]
    test = str(data.get('test') or '').lower() in ('true', '1', 'yes')
    amount = 0 if test else cents_to_usd(data.get('price'))
    return {'sale_id': sale_id, 'email': email, 'product': product, 'amount': amount, 'test': test}


def extract_price(html):
    patterns = (
        r'property="product:price:amount"\s+content="([0-9]+(?:\.[0-9]{1,2})?)"',
        r'"price"\s*:\s*"([0-9]+(?:\.[0-9]{1,2})?)"',
        r'"price"\s*:\s*([0-9]+(?:\.[0-9]{1,2})?)',
    )
    for pattern in patterns:
        found = re.search(pattern, html or '', re.I)
        if found:
            value = round(float(found.group(1)), 2)
            if 0 < value < 1000000:
                return value
    return None


def kit_pdf():
    import io
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    styles = getSampleStyleSheet()
    pages = (
        ('1. Ficha del proyecto',
         'Área:<br/>Qué se cambia:<br/>Qué no se toca:<br/>Fecha deseada:<br/>Presupuesto máximo que tú decides:'),
        ('2. Registro de fotos',
         'Foto 1, pared o zona, fecha:<br/>Foto 2:<br/>Foto 3:<br/>Foto 4:<br/>Las medidas que escribas aquí siguen sin verificar hasta que alguien las confirme en el sitio.'),
        ('3. Solicitud de cotización',
         'Mismo alcance para cada contratista. Pide precio, plazo y qué queda fuera. No incluye inspección ni planos.'),
        ('4. Comparación',
         'Propuesta A — precio — incluye — no incluye — plazo<br/>Propuesta B — precio — incluye — no incluye — plazo<br/>El precio más bajo no gana si le falta una parte.'),
        ('5. Cambios',
         'Fecha, qué se pidió, quién lo pidió, y si cambia el precio. Un cambio sin nota se vuelve una discusión.'),
        ('6. Cierre',
         'Pendientes:<br/>Fotos finales:<br/>Garantías:<br/>Visto bueno tuyo:<br/>Sin esa línea, el trabajo no está cerrado.'),
        ('7. Qué no es este kit',
         'No inspecciona, no dibuja planos, no calcula materiales y no certifica código. Organiza lo que tú ya sabes.'),
    )
    buf = io.BytesIO()
    story = [Paragraph('AINCRAD', styles['Title']),
             Paragraph('Organiza tu remodelación', styles['Heading2']),
             Paragraph('Siete hojas para definir el alcance antes de pedir precios.', styles['Normal']),
             PageBreak()]
    for title, body in pages:
        story += [Paragraph(escape(title), styles['Heading2']), Spacer(1, 12),
                  Paragraph(body, styles['Normal']), PageBreak()]
    SimpleDocTemplate(buf, pagesize=letter).build(story)
    return buf.getvalue()


def kit_markdown():
    return '\n'.join([
        '# Plantillas AINCRAD',
        '',
        '## Ficha',
        '- Área:',
        '- Se cambia:',
        '- No se toca:',
        '',
        '## Fotos',
        '- [ ] Foto 1, fecha',
        '- [ ] Foto 2, fecha',
        '- [ ] Foto 3, fecha',
        '- [ ] Foto 4, fecha',
        '',
        '## Comparación',
        '| | A | B |',
        '| --- | --- | --- |',
        '| Precio | | |',
        '| Incluye | | |',
        '| Fuera | | |',
        '| Plazo | | |',
        '',
        '## Cambio',
        '- Fecha:',
        '- Pedido:',
        '- Precio nuevo:',
        '',
        '## Cierre',
        '- [ ] Pendientes',
        '- [ ] Fotos finales',
        '- [ ] Visto bueno',
        '',
    ])


def book_sale(payload):
    sale = sale_from_payload(payload)
    with core._data_lock:
        d = load()
        if any(x['sale_id'] == sale['sale_id'] for x in d['sales']):
            return {**sale, 'duplicate': True}
        d['sales'].append({k: sale[k] for k in ('sale_id', 'email', 'product', 'amount', 'test')})
        d['sales'] = d['sales'][-500:]
        save(d)
    if sale['test']:
        return sale
    entry = core.add_income(sale['amount'], f"Gumroad {sale['product']} {sale['sale_id']}")
    sale['income_id'] = entry['id']
    if sale['email']:
        try:
            jarvis_aincrad.reply(f"alta {sale['email']}", '/secuencia')
        except Exception:
            pass
    return sale


def price_reply(arg):
    action, _, rest = (arg or '').strip().partition(' ')
    with core._data_lock:
        d = load()
        if not action:
            if not d['prices']:
                return 'Sin precios vigilados.\n/precio alta NOMBRE https://www.amazon.com/...'
            return '\n'.join(f"{p['name']}: {p.get('price', 'sin precio')} · {p['url']}" for p in d['prices']) + '\n' + HELP
        if action == 'alta':
            name, _, url = rest.partition(' ')
            if not url:
                raise ValueError('/precio alta NOMBRE URL')
            url = price_host_ok(url)
            label = name.strip()[:40]
            if not label:
                raise ValueError('Falta el nombre')
            if any(p['name'].lower() == label.lower() for p in d['prices']):
                raise ValueError('Ese nombre ya está')
            if len(d['prices']) >= 8:
                raise ValueError('Máximo 8 precios')
            d['prices'].append({'name': label, 'url': url, 'price': None})
            save(d)
            return f'Vigilo {label}.'
        if action == 'quitar':
            before = len(d['prices'])
            d['prices'] = [p for p in d['prices'] if p['name'].lower() != rest.strip().lower()]
            if len(d['prices']) == before:
                raise ValueError('No está')
            save(d)
            return 'Quitado.'
    raise ValueError(HELP)


def configured(value):
    text = value or ''
    return len(text) >= 20 and ' ' not in text


def network_flags():
    return {
        'x': configured(env('X_USER_ACCESS_TOKEN')) and enabled('X_POST_ENABLED'),
        'pinterest': configured(env('PINTEREST_ACCESS_TOKEN')) and bool(re.fullmatch(r'\S{4,}', env('PINTEREST_BOARD_ID'))) and enabled('PINTEREST_POST_ENABLED'),
        'tiktok': configured(env('TIKTOK_ACCESS_TOKEN')) and enabled('TIKTOK_POST_ENABLED'),
        'gumroad': True,
    }


def stage_post(platform, text, media=''):
    if platform not in PLATFORMS:
        raise ValueError('Plataforma: x, pinterest o tiktok')
    text = ' '.join(str(text).split())
    limit = 280 if platform == 'x' else 500
    if not text or len(text) > limit:
        raise ValueError(f'Texto de 1 a {limit} caracteres')
    if platform != 'x':
        media = https_url(media)
    flags = network_flags()
    if not flags[platform]:
        raise ValueError(f'{platform} no está activo. Falta el token o la variable *_POST_ENABLED=true')
    with core._data_lock:
        d = load()
        d['_seq']['posts'] = int(d['_seq'].get('posts') or 0) + 1
        code = str(secrets.randbelow(1000000)).zfill(6)
        post = {'id': d['_seq']['posts'], 'platform': platform, 'text': text, 'media': media,
                'status': 'preview', 'approval_hash': digest(code),
                'approval_expires': (core._now() + dt.timedelta(minutes=10)).isoformat(),
                'approval_fails': 0}
        d['posts'].append(post)
        d['posts'] = d['posts'][-100:]
        save(d)
    return post, code


async def publish_post(post):
    import httpx
    timeout = httpx.Timeout(30)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if post['platform'] == 'x':
            response = await client.post('https://api.x.com/2/tweets',
                                         headers={'Authorization': 'Bearer ' + env('X_USER_ACCESS_TOKEN')},
                                         json={'text': post['text']})
        elif post['platform'] == 'pinterest':
            response = await client.post('https://api.pinterest.com/v5/pins',
                                         headers={'Authorization': 'Bearer ' + env('PINTEREST_ACCESS_TOKEN')},
                                         json={'board_id': env('PINTEREST_BOARD_ID'), 'description': post['text'],
                                               'link': jarvis_aincrad.hub_url(),
                                               'media_source': {'source_type': 'image_url', 'url': post['media']}})
        else:
            response = await client.post('https://open.tiktokapis.com/v2/post/publish/video/init/',
                                         headers={'Authorization': 'Bearer ' + env('TIKTOK_ACCESS_TOKEN')},
                                         json={'post_info': {'title': post['text'][:150], 'privacy_level': 'SELF_ONLY'},
                                               'source_info': {'source': 'PULL_FROM_URL', 'video_url': post['media']}})
    if response.status_code >= 400:
        raise ValueError(f'{post["platform"]} respondió {response.status_code}')
    return response.status_code


async def confirm_command(chat_id, arg):
    if str(chat_id) != str(core.TG_OWNER):
        return
    parts = (arg or '').split()
    if len(parts) != 2 or not parts[0].isdigit():
        await core._tg_safe_send(chat_id, '/confirmarredes ID CODIGO')
        return
    snapshot = None
    try:
        with core._data_lock:
            d = load()
            post = next((p for p in d['posts'] if p['id'] == int(parts[0])), None)
            if not post or post['status'] != 'preview':
                raise ValueError('No hay una aprobación pendiente')
            if core._now() > dt.datetime.fromisoformat(post['approval_expires']):
                post['status'] = 'expired'
                save(d)
                raise ValueError('El código venció')
            if not secrets.compare_digest(digest(parts[1]), post.get('approval_hash', '')):
                post['approval_fails'] = int(post.get('approval_fails') or 0) + 1
                if post['approval_fails'] >= 5:
                    post['status'] = 'cancelled'
                save(d)
                raise ValueError('Código incorrecto')
            post['status'] = 'publishing'
            post.pop('approval_hash', None)
            save(d)
            snapshot = dict(post)
        await publish_post(snapshot)
    except ValueError as e:
        await core._tg_safe_send(chat_id, str(e))
        return
    except Exception as e:
        if snapshot:
            with core._data_lock:
                d = load()
                post = next((p for p in d['posts'] if p['id'] == snapshot['id']), None)
                if post and post.get('status') == 'publishing':
                    post['status'] = 'failed'
                    save(d)
        await core._tg_safe_send(chat_id, f'No se confirmó la publicación ({type(e).__name__}). Revisa la red antes de repetir.')
        return
    with core._data_lock:
        d = load()
        post = next((p for p in d['posts'] if p['id'] == snapshot['id']), None)
        if post:
            post['status'] = 'published'
            save(d)
    await core._tg_safe_send(chat_id, f"Publicado en {snapshot['platform']} #{snapshot['id']}.")


def reply(arg, cmd):
    if cmd == '/precio':
        return price_reply(arg)
    if cmd != '/redes':
        raise ValueError(HELP)
    text = (arg or '').strip()
    if not text:
        flags = network_flags()
        return 'X: {x}\nPinterest: {pinterest}\nTikTok: {tiktok}\nGumroad: {gumroad}\n'.format(**flags) + HELP
    platform, _, rest = text.partition(' ')
    platform = platform.lower()
    if platform == 'x':
        post, code = stage_post('x', rest)
    else:
        media, _, caption = rest.partition('|')
        post, code = stage_post(platform, caption, media.strip())
    where = post['media'] or '(solo texto)'
    privacy = '\nTikTok se publica como privado en la cuenta.\n' if post['platform'] == 'tiktok' else '\n'
    return (f"Publicar #{post['id']} en {post['platform']}\n{post['text']}\nArchivo: {where}{privacy}"
            f"/confirmarredes {post['id']} {code}")


async def check_prices():
    import httpx
    with core._data_lock:
        rows = list(load()['prices'])
    changes = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(15), follow_redirects=True) as client:
        for row in rows:
            try:
                response = await client.get(row['url'], headers={'User-Agent': 'JarvisPrice/1.0'})
                found = extract_price(response.text[:200000]) if response.status_code < 400 else None
            except Exception:
                found = None
            if found is None or found == row.get('price'):
                continue
            changes.append((row['name'], row.get('price'), found, row['url']))
            with core._data_lock:
                d = load()
                current = next((p for p in d['prices'] if p['url'] == row['url']), None)
                if current:
                    current['price'] = found
                    save(d)
    if changes and core.TG_OWNER:
        lines = ['Precios que cambiaron:']
        for name, old, new, url in changes:
            lines.append(f'{name}: {old} → {new} · {url}')
        await core._tg_send(core.TG_OWNER, '\n'.join(lines))


def install(j):
    global core
    core = j
    from fastapi.responses import Response

    @j.app.post('/public/gumroad-sale')
    async def gumroad_sale(request: j.Request):
        secret = ping_secret()
        given = request.query_params.get('token', '')
        if not secret or not secrets.compare_digest(given, secret):
            raise j.HTTPException(404, 'No está')
        raw = await request.body()
        if len(raw) > 20000:
            raise j.HTTPException(413, 'Grande')
        ctype = request.headers.get('content-type', '')
        if 'application/json' in ctype:
            import json
            try:
                data = json.loads(raw)
            except ValueError:
                raise j.HTTPException(400, 'JSON inválido')
        else:
            data = {k: v[-1] for k, v in parse_qs(raw.decode('utf-8', 'replace'), keep_blank_values=True).items()}
        try:
            sale = book_sale(data)
        except ValueError as e:
            raise j.HTTPException(400, str(e))
        if not sale.get('duplicate') and not sale.get('test') and j.TG_OWNER:
            note = 'El correo entra en la secuencia.' if j.EMAIL_ON else 'El correo quedó guardado. No sale hasta que Resend tenga una clave real.'
            await j._tg_send(j.TG_OWNER, f"Venta Gumroad ${sale['amount']:.2f} · {sale['product']} · {sale['email'] or 'sin email'}. {note}")
        return {'ok': True, 'duplicate': bool(sale.get('duplicate')), 'test': bool(sale.get('test'))}

    @j.app.get('/kit/archivo.pdf')
    async def kit_pdf_route():
        data = kit_pdf()
        return Response(content=data, media_type='application/pdf',
                        headers={'Content-Disposition': 'inline; filename="aincrad-kit.pdf"'})

    @j.app.get('/kit/plantillas.md')
    async def kit_md_route():
        return Response(content=kit_markdown(), media_type='text/markdown; charset=utf-8')

    old_tick = j._tick_v38

    async def tick(now, can_send):
        await old_tick(now, can_send)
        if not can_send or now.hour < 9:
            return
        day = now.date().isoformat()
        with j._data_lock:
            d = load()
            if d.get('price_day') == day:
                return
            d['price_day'] = day
            save(d)
        try:
            await check_prices()
        except Exception as e:
            j._sched_state['last_error'] = 'precios: ' + type(e).__name__

    j._tick_v38 = tick
    old = j._extensions.command

    async def command(chat_id, cmd, arg):
        if cmd not in ('/precio', '/redes'):
            return await old(chat_id, cmd, arg)
        if str(chat_id) != str(j.TG_OWNER):
            return
        try:
            text = reply(arg, cmd)
        except ValueError as e:
            text = str(e)
        await j._tg_safe_send(chat_id, text)

    j._extensions.command = command
    j._extensions.COMMANDS.update({'/precio', '/redes', '/confirmarredes'})
    j.HELP_TEXT += '\n' + HELP
    j._evolve = __import__(__name__)
