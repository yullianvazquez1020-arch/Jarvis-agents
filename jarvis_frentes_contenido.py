"""Frente 3 · Contenido a volumen: guiones, títulos y descripciones de YouTube y borradores de
productos digitales en una cola de REVISIÓN, ligados al plan de 30 días hacia 2,000 suscriptores.

Nada se publica automáticamente: cada pieza queda 'en_revision' y publicar sigue siendo /publicaryoutube del dueño.
"""
import pathlib, re

KEY = 'jarvis:frentes_contenido'
PLAN = pathlib.Path(__file__).resolve().parent / 'docs' / 'youtube' / 'PLAN-CONTENIDO-2000-SUBS.md'
META_SUBS = 2000
_FILA = re.compile(r'^\| (\d+) \| (Largo|Short) \| (.+?) \|$', re.M)


def cargar_plan(path=PLAN):
    return [{'dia': int(d), 'formato': f, 'titulo': t.strip()} for d, f, t in _FILA.findall(pathlib.Path(path).read_text(encoding='utf-8'))]


def nuevo_estado():
    return {'cola': [], 'seq': 0}


def guion(item):
    largo = item['formato'] == 'Largo'
    partes = ['Gancho (0-2 s): ' + item['titulo'],
              'Contexto: quién soy (Yullian, ISLAFIX PRO LLC) y el problema real.',
              'Demostración con datos ficticios, sin pantallas con datos personales.',
              'Cierre: suscríbete; ' + ('enlace a Shorts del tema.' if largo else 'el video completo está en el canal.')]
    if largo:
        partes.insert(3, 'Desarrollo en 3 bloques de 2-3 min con un resultado medible cada uno.')
    return '\n'.join(partes)


class Contenido:
    def __init__(self, estado=None, plan=None):
        self.s = estado if estado is not None else nuevo_estado()
        self.plan = plan if plan is not None else cargar_plan()

    def _encolar(self, tipo, dia, datos):
        self.s['seq'] += 1
        item = {'n': self.s['seq'], 'tipo': tipo, 'dia': dia, **datos, 'estado': 'en_revision', 'publicado': False}
        self.s['cola'].append(item)
        return item

    def generar_dia(self, dia):
        piezas = [p for p in self.plan if p['dia'] == int(dia)]
        if not piezas:
            raise ValueError(f'día {dia} es de descanso o no existe en el plan')
        out = []
        for p in piezas:
            out.append(self._encolar('youtube', p['dia'], {
                'formato': p['formato'], 'titulo': p['titulo'][:100], 'guion': guion(p),
                'descripcion': f"{p['titulo']}. Jarvis IA en Puerto Rico. Contenido hecho con apoyo de IA. #IA #PuertoRico",
            }))
        return out

    def generar_lote(self, desde, hasta):
        out = []
        for d in range(int(desde), int(hasta) + 1):
            if any(p['dia'] == d for p in self.plan):
                out += self.generar_dia(d)
        return out

    def producto_digital(self, titulo, audiencia, precio_propuesto):
        return self._encolar('producto', None, {'titulo': str(titulo)[:100], 'audiencia': str(audiencia)[:80],
                             'precio_propuesto_usd': float(precio_propuesto), 'precio_estado': 'PENDIENTE_APROBACION',
                             'esquema': ['Portada', 'Problema', 'Plantillas', 'Ejemplo ficticio', 'Límites (no es asesoría)']})

    def revisar(self, n, decision):
        if decision not in ('aprobado', 'rechazado'):
            raise ValueError(decision)
        item = next(x for x in self.s['cola'] if x['n'] == int(n))
        item['estado'] = decision       # aprobado = listo para que el dueño publique; no se publica aquí
        return item

    def progreso(self):
        dias = sorted({p['dia'] for p in self.plan})
        hechos = sorted({x['dia'] for x in self.s['cola'] if x['tipo'] == 'youtube'})
        return {'meta_suscriptores': META_SUBS, 'dias_con_contenido': len(dias), 'dias_generados': len(hechos),
                'en_revision': sum(1 for x in self.s['cola'] if x['estado'] == 'en_revision')}
