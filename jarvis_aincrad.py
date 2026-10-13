"""AINCRAD: landing, secuencia, ventas y afiliados. El hub sigue en /hub."""
import datetime as dt
import hashlib
import hmac
import os
import re
import secrets
from base64 import b64encode
from urllib.parse import parse_qs
from xml.sax.saxutils import escape

import jarvis_business
import jarvis_funnel

KEY = 'jarvis:aincrad'
HELP = ('/aincrad · /secuencia · /secuencia alta EMAIL · /afiliado · /afiliado alta NOMBRE · '
        '/ventas · /monetizar · /monetizar medium N · /monetizar quora N · '
        '/llamar +NUMERO | MENSAJE · /confirmarllamada ID CODIGO')
PHONE_RE = re.compile(r'^\+[1-9]\d{7,14}$')
OFFSETS = (0, 1, 2, 4, 7)
COMMISSION = (('Gumroad', 30), ('Amazon', 25), ('Otros productos', 40))
EMAIL_RE = re.compile(r'[^@\s<>,;]+@[^@\s<>,;]+\.[A-Za-z]{2,}')

MEDIUM = (
    ('Cómo definir el alcance antes de pedir cotizaciones',
     'Escribe qué habitación, qué se queda y qué se va. Sin eso, cada contratista cotiza un trabajo distinto. Una página alcanza.'),
    ('La ficha de fotos que evita malentendidos',
     'Cuatro fotos por pared, con la fecha. Cuando el trabajo cambia, las fotos viejas dicen qué había antes.'),
    ('Comparar dos propuestas sin perderte',
     'Pon el mismo alcance al lado. Si una incluye pintura y la otra no, no son el mismo precio.'),
    ('Qué preguntar el primer día de obra',
     'Horario, quién entra, qué se protege y qué queda fuera. Escríbelo antes de que empiece el ruido.'),
    ('Cambios de obra: anótalos el mismo día',
     'Un cambio sin nota se vuelve una discusión. Fecha, qué se pidió y quién lo pidió.'),
    ('Cierre de proyecto en una hoja',
     'Pendientes, llaves, garantías y fotos finales. Si no está escrito, no está cerrado.'),
    ('Presupuesto de remodelación para una familia',
     'Separa materiales, mano de obra y lo que todavía no se sabe. Lo desconocido también se escribe.'),
    ('Cómo hablar con un contratista en Puerto Rico',
     'Español claro, alcance corto y fecha. La cortesía no reemplaza la lista.'),
    ('Errores al guardar cotizaciones en el teléfono',
     'Un chat no es un archivo. Pasa el precio, el alcance y la fecha a una sola ficha.'),
    ('Qué no incluye un kit de organización',
     'No inspecciona, no dibuja planos y no calcula materiales. Organiza lo que tú ya sabes para poder pedirlo bien.'),
)

QUORA = (
    ('¿Cómo organizo una remodelación pequeña?',
     'Define una sola área, saca fotos y escribe qué entra y qué queda fuera. Después compara propuestas sobre ese mismo texto.'),
    ('¿Qué llevar cuando pido una cotización?',
     'Fotos, medidas que tú tomaste y una lista de lo que no quieres que toquen. Las medidas siguen sin verificar hasta que alguien las confirme en el sitio.'),
    ('¿Por qué dos precios de obra salen tan distintos?',
     'Casi siempre el alcance no es el mismo. Pon los dos textos juntos y marca lo que uno incluye y el otro no.'),
    ('¿Cuándo doy por cerrada una remodelación?',
     'Cuando los pendientes están escritos, las fotos finales guardadas y tú diste el visto bueno. Un mensaje suelto no cierra el trabajo.'),
    ('¿Sirve un PDF para coordinar una obra?',
     'Sirve si cabe en pocas páginas y lo vuelves a usar. No reemplaza al contratista ni al inspector.'),
)


def empty():
    return {'subscribers': [], 'affiliates': [], 'sent_day': '', 'sent_count': 0, 'replies': {}}


def load():
    d = core.kv_get(KEY, empty())
    if not isinstance(d, dict):
        d = empty()
    for k, v in empty().items():
        d.setdefault(k, v)
    return d


def save(d):
    core.kv_set(KEY, d)


def call_twiml(text):
    return f'<Response><Say language="es-MX">{escape(text)}</Say></Response>'


def parse_call(arg):
    phone, _, text = str(arg or '').partition('|')
    phone = phone.strip().replace(' ', '')
    text = ' '.join(text.split())[:280] or 'Hola. Te llama AINCRAD.'
    if not PHONE_RE.fullmatch(phone):
        raise ValueError('Usa /llamar +1787XXXXXXX | mensaje')
    return phone, text


def stage_call(phone, text):
    if not core.SMS_ON:
        raise ValueError('Falta una clave real de Twilio. La llamada está cableada; falta la clave.')
    code = f'{secrets.randbelow(1000000):06d}'
    with core._data_lock:
        d = load()
        calls = d.setdefault('calls', [])
        if not isinstance(calls, list):
            calls = []
        call = {'id': int(d.get('call_seq') or 0) + 1, 'to': phone, 'text': text, 'status': 'preview',
                'hash': hashlib.sha256(code.encode()).hexdigest(),
                'expires': (core._now() + dt.timedelta(minutes=10)).isoformat()}
        d['call_seq'] = call['id']
        calls.append(call)
        d['calls'] = calls[-30:]
        save(d)
    return call, code


async def dial(call):
    import httpx
    origin = str(core.TW_FROM).removeprefix('whatsapp:')
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f'https://api.twilio.com/2010-04-01/Accounts/{core.TW_SID}/Calls.json',
            auth=(core.TW_SID, core.TW_TOKEN),
            data={'From': origin, 'To': call['to'], 'Twiml': call_twiml(call['text'])})
    if response.status_code >= 400:
        raise ValueError('Twilio no marcó la llamada')
    try:
        return str(response.json().get('sid') or '')
    except ValueError:
        return ''


def valid_email(value):
    mail = str(value or '').strip()
    return mail if len(mail) <= 120 and EMAIL_RE.fullmatch(mail) else ''


def hub_url():
    host = os.getenv('PUBLIC_HOST', '').strip()
    return f'https://{host}/hub' if host else '/hub'


PRODUCT_URL = 'https://yullian.gumroad.com/l/ketec'


def kit_html():
    offer = jarvis_business.OFFERS['gumroad']
    name = escape(offer['name'])
    scope = escape(offer['scope'])
    draft = escape(offer['draft'])
    price = int(offer['price_proposed_usd'])
    return f'''<!doctype html>
<html lang="es">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name}</title>
<style>
  body {{ margin:0; background:#0c0c0c; color:#f4f1ea; font:18px/1.45 Georgia, serif; }}
  main {{ max-width:640px; margin:0 auto; padding:48px 20px 80px; }}
  .mark {{ letter-spacing:.18em; color:#d6b25e; font-size:13px; }}
  h1 {{ font-size:36px; line-height:1.15; margin:12px 0; }}
  .price {{ font-size:28px; margin:0 0 20px; }}
  .card {{ border:1px solid #3a3428; padding:18px; margin:0 0 18px; }}
  a.buy {{ display:block; text-align:center; background:#d6b25e; color:#1a1408; text-decoration:none;
           padding:16px; font-weight:700; letter-spacing:.04em; }}
  a.wa {{ position:fixed; right:16px; bottom:16px; background:#25D366; color:#06210f;
         text-decoration:none; font-weight:700; padding:14px 18px; border-radius:999px; }}
</style>
<main>
  <div class="mark">AINCRAD</div>
  <h1>{name}</h1>
  <p class="price">${price} USD</p>
  <div class="card">{draft}</div>
  <div class="card">{scope}</div>
  <a class="buy" href="{PRODUCT_URL}">Comprar el kit</a>
  <p style="height:12px"></p>
  <a class="buy" href="/kit/archivo.pdf" style="background:transparent;color:#d6b25e;border:1px solid #d6b25e">Ver el contenido</a>
</main>
<a class="wa" href="/hub/go/whatsapp">WhatsApp</a>
'''


def email_for(step, hub):
    n = int(step)
    sub = (
        'Tu kit para organizar la remodelación',
        'Día 1: escribe el alcance en una página',
        'Día 2: las fotos que sí sirven',
        'Día 4: compara las propuestas',
        'Día 7: cierra lo que quedó pendiente',
    )[n]
    body = (
        'Aquí está el punto de partida. Abre el hub y guarda el kit. No incluye inspección, planos ni cálculo de materiales.',
        'Hoy escribe una sola área: qué se cambia y qué no se toca. Con eso puedes pedir una cotización comparable.',
        'Toma cuatro fotos de la zona, con fecha. Cuando alguien te mande un precio, las fotos dicen de qué hablan.',
        'Si tienes dos propuestas, ponlas juntas. El precio más bajo no cuenta si le falta una parte del trabajo.',
        'Revisa pendientes, fotos finales y lo que quedó fuera. Si quieres el siguiente paso, está en el mismo enlace.',
    )[n]
    return sub, body + '\n\nCompra: ' + PRODUCT_URL + '\n' + hub + '\n\nAINCRAD'


def pending_step(sub, today):
    start = dt.date.fromisoformat(str(sub['started'])[:10])
    step = int(sub.get('step') or 0)
    if step >= len(OFFSETS):
        return None
    if sub.get('tried') == today.isoformat():
        return None
    if (today - start).days >= OFFSETS[step]:
        return step
    return None


def sales_reply(text, hub=None):
    hub = hub or hub_url()
    q = str(text or '').lower()
    offer = jarvis_business.OFFERS['gumroad']
    price = int(offer['price_proposed_usd'])
    if any(w in q for w in ('precio', 'cuesta', 'costo', 'cuánto', 'cuanto')):
        return f'El kit está en ${price} USD. Compra: {PRODUCT_URL}\n{hub}'
    if any(w in q for w in ('kit', 'compra', 'comprar', 'gumroad', 'link', 'enlace')):
        return f'{offer["name"]}. Compra: {PRODUCT_URL}\n{hub}'
    return ('Organizo el alcance de una remodelación en un kit corto, en español. '
            f'No incluye inspección ni planos. Compra: {PRODUCT_URL}\n{hub}')


def monetizar(kind, number=None):
    kind = (kind or '').strip().lower()
    if kind in ('', 'todo'):
        return ('Textos listos.\n'
                '/monetizar tiktok\n/monetizar reddit\n/monetizar medium 1-10\n/monetizar quora 1-5')
    if kind == 'tiktok':
        return ('TikTok Creator Fund\n'
                'Cuenta de creador, 18+, región donde el fondo esté abierto, y videos originales de AINCRAD: '
                'cómo organizar una remodelación en español, sin metraje de otros.\n'
                'Bio: el hub /hub.\n'
                'Cuando la cuenta cumpla las reglas de TikTok, la solicitud se manda desde la app de TikTok.')
    if kind == 'reddit':
        return ('r/yullian\n'
                'Descripción: Organización de remodelaciones y notas de obra, en español. Sin spam.\n'
                'Primera publicación: el kit de AINCRAD y el enlace del hub. '
                'El subreddit se crea en Reddit con tu usuario; este texto es el que pegas.')
    if kind == 'medium':
        idx = int(number or 1)
        if not 1 <= idx <= len(MEDIUM):
            raise ValueError('medium va del 1 al 10')
        title, body = MEDIUM[idx - 1]
        return f'Medium {idx}/10\n{title}\n\n{body}\n\nEnlace: {hub_url()}'
    if kind == 'quora':
        idx = int(number or 1)
        if not 1 <= idx <= len(QUORA):
            raise ValueError('quora va del 1 al 5')
        question, answer = QUORA[idx - 1]
        return f'Quora {idx}/5\n{question}\n\n{answer}\n\nEnlace: {hub_url()}'
    raise ValueError(HELP)


def status_text():
    pixel = bool(jarvis_funnel.tracking()['pixel'])
    ga = bool(jarvis_funnel.tracking()['ga4'])
    mail = 'envía solo' if core.EMAIL_ON else 'textos listos; falta Resend en Render'
    sales = 'WhatsApp activo' if sales_enabled() else 'falta Twilio WhatsApp (TWILIO_FROM=whatsapp:+...)'
    d = load()
    return '\n'.join([
        'AINCRAD',
        'Landing: /kit',
        'Hub (reemplaza Linktree): /hub',
        f'Email, 5 mensajes en los días 0, 1, 2, 4 y 7: {mail}. Suscritos: {len(d["subscribers"])}',
        f'Pixel: {"en cada clic" if pixel else "falta META_PIXEL_ID"}',
        f'GA4: {"en cada clic" if ga else "falta GA4_MEASUREMENT_ID"}',
        'Video: intro, outro, marca AINCRAD y texto de la escena en el cuadro',
        f'Ventas 24/7: {sales}',
        'Llamada: /llamar +NUMERO | MENSAJE y después /confirmarllamada',
        'Afiliados: Gumroad 30% · Amazon 25% · otros 40%. /afiliado alta NOMBRE',
        'TikTok, Reddit, Medium y Quora: /monetizar',
        HELP,
    ])


def sales_enabled():
    flag = os.getenv('SALES_BOT_ENABLED', 'true').strip().lower()
    return flag in ('1', 'true', 'yes') and core.SMS_ON and str(core.TW_FROM).startswith('whatsapp:')


def twilio_signature(url, params, token):
    base = url + ''.join(k + params[k] for k in sorted(params))
    digest = hmac.new(token.encode(), base.encode(), hashlib.sha1).digest()
    return b64encode(digest).decode()


def affiliate_code(name):
    return hashlib.sha256(name.strip().lower().encode()).hexdigest()[:8]


def reply(arg, cmd):
    if cmd == '/llamar':
        phone, text = parse_call(arg)
        call, code = stage_call(phone, text)
        return f"Llamada #{call['id']} a {phone}. Confirma en 10 minutos: /confirmarllamada {call['id']} {code}"
    if cmd == '/aincrad':
        return status_text()
    if cmd == '/ventas':
        return sales_reply('precio') + '\n\n' + sales_reply('kit') + '\n\n' + status_text().split('Ventas')[1]
    if cmd == '/monetizar':
        parts = (arg or '').split()
        kind = parts[0] if parts else ''
        number = parts[1] if len(parts) > 1 else None
        return monetizar(kind, number)
    if cmd == '/secuencia':
        parts = (arg or '').split()
        if not parts:
            lines = ['Secuencia de 5 correos.']
            for i, day in enumerate(OFFSETS):
                subject, _ = email_for(i, hub_url())
                lines.append(f'{i + 1}. día {day}: {subject}')
            lines.append(f"Suscritos: {len(load()['subscribers'])}")
            lines.append('/secuencia alta EMAIL')
            return '\n'.join(lines)
        if parts[0] != 'alta' or len(parts) != 2:
            raise ValueError('/secuencia alta EMAIL')
        mail = valid_email(parts[1])
        if not mail:
            raise ValueError('Email inválido')
        with core._data_lock:
            d = load()
            if any(x['email'] == mail for x in d['subscribers']):
                return 'Ese email ya está en la secuencia.'
            if len(d['subscribers']) >= 500:
                raise ValueError('Tope de 500 suscritos')
            d['subscribers'].append({'email': mail, 'started': core._today().isoformat(), 'step': 0, 'tried': ''})
            save(d)
        return f'{mail} entra hoy. El correo 1 sale en el siguiente ciclo (9:00) si Resend está activo.'
    if cmd == '/afiliado':
        parts = (arg or '').split(maxsplit=1)
        d = load()
        if not parts:
            lines = ['Programa: ' + ' · '.join(f'{n} {p}%' for n, p in COMMISSION)]
            if not d['affiliates']:
                lines.append('Nadie todavía. /afiliado alta NOMBRE')
            for row in d['affiliates']:
                lines.append(f"{row['name']} · ref={row['code']} · {hub_url()}?ref={row['code']}")
            return '\n'.join(lines)
        if parts[0] != 'alta' or len(parts) != 2 or not parts[1].strip():
            raise ValueError('/afiliado alta NOMBRE')
        name = parts[1].strip()[:60]
        code = affiliate_code(name)
        with core._data_lock:
            d = load()
            if any(x['code'] == code for x in d['affiliates']):
                return f'Ya existe. ref={code}'
            d['affiliates'].append({'name': name, 'code': code})
            save(d)
        return f'{name} queda con ref={code}. Enlace: {hub_url()}?ref={code}'
    raise ValueError(HELP)


async def send_due(now):
    if not core.EMAIL_ON or now.hour < 9:
        return
    today = now.date()
    hub = hub_url()
    with core._data_lock:
        d = load()
        if d.get('sent_day') != today.isoformat():
            d['sent_day'] = today.isoformat()
            d['sent_count'] = 0
        due = []
        for sub in d['subscribers']:
            step = pending_step(sub, today)
            if step is None:
                continue
            if int(d['sent_count']) >= int(core.OUTBOX_MAX_DAY):
                break
            sub['tried'] = today.isoformat()
            d['sent_count'] = int(d['sent_count']) + 1
            due.append((sub['email'], step))
        save(d)
    for mail, step in due:
        subject, body = email_for(step, hub)
        try:
            await core._send_email(mail, subject, body, f'seq-{hashlib.sha256(mail.encode()).hexdigest()[:12]}-{step}')
        except Exception as e:
            await core._tg_send(core.TG_OWNER, f'No salió el correo {step + 1}/5 a {mail}. {type(e).__name__}. Se reintenta mañana.')
            continue
        with core._data_lock:
            d = load()
            row = next((x for x in d['subscribers'] if x['email'] == mail), None)
            if row and int(row.get('step') or 0) == step:
                row['step'] = step + 1
                save(d)
        await core._tg_send(core.TG_OWNER, f'Secuencia {step + 1}/5 enviada a {mail}')


async def confirm_call(arg):
    parts = (arg or '').split()
    if len(parts) != 2 or not parts[0].isdigit():
        raise ValueError('/confirmarllamada ID CODIGO')
    with core._data_lock:
        d = load()
        call = next((c for c in d.get('calls') or [] if c.get('id') == int(parts[0])), None)
        if not call or call.get('status') != 'preview':
            raise ValueError('No hay una llamada pendiente')
        if core._now() > dt.datetime.fromisoformat(call['expires']):
            call['status'] = 'expired'
            save(d)
            raise ValueError('El código venció')
        if not hmac.compare_digest(hashlib.sha256(parts[1].encode()).hexdigest(), call.get('hash', '')):
            raise ValueError('Código incorrecto')
        call['status'] = 'dialing'
        snapshot = dict(call)
        save(d)
    try:
        sid = await dial(snapshot)
    except Exception:
        with core._data_lock:
            d = load()
            row = next((c for c in d.get('calls') or [] if c.get('id') == snapshot['id']), None)
            if row and row.get('status') == 'dialing':
                row['status'] = 'failed'
                save(d)
        raise
    with core._data_lock:
        d = load()
        row = next((c for c in d.get('calls') or [] if c.get('id') == snapshot['id']), None)
        if row:
            row['status'] = 'placed'
            row['sid'] = sid
            save(d)
    return f"Llamada marcada a {snapshot['to']}."


def install(j):
    global core
    core = j
    from fastapi.responses import HTMLResponse, PlainTextResponse

    @j.app.get('/kit')
    async def kit():
        return HTMLResponse(kit_html())

    @j.app.post('/ventas/whatsapp')
    async def whatsapp(request: j.Request):
        if not sales_enabled():
            raise j.HTTPException(404, 'Ventas apagadas')
        raw = (await request.body()).decode('utf-8', 'replace')
        params = {k: v[-1] for k, v in parse_qs(raw, keep_blank_values=True).items()}
        host = os.getenv('PUBLIC_HOST', '').strip().lower()
        for prefix in ('https://', 'http://'):
            if host.startswith(prefix):
                host = host[len(prefix):]
        host = host.strip('/')
        if not host or '/' in host:
            raise j.HTTPException(400, 'Falta PUBLIC_HOST')
        url = f'https://{host}/ventas/whatsapp'
        given = request.headers.get('x-twilio-signature', '')
        expected = twilio_signature(url, params, j.TW_TOKEN)
        if not hmac.compare_digest(expected, given):
            raise j.HTTPException(403, 'Firma inválida')
        sender = params.get('From', '')
        if not sender.startswith('whatsapp:+'):
            return PlainTextResponse('', status_code=204)
        phone = sender.split(':', 1)[1]
        key = re.sub(r'\D', '', phone)[:15]
        now = j._now()
        with j._data_lock:
            d = load()
            last = d['replies'].get(key)
            if last and (now - dt.datetime.fromisoformat(last)).total_seconds() < 600:
                return PlainTextResponse('', status_code=204)
        body = sales_reply(params.get('Body', ''))
        await j._send_sms(phone, body)
        with j._data_lock:
            d = load()
            if len(d['replies']) > 400:
                d['replies'] = dict(list(d['replies'].items())[-200:])
            d['replies'][key] = now.isoformat(timespec='seconds')
            save(d)
        return PlainTextResponse('', status_code=204)

    old_tick = j._tick_v38

    async def tick(now, can_send):
        await old_tick(now, can_send)
        if not can_send:
            return
        try:
            await send_due(now)
        except Exception as e:
            j._sched_state['last_error'] = 'aincrad: ' + type(e).__name__

    j._tick_v38 = tick
    old = j._extensions.command

    async def command(chat_id, cmd, arg):
        if cmd not in ('/aincrad', '/secuencia', '/afiliado', '/ventas', '/monetizar', '/llamar', '/confirmarllamada'):
            return await old(chat_id, cmd, arg)
        if str(chat_id) != str(j.TG_OWNER):
            return
        if cmd == '/confirmarllamada':
            try:
                text = await confirm_call(arg)
            except ValueError as e:
                text = str(e)
            except Exception as e:
                text = f'No se marcó ({type(e).__name__}).'
            await j._tg_safe_send(chat_id, text)
            return
        try:
            text = reply(arg, cmd)
        except (ValueError, TypeError) as e:
            text = str(e)
        if cmd == '/secuencia' and str(arg or '').startswith('alta') and 'entra hoy' in text:
            try:
                await send_due(j._now())
            except Exception:
                text += '\nEl alta quedó guardada. El envío sigue en el ciclo de las 9:00.'
        await j._tg_safe_send(chat_id, text)

    j._extensions.command = command
    j._extensions.COMMANDS.update({'/aincrad', '/secuencia', '/afiliado', '/ventas', '/monetizar', '/llamar', '/confirmarllamada'})
    j.HELP_TEXT += '\n' + HELP
    j._aincrad = __import__(__name__)
