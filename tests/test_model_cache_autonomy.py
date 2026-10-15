import asyncio
import copy
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from desktop_helpers import DesktopBase, D, j


class CacheAndAutonomy(DesktopBase):
    def test_scoped_cache_preserves_tools_and_input(self):
        allowed = [t for t in j.TOOLS if t['name'] in j.READ_ONLY_TOOLS]
        before = copy.deepcopy(allowed)
        result = SimpleNamespace(usage=SimpleNamespace(cache_read_input_tokens=123, cache_creation_input_tokens=0))
        call = AsyncMock(return_value=result)
        with patch.object(j.client.messages, 'create', call), patch.dict(os.environ, {'AI_TOOL_CACHE_ENABLED': 'true'}):
            asyncio.run(j._ai_call_scoped([{'role': 'user', 'content': 'hello'}], allowed, 'voice'))
        sent = call.call_args.kwargs['tools']
        self.assertEqual([t['name'] for t in sent], [t['name'] for t in allowed])
        self.assertEqual(allowed, before)
        self.assertEqual(sent[-1]['cache_control'], {'type': 'ephemeral'})
        self.assertEqual(j._model_timing['cache_read_tokens'], 123)
        self.assertNotIn('hello', str(j._model_timing))
        self.assertEqual(j._cache_tools([]), [])
        with patch.dict(os.environ, {'AI_TOOL_CACHE_ENABLED': 'false'}):
            self.assertEqual(j._cache_tools(allowed), before)

    def test_configuration_does_not_claim_verified_autonomy(self):
        env = {'AUTO_PUBLISH_OWN_SOCIAL': 'true', 'BRAIN_ENABLED': 'false',
               'META_PAGE_ACCESS_TOKEN': 'private-test-token', 'META_PAGE_ID': '123456', 'META_GRAPH_VERSION': 'v25.0'}
        with patch.dict(os.environ, env), patch.object(j, 'kv_set', side_effect=AssertionError('must not write')):
            status = j._connections.autonomy_status()
            self.assertTrue(status['auto_publish_enabled'])
            self.assertFalse(status['brain_enabled'])
            self.assertTrue(status['accounts']['facebook']['configured'])
            self.assertEqual(status['accounts']['facebook']['check'], 'not_tested')
            self.assertNotIn('private-test-token', str(status))
            self.assertEqual(status['purchases'], 'owner_approval_required')
            panel = D._panel_estado()
            self.assertIn('Ciclo autónomo: apagado', panel['lines'])
            self.assertNotIn('private-test-token', str(panel))
