"""Commercial opportunity backlog, not 100 businesses or guaranteed income."""
import copy

KEY = 'jarvis:income_pipeline'
# Brainstorming tied to the owner's services; no demand, suppliers or returns are claimed verified.
GROUPS = [
 ('Servicios de propiedad', 'dueños de propiedades', [
  'Mantenimiento preventivo por membresía', 'Lavado a presión de comercios', 'Pintura de interiores', 'Reparación de losas', 'Carpintería básica', 'Sellado de juntas de baño', 'Preparación de propiedad para alquilar', 'Mantenimiento de puertas', 'Montaje de muebles', 'Reparación de paredes']),
 ('Talleres de IA', 'pequeños negocios', [
  'Taller introductorio de IA', 'Taller de cotizaciones con IA', 'Taller de contenido comercial', 'Taller de organización administrativa', 'Taller de atención al cliente', 'Taller de hojas de cálculo', 'Taller de propuestas de servicios', 'Taller de catálogos digitales', 'Taller privado para equipos', 'Sesión práctica individual de IA']),
 ('Documentos digitales', 'contratistas y emprendedores', [
  'Plantilla de cotización', 'Plantilla de orden de trabajo', 'Checklist de entrega de propiedad', 'Planificador de mantenimiento', 'Control de costos de proyectos', 'Registro de inventario', 'Calendario de contenido', 'Guía introductoria de IA', 'Plantilla de seguimiento comercial', 'Control de herramientas']),
 ('Servicios digitales', 'negocios locales', [
  'Redacción de fichas de productos', 'Diseño de catálogo PDF', 'Preparación de presentación comercial', 'Organización de fotos de proyectos', 'Redacción de biografía comercial', 'Diseño de menú digital', 'Preparación de preguntas frecuentes', 'Redacción de anuncios', 'Preparación de boletín comercial', 'Diseño de tarjeta digital']),
 ('Operación de propiedades', 'administradores de inmuebles', [
  'Reporte fotográfico de mantenimiento', 'Checklist entre alquileres', 'Inventario de suministros de propiedad', 'Coordinación de acceso a contratistas', 'Calendario preventivo de edificios', 'Organización de garantías de equipos', 'Manual de mantenimiento para dueño', 'Control de pendientes de reparación', 'Reporte de avance de obra', 'Supervisión de entrega de trabajos']),
 ('Paquetes de mantenimiento', 'comercios y oficinas', [
  'Mantenimiento de oficinas pequeñas', 'Puesta a punto de locales vacíos', 'Retoques de pintura comercial', 'Mantenimiento de áreas comunes', 'Limpieza de patios', 'Renovación de letreros interiores', 'Organización de almacén pequeño', 'Montaje de estanterías', 'Mantenimiento de cercas', 'Revisión visual de acabados']),
 ('Productos de hogar por validar', 'hogares', [
  'Organizadores de gavetas', 'Topes de puertas', 'Protectores de muebles', 'Ganchos adhesivos', 'Bolsas organizadoras', 'Paños de microfibra', 'Cepillos de limpieza', 'Etiquetas reutilizables', 'Organizadores de cables', 'Bandejas de almacenamiento']),
 ('Productos de trabajo por validar', 'trabajadores y pequeños negocios', [
  'Bolsas para herramientas', 'Organizadores de tornillos', 'Lápices de carpintería', 'Cintas de señalización', 'Fundas de documentos', 'Portaidentificaciones', 'Etiquetas de inventario', 'Libretas de campo', 'Portaherramientas', 'Protectores de superficies']),
 ('Contenido educativo', 'personas que aprenden mantenimiento e IA', [
  'Guía de mantenimiento del hogar', 'Video de organización de herramientas', 'Curso básico de cotizaciones', 'Serie de costos de proyectos', 'Manual de fotos de antes y después', 'Tutoriales de plantillas administrativas', 'Guía de selección de materiales', 'Cuaderno de planificación de remodelación', 'Minicurso de servicio al cliente', 'Guía de inventario para negocios']),
 ('Servicios administrativos', 'microempresas', [
  'Digitalización de órdenes de trabajo', 'Organización de recibos', 'Carga de inventario inicial', 'Preparación de agenda comercial', 'Clasificación de consultas de clientes', 'Configuración de formularios de solicitud', 'Organización de archivos digitales', 'Preparación de reportes operativos', 'Documentación de procesos', 'Catálogo de servicios de contratista'])
]
CATALOG = [{'id': n * 10 + i + 1, 'name': name, 'group': group, 'audience': audience}
           for n, (group, audience, names) in enumerate(GROUPS) for i, name in enumerate(names)]
HELP = '/fuentes [1-10] · /fuente ID · /fuente ID activar|pausar|borrador · /fuente ID nota TEXTO · /ingresosplan'


def empty():
    return {'items': {}}


def validate(d):
    if not isinstance(d, dict) or set(d) != {'items'} or not isinstance(d['items'], dict):
        raise ValueError('Plan inválido')
    for key, item in d['items'].items():
        if key not in {str(x['id']) for x in CATALOG} or not isinstance(item, dict) or set(item) != {'active', 'note', 'draft'}:
            raise ValueError('Fuente inválida')
        if type(item['active']) is not bool or any(not isinstance(item[k], str) or len(item[k]) > 2500 for k in ('note', 'draft')):
            raise ValueError('Datos inválidos')
    return d


def load():
    return validate(copy.deepcopy(core.kv_get(KEY, empty())))


def status():
    with core._data_lock:
        d = load()
        return {'ideas': 100, 'active': [x for x in CATALOG if d['items'].get(str(x['id']), {}).get('active')],
                'records': d['items'], 'verified_revenue': None,
                'note': 'Ideas sin demanda validada. No son 100 negocios abiertos. Ventas y cobros se llevan en los libros existentes.'}


def brief():
    s = status()
    active = s['active']
    return ['FUENTES COMERCIALES · separadas de cripto',
            '100 ideas para validar; ' + str(len(active)) + ' pilotos seleccionados.',
            *[f"#{x['id']} {x['name']} — validar cliente, alcance y costos" for x in active],
            *[f"#{row['id']} {row['name']} — " +
              ('piloto activo' if item['active'] else 'piloto no activo') +
              (f". Nota guardada: {item['note'][:300]}" if item['note'] else '') +
              (f". Borrador guardado: /fuente {row['id']}" if item['draft'] else '')
              for row in CATALOG
              if (item := s['records'].get(str(row['id']))) and (item['note'] or item['draft'])][:6],
            'Resumen de hasta 6 fuentes con notas o borradores; consulta cualquier registro completo con /fuente ID.',
            'Prioridad propuesta: #11 taller de IA, #2 lavado comercial, #1 mantenimiento.',
            'Revisar /seguimientos y /cobros para oportunidades ya registradas.',
            'Sin ingresos atribuidos a estas ideas. /fuentes · /fuente ID · /ingresosplan']


def offer(row):
    return (f"BORRADOR PARA REVISAR — {row['name']}\n"
            f"Hola. En {core.BUSINESS_NAME} estamos evaluando ofrecer {row['name'].lower()} "
            f"para {row['audience']}. ¿Le interesaría compartir lo que necesita para preparar una propuesta?\n\n"
            'Antes de enviar: confirmar capacidad de entrega, alcance, costos, precio, plazo y requisitos aplicables. '
            'No incluye precio ni disponibilidad confirmados. No se ha enviado ni publicado.')


def reply(cmd, arg):
    with core._data_lock:
        if cmd == '/ingresosplan':
            return '\n'.join(brief()) + '\n\n' + HELP
        if cmd == '/fuentes':
            page = int(arg or '1')
            if not 1 <= page <= 10:
                raise ValueError('Página entre 1 y 10')
            return ('100 ideas por validar — página ' + str(page) + '/10\n' +
                    '\n'.join(f"#{r['id']} {r['name']}" for r in CATALOG[(page-1)*10:page*10]) + '\n' + HELP)
        parts = arg.split(maxsplit=2)
        idx = int(parts[0]) if parts else 0
        if not 1 <= idx <= 100:
            raise ValueError('ID entre 1 y 100')
        row = CATALOG[idx-1]
        action = parts[1] if len(parts) > 1 else ''
        d = load()
        item = d['items'].setdefault(str(idx), {'active': False, 'note': '', 'draft': ''})
        if not action:
            return (f"#{idx} {row['name']}\nPúblico por validar: {row['audience']}\n"
                    f"Piloto seleccionado: {'sí' if item['active'] else 'no'}\n"
                    'Demanda, precio, inversión y ganancia: sin dato.\n'
                    'Validar: comprador interesado, competencia, entrega, costo total y margen.\n'
                    f"Nota del dueño: {item['note'] or 'sin nota'}\n{item['draft']}\n{HELP}")
        if action in ('activar', 'pausar'):
            item['active'] = action == 'activar'
        elif action == 'borrador':
            item['draft'] = offer(row)
        elif action == 'nota' and len(parts) == 3:
            item['note'] = parts[2]
        else:
            raise ValueError(HELP)
        validate(d)
        core.kv_set(KEY, d)
        return item['draft'] if action == 'borrador' else 'Guardado en Jarvis. No envía, publica ni mueve dinero.\n' + HELP


def install(j):
    global core
    core = j
    j.HANDLERS['income_pipeline_status'] = status
    j.TOOLS.append(j._t('income_pipeline_status', 'Read commercial ideas and selected pilots. Demand and revenue are unverified. Separate from crypto; never imply sales occurred.', {}, []))
    j.READ_ONLY_TOOLS = j.READ_ONLY_TOOLS | {'income_pipeline_status'}
    if getattr(j, '_desktop', None):
        j._desktop.READ_TOOLS = j.READ_ONLY_TOOLS
    old_snapshot = j.snapshot
    def snapshot():
        with j._data_lock:
            return {**old_snapshot(), 'income_pipeline': load()}
    j.snapshot = snapshot
    j.RESTORE_KEYS['income_pipeline'] = KEY
    old_validate = j._validate_backup
    def validate_backup(snap):
        known = old_validate(snap)
        if 'income_pipeline' in snap:
            validate(snap['income_pipeline'])
        return known
    j._validate_backup = validate_backup
    old_command = j._extensions.command
    async def command(chat_id, cmd, arg):
        if cmd not in ('/fuentes', '/fuente', '/ingresosplan'):
            return await old_command(chat_id, cmd, arg)
        if str(chat_id) != str(j.TG_OWNER):
            return
        try:
            text = reply(cmd, arg)
        except (ValueError, TypeError) as exc:
            text = str(exc)[:500] + '\n' + HELP
        await j._tg_safe_send(chat_id, text)
    j._extensions.command = command
    j._extensions.COMMANDS.update(('/fuentes', '/fuente', '/ingresosplan'))
    j.HELP_TEXT += '\n' + HELP
    if getattr(j, 'BRIEF_STATUS', '') == 'activo':
        j._brief.EXTRA_SECTIONS.append(brief)
