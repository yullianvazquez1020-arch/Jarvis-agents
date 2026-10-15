"""Business context is shared data, never a fabricated team or cross-device chat."""
import asyncio
import json
from unittest.mock import patch
from desktop_helpers import DesktopBase, D, ai_text, ai_tool, j
import jarvis_specialists as specialists


class BusinessConversation(DesktopBase):
    def test_shared_records_and_followup_survive_restart(self):
        token, device = self.pair()
        j.kv_set('jarvis:facts', [{'id': 1, 'text': 'Proyecto Coral: comparar proveedores', 'at': '2026-10-15'}])
        calls = self.ai(ai_tool('business_context', {'specialty': 'research'}),
                        ai_text('We are comparing suppliers for Coral.'),
                        ai_text('For Coral, compare the landed costs first.'))
        reply = self.turn(token, 'Hablemos de nuestros negocios', rid='business-001').json()
        self.assertEqual(reply['state'], 'done')
        self.assertIn('Proyecto Coral', str(calls[1]['history']))
        self.assertIn('business_context', calls[0]['tools'])
        j.conversations.clear(); j._locks.clear()
        self.turn(token, 'Which costs should we compare for that one?', rid='business-002')
        self.assertIn('Coral', str(calls[-1]['history']))
        self.assertNotIn('tool_result', str(calls[-1]['history']))
        self.assertEqual(j.phase_a_restore('desk:other-device'), [])

    def test_context_tool_has_no_writes_or_network(self):
        with patch.object(j, 'kv_set', side_effect=AssertionError('write forbidden')), \
             patch.object(j, 'kv_set_many', side_effect=AssertionError('write forbidden')):
            for specialty in specialists.SPECIALTIES:
                result = asyncio.run(j.run_tool('business_context', {'specialty': specialty}, read_only='escritorio'))
                self.assertNotIn('error', result)
                self.assertFalse(result['live_verification'])
                self.assertEqual(result['unavailable'], [])
        self.assertFalse(self.sent)

    def test_missing_source_is_not_empty_or_deleted(self):
        with patch.object(j._store, 'status', side_effect=RuntimeError('secret detail')):
            result = specialists.business_context(j)
        self.assertIn('business_plan', result['unavailable'])
        self.assertNotIn('business_plan', result['sources'])
        self.assertNotIn('secret detail', str(result))

    def test_natural_discussion_does_not_open_a_panel(self):
        for text in ('cómo estás', '¿Cómo mejoramos los cobros?', 'Compara la caja con los cobros',
                     'Investiga opciones para la agenda', '¿Por qué bajaron los cobros?'):
            self.assertEqual(D.classify(text)[0], 'ai', text)
        for text in ('muéstrame los cobros', 'dame resumen comercial', 'estado del sistema'):
            self.assertEqual(D.classify(text)[0], 'panel', text)
        self.assertEqual(D.classify('aprueba el pago')[0], 'refuse')

    def test_specialty_validation_and_unchanged_action_boundary(self):
        result = asyncio.run(j.run_tool('business_context', {'specialty': 'unknown'}, read_only='escritorio'))
        self.assertIn('error', result)

    def test_large_records_stay_valid_and_signal_omissions(self):
        with patch.dict(j.HANDLERS, {'list_notes': lambda: {'notes': [{'title': 'x' * 20000}]}}):
            result = specialists.business_context(j)
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False)), 12000)
        self.assertIn('saved_notes', result['omitted_for_size'])
        with patch.dict(j.HANDLERS, {'add_expense': lambda **kw: self.fail('action ran')}):
            result = asyncio.run(j.run_tool('add_expense', {'amount': 10}, read_only='escritorio'))
        self.assertIn('error', result)
