"""Tres frentes de dinero (acceso, automatización, contenido) conectados a Jarvis.

Reutiliza: kv_get/kv_set de Jarvis, el bus de negocios (PR #120) y la regla de topes del money gate.
Solo lectura y borradores: sin cobros, envíos ni publicaciones. Comandos solo para el dueño.
"""
import jarvis_bus
import jarvis_frentes_acceso as acceso
import jarvis_frentes_contenido as contenido
import jarvis_frentes_playbooks as playbooks

HELP = '/frentes · /frentes planes · /frentes contenido DIA · /frentes pendientes'
COMMANDS = ('/frentes',)
core = None


def _load(key, factory):
    return core.kv_get(key, None) or factory()


def reply(arg):
    parts = (arg or '').split()
    sub = parts[0].lower() if parts else ''
    ac = acceso.Acceso(_load(acceso.KEY, acceso.nuevo_estado))
    if sub in ('', 'planes'):
        return ac.resumen()
    if sub == 'contenido':
        if len(parts) < 2 or not parts[1].isdigit():
            raise ValueError('uso: /frentes contenido DIA')
        st = _load(contenido.KEY, contenido.nuevo_estado)
        c = contenido.Contenido(st)
        out = c.generar_dia(int(parts[1]))
        core.kv_set(contenido.KEY, st)
        jarvis_bus.BUS.emitir('youtube', 'borrador', f'Día {parts[1]}: {len(out)} piezas en revisión', fuente='jarvis')
        return '\n'.join(f"#{x['n']} {x['formato']}: {x['titulo']} (en revisión, no publicado)" for x in out)
    if sub == 'pendientes':
        pb = playbooks.Playbooks(_load(playbooks.KEY, playbooks.nuevo_estado))
        ct = contenido.nuevo_estado() if core is None else _load(contenido.KEY, contenido.nuevo_estado)
        return (f"Playbooks: {len(pb.pendientes())} borradores/tareas · Contenido en revisión: "
                f"{sum(1 for x in ct['cola'] if x['estado'] == 'en_revision')} · Propuestas de pago: "
                f"{sum(1 for x in ac.s['propuestas'] if x['estado'] == 'propuesto')}")
    raise ValueError(HELP)


def install(j):
    global core
    core = j
    old_command = j._extensions.command

    async def command(chat_id, cmd, arg):
        if cmd not in COMMANDS:
            return await old_command(chat_id, cmd, arg)
        if str(chat_id) != str(j.TG_OWNER):
            return
        try:
            text = reply(arg)
        except (ValueError, KeyError) as exc:
            text = str(exc)[:500] + '\n' + HELP
        await j._tg_safe_send(chat_id, text)
    j._extensions.command = command
    j._extensions.COMMANDS.update(COMMANDS)
    j.HELP_TEXT += '\n' + HELP
