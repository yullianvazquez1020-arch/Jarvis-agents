"""Owner's prepared commercial offers, usable even when the paid model is unavailable."""
import copy

HELP = '/negocios · /negocios gumroad · /negocios fiverr · /negocios preparar · /tienda'
OFFERS = {
    'gumroad': {
        'name': 'Organiza tu remodelación: kit práctico en español',
        'price_proposed_usd': 9,
        'scope': 'PDF imprimible de 7 páginas y plantillas editables Markdown: ficha del proyecto, registro de fotos, solicitud de cotización, comparación de proveedores, cambios y cierre.',
        'draft': ('¿Tienes una remodelación en mente? Organiza lo que necesitas antes de pedir cotizaciones. '
                  'Incluye un PDF imprimible de 7 páginas y plantillas editables en español para definir el alcance, '
                  'registrar fotos, comparar propuestas y dar seguimiento a cambios y pendientes. '
                  'Puedes reutilizar las hojas en tus propios proyectos. '
                  'No incluye inspección, planos, cálculo de materiales ni asesoría personalizada.'),
        'next': 'Entrar a la cuenta existente, comprobar productos para evitar duplicados y preparar la ficha con los archivos del kit.',
    },
    'fiverr': {
        'name': 'I will organize your renovation project brief in Spanish',
        'price_proposed_usd': 35,
        'scope': 'Un área, hasta 8 fotos y 2 páginas de notas; entrega propuesta de PDF de 2–3 páginas en español, 3 días y una revisión del mismo alcance. Confirmar capacidad antes de publicar.',
        'draft': ('Turn your renovation notes into an organized project brief in Spanish. '
                  'I am a contractor based in Puerto Rico. Send your goals, up to 8 photos and up to 2 pages of notes for one area. '
                  'You will receive a 2–3 page PDF in Spanish with scope, exclusions, missing information and questions for contractors, '
                  'with one revision for the same scope. '
                  'This service does not include inspection, plans, construction pricing, material quantities or code certification. '
                  'Measurements provided by you remain unverified. Communication and delivery are in Spanish.'),
        'next': 'Entrar a la cuenta existente, revisar servicios previos y preparar un borrador con requisitos del comprador y plazo confirmado.',
    },
}
TASKS = (
    'AINCRAD · Gumroad: recuperar Kit-Organiza-tu-remodelacion.pdf y Plantillas-editables.md del paquete preparado; revisar ambos archivos.',
    'AINCRAD · Gumroad: verificar cuenta y configuración de cobro; guardar ficha como borrador a precio propuesto de $9.',
    'AINCRAD · Fiverr: verificar cuenta; guardar oferta de organización de remodelación como borrador a precio propuesto de $35; confirmar plazo y requisitos.',
    'AINCRAD · Publicación: revisar cada ficha y publicar con autorización del dueño; registrar URL comprobada y fecha.',
)


def status():
    return {
        'prepared_on': '2026-10-12',
        'offers': copy.deepcopy(OFFERS),
        'tasks_proposed': list(TASKS),
        'store': core._store.status(),
        'pipeline': core._income.status(),
        'publication_verified': False,
        'revenue_verified': None,
        'artifact_note': 'El kit fue preparado en ChatGPT; este módulo contiene las ofertas, no los archivos del comprador. Recuperarlos del paquete Aincrad antes de subirlos.',
    }


def summary():
    d = core._store.status()
    pending = [r for r in d['entries'] if r['kind'] == 'tarea' and not r['done']]
    lines = ['AINCRAD · NEGOCIOS',
             'Dos ofertas preparadas: Gumroad $9 y Fiverr $35 (precios propuestos, brutos).',
             'Publicación, ventas y cobros todavía sin verificar.',
             'Hoy: recuperar el kit, abrir las cuentas existentes y preparar las fichas para revisión.',
             'Kit preparado en ChatGPT: PDF de 7 páginas + plantillas. Los archivos del comprador no están adjuntos a este mensaje.',
             'Manos y mouse: a cargo de Claude por ahora.',
             'Tareas guardadas pendientes: ' + str(len(pending))]
    lines += [f"#{r['id']} {r['text'][:220]}" for r in pending[:5]]
    if not d['entries']:
        lines.append('Para guardar las ofertas y tareas sin duplicarlas: /negocios preparar')
    lines += ['Ver textos de venta: /negocios gumroad · /negocios fiverr',
              'Ver plan guardado: /tienda. Completar una tarea: /tienda listo ID.',
              'Estos comandos funcionan sin créditos de IA. No hay ingresos confirmados.']
    return '\n'.join(lines)


def prepare():
    """One guarded persistent write; preserves owner records, budget and completed tasks."""
    with core._data_lock:
        d = core._store.load()
        rows = [('borrador', f"AINCRAD · {key}: {v['name']}\nPrecio propuesto: ${v['price_proposed_usd']} USD.\n{v['scope']}\n{v['draft']}")
                for key, v in OFFERS.items()] + [('tarea', text) for text in TASKS]
        for kind, text in rows:
            if not any(r['kind'] == kind and r['text'] == text for r in d['entries']):
                d['entries'].append({'id': len(d['entries']) + 1, 'kind': kind, 'text': text, 'done': False})
        if not d['name']:
            d['name'] = 'AINCRAD · primeras ofertas'
        core._store.validate(d)
        previous = core._store.load()
        if d != previous:
            d['updated'] = core._now().isoformat(timespec='seconds')
            core.kv_set(core._store.KEY, d)
        return 'Ofertas y tareas guardadas en Jarvis.\n' + summary()


def reply(arg):
    key = arg.strip().lower()
    if key in ('', 'hoy'):
        return summary()
    if key == 'preparar':
        return prepare()
    if key in OFFERS:
        v = OFFERS[key]
        return (f"BORRADOR · {key.upper()}\n{v['name']}\n"
                f"Precio de prueba propuesto: ${v['price_proposed_usd']} USD, antes de comisiones y costos.\n"
                f"Alcance: {v['scope']}\n\nTexto de venta:\n{v['draft']}\n\n"
                f"Próximo paso: {v['next']}\nPublicación y cobros sin verificar.\n" + HELP)
    return HELP


def install(j):
    global core
    core = j
    j.HANDLERS['business_plan'] = status
    j.TOOLS.append(j._t('business_plan', 'Read the owner prepared Gumroad/Fiverr offers and saved business tasks. Use when asked to resume the business or empire. Prices are proposed; publication and revenue unverified.', {}, []))
    j.READ_ONLY_TOOLS = j.READ_ONLY_TOOLS | {'business_plan'}
    if getattr(j, '_desktop', None):
        j._desktop.READ_TOOLS = j.READ_ONLY_TOOLS
    old_prompt = j.system_prompt
    def system_prompt():
        return old_prompt() + ('\nBusiness continuity: when the owner asks to continue negocios, Aincrad or imperio, '
                               'read business_plan and store_status before asking them to repeat the plan. '
                               'Use saved tasks and clearly distinguish proposed drafts from verified publication or sales. '
                               'Hands and mouse are currently being handled by Claude; focus this business conversation on the offers.\n')
    j.system_prompt = system_prompt
    old_command = j._extensions.command
    async def command(chat_id, cmd, arg):
        if cmd != '/negocios':
            return await old_command(chat_id, cmd, arg)
        if str(chat_id) != str(j.TG_OWNER):
            return
        try:
            text = reply(arg)
        except (ValueError, TypeError):
            text = 'No pude cargar o guardar el plan. Revisa /tienda y /diagnostico; no se marcó ninguna venta.'
        await j._tg_safe_send(chat_id, text)
    j._extensions.command = command
    j._extensions.COMMANDS.add('/negocios')
    j.HELP_TEXT += '\n' + HELP
