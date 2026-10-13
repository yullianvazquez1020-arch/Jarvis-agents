"""Owner's prepared commercial offers, usable even when the paid model is unavailable."""
import copy
import os

HELP = '/negocios · /negocios gumroad · /negocios fiverr · /negocios preparar · /negocios desarrollar · /tienda'
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
        'next': 'Promocionar el producto existente https://yullian.gumroad.com/l/ketec; revisar /ventas para resultados registrados.',
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
LEGACY_TASKS = ('AINCRAD · Gumroad: recuperar Kit-Organiza-tu-remodelacion.pdf y Plantillas-editables.md del paquete preparado; revisar ambos archivos.', 'AINCRAD · Gumroad: verificar cuenta y configuración de cobro; guardar ficha como borrador a precio propuesto de $9.', 'AINCRAD · Fiverr: verificar cuenta; guardar oferta de organización de remodelación como borrador a precio propuesto de $35; confirmar plazo y requisitos.', 'AINCRAD · Publicación: revisar cada ficha y publicar con autorización del dueño; registrar URL comprobada y fecha.')
PRODUCT_URL = 'https://yullian.gumroad.com/l/ketec'
TASKS = (
    'AINCRAD · Gumroad: promocionar el kit existente de $9 en https://yullian.gumroad.com/l/ketec; no crear un duplicado.',
    'AINCRAD · Contenido: preparar textos para Facebook y guion de Reel con el alcance real del kit.',
    'AINCRAD · Fiverr: preparar la oferta de organización de remodelación de $35 propuestos; revisar capacidad y plazo antes de publicarla.',
    'AINCRAD · Medición: revisar ventas registradas y clics del hub; distinguir visitas, ventas e ingresos netos.',
)
CAMPAIGN = (
    ('Facebook · kit', '¿Vas a remodelar? Organiza el alcance antes de pedir cotizaciones. '
     'Nuestro kit práctico en español incluye un PDF de 7 páginas y plantillas editables Markdown '
     'para registrar fotos, comparar propuestas y dar seguimiento a cambios y pendientes. '
     'Precio: $9 USD. Compra y descarga: ' + PRODUCT_URL),
    ('Reel · guion de 20 segundos', 'Escena 1: notas de un proyecto. Texto: Antes de pedir precios, define el alcance. '
     'Escena 2: ficha del kit. Texto: Guarda fotos y compara propuestas sobre el mismo trabajo. '
     'Escena 3: lista de pendientes. Texto: Organiza cambios y cierre. '
     'Cierre: Kit práctico en español, $9 USD. ' + PRODUCT_URL +
     ' — Guion preparado; el video todavía no se ha renderizado.'),
    ('Fiverr · requisitos del comprador', 'Envía el objetivo de una sola área, hasta 8 fotos, '
     'hasta 2 páginas de notas y las medidas que tengas. Indica qué deseas conservar y qué cambiar. '
     'Entrega propuesta: PDF en español de 2–3 páginas, 3 días y una revisión del mismo alcance. '
     'Precio propuesto: $35 USD. No incluye inspección, planos ni cálculo de materiales.'),
)


def capabilities():
    return {
        'kit_routes_available': getattr(core, 'EVOLVE_STATUS', '') == 'activo',
        'landing_available': getattr(core, 'AINCRAD_STATUS', '') == 'activo',
        'product_url': PRODUCT_URL,
        'publication_evidence': 'Producto publicado confirmado por el dueño el 2026-10-13; no es una consulta en vivo a Gumroad.',
        'email_configured': bool(core.EMAIL_ON),
        'whatsapp_configured': bool(core.SMS_ON and str(core.TW_FROM).startswith('whatsapp:')),
        'connections': core._connections.configuration(),
    }



def status():
    return {
        'prepared_on': '2026-10-13',
        'offers': copy.deepcopy(OFFERS),
        'tasks_proposed': list(TASKS),
        'superseded_task_texts': list(LEGACY_TASKS),
        'store': core._store.status(),
        'pipeline': core._income.status(),
        'publication_verified': False,  # no live marketplace check by this tool
        'capabilities': capabilities(),
        'revenue_verified': None,
        'artifact_note': 'Kit existente: /kit/archivo.pdf y /kit/plantillas.md cuando kit_routes_available=true. La entrega comercial está en Gumroad; no inventar videos, proveedores ni plantillas Google Docs.',
    }


def summary():
    d = core._store.status()
    pending = [r for r in d['entries'] if r['kind'] == 'tarea' and not r['done'] and r['text'] not in LEGACY_TASKS]
    lines = ['AINCRAD · NEGOCIOS',
             'Gumroad $9: producto existente. Fiverr $35: oferta propuesta.',
             'Gumroad: ' + PRODUCT_URL,
             'Ventas y cobros: consultar /ventas; no son ingresos garantizados.',
             'Hoy: desarrollar contenido para el kit existente y preparar la oferta Fiverr.',
             ('Archivos del kit: /kit/archivo.pdf · /kit/plantillas.md' if capabilities()['kit_routes_available'] else 'El módulo de archivos del kit no está disponible en esta instancia; revisar /diagnostico.'),
             'Manos y mouse: a cargo de Claude por ahora.',
             'Tareas guardadas pendientes: ' + str(len(pending))]
    lines += [f"#{r['id']} {r['text'][:220]}" for r in pending[:5]]
    if not d['entries']:
        lines.append('Para guardar las ofertas y tareas sin duplicarlas: /negocios preparar')
    lines += ['Ver textos de venta: /negocios gumroad · /negocios fiverr',
              'Ver plan guardado: /tienda. Completar una tarea: /tienda listo ID.',
              'Preparación sin créditos de IA: /negocios desarrollar. No publica ni cobra.']
    return '\n'.join(lines)


def prepare(extra_rows=()):
    """One guarded persistent write; preserves owner records, budget and completed tasks."""
    with core._data_lock:
        d = core._store.load()
        rows = [('borrador', f"AINCRAD · {key}: {v['name']}\nPrecio propuesto: ${v['price_proposed_usd']} USD.\n{v['scope']}\n{v['draft']}")
                for key, v in OFFERS.items()] + [('tarea', text) for text in TASKS]
        rows += list(extra_rows)
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


def develop():
    rows = [('borrador', 'AINCRAD · ' + title + '\n' + body) for title, body in CAMPAIGN]
    prepare(rows)
    return ('Paquete comercial guardado en /tienda: oferta Gumroad, oferta Fiverr, texto Facebook, '
            'guion de Reel y requisitos del comprador. Puedes trabajar más de tres ideas. '
            'No se publicó contenido ni se envió a clientes.\n\n' +
            '\n\n'.join(title + '\n' + body for title, body in CAMPAIGN))


def reply(arg):
    key = arg.strip().lower()
    if key in ('', 'hoy'):
        return summary()
    if key == 'desarrollar':
        return develop()
    if key == 'preparar':
        return prepare()
    if key in OFFERS:
        v = OFFERS[key]
        return (f"BORRADOR · {key.upper()}\n{v['name']}\n"
                f"Precio de prueba propuesto: ${v['price_proposed_usd']} USD, antes de comisiones y costos.\n"
                f"Alcance: {v['scope']}\n\nTexto de venta:\n{v['draft']}\n\n"
                f"Próximo paso: {v['next']}\nConsulta /ventas para registros de ventas.\n" + HELP)
    return HELP


def install(j):
    global core
    core = j
    j.HANDLERS['business_plan'] = status
    j.TOOLS.append(j._t('business_plan', 'Read the owner prepared Gumroad/Fiverr offers and saved business tasks. Use when asked to resume the business or empire. Gumroad is an existing product; Fiverr price is proposed. Check runtime capabilities; never infer sales.', {}, []))
    j.HANDLERS['business_develop'] = develop
    j.TOOLS.append(j._t('business_develop', 'Prepare and persist the existing kit campaign and Fiverr offer without publishing, sending, spending or extra model calls. Use when the owner asks to proceed or develop businesses. Idempotent.', {}, []))
    j.READ_ONLY_TOOLS = j.READ_ONLY_TOOLS | {'business_plan'}
    if getattr(j, '_desktop', None):
        j._desktop.READ_TOOLS = j.READ_ONLY_TOOLS
    old_prompt = j.system_prompt
    def system_prompt():
        return old_prompt() + ('\nBusiness continuity: when the owner asks to continue negocios, Aincrad or imperio, '
                               'read business_plan and store_status before asking them to repeat the plan. '
                               'Use current tasks_proposed; superseded_task_texts are historical and must not restart completed setup. '
                               'Clearly distinguish proposed drafts from verified publication or sales. '
                               'When asked to proceed, use business_develop immediately; do not ask again for the kit or permission to draft. '
                               'Existing kit scope: 7-page PDF plus Markdown templates, $9; never add uncreated videos, supplier contacts, Google Docs, guarantees or proven savings. '
                               'Create concrete deliverables now with available tools; do not promise background work or income in 48-72 hours. '
                               'Missing email/WhatsApp keys block only sending through those channels, not research, drafting or preparation. '
                               'Hands and mouse are currently being handled by Claude; focus this business conversation on the offers.\n') + (
            'Owner language preference: respond in British English, even to Spanish questions. Use a calm, concise, formal assistant manner. '
            'Keep command names, proper nouns and saved client/marketing drafts in their original language. '
            'Use Spanish only when the owner explicitly requests it.\n'
            if os.getenv('JARVIS_REPLY_LANGUAGE','es').lower() in ('en','en-gb','en_gb') else '')
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
