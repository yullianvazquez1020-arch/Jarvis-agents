"""Frente 2 · Automatizar negocio: plantillas (playbooks) de tareas repetitivas para negocios cliente.

Jarvis prepara tareas y BORRADORES de mensajes; publica el avance en el bus de negocios.
Ningún mensaje a clientes sale sin /aprobar del dueño. Este módulo no envía nada.
"""
import copy, re

KEY = 'jarvis:frentes_playbooks'
PLANTILLAS = {
    'lead': {'nombre': 'Entrada de lead', 'pasos': [
        ('registrar', 'Registrar lead {nombre} ({canal}) para {negocio}.'),
        ('borrador', 'Hola {nombre}, gracias por escribir a {negocio}. ¿Qué día y hora te funciona para la cita?'),
    ]},
    'recordatorio': {'nombre': 'Recordatorio de cita', 'pasos': [
        ('borrador', 'Hola {nombre}, te recordamos tu cita con {negocio} el {fecha}. Responde SÍ para confirmar.'),
    ]},
    'seguimiento': {'nombre': 'Seguimiento post-servicio', 'pasos': [
        ('borrador', 'Hola {nombre}, ¿cómo te fue con el servicio de {negocio}? Si te gustó, una reseña nos ayuda mucho.'),
        ('tarea', 'Revisar respuesta de {nombre} en 3 días.'),
    ]},
}
_CAMPO = re.compile(r'\{(\w+)\}')


def nuevo_estado():
    return {'cola': [], 'seq': 0}


class Playbooks:
    def __init__(self, estado=None, bus=None):
        self.s = estado if estado is not None else nuevo_estado()
        self.bus = bus

    def ejecutar(self, plantilla, datos):
        if plantilla not in PLANTILLAS:
            raise KeyError(f'plantilla desconocida: {plantilla}')
        datos = {k: str(v)[:120] for k, v in datos.items()}
        out = []
        for tipo, texto in PLANTILLAS[plantilla]['pasos']:
            faltan = [c for c in _CAMPO.findall(texto) if c not in datos]
            if faltan:
                raise ValueError(f'faltan datos: {", ".join(faltan)}')
            self.s['seq'] += 1
            item = {'n': self.s['seq'], 'plantilla': plantilla, 'tipo': tipo, 'texto': texto.format(**datos),
                    'estado': 'borrador' if tipo == 'borrador' else 'pendiente', 'enviado': False,
                    'requiere': '/aprobar del dueño' if tipo == 'borrador' else ''}
            self.s['cola'].append(item)
            out.append(item)
        if self.bus is not None:
            self.bus.emitir('contesta-ya', 'playbook', f"{PLANTILLAS[plantilla]['nombre']}: {len(out)} pasos preparados (borrador)", fuente='jarvis')
        return out

    def aprobar(self, n, aprobado_por_dueno):
        """Marca un borrador como aprobado para envío manual. Sin aprobación del dueño, se rechaza."""
        item = next((x for x in self.s['cola'] if x['n'] == int(n)), None)
        if item is None or item['tipo'] != 'borrador':
            raise KeyError(n)
        if aprobado_por_dueno is not True:
            raise PermissionError('solo el dueño aprueba con /aprobar')
        item['estado'] = 'aprobado'   # el envío real lo hace el canal existente; aquí no se envía
        return item

    def pendientes(self):
        return [x for x in self.s['cola'] if x['estado'] in ('borrador', 'pendiente')]
