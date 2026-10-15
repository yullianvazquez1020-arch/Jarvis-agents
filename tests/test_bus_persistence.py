import copy
import unittest
from unittest.mock import patch
import jarvis_bus as jb

class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.redactor = patch.object(jb, '_REDACTOR', lambda t: t)
        self.redactor.start()
        self.addCleanup(self.redactor.stop)

    def test_nine_businesses_survive_restart(self):
        saved = {}
        def save(data): saved['state'] = copy.deepcopy(data)
        old = jb.Bus()
        for name in jb.NEGOCIOS:
            old.emitir_guardado(save, name, 'status', 'Verified progress '+name, 'live', 'grokbot')
        new = jb.Bus()
        new.restore(saved['state'])
        self.assertEqual(new.tablero()['negocios'], old.tablero()['negocios'])
        self.assertEqual(new.eventos(), old.eventos())
        self.assertEqual(new.emitir_guardado(save, 'amazon', 'note')['seq'], 10)

    def test_failed_write_does_not_erase_evicted_event_or_allow_blind_retry(self):
        bus = jb.Bus()
        for i in range(jb.MAX_EVENTOS): bus.emitir('amazon', 'note', str(i))
        before = bus.snapshot()
        def fail(data): raise OSError('uncertain storage')
        with self.assertRaises(OSError): bus.emitir_guardado(fail, 'amazon', 'note', 'new')
        self.assertEqual(bus.snapshot(), before)
        with self.assertRaises(RuntimeError): bus.emitir_guardado(lambda d: None, 'amazon', 'note')
        bus.restore(before)
        bus.emitir_guardado(lambda d: None, 'amazon', 'note')

    def test_corrupt_snapshot_rejected_without_overwriting(self):
        bus = jb.Bus(); bus.emitir('amazon', 'note', 'keep')
        before = bus.snapshot()
        broken = copy.deepcopy(before); broken['negocios'] = {}
        with self.assertRaises(ValueError): bus.restore(broken)
        self.assertEqual(before, bus.snapshot())

    def test_legacy_counter_does_not_claim_history_recovered(self):
        bus = jb.Bus(); bus.continuar_desde(42)
        self.assertTrue(bus.tablero()['recovery_required'])
        self.assertEqual(bus.eventos(), [])
        self.assertEqual(bus.emitir('amazon', 'note')['seq'], 43)

    def test_storage_roundtrip_uses_existing_atomic_backend(self):
        from tests.test_hardening import j
        bus = jb.Bus(); bus.emitir('amazon', 'note', 'saved', 'live')
        data = bus.snapshot()
        with patch.object(j, 'kv_set_many') as write:
            j._guardar_estado_bus(data)
            write.assert_called_once_with({j.BUS_STATE_KEY: data, j.BUS_SEQ_KEY: data['seq']})
        fresh = jb.Bus()
        with patch.object(jb, 'BUS', fresh), patch.object(j, 'kv_get', return_value=data):
            j._restaurar_seq_bus()
        self.assertEqual(fresh.tablero()['negocios'], bus.tablero()['negocios'])
