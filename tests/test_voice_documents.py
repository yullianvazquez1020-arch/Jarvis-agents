"""Document requests must produce files, preserve revisions and never send messages."""
import io
import json
import tempfile
import threading
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from desktop import documentos as local
from desktop_helpers import DesktopBase, D, j, ai_text

DOC = {'title': 'Energía solar', 'content': '## Introducción\nUn ejemplo & sus límites.\n## Conclusión\nTexto de prueba.', 'summary': 'El borrador está preparado.'}

class LocalDocuments(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = local.Store(self.tmp.name)

    def test_valid_docx_and_versions(self):
        first = self.store.save('request-0001', DOC)
        raw = first.read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for name in z.namelist(): ET.fromstring(z.read(name))
            self.assertIn('Introducción', z.read('word/document.xml').decode())
            self.assertNotIn('TargetMode="External"', z.read('_rels/.rels').decode())
        self.assertEqual(first, self.store.save('request-0001', DOC))
        second = self.store.save('request-0002', dict(DOC, content='Nueva introducción'))
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), raw)
        self.assertEqual(self.store.latest()['version'], 2)
        with self.assertRaises(ValueError): self.store.save('request-0001', dict(DOC, content='Overwrite'))

    def test_explicit_preferences_and_path_safety(self):
        self.assertIsNone(local.intent('¿Qué es una monografía?'))
        self.assertEqual(local.intent('Jarvis, hazme una monografía del sol'), 'new')
        self.assertEqual(local.intent('expand the introduction', True), 'revise')
        # Whisper transcriptions: punctuation after the name and question forms.
        for text in ('Jarvis. Hazme un documento corto sobre energía solar.',
                     '¿Jarvis, me haces un documento sobre energía solar?',
                     'Jarvis! Redáctame un informe del proyecto',
                     'Oye, Jarvis: escríbeme una carta para el cliente',
                     '¿Puedes hacerme un ensayo sobre el agua?',
                     'Jarvis; write an essay about solar energy'):
            with self.subTest(text=text):
                self.assertEqual(local.intent(text), 'new')
        for text in ('Jarvis. ¿Qué es una monografía?', 'Jarvis, ¿cómo va el día?', 'Jarvisito, hazme caso',
                     'Me haces falta', 'Jarvis. Hazme caso'):
            with self.subTest(text=text):
                self.assertIsNone(local.intent(text))
        self.assertEqual(local.intent('Jarvis. Abre el último documento.'), 'open')
        self.store.remember('Recuerda para mis documentos: usa párrafos cortos')
        self.assertEqual(self.store.preferences(), ['usa párrafos cortos'])
        with self.assertRaises(ValueError): self.store.remember('Recuerda para mis documentos: mi password es secreto')
        path = self.store.save('request-0003', dict(DOC, title='../../outside'))
        self.assertEqual(path.parent, self.store.root)
        path.unlink(); path.symlink_to(Path(self.tmp.name) / 'outside')
        with self.assertRaises(ValueError): self.store.save('request-0003', DOC)

    def test_voice_writes_revises_and_recovers_without_second_generation(self):
        class Companion:
            def _run_turn(self, tid, text): return 'ordinary'
            def _finish(self, *args, **kwargs): self.result = args
            def _token(self): return 'paired'
            def emit(self, event): pass
        local.install(Companion)
        obj = Companion(); obj.home = self.tmp.name; obj.demo = False; obj.lock = threading.RLock()
        obj.turns = {key: {} for key in ('request-0001', 'request-0002', 'request-0003', 'request-0004')}
        from unittest.mock import Mock
        obj.client = SimpleNamespace(url='https://example.invalid', _call=Mock(return_value={'state': 'done', 'document': DOC}))
        with patch.object(local, 'open_document', return_value=True) as opened:
            obj._run_turn('request-0001', 'hazme una monografía sobre energía solar')
            self.assertTrue(opened.call_args.args[0].is_file())
            self.assertNotIn(DOC['content'], obj.result[2])
            obj._run_turn('request-0002', 'amplía la introducción')
            self.assertEqual(obj.client._call.call_args.args[2]['previous'], DOC)
            obj.client._call.side_effect = TimeoutError()
            obj._run_turn('request-0003', 'write an essay about water')
            self.assertEqual(self.store.pending(), 'request-0003')
            obj.client._call.side_effect = None
            obj._run_turn('request-0004', 'recupera el documento pendiente')
            self.assertEqual(obj.client._call.call_args.args[1], '/desktop/v1/documents/get')
            self.assertIsNone(self.store.pending())
        self.assertEqual(obj._run_turn('unused', '¿Estás despierto?'), 'ordinary')

class Installer(unittest.TestCase):
    def test_unknown_panel_refused_without_mutation(self):
        from scripts.install_voice_documents import install
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'desktop').mkdir()
            app = root / 'desktop/app.py'; app.write_text('custom = True\n')
            with self.assertRaises(ValueError): install(root, b'x = 1', root / 'backups')
            self.assertEqual(app.read_text(), 'custom = True\n')
            self.assertFalse((root / 'backups').exists())
            self.assertFalse((root / 'desktop/documentos.py').exists())

class DocumentAPI(DesktopBase):
    def post(self, token, **updates):
        data = {'request_id': 'document-0001', 'text': 'Escribe una monografía sobre el sol'}
        data.update(updates)
        return self.client.post('/desktop/v1/documents', headers=self.hdr(token), json=data)

    def test_authentication_and_device_isolation(self):
        self.assertEqual(self.client.post('/desktop/v1/documents', json={}).status_code, 401)
        token, _ = self.pair()
        with patch.object(j, 'AI_READY', True), patch.object(j, '_model_call', new=AsyncMock(return_value=ai_text(json.dumps(DOC)))):
            self.assertEqual(self.post(token).json()['state'], 'done')
        second, _ = self.pair('Other Mac')
        self.assertEqual(self.client.post('/desktop/v1/documents/get', headers=self.hdr(second), json={'request_id': 'document-0001'}).status_code, 404)

    def test_generation_is_idempotent_and_has_no_tools(self):
        token, _ = self.pair()
        with patch.object(j, 'AI_READY', True), patch.object(j, '_model_call', new=AsyncMock(return_value=ai_text(json.dumps(DOC)))) as model:
            self.assertEqual(self.post(token).json()['document'], DOC)
            self.assertEqual(self.post(token).json()['document'], DOC)
            self.assertEqual(model.await_count, 1)
            self.assertEqual(model.call_args.args[1], [])
            self.assertEqual(self.post(token, text='Otro documento').status_code, 409)

    def test_invalid_or_partial_output_never_succeeds(self):
        token, _ = self.pair()
        response = ai_text(json.dumps(DOC)); response.stop_reason = 'max_tokens'
        with patch.object(j, 'AI_READY', True), patch.object(j, '_model_call', new=AsyncMock(return_value=response)) as model:
            result = self.post(token).json()
            self.assertEqual(result['state'], 'error'); self.assertNotIn('document', result)
            self.post(token); self.assertEqual(model.await_count, 1)
            self.assertEqual(self.post(token, request_id='bad').status_code, 400)
            self.assertEqual(self.post(token, preferences='invalid').status_code, 400)

if __name__ == '__main__': unittest.main()
