"""Frente 1 · Venta de acceso: planes de suscripción para servicios de agentes (Contesta Ya primero).

NO hay cobro real. Los pagos solo se PROPONEN; un humano los aprueba con /aprobar + /confirmar
y siguen los topes duros del money gate ($100 por operación, $300 por día).
Precios y garantía: PENDIENTE_APROBACION del dueño. IVU: configurable, confirmar con CPA.
"""
import copy, datetime, os, re
from decimal import Decimal, ROUND_HALF_UP

KEY = 'jarvis:frentes_acceso'
ESTADO_PRECIOS = 'PENDIENTE_APROBACION'
HARD_MAX_OP = Decimal('100')
HARD_MAX_DIA = Decimal('300')
CONFIG = {
    'servicio': 'contesta-ya',
    'estado_precios': ESTADO_PRECIOS,
    'estado_garantia': ESTADO_PRECIOS,
    'garantia_borrador': 'Borrador: si en 30 días no contesta al menos el 90 % de los leads de prueba, se devuelve la mensualidad. Requiere aprobación del dueño.',
    'ivu_tasa': os.getenv('FRENTES_IVU_TASA', '0.115'),
    'ivu_nota': 'confirmar con CPA',
    'minimo_meses': 3,
    'minuto_extra_usd': '0.35',
    'planes': {
        'fundador': {'nombre': 'Fundador', 'setup_usd': '750', 'mensual_usd': '397', 'minutos_incluidos': 500,
                     'cupo_clientes': 3, 'meses_precio_fundador': 6},
        'basico': {'nombre': 'Básico', 'setup_usd': '1250', 'mensual_usd': '497', 'minutos_incluidos': 500},
        'pro': {'nombre': 'Pro', 'setup_usd': '2500', 'mensual_usd': '997', 'minutos_incluidos': 1500},
    },
}


def _d(v):
    return Decimal(str(v)).quantize(Decimal('0.01'), ROUND_HALF_UP)


def nuevo_estado():
    return {'clientes': {}, 'uso': {}, 'propuestas': [], 'seq': 0}


class Acceso:
    """Estado en un dict (persistible con kv_set). Sin red, sin cobros."""

    def __init__(self, estado=None, config=None):
        self.s = estado if estado is not None else nuevo_estado()
        self.c = copy.deepcopy(config or CONFIG)

    def ivu(self):
        t = Decimal(str(self.c['ivu_tasa']))
        if not (Decimal('0') <= t < Decimal('1')):
            raise ValueError('tasa IVU inválida')
        return t

    def alta_cliente(self, cid, nombre, plan):
        cid = re.sub(r'[^a-z0-9-]', '', str(cid).lower())[:40]
        if not cid or cid in self.s['clientes']:
            raise ValueError('id de cliente vacío o repetido')
        if plan not in self.c['planes']:
            raise KeyError(f'plan desconocido: {plan}')
        p = self.c['planes'][plan]
        if 'cupo_clientes' in p:
            usados = sum(1 for x in self.s['clientes'].values() if x['plan'] == plan)
            if usados >= p['cupo_clientes']:
                raise ValueError(f"cupo {p['nombre']} lleno ({p['cupo_clientes']} clientes)")
        self.s['clientes'][cid] = {'id': cid, 'nombre': str(nombre)[:80], 'plan': plan, 'meses_min': self.c['minimo_meses']}
        self.s['uso'][cid] = {}
        return self.s['clientes'][cid]

    def cambiar_plan(self, cid, plan):
        if plan not in self.c['planes']:
            raise KeyError(plan)
        self.s['clientes'][cid]['plan'] = plan
        return self.s['clientes'][cid]

    def registrar_minutos(self, cid, mes, minutos):
        if cid not in self.s['clientes']:
            raise KeyError(cid)
        if not re.fullmatch(r'\d{4}-\d{2}', mes) or minutos < 0:
            raise ValueError('mes AAAA-MM y minutos >= 0')
        u = self.s['uso'][cid]
        u[mes] = round(u.get(mes, 0) + float(minutos), 2)
        return u[mes]

    def factura_borrador(self, cid, mes, incluir_setup=False):
        cl = self.s['clientes'][cid]
        p = self.c['planes'][cl['plan']]
        usados = Decimal(str(self.s['uso'][cid].get(mes, 0)))
        extra_min = max(Decimal('0'), usados - p['minutos_incluidos'])
        extra = _d(extra_min * Decimal(self.c['minuto_extra_usd']))
        sub = _d(p['mensual_usd']) + extra + (_d(p['setup_usd']) if incluir_setup else 0)
        ivu = _d(sub * self.ivu())
        return {'cliente': cid, 'mes': mes, 'plan': cl['plan'], 'mensual': str(_d(p['mensual_usd'])),
                'setup': str(_d(p['setup_usd'])) if incluir_setup else '0.00', 'minutos_extra': str(extra_min),
                'extra': str(extra), 'subtotal': str(sub), 'ivu': str(ivu), 'ivu_nota': self.c['ivu_nota'],
                'total': str(sub + ivu), 'estado_precios': self.c['estado_precios'], 'borrador': True}

    def proponer_pago(self, concepto, usd, gastado_hoy=0, limites=None):
        """Crea una propuesta; NUNCA cobra. limites(gastado, usd)->texto de problema ('' = ok) del money gate."""
        usd = _d(usd)
        if limites is not None:
            problema = limites(float(gastado_hoy), float(usd))
        elif usd <= 0:
            problema = 'monto inválido'
        elif usd > HARD_MAX_OP:
            problema = 'pasa el límite por operación ($100)'
        elif _d(gastado_hoy) + usd > HARD_MAX_DIA:
            problema = 'pasaría el límite del día ($300)'
        else:
            problema = ''
        self.s['seq'] += 1
        prop = {'n': self.s['seq'], 'concepto': str(concepto)[:120], 'usd': str(usd),
                'estado': 'bloqueado' if problema else 'propuesto', 'motivo': problema,
                'requiere': '/aprobar N + /confirmar N CODIGO del dueño', 'cobro_real': False}
        self.s['propuestas'].append(prop)
        return prop

    def resumen(self):
        lines = [f"Planes ({self.c['estado_precios']}; IVU {self.c['ivu_tasa']} — {self.c['ivu_nota']}; mínimo {self.c['minimo_meses']} meses):"]
        for k, p in self.c['planes'].items():
            extra = f" · cupo {p['cupo_clientes']} clientes, {p['meses_precio_fundador']} meses" if 'cupo_clientes' in p else ''
            lines.append(f"• {p['nombre']}: ${p['setup_usd']} setup + ${p['mensual_usd']}/mes{extra}")
        lines.append(f"Minuto extra ${self.c['minuto_extra_usd']}. Clientes: {len(self.s['clientes'])}. Sin cobros reales.")
        return '\n'.join(lines)
