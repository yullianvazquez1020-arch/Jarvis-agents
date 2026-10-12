import asyncio
import os
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
import test_jarvis as base

j=base.j
c=j._connections

def response(blocks,stop='end_turn'):
    return NS(content=blocks,stop_reason=stop,usage=NS(input_tokens=12,output_tokens=3))

def page(url='https://example.com/article'):
    return NS(type='web_fetch_tool_result',content=NS(type='web_fetch_result',url=url,retrieved_at='2026-10-12T03:00:00Z'))

class WebNavigation(unittest.TestCase):
    def setUp(self):
        base.Tests.setUp(self)
        ready=patch.object(j,'AI_READY',True)
        ready.start();self.addCleanup(ready.stop)

    def test_private_and_credential_links_never_call_provider(self):
        urls=['http://example.com','https://localhost/a','https://127.0.0.1/a',
              'https://[::1]/a','https://host.internal/a','https://example.com:8443/a',
              'https://user:pass@example.com/a','https://example.com/?token=abc',
              'https://example.com/?%74oken=abc',
              'https://example.com/\nsecret','https://example.com/'+('x'*250)]
        with patch.object(c,'claude',new=AsyncMock()) as request:
            for url in urls:
                with self.subTest(url=url),self.assertRaises(ValueError):
                    asyncio.run(c.browse_web(url=url))
            request.assert_not_called()

    def test_hosted_reader_only_and_real_fetch_evidence(self):
        r=response([page(),NS(type='text',text='Resumen')])
        with patch.object(j.client.messages,'create',new=AsyncMock(return_value=r)) as req:
            out=asyncio.run(c.browse_web(url='https://example.com/article'))
        tools=req.call_args.kwargs['tools']
        self.assertEqual([t['name'] for t in tools],['web_fetch'])
        self.assertEqual(tools[0]['allowed_domains'],['example.com'])
        self.assertEqual(tools[0]['max_content_tokens'],6000)
        self.assertEqual(out['sources'],['https://example.com/article'])
        self.assertEqual(len(out['pages_read']),1)
        self.assertFalse(out['executed_actions'])

    def test_failed_fetch_is_not_claimed_as_read(self):
        r=response([NS(type='web_fetch_tool_result',content={'type':'web_fetch_tool_result_error','error_code':'url_not_accessible'}),NS(type='text',text='No accesible')])
        with patch.object(j.client.messages,'create',new=AsyncMock(return_value=r)):
            out=asyncio.run(c.browse_web(url='https://example.com/article'))
        self.assertFalse(out['web_search_used'])
        self.assertEqual(out['pages_read'],[])
        self.assertIn('No se confirmó',out['warning'])

    def test_pause_resumes_with_evidence_and_usage(self):
        replies=[response([page()],stop='pause_turn'),response([NS(type='text',text='Final')])]
        with patch.object(j.client.messages,'create',new=AsyncMock(side_effect=replies)) as req:
            out=asyncio.run(c.browse_web(query='investiga'))
        self.assertEqual(req.await_count,2)
        self.assertTrue(out['web_search_used'])
        self.assertEqual(out['text'],'Final')
        self.assertEqual(c.load()['usage']['calls'],2)
        self.assertEqual(c.load()['usage']['tokens'],30)

    def test_repeated_pause_is_bounded_and_marked_incomplete(self):
        r=response([NS(type='text',text='En proceso')],stop='pause_turn')
        with patch.object(j.client.messages,'create',new=AsyncMock(return_value=r)) as req:
            out=asyncio.run(c.browse_web(query='investiga'))
        self.assertEqual(req.await_count,3)
        self.assertTrue(out['incomplete'])

    def test_daily_limit_applies_to_continuations(self):
        r=response([page()],stop='pause_turn')
        with patch.dict(os.environ,{'SPECIALIST_DAILY_CALL_LIMIT':'1'}),patch.object(j.client.messages,'create',new=AsyncMock(return_value=r)) as req:
            with self.assertRaises(ValueError):asyncio.run(c.browse_web(query='tema'))
        self.assertEqual(req.await_count,1)

    def test_openai_search_fallback_and_no_fake_direct_read(self):
        r={'text':'Respuesta','sources':[],'web_search_used':False,'incomplete':False}
        with patch.object(j,'AI_READY',False),patch.object(c,'openai',new=AsyncMock(return_value=r)) as req:
            out=asyncio.run(c.browse_web(query='tema'))
            self.assertTrue(out['warning'])
            with self.assertRaises(ValueError):asyncio.run(c.browse_web(url='https://example.com'))
        self.assertEqual(req.await_count,1)

    def test_owner_command_and_natural_language_tool(self):
        self.assertIn('browse_web',j.ASYNC_TOOLS)
        self.assertIn('/web',j._extensions.COMMANDS)
        with patch.object(j,'_tg_send',new=AsyncMock()) as send,patch.object(c,'browse_web',new=AsyncMock(return_value={})) as browse:
            asyncio.run(c.command('wrong','/web','tema'))
            browse.assert_not_called()
            asyncio.run(c.command('123','/web','https://example.com pregunta'))
            browse.assert_awaited_once_with(query='pregunta',url='https://example.com')

if __name__=='__main__':unittest.main()
