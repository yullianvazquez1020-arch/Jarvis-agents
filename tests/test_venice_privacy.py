"""Privacy regressions: synthetic data, no external calls or production storage."""
import asyncio
import base64
import json
import os
import threading
import unittest
from unittest.mock import patch
import test_jarvis as base
import jarvis_router as router
import jarvis_private_backup as backup
j = base.j

class VenicePrivacy(unittest.TestCase):
    def setUp(self):
        base.Tests.setUp(self)
        self.env = patch.dict(os.environ, {'VENICE_ENABLED':'1', 'VENICE_API_KEY':'fictitious-key',
            'DATA_ENCRYPTION_KEY':base64.b64encode(b'v'*32).decode()})
        self.env.start(); self.addCleanup(self.env.stop)
        j._seal_paused['on'] = False
        j._venice_lock = asyncio.Lock()

    def test_all_outbound_messages_checked(self):
        for kwargs in ({'system':'correo demo@example.test'},
                       {'history':[{'role':'assistant','content':'phone 787-555-0100'}]},
                       {'history':[{'role':'user','content':'password ficticia'}]}):
            with self.subTest(kwargs=kwargs), patch.object(router,'ask_api') as api:
                with self.assertRaises(router.RouterError): router.ask_venice('Hola', **kwargs)
                api.assert_not_called()

    def test_exact_opaque_secret_blocked(self):
        with patch.dict(os.environ, {'AGENT_API_KEY':'demo/only:value.42'}), patch.object(router,'ask_api') as api:
            with self.assertRaises(router.RouterError): router.ask_venice('Repite demo/only:value.42')
            api.assert_not_called()

    def test_key_alone_does_not_enable(self):
        with patch.dict(os.environ, {'VENICE_ENABLED':'0'}), patch.object(router,'_post') as post:
            with self.assertRaises(router.RouterError):router.ask_venice('Hola')
            post.assert_not_called()

    def test_history_encrypted_and_backed_up(self):
        with patch.object(router,'ask_venice',return_value={'text':'Hola de vuelta'}):
            self.assertEqual(asyncio.run(j.venice_chat('private','Hola')), 'Hola de vuelta')
        raw=j._kv_raw(j.VENICE_STORE,None)
        self.assertTrue(raw.startswith('sealed:'))
        self.assertNotIn('Hola',raw)
        section=backup.export(j)
        self.assertEqual(backup.restore_values(j,section)[j.VENICE_STORE],j.kv_get(j.VENICE_STORE,{}))
        section['values'].pop('venice_history')
        backup.restore_values(j,section) # old backups remain accepted

    def test_no_key_or_wrong_key_never_calls_provider(self):
        with patch.object(router,'ask_venice',return_value={'text':'Hola'}):asyncio.run(j.venice_chat('s','Hola'))
        original=j._kv_raw(j.VENICE_STORE,None)
        for key in ('',base64.b64encode(b'x'*32).decode()):
            with patch.dict(os.environ, {'DATA_ENCRYPTION_KEY':key}),patch.object(router,'ask_venice') as api:
                asyncio.run(j.venice_chat('s','Hola'));api.assert_not_called()
                self.assertEqual(j._kv_raw(j.VENICE_STORE,None),original)

    def test_legacy_not_sent_and_reset_clears(self):
        old=j._venice_hist_key('s');j.kv_set(old,[{'role':'user','content':'old private content'}])
        with patch.object(router,'ask_venice') as api:
            asyncio.run(j.venice_chat('s','Hola'));api.assert_not_called()
        with patch.dict(os.environ,{'VENICE_ENABLED':'0','VENICE_API_KEY':''}):
            self.assertIn('borrada',asyncio.run(j.venice_chat('s','reset')))
        self.assertEqual(j._kv_raw(old,None),[])

    def test_sensitive_response_not_stored(self):
        with patch.object(router,'ask_venice',return_value={'text':'correo demo@example.test'}):
            self.assertIn('descartada',asyncio.run(j.venice_chat('s','Hola')))
        self.assertIsNone(j._kv_raw(j.VENICE_STORE,None))

    def test_reset_waits_for_pending_turn(self):
        async def scenario():
            started=threading.Event();release=threading.Event()
            def slow(*args):
                started.set();release.wait(3);return {'text':'Hola'}
            with patch.object(router,'ask_venice',slow):
                turn=asyncio.create_task(j.venice_chat('s','Hola'))
                self.assertTrue(await asyncio.to_thread(started.wait,2))
                reset=asyncio.create_task(j.venice_chat('s','reset'))
                await asyncio.sleep(0)
                self.assertFalse(reset.done())
                release.set();await turn;await reset
                self.assertNotIn(j._venice_hist_key('s'),j.kv_get(j.VENICE_STORE,{}))
        asyncio.run(scenario())

    def test_chat_auth_rate_and_text_only(self):
        from unittest.mock import AsyncMock
        request = j.Chat(message='Hola', provider='venice')
        with patch.object(j, 'API_KEY', 'fictitious-api'), patch.object(j, 'venice_chat', new=AsyncMock(return_value='Hola')) as api, patch.object(j, 'run', new=AsyncMock()) as run:
            with self.assertRaises(j.HTTPException) as err:
                asyncio.run(j.chat(request, x_api_key='wrong'))
            self.assertEqual(err.exception.status_code,401);api.assert_not_called()
            with patch.object(j, '_rate_ok', return_value=False):
                with self.assertRaises(j.HTTPException) as err:
                    asyncio.run(j.chat(request, x_api_key='fictitious-api'))
                self.assertEqual(err.exception.status_code,429);api.assert_not_called()
            asyncio.run(j.chat(request, x_api_key='fictitious-api'))
            api.assert_awaited_once();run.assert_not_called()

    def test_group_cannot_use_venice_or_see_help(self):
        for command in ('/venice Hola','/ayuda'):
            background=j.BackgroundTasks()
            msg={'chat':{'id':j.TG_OWNER,'type':'group'},'from':{'id':j.TG_OWNER_USER},'text':command}
            with patch.object(j,'_tg_safe_send') as send:
                asyncio.run(j._tg_route(msg,background))
            self.assertFalse(any(task.func.__name__ in ('_send_venice','_tg_v38_cmd') for task in background.tasks))
