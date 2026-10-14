"""Tres frentes de dinero: datos ficticios, sin red, sin cobros, envíos ni publicaciones."""
import asyncio, pathlib, sys, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
import test_hardening as h
j = h.j
import jarvis_bus as jb
import jarvis_frentes as fr
import jarvis_frentes_acceso as acc
import jarvis_frentes_contenido as con
import jarvis_frentes_playbooks as pb


class AccesoTest(unittest.TestCase):
    def setUp(self): self.a = acc.Acceso()

    def test_config_pendiente_y_ivu_cpa(self):
        c = acc.CONFIG
        self.assertEqual(c['estado_precios'], 'PENDIENTE_APROBACION')
        self.assertEqual(c['estado_garantia'], 'PENDIENTE_APROBACION')
        self.assertIn('CPA', c['ivu_nota'])
        self.assertEqual(c['minimo_meses'], 3)
        p = c['planes']
        self.assertEqual((p['fundador']['setup_usd'], p['fundador']['mensual_usd'], p['fundador']['cupo_clientes'], p['fundador']['meses_precio_fundador']), ('750', '397', 3, 6))
        self.assertEqual((p['basico']['setup_usd'], p['basico']['mensual_usd']), ('1250', '497'))
        self.assertEqual((p['pro']['setup_usd'], p['pro']['mensual_usd']), ('2500', '997'))
        self.assertEqual(c['minuto_extra_usd'], '0.35')

    def test_cupo_fundador(self):
        for i in range(3): self.a.alta_cliente(f'demo-{i}', f'Negocio Ficticio {i}', 'fundador')
        with self.assertRaises(ValueError): self.a.alta_cliente('demo-9', 'X', 'fundador')
        with self.assertRaises(ValueError): self.a.alta_cliente('demo-0', 'X', 'basico')
        with self.assertRaises(KeyError): self.a.alta_cliente('demo-8', 'X', 'oro')
        self.assertEqual(self.a.cambiar_plan('demo-0', 'pro')['plan'], 'pro')

    def test_uso_y_factura_borrador(self):
        self.a.alta_cliente('barberia-demo', 'Barbería Ficticia', 'basico')
        self.a.registrar_minutos('barberia-demo', '2026-11', 600)
        f = self.a.factura_borrador('barberia-demo', '2026-11')
        self.assertEqual(f['extra'], '35.00'); self.assertEqual(f['subtotal'], '532.00')
        self.assertEqual(f['ivu'], '61.18'); self.assertTrue(f['borrador'])
        self.assertEqual(self.a.factura_borrador('barberia-demo', '2026-11', incluir_setup=True)['setup'], '1250.00')
        with self.assertRaises(ValueError): self.a.registrar_minutos('barberia-demo', 'nov', 1)
        b = acc.Acceso(config={**acc.CONFIG, 'ivu_tasa': '0'})
        b.alta_cliente('c', 'C', 'pro'); self.assertEqual(b.factura_borrador('c', '2026-11')['ivu'], '0.00')

    def test_pagos_solo_propuestos_con_topes(self):
        ok = self.a.proponer_pago('abono ficticio', 90)
        self.assertEqual(ok['estado'], 'propuesto'); self.assertFalse(ok['cobro_real']); self.assertIn('/aprobar', ok['requiere'])
        self.assertEqual(self.a.proponer_pago('setup', 750)['estado'], 'bloqueado')
        self.assertEqual(self.a.proponer_pago('x', 90, gastado_hoy=250)['estado'], 'bloqueado')
        self.assertEqual(self.a.proponer_pago('x', 50, limites=j._limits_problem)['estado'], 'propuesto')
        self.assertEqual(self.a.proponer_pago('x', 101, limites=j._limits_problem)['estado'], 'bloqueado')
        self.assertEqual(self.a.proponer_pago('x', 99, gastado_hoy=250, limites=j._limits_problem)['estado'], 'bloqueado')
        self.assertFalse(any(hasattr(acc, n) for n in ('cobrar', 'charge', 'stripe')))


class PlaybooksTest(unittest.TestCase):
    def setUp(self):
        self.old = jb._REDACTOR; jb.set_redactor(lambda t: j._redact_secrets(t)[0])
        self.bus = jb.Bus(now=lambda: 1.0); self.p = pb.Playbooks(bus=self.bus)

    def tearDown(self): jb.set_redactor(self.old)

    def test_lead_crea_borrador_y_evento(self):
        out = self.p.ejecutar('lead', {'nombre': 'Ana Ficticia', 'canal': 'web', 'negocio': 'Taller Demo'})
        self.assertEqual([x['tipo'] for x in out], ['registrar', 'borrador'])
        self.assertTrue(all(x['enviado'] is False for x in out))
        self.assertEqual(self.bus.eventos()[0]['tipo'], 'playbook')

    def test_aprobacion_solo_dueno(self):
        n = self.p.ejecutar('recordatorio', {'nombre': 'Luis', 'negocio': 'Demo', 'fecha': '2026-11-02'})[0]['n']
        with self.assertRaises(PermissionError): self.p.aprobar(n, 'si')
        self.assertEqual(self.p.aprobar(n, True)['estado'], 'aprobado')
        self.assertFalse(self.p.s['cola'][0]['enviado'])

    def test_validacion(self):
        with self.assertRaises(KeyError): self.p.ejecutar('spam', {})
        with self.assertRaises(ValueError): self.p.ejecutar('seguimiento', {'nombre': 'x'})
        self.assertEqual(len(self.p.ejecutar('seguimiento', {'nombre': 'x', 'negocio': 'y'})), 2)
        self.assertEqual(len(self.p.pendientes()), 2)


class ContenidoTest(unittest.TestCase):
    def setUp(self): self.c = con.Contenido()

    def test_plan_30_dias(self):
        self.assertEqual(len(self.c.plan), 30)
        self.assertEqual(self.c.progreso()['meta_suscriptores'], 2000)

    def test_genera_en_revision_sin_publicar(self):
        out = self.c.generar_dia(1)
        self.assertEqual([x['formato'] for x in out], ['Largo', 'Short'])
        self.assertTrue(all(x['estado'] == 'en_revision' and not x['publicado'] for x in out))
        self.assertIn('Gancho', out[0]['guion']); self.assertIn('IA', out[0]['descripcion'])
        with self.assertRaises(ValueError): self.c.generar_dia(7)
        self.assertEqual(len(self.c.generar_lote(2, 8)), 7)
        self.assertEqual(self.c.revisar(out[0]['n'], 'aprobado')['publicado'], False)
        with self.assertRaises(ValueError): self.c.revisar(1, 'publicar')

    def test_producto_digital(self):
        p = self.c.producto_digital('Kit ficticio de cotizaciones', 'contratistas', 9)
        self.assertEqual(p['precio_estado'], 'PENDIENTE_APROBACION'); self.assertEqual(p['estado'], 'en_revision')


class InstalacionTest(unittest.TestCase):
    def test_instalado_y_comando(self):
        self.assertEqual(j.FRENTES_STATUS, 'activo')
        self.assertIn('/frentes', j._extensions.COMMANDS)
        self.assertIn('PENDIENTE_APROBACION', fr.reply('planes'))
        with self.assertRaises(ValueError): fr.reply('nada')

    def test_contenido_por_comando_persiste(self):
        old = jb._REDACTOR; jb.set_redactor(lambda t: j._redact_secrets(t)[0])
        try:
            self.assertIn('no publicado', fr.reply('contenido 2'))
            self.assertIn('Contenido en revisión', fr.reply('pendientes'))
        finally:
            jb.set_redactor(old)

    def test_solo_dueno(self):
        sent = []
        orig = j._tg_safe_send
        async def fake(chat, text): sent.append(text)
        j._tg_safe_send = fake
        try:
            asyncio.run(j._extensions.command('999-no-dueno', '/frentes', ''))
            self.assertEqual(sent, [])
        finally:
            j._tg_safe_send = orig


class TokensTest(unittest.TestCase):
    T = ROOT / 'tokens'

    def test_guardas_testnet(self):
        src = (self.T / 'src' / 'JarvisTestToken.sol').read_text()
        self.assertIn('MainnetBlocked', src); self.assertIn('11155111', src); self.assertNotIn('id == 1 ', src)
        dep = (self.T / 'script' / 'Deploy.s.sol').read_text()
        self.assertIn('MAINNET_ENABLED = false', dep)
        self.assertNotIn('mainnet', (self.T / 'foundry.toml').read_text().split('[rpc_endpoints]')[1].lower().replace('# solo testnets. no hay rpc de mainnet', ''))

    def test_sin_llaves_y_aviso_legal(self):
        for f in self.T.rglob('*'):
            if f.is_file():
                t = f.read_text()
                self.assertNotRegex(t, r'0x[0-9a-fA-F]{64}', f.name)
                self.assertNotIn('PRIVATE_KEY=', t)
        gi = (self.T / '.gitignore').read_text()
        for x in ('.env', '*.key'): self.assertIn(x, gi)
        self.assertIn('responsabilidad exclusiva de Yullian', (self.T / 'README.md').read_text())


if __name__ == '__main__':
    unittest.main()
