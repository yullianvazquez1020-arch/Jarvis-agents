"""Local business reports and owner-reviewed drafts. No payment or publication adapters."""
import asyncio
import datetime as dt
import hashlib
import html
import json
import re
from decimal import Decimal, ROUND_HALF_UP

KEY = 'jarvis:business_workflows'
COMMANDS = {'/caja', '/fichaamazon', '/negocio', '/pagina', '/paquete', '/capacidades', '/solicitudes'}
BANK_STALE_DAYS = 3
CASH_WARNING_USD = Decimal('50')


def load():
    d = core.kv_get(KEY, {})
    for k, v in {'businesses': [], 'packages': [], 'requests': [], '_seq': {}}.items():
        d.setdefault(k, v)
    return d


def money(value, *, negative=False):
    if isinstance(value, bool) or value is None:
        raise ValueError('Falta un importe válido del dueño')
    try:
        n = Decimal(str(value))
    except Exception:
        raise ValueError('Importe inválido') from None
    if not n.is_finite() or abs(n) > Decimal('1000000000') or not negative and n < 0:
        raise ValueError('Importe fuera de rango')
    return n.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def cash_flow_report(account=''):
    """Observed bank balance != recorded books != conditional future cash. No storage writes."""
    with core._data_lock:
        today = core._today()
        end = today + dt.timedelta(days=7)
        bank, books, clients = core._kload(), core._bload(), core._cload()
        observed, missing = [], []
        for key, a in bank['accounts'].items():
            balance, date = a.get('balance'), a.get('balance_date')
            if balance is None or not date:
                continue
            try:
                age = (today - dt.date.fromisoformat(date)).days
                amount = money(balance, negative=True)
            except (ValueError, TypeError):
                continue
            observed.append({'account': key, 'name': a.get('name', 'Cuenta importada'),
                             'balance': float(amount), 'date': date, 'stale_days': age,
                             'stale': age > BANK_STALE_DAYS, 'future_date': age < 0,
                             'type': a.get('type', '')})
        selected = [a for a in observed if a['account'] == account] if account else observed
        if len(selected) != 1:
            missing.append('importación con saldo y fecha' if not selected else 'elegir una cuenta: /caja CLAVE')
            chosen = None
        else:
            chosen = selected[0]
            if chosen['stale']:
                missing.append('importación reciente: saldo viejo')
            if chosen['future_date']:
                missing.append('corregir fecha futura del saldo')
            if str(chosen['type']).upper() in ('CREDITCARD', 'CREDITLINE', 'LOAN'):
                missing.append('una cuenta de efectivo; saldo de crédito no es caja')
        pending = [j for j in clients['jobs'] if j.get('status') not in ('quote', 'paid', 'cancelled')
                   and core._job_balance(j) > 0]
        incoming = []
        for j in pending:
            if not j.get('due_date'):
                missing.append('vencimiento del trabajo #' + str(j['id']))
                continue
            try:
                due = dt.date.fromisoformat(j['due_date'])
            except (ValueError, TypeError):
                missing.append('fecha válida del trabajo #' + str(j['id']))
                continue
            if today <= due <= end:
                incoming.append({'id': j['id'], 'date': j['due_date'], 'title': j['title'],
                                 'amount': core._job_balance(j), 'client_id': j.get('client_id')})
        outgoing = []
        for b in core.upcoming(7)['bills']:
            if not today.isoformat() <= b['due'] <= end.isoformat():
                continue
            try:
                amount = money(b.get('amount'))
            except ValueError:
                missing.append('importe de la cuenta #' + str(b['id']))
                continue
            outgoing.append({'id': b['id'], 'date': b['due'], 'name': b['name'], 'amount': float(amount)})
        # Calendar amounts may describe these same jobs/bills. Do not add them twice or infer a linkage.
        events = core.list_events(today.isoformat(), 7, include_done=False)['events']
        unresolved = [e for e in events if e.get('type') in ('payment', 'collection')]
        if unresolved:
            missing.append('conciliar cobros/pagos del calendario con trabajos/cuentas; no se suman dos veces')
        if not incoming and not outgoing:
            missing.append('vencimientos con importes para los próximos 7 días')
        totals = {}
        for kind in ('income', 'expenses'):
            amounts = [money(x['amount']) for x in books[kind]
                       if x.get('currency', 'USD') == 'USD' and x.get('date', '') <= today.isoformat()]
            totals[kind] = float(sum(amounts, Decimal(0)))
        totals['net'] = round(totals['income'] - totals['expenses'], 2)
        totals['note'] = 'Libros registrados en USD; no equivalen al saldo del banco. Otras monedas no se convierten.'
        collections = sum((money(x['amount']) for x in incoming), Decimal(0))
        payments = sum((money(x['amount']) for x in outgoing), Decimal(0))
        projection = None
        if not missing and chosen:
            opening = money(chosen['balance'], negative=True)
            projection = {'opening_observed': float(opening), 'collections': float(collections),
                          'payments': float(payments), 'end_balance': float(opening + collections - payments),
                          'without_collections': float(opening - payments), 'date': end.isoformat(),
                          'conditional': True, 'formula': 'saldo observado + cobros futuros - pagos futuros'}
        return {'observed': observed, 'selected': chosen, 'recorded': totals, 'projection': projection,
                'incoming': incoming, 'outgoing': outgoing, 'missing': sorted(set(missing)),
                'overdue_jobs': [j['id'] for j in pending if (j.get('due_date') or '9999') < today.isoformat()],
                'warning': bool(projection and money(projection['end_balance'], negative=True) <= -CASH_WARNING_USD),
                'note': 'Proyección condicional, no saldo actual ni cobros garantizados. No paga ni registra ingresos.'}


def cash_text(report=None):
    r = report if report is not None else cash_flow_report()
    lines = ['💼 Caja: observado · registrado · proyección']
    for a in r['observed']:
        tag = ' — saldo viejo' if a['stale'] else ' — fecha futura' if a['future_date'] else ''
        lines.append(f"Observado: {a['name']} ${a['balance']:,.2f} al {a['date']}{tag} (clave {a['account']}).")
    b = r['recorded']
    lines.append(f"Registrado USD: ingresos ${b['income']:,.2f}, gastos ${b['expenses']:,.2f}; no es caja.")
    if r['projection']:
        p = r['projection']
        lines.append(f"Proyección a {p['date']}: ${p['opening_observed']:,.2f} + cobros ${p['collections']:,.2f} "
                     f"− pagos ${p['payments']:,.2f} = ${p['end_balance']:,.2f}, si se cobran.")
        lines.append(f"Sin esos cobros: ${p['without_collections']:,.2f}.")
    else:
        lines.append('Sin proyección: falta ' + '; '.join(r['missing']) + '.')
    if r['incoming']:
        lines.append('Cobros próximos: ' + ', '.join(f"#{x['id']} ${x['amount']:,.2f} al {x['date']}" for x in r['incoming'][:10]))
    elif not r['overdue_jobs']:
        lines.append('Nada con vencimiento que cobrar hoy en los trabajos registrados.')
    if r['overdue_jobs']:
        lines.append('Trabajos vencidos: ' + ', '.join('#' + str(i) for i in r['overdue_jobs'][:10]))
    lines.append('Los cobros siguen pendientes hasta registrar el pago. Seguimientos: /cobros · /mensajes; envío solo con /enviar.')
    return '\n'.join(lines)


def prepare_cash_followups():
    """Draft one pending follow-up per recorded job; never send or mark a payment received."""
    with core._data_lock:
        d = core._oload()
        core._expire_drafts(d)
        clients = {c['id']: c for c in core._cload()['clients']}
        end = (core._today() + dt.timedelta(days=7)).isoformat()
        result = []
        for job in core._cload()['jobs']:
            if job.get('status') in ('quote', 'paid', 'cancelled') or core._job_balance(job) <= 0:
                continue
            if not job.get('due_date') or job['due_date'] > end:
                continue
            cl = clients.get(job['client_id'])
            if not cl or any(m.get('job_id') == job['id'] and m['status'] in ('pending', 'sending', 'unknown') for m in d['drafts']):
                continue
            try:
                channel, to = core._pick_channel(cl)
            except ValueError:
                continue
            body = (f"Hola {cl['name']}, le saluda {core.BUSINESS_NAME}. El saldo registrado de "
                    f"${core._job_balance(job):,.2f} del trabajo {job['title']} tiene vencimiento "
                    f"{job['due_date']}. ¿Nos confirma la fecha prevista de pago? Gracias.")
            result.append(core._new_draft(d, cl, channel, to, body, reason='seguimiento de caja', job_id=job['id']))
        if result:
            core._osave(d)
        return [{'id': m['id'], 'job_id': m['job_id'], 'status': m['status']} for m in result]


async def cash_tick(now, can_send):
    if not can_send or not core.BRIEF_HOUR.isdigit() or now.hour != int(core.BRIEF_HOUR):
        return
    if core.NOTICES_ON:
        draft_key = 'jarvis:cash:followups:' + now.date().isoformat()
        if await asyncio.to_thread(core._claim, draft_key, 3 * 86400):
            await asyncio.to_thread(prepare_cash_followups)
    r = await asyncio.to_thread(cash_flow_report)
    if not r['warning']:
        return
    # One per rule and local date, persisted through the same Redis NX/EX claims used by the scheduler.
    key = 'jarvis:cash:warning:' + now.date().isoformat()
    if not await asyncio.to_thread(core._claim, key, 3 * 86400):
        return
    refs = ', '.join(f"#{x['id']}@{x['date']}" for x in r['outgoing'])
    try:
        await core._tg_send(core.TG_OWNER, '⚠️ Caja proyectada negativa por al menos $50.\n' + cash_text(r)
                            + '\nRegla: caja-7d; pagos: ' + refs)
    except Exception:
        # Ambiguous delivery is not retried automatically: preserves at most one attempt per day.
        core.logger.warning('cash alert delivery unconfirmed; daily claim retained')


def amazon_margin(sale_price, unit_cost, shipping_pr, packaging, referral_percent, other_costs=0, source_url=''):
    price, cost, ship, pack, other = [money(v) for v in (sale_price, unit_cost, shipping_pr, packaging, other_costs)]
    pct = money(referral_percent)
    if pct > 100:
        raise ValueError('Comisión debe estar entre 0 y 100%')
    url = core._growth.https_url(source_url, 'amazon.com') if source_url else ''
    fee = (price * pct / 100).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    return {'currency': 'USD', 'published_price': float(price), 'product_cost': float(cost), 'shipping_pr': float(ship),
            'packaging': float(pack), 'other_costs': float(other), 'referral_fee': float(fee),
            'estimated_margin': float(price - cost - ship - pack - other - fee), 'source_url': url,
            'fee_status': 'porcentaje suministrado por el dueño, no comprobado en Seller Central',
            'demand': 'no disponible', 'units_sold': 'no disponible',
            'note': 'Precio publicado no es una venta. No consulta Orders, compra ni publica fichas; falta validar restricciones y tarifas reales.'}


def blocked_request(text):
    import unicodedata
    norm = ''.join(c for c in unicodedata.normalize('NFKD', str(text).casefold()) if not unicodedata.combining(c))
    if re.search(r'\b(?:ocult\w*|escond\w*|evad\w*)\b.{0,100}\b(?:ingres\w*|cobr\w*|venta\w*)\b', norm) or re.search(
            r'\b(?:ingres\w*|cobr\w*)\b.{0,100}\b(?:ocult\w*|escond\w*)\b', norm):
        return 'No oculto ingresos ni cobros. Los libros se conservan; una corrección debe quedar registrada y revisada.'
    if re.search(r'\b(?:pide|solicita|tramita|disputa|entra|maneja)\b.{0,100}\b(?:tarjeta|credito|buro|credit karma)\b', norm):
        return 'No tramito crédito, solicitudes de tarjetas ni disputas, ni accedo a crédito de terceros. El dueño gestiona eso directamente; puedo recordarle una fecha de pago.'
    return None


def reject_sensitive(text):
    if re.search(r'\b(ein|ssn|iban|password|contrase[nñ]a|numero de cuenta|número de cuenta)\b', str(text), re.I) or core._redact_secrets(str(text))[1]:
        raise ValueError('No incluyas EIN, datos bancarios ni credenciales')


def request_enabled():
    import os
    return os.getenv('BUSINESS_REQUESTS_ENABLED', 'false').lower() == 'true'


def business_slug(name):
    return hashlib.sha256(name.casefold().encode()).hexdigest()[:20]


def receive_request(business, name, phone, message, adult=False, website=''):
    if not request_enabled():
        raise ValueError('Recepción de solicitudes apagada; la ficha es solo una vista previa')
    if adult is not True or website:
        raise ValueError('Solicitud inválida: consulta de un adulto requerida')
    name = core._text(name, 'nombre', 100)
    message = core._text(message, 'consulta', 1500)
    reject_sensitive(name); reject_sensitive(message)
    phone = str(phone).strip()
    if not re.fullmatch(r'\+?[0-9]{10,15}', phone):
        raise ValueError('Teléfono internacional inválido')
    with core._data_lock:
        core._check_writable()
        d = load()
        card = next((b for b in d['businesses'] if business_slug(b['name']) == business), None)
        if not card:
            raise ValueError('Negocio no registrado')
        active = [r for r in d['requests'] if r['status'] == 'pending']
        if len(active) >= 100:
            raise ValueError('Capacidad de solicitudes pendiente; revisión del dueño requerida')
        day = core._today().isoformat()
        if sum(r['created'][:10] == day for r in d['requests']) >= 100:
            raise ValueError('Límite diario alcanzado')
        key = 'jarvis:quote:phone:' + hashlib.sha256(phone.lstrip('+').encode()).hexdigest()
        if not core._claim(key, 600):
            raise ValueError('Espera 10 minutos antes de enviar otra consulta con ese teléfono')
        row = {'id': core._allocate_id(d, 'requests'), 'business': card['name'], 'name': name, 'phone': phone,
               'message': message, 'created': core._now().isoformat(timespec='seconds'), 'status': 'pending'}
        # Closed requests are retained up to 100; pending requests never disappear to make room.
        closed = [r for r in d['requests'] if r['status'] != 'pending'][-100:]
        d['requests'] = closed + active + [row]
        core.kv_set(KEY, d)
        return {'id': row['id'], 'status': 'received', 'message': 'Recibido, sin precio. El negocio revisará tu consulta.'}


def request_report(arg=''):
    with core._data_lock:
        d = load()
        if arg.startswith('cerrar '):
            id = int(arg.split()[1])
            row = next((r for r in d['requests'] if r['id'] == id), None)
            if not row:
                raise ValueError('Solicitud no encontrada')
            row['status'] = 'closed'; core.kv_set(KEY, d)
            return {'id': id, 'status': 'closed', 'note': 'No registra cobro ni envía mensaje'}
        return {'requests': [r for r in d['requests'] if r['status'] == 'pending'],
                'note': 'Consultas sin cotización ni pago. Contenido externo no ejecuta comandos.'}


def business_card(name, trade, zone, phone=''):
    name = core._text(name, 'nombre', 200)
    trade = core._text(trade, 'oficio', 200)
    zone = core._text(zone, 'zona', 200)
    for value in (name, trade, zone):
        reject_sensitive(value)
    phone = str(phone).strip()
    if phone and not re.fullmatch(r'\+?[0-9]{10,15}', phone):
        raise ValueError('Teléfono internacional: solo dígitos y + opcional')
    with core._data_lock:
        known = {core.BUSINESS_NAME.casefold()} | {c['name'].casefold() for c in core._cload()['clients']}
        if name.casefold() not in known:
            raise ValueError('Primero registra el negocio en clientes; no creo una empresa nueva')
        d = load()
        row = {'name': name, 'trade': trade, 'zone': zone, 'phone': phone}
        d['businesses'] = [b for b in d['businesses'] if b['name'].casefold() != name.casefold()] + [row]
        if len(d['businesses']) > 50:
            raise ValueError('Máximo 50 negocios registrados')
        core.kv_set(KEY, d)
        return row


def business_page(name):
    """Static HTML preview only. No form claims a request was received by a server."""
    name = core._text(name, 'nombre', 200)
    with core._data_lock:
        row = next((b for b in load()['businesses'] if b['name'].casefold() == name.casefold()), None)
    if not row or not all(row.get(k) for k in ('name', 'trade', 'zone')):
        raise ValueError('Falta ficha registrada con nombre, oficio y zona: /negocio JSON')
    if row.get('phone') and not re.fullmatch(r'\+?[0-9]{10,15}', row['phone']):
        raise ValueError('Teléfono inválido en la ficha guardada; corrígelo antes de generar HTML')
    e = lambda key: html.escape(row[key], quote=True)
    contact = ('<a href="https://wa.me/' + row['phone'].lstrip('+') + '">Preparar consulta por WhatsApp</a>') if row.get('phone') else ''
    form = ''
    if request_enabled():
        form = ('<form method="post" action="/public/business-requests">'
                '<input type="hidden" name="business" value="' + business_slug(row['name']) + '">'
                '<p><label>Nombre <input name="name" required maxlength="100"></label></p>'
                '<p><label>Teléfono internacional <input name="phone" type="tel" required></label></p>'
                '<p><label>Consulta <textarea name="message" required maxlength="1500"></textarea></label></p>'
                '<label><input type="checkbox" name="adult" value="true" required>Soy adulto</label>'
                '<input name="website" tabindex="-1" autocomplete="off" style="display:none">'
                '<p>No incluyas datos bancarios, EIN ni datos de niños. Tu nombre, teléfono y consulta se guardan para que el negocio los revise.</p>'
                '<button>Enviar consulta sin precio</button></form>')
    page = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e('name')}</title>
<style>body{{font:18px system-ui;max-width:850px;margin:3rem auto;padding:1.5rem;background:#eef7fa;color:#103347}}main{{background:white;padding:2rem;border-top:8px solid #12a9c5;border-radius:16px}}a{{display:inline-block;padding:1rem;background:#103347;color:white;border-radius:8px}}</style></head><body><main><h1>{e('name')}</h1><p>{e('trade')}</p><p>Zona: {e('zone')}</p><h2>Solicita una evaluación</h2><p>Consulta sin precio confirmado. La cotización requiere revisión del negocio.</p>{contact}{form}<p>WhatsApp no envía nada automáticamente. No recibimos pagos ni datos bancarios. El formulario, si está habilitado, requiere alojar esta página en el mismo dominio del servicio.</p></main></body></html>'''
    return page


def adult_package(title, price=None):
    if price is None:
        raise ValueError('Falta precio del dueño; no creo ni publico un monto')
    title = core._text(title, 'título', 200)
    with core._data_lock:
        d = load()
        if len(d['packages']) >= 100:
            raise ValueError('Máximo 100 borradores')
        row = {'id': core._allocate_id(d, 'packages'), 'title': title, 'price_usd': float(money(price)),
               'audience': 'adultos: familias o docentes', 'status': 'draft',
               'note': 'Borrador de PDF/licencia para adultos. No se generó el PDF, no cobra ni publica; no solicita datos de niños.'}
        d['packages'].append(row)
        core.kv_set(KEY, d)
        return row


def capabilities():
    return {'local': ['Telegram existente', 'libros', 'importación de archivo bancario', 'Whisper/Piper',
                      'caja condicional', 'ficha HTML sin publicar', 'margen Amazon con costos del dueño'],
            'needs_authorization': ['YouTube Analytics: OAuth del canal propio', 'Amazon Fees: vendedor y permisos'],
            'costs': 'No se activan proveedores ni cuentas. Verificar tarifas de SMS/correo/vendedor/dominio antes de contratar; Analytics no implica por sí solo cuota mensual.',
            'voice': 'STT/TTS locales; una pregunta libre todavía puede usar Claude.',
            'limits': {'order': core.MONEY_MAX_ORDER, 'day': core.MONEY_MAX_DAY},
            'requests_enabled': request_enabled(),
            'note': '/conexiones distingue configuración de conexión comprobada. /pagina no aloja; recepción pública apagada por defecto.'}


async def command(chat_id, cmd, arg):
    try:
        if cmd == '/pagina':
            page = await asyncio.to_thread(business_page, arg)
            filename = 'negocio-' + hashlib.sha256(arg.casefold().encode()).hexdigest()[:12] + '.html'
            core._check_writable()
            await asyncio.to_thread(core._atomic_file, core.DATA_DIR / filename, page)
            await core._tg_send_document(chat_id, filename, page.encode(), 'Vista previa HTML; no publicada.', 'text/html')
            return
        def local():
            if cmd == '/caja':
                return cash_text(cash_flow_report(arg.strip()))
            if cmd == '/capacidades':
                return capabilities()
            if cmd == '/solicitudes':
                return request_report(arg)
            args = json.loads(arg)
            if not isinstance(args, dict):
                raise ValueError('Se requiere un objeto JSON con datos del dueño')
            if cmd == '/fichaamazon':
                return amazon_margin(**args)
            if cmd == '/negocio':
                return business_card(**args)
            if cmd == '/paquete':
                return adult_package(**args)
        value = await asyncio.to_thread(local)
        await core._tg_safe_send(chat_id, value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2))
    except (ValueError, TypeError) as exc:
        await core._tg_safe_send(chat_id, '⚠️ ' + core._redact_secrets(str(exc))[0][:350])


def install(j):
    global core
    core = j
    handlers = {'cash_flow_report': cash_flow_report, 'amazon_margin': amazon_margin,
                'register_business_card': business_card, 'prepare_adult_package': adult_package,
                'local_capabilities': capabilities}
    j.HANDLERS.update(handlers)
    S, N = {'type': 'string'}, {'type': 'number'}
    specs = [
        ('cash_flow_report', 'Read observed bank balance, recorded books and conditional seven-day cash; never counts ledger income as bank cash.', {'account': S}, []),
        ('amazon_margin', 'Estimate margin only from explicit owner costs. Requires shipping to Puerto Rico and packaging; no fees/price invention, Orders, purchases or publication.', {**{k: N for k in ('sale_price', 'unit_cost', 'shipping_pr', 'packaging', 'referral_percent', 'other_costs')}, 'source_url': S}, ['sale_price', 'unit_cost', 'shipping_pr', 'packaging', 'referral_percent']),
        ('register_business_card', 'Record an existing business only with explicit owner name, trade, zone and optional phone. Never invent business, EIN or contact data.', {'name': S, 'trade': S, 'zone': S, 'phone': S}, ['name', 'trade', 'zone']),
        ('prepare_adult_package', 'Record a draft for adults only with explicit owner price. No PDF generated, payment, publishing or children data.', {'title': S, 'price': N}, ['title', 'price']),
        ('local_capabilities', 'Read implemented local workflows and unconnected integrations. No new subscription or activation.', {}, [])]
    for name, desc, props, req in specs:
        j.TOOLS.append(j._t(name, desc, props, req))
    j.READ_ONLY_TOOLS = j.READ_ONLY_TOOLS | {'cash_flow_report', 'amazon_margin', 'local_capabilities'}
    original_brief = j.brief_text
    def brief():
        return original_brief() + '\n\n' + cash_text()
    j.brief_text = brief
    old_tick = j._tick_v38
    async def tick(now, can_send):
        await old_tick(now, can_send)
        try:
            await cash_tick(now, can_send)
        except Exception as exc:
            j._sched_state['last_error'] = 'cash: ' + type(exc).__name__
    j._tick_v38 = tick
    old_command = j._extensions.command
    async def routed(chat_id, cmd, arg):
        if cmd in COMMANDS:
            return await command(chat_id, cmd, arg)
        return await old_command(chat_id, cmd, arg)
    j._extensions.command = routed
    j._extensions.COMMANDS.update(COMMANDS)
    old_snapshot = j.snapshot
    def snapshot():
        with j._data_lock:
            return {**old_snapshot(), 'business_workflows': load()}
    j.snapshot = snapshot
    j.RESTORE_KEYS['business_workflows'] = KEY
    old_validate = j._validate_backup
    def validate(snap):
        known = old_validate(snap)
        data = snap.get('business_workflows')
        if data is not None:
            if not isinstance(data.get('_seq', {}), dict):
                raise ValueError('business_workflows._seq inválido')
            for key, limit in (('businesses', 50), ('packages', 100), ('requests', 200)):
                rows = data.get(key, [])
                if not isinstance(rows, list) or len(rows) > limit or not all(isinstance(r, dict) for r in rows):
                    raise ValueError('business_workflows.' + key + ' inválido')
            for r in data.get('businesses', []):
                if not all(isinstance(r.get(k), str) and r[k].strip() for k in ('name', 'trade', 'zone')):
                    raise ValueError('Ficha de negocio dañada')
                if r.get('phone') and not re.fullmatch(r'\+?[0-9]{10,15}', r['phone']):
                    raise ValueError('Teléfono de ficha inválido')
            for r in data.get('packages', []):
                if r.get('status') != 'draft' or type(r.get('id')) is not int:
                    raise ValueError('Paquete dañado')
                money(r.get('price_usd'))
            for r in data.get('requests', []):
                if r.get('status') not in ('pending', 'closed') or type(r.get('id')) is not int:
                    raise ValueError('Solicitud dañada')
                if not all(isinstance(r.get(k), str) for k in ('business', 'name', 'phone', 'message', 'created')):
                    raise ValueError('Solicitud dañada')
        return known
    j._validate_backup = validate
    old_prompt = j.system_prompt
    j.system_prompt = lambda: old_prompt() + ('\nSeparate observed cash, books and conditional projections. No guaranteed income, sales or monetization. '
        'Do not request EIN, banking credentials or children personal data. No account creation, credit applications or bureau disputes. '
        'Preserve every recorded income; never use delete/edit tools to hide an income. New business cards need owner name, trade and zone. '
        'Use /pagina NAME for an unhosted static preview only. Every message to clients still requires owner /enviar.')
    @j.app.post('/public/business-requests')
    async def incoming(request: j.Request):
        from urllib.parse import parse_qs
        if not request_enabled():
            raise j.HTTPException(404, 'Solicitudes apagadas')
        chunks = bytearray()
        async for chunk in request.stream():
            if len(chunks) + len(chunk) > 5000:
                raise j.HTTPException(413, 'Consulta demasiado grande')
            chunks.extend(chunk)
        try:
            if request.headers.get('content-type', '').startswith('application/json'):
                data = json.loads(chunks)
            else:
                data = {k: v[-1] for k, v in parse_qs(chunks.decode('utf-8')).items()}
                data['adult'] = data.get('adult') == 'true'
            if not isinstance(data, dict):
                raise ValueError('Solicitud inválida')
            result = await asyncio.to_thread(receive_request, **data)
        except (ValueError, TypeError, UnicodeError) as exc:
            raise j.HTTPException(400, core._redact_secrets(str(exc))[0][:200]) from None
        return result
    j.HELP_TEXT += '\nLocal: /caja [cuenta] · /fichaamazon JSON · /negocio JSON · /pagina NOMBRE · /paquete JSON · /capacidades · /solicitudes [cerrar ID]'
