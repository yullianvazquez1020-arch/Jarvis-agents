"""One owner-managed store plan. No publishing, spending or external calls."""
import copy
import math

KEY = 'jarvis:store'
KINDS = ('producto', 'borrador', 'tarea', 'resultado')
HELP = ('/tienda — resumen\n/tienda nombre NOMBRE\n/tienda presupuesto 0\n'
        '/tienda producto TEXTO\n/tienda borrador TEXTO\n/tienda tarea TEXTO\n'
        '/tienda resultado TEXTO\n/tienda ver ID\n/tienda listo ID\n'
        'Presupuesto planificado en USD; no autoriza gastos. Los resultados son notas, no ingresos contables.')


def empty():
    return {'name': '', 'daily_budget': 0, 'entries': [], 'updated': None}


def validate(data):
    if not isinstance(data, dict) or set(data) != set(empty()):
        raise ValueError('Registro de tienda inválido')
    if not isinstance(data['name'], str) or len(data['name']) > 100:
        raise ValueError('Nombre de tienda inválido')
    budget = data['daily_budget']
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or not 0 <= budget <= 300:
        raise ValueError('Presupuesto: número entre 0 y 300 USD')
    if data['updated'] is not None and (not isinstance(data['updated'], str) or len(data['updated']) > 50):
        raise ValueError('Fecha inválida')
    rows = data['entries']
    if not isinstance(rows, list) or len(rows) > 500:
        raise ValueError('Máximo 500 registros por tienda')
    for idx, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) != {'id', 'kind', 'text', 'done'}:
            raise ValueError('Registro inválido')
        if type(row['id']) is not int or row['id'] != idx or row['kind'] not in KINDS:
            raise ValueError('Identificador o tipo inválido')
        if not isinstance(row['text'], str) or not row['text'].strip() or len(row['text']) > 2000 or type(row['done']) is not bool:
            raise ValueError('Texto o estado inválido')
        if row['done'] and row['kind'] != 'tarea':
            raise ValueError('Solo las tareas se completan')
    return data


def load():
    return validate(copy.deepcopy(core.kv_get(KEY, empty())))


def status():
    with core._data_lock:
        return {**load(), 'published': False, 'spending_authorized': False,
                'note': 'Plan interno. Resultados declarados por el dueño, sin verificar; no son ingresos contables.'}


def summary(data=None):
    d = data if data is not None else load()
    lines = ['Primera tienda: ' + (d['name'] or 'sin nombre'),
             f"Presupuesto planificado: ${d['daily_budget']:.2f} USD/día (no autoriza gastos)",
             'Plan interno; no publica ni mueve dinero.']
    for kind in KINDS:
        rows = [r for r in d['entries'] if r['kind'] == kind]
        lines.append(f'{kind.capitalize()}: {len(rows)}')
        for row in rows[-3:]:
            lines.append(f"#{row['id']} {'✓ ' if row['done'] else ''}{row['text'][:120]}")
    lines.append('Resultados: notas del dueño, sin verificar. /tienda ver ID muestra el texto completo.')
    return '\n'.join(lines)


def reply(arg):
    action, _, value = arg.strip().partition(' ')
    value = value.strip()
    with core._data_lock:
        d = load()
        if not action:
            return summary(d) + '\n\n' + HELP
        if action == 'ver':
            row = next((r for r in d['entries'] if str(r['id']) == value), None)
            if row is None:
                raise ValueError('ID no encontrado')
            return f"#{row['id']} {row['kind']}\n{row['text']}"
        if action == 'nombre':
            if not value or len(value) > 100:
                raise ValueError('Escribe un nombre de 1 a 100 caracteres')
            d['name'] = value
        elif action == 'presupuesto':
            d['daily_budget'] = float(value)
        elif action in KINDS:
            if not d['name']:
                raise ValueError('Primero escribe /tienda nombre NOMBRE')
            if not value or len(value) > 2000:
                raise ValueError('Escribe de 1 a 2000 caracteres')
            # A retried Telegram delivery must not duplicate the same entry.
            if any(r['kind'] == action and r['text'] == value for r in d['entries']):
                return 'Ya está guardado.\n' + summary(d)
            d['entries'].append({'id': len(d['entries']) + 1, 'kind': action, 'text': value, 'done': False})
        elif action == 'listo':
            row = next((r for r in d['entries'] if str(r['id']) == value and r['kind'] == 'tarea'), None)
            if row is None:
                raise ValueError('ID de tarea no encontrado')
            row['done'] = True
        else:
            return HELP
        d['updated'] = core._now().isoformat(timespec='seconds')
        validate(d)
        core.kv_set(KEY, d)
        return 'Guardado en Jarvis.\n' + summary(d)


def install(j):
    global core
    core = j
    j.HANDLERS['store_status'] = status
    j.TOOLS.append(j._t('store_status', 'Read the first store plan, products, drafts, tasks and owner-reported results. No verified revenue or spending permission.', {}, []))
    j.READ_ONLY_TOOLS = j.READ_ONLY_TOOLS | {'store_status'}
    if getattr(j, '_desktop', None):
        j._desktop.READ_TOOLS = j.READ_ONLY_TOOLS
    old_snapshot = j.snapshot
    def snapshot():
        with j._data_lock:
            return {**old_snapshot(), 'store': load()}
    j.snapshot = snapshot
    j.RESTORE_KEYS['store'] = KEY
    old_validate = j._validate_backup
    def validate_backup(snap):
        known = old_validate(snap)
        if 'store' in snap:
            validate(snap['store'])
        return known
    j._validate_backup = validate_backup
    old_command = j._extensions.command
    async def command(chat_id, cmd, arg):
        if cmd != '/tienda':
            return await old_command(chat_id, cmd, arg)
        if str(chat_id) != str(j.TG_OWNER):
            return
        try:
            text = reply(arg)
        except (ValueError, TypeError):
            text = 'Datos inválidos.\n' + HELP
        await j._tg_safe_send(chat_id, text)
    j._extensions.command = command
    j._extensions.COMMANDS.add('/tienda')
    j.HELP_TEXT += '\n/tienda — plan de primera tienda guardado en Jarvis, sin gasto ni publicación'
