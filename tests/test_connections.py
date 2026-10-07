import asyncio, datetime, json, os, unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import test_jarvis as base
j=base.j;c=j._connections
META={'META_PAGE_ID':'123456789','META_INSTAGRAM_ACCOUNT_ID':'987654321','META_PAGE_ACCESS_TOKEN':'test-meta-secret','META_GRAPH_VERSION':'v25.0','SOCIAL_PUBLISH_ENABLED':'true'}

class Connections(unittest.TestCase):
 def setUp(self):base.Tests.setUp(self)
 def runasync(self,fn):return asyncio.run(fn)
 def draft(self,platform='facebook',asset=''):
  return c.prepare_social_post(platform,'Cotiza tu remodelación con ISLAFIX PRO LLC',asset)['id']
 def code(self,id):return c.publication_preview(id).split()[-1]
 def test_configuration_not_verification(self):
  with patch.dict(os.environ,META):
   r=c.configuration()['facebook'];self.assertTrue(r['configured']);self.assertEqual(r['check']['status'],'not_tested');self.assertNotIn('test-meta-secret',str(c.configuration()))
 def test_draft_no_network(self):
  with patch.object(c,'graph',new=AsyncMock()) as network:
   self.draft();network.assert_not_called();self.assertEqual(c.load()['posts'][0]['status'],'draft')
 def test_reject_missing_instagram_asset(self):
  with self.assertRaises(ValueError):self.draft('instagram')
 def test_reject_secret_and_local_media_url(self):
  for url in ('http://site.test/a.jpg','https://localhost/a','https://example.com/a?token=secret','https://127.0.0.1/a'):
   with self.subTest(url=url),self.assertRaises(ValueError):c.media_url(url)
 def test_publish_exact_draft_once(self):
  with patch.dict(os.environ,META),patch.object(c,'graph',new=AsyncMock(return_value={'id':'remote-1'})) as req:
   id=self.draft();code=self.code(id);self.assertNotIn(code,json.dumps(c.load()))
   self.assertEqual(self.runasync(c.publish_social(id,code))['status'],'published')
   with self.assertRaises(ValueError):self.runasync(c.publish_social(id,code))
   self.assertEqual(req.await_count,1);self.assertEqual(req.call_args.kwargs['data']['message'],c.load()['posts'][0]['caption'])
 def test_no_automatic_retry_after_timeout(self):
  with patch.dict(os.environ,META),patch.object(c,'graph',new=AsyncMock(side_effect=TimeoutError('ambiguous'))) as req:
   id=self.draft();code=self.code(id)
   with self.assertRaises(TimeoutError):self.runasync(c.publish_social(id,code))
   with self.assertRaises(ValueError):self.runasync(c.publish_social(id,code))
   self.assertEqual(req.await_count,1);self.assertEqual(c.load()['posts'][0]['status'],'uncertain')
 def test_changed_target_needs_new_preview(self):
  with patch.dict(os.environ,META),patch.object(c,'graph',new=AsyncMock()) as req:
   id=self.draft();code=self.code(id)
   with patch.dict(os.environ,{'META_PAGE_ID':'222222222'}),self.assertRaises(ValueError):self.runasync(c.publish_social(id,code))
   req.assert_not_called()
 def test_wrong_codes_lock_after_five(self):
  with patch.dict(os.environ,META),patch.object(c,'graph',new=AsyncMock()) as req:
   id=self.draft();code=self.code(id);wrong='111111' if code!='111111' else '222222'
   for _ in range(5):
    with self.assertRaises(ValueError):self.runasync(c.publish_social(id,wrong))
   self.assertEqual(c.load()['posts'][0]['status'],'draft');req.assert_not_called()
 def test_expired_code(self):
  with patch.dict(os.environ,META),patch.object(c,'graph',new=AsyncMock()) as req:
   id=self.draft();code=self.code(id)
   with patch.object(j,'_now',return_value=j._now()+datetime.timedelta(minutes=11)),self.assertRaises(ValueError):self.runasync(c.publish_social(id,code))
   req.assert_not_called()
 def test_publish_is_disabled_by_default(self):
  with patch.dict(os.environ,{**META,'SOCIAL_PUBLISH_ENABLED':'false'}),patch.object(c,'graph',new=AsyncMock()) as req:
   id=self.draft();code=self.code(id)
   with self.assertRaises(ValueError):self.runasync(c.publish_social(id,code))
   req.assert_not_called()
 def test_instagram_waits_for_ready_before_publish(self):
  responses=[{'id':'container'},{'status_code':'FINISHED'},{'id':'media-1'}]
  with patch.dict(os.environ,META),patch.object(c,'graph',new=AsyncMock(side_effect=responses)) as req:
   id=self.draft('instagram','https://assets.example.com/photo.jpg');code=self.code(id)
   self.assertEqual(self.runasync(c.publish_social(id,code))['remote_id'],'media-1')
   self.assertEqual(req.call_args.kwargs['data'],{'creation_id':'container'})
 def test_instagram_processing_error_never_publishes(self):
  with patch.dict(os.environ,META),patch.object(c,'graph',new=AsyncMock(side_effect=[{'id':'container'},{'status_code':'ERROR'}])) as req:
   id=self.draft('instagram','https://assets.example.com/photo.jpg');code=self.code(id)
   with self.assertRaises(ValueError):self.runasync(c.publish_social(id,code))
   self.assertEqual(req.await_count,2)
 def test_approvals_not_model_tools_or_voice(self):
  for name in ('publication_preview','publish_social','cancel_post','check_connection'):
   self.assertNotIn(name,j.HANDLERS);self.assertNotIn(name,j.ASYNC_TOOLS);self.assertNotIn(name,j.READ_ONLY_TOOLS)
 def test_read_only_cannot_draft(self):
  r=self.runasync(j.run_tool('prepare_social_post',{'platform':'facebook','caption':'Test'},read_only='desktop'))
  self.assertIn('error',r);self.assertEqual(c.load()['posts'],[])
 def test_restore_invalidates_social_approvals(self):
  with patch.dict(os.environ,META):
   id=self.draft();code=self.code(id);snap=j.snapshot()
   j.restore_snapshot(snap,dry_run=False)
   self.assertEqual(c.load()['posts'][0]['status'],'cancelled')
   with self.assertRaises(ValueError):self.runasync(c.publish_social(id,code))
 def test_budget_reserved_even_when_provider_fails(self):
  with patch.dict(os.environ,{'OPENAI_API_KEY':'fake','SPECIALIST_DAILY_CALL_LIMIT':'1'}),patch.object(c,'request',new=AsyncMock(side_effect=TimeoutError())) as req:
   with self.assertRaises(TimeoutError):self.runasync(c.openai('test'))
   with self.assertRaises(ValueError):self.runasync(c.openai('test'))
   self.assertEqual(req.await_count,1)
 def test_provider_parses_sources_and_redacts(self):
  response={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'Respuesta test-meta-secret','annotations':[{'type':'url_citation','url':'https://example.com/source'}]}]}],'usage':{'total_tokens':20}}
  with patch.dict(os.environ,{**META,'OPENAI_API_KEY':'fake'}),patch.object(c,'request',new=AsyncMock(return_value=response)) as req:
   r=self.runasync(c.openai('pregunta test-meta-secret',web=True));self.assertTrue(r['web_search_used']);self.assertNotIn('test-meta-secret',r['text']);self.assertNotIn('test-meta-secret',str(req.call_args.kwargs['json']['input']));self.assertFalse(req.call_args.kwargs['json']['store'])
 def test_cross_review_failure_keeps_original(self):
  answer={'text':'Original','web_search_used':True,'sources':['https://example.com'],'incomplete':False}
  with patch.dict(os.environ,{'OPENAI_API_KEY':'fake'}),patch.object(j,'AI_READY',True),patch.object(c,'openai',new=AsyncMock(return_value=answer)),patch.object(c,'claude',new=AsyncMock(side_effect=TimeoutError())):
   r=self.runasync(c.collaborative_analysis('test'));self.assertEqual(r['summary'],'Original');self.assertIsNone(r['review_provider']);self.assertEqual(r['sources'],answer['sources'])
 def test_openai_missing_falls_back_to_existing_claude(self):
  answer={'text':'Claude','web_search_used':False,'sources':[],'incomplete':False}
  with patch.dict(os.environ,{'OPENAI_API_KEY':''}),patch.object(j,'AI_READY',True),patch.object(c,'claude',new=AsyncMock(return_value=answer)):
   r=self.runasync(c.collaborative_analysis('test'));self.assertEqual(r['draft_provider'],'claude');self.assertFalse(r['web_search_used'])
 def test_diagnostic_missing_never_sends(self):
  with patch.dict(os.environ,{'OPENAI_API_KEY':''}),patch.object(c,'request',new=AsyncMock()) as req:
   self.assertEqual(self.runasync(c.check_connection('openai'))['openai']['status'],'missing');req.assert_not_called()
 def test_diagnostic_coinbase_is_read_only(self):
  with patch.dict(os.environ,{'COINBASE_API_KEY_NAME':'fake','COINBASE_API_PRIVATE_KEY':'fake'}),patch.object(j,'coinbase_balances',new=AsyncMock(return_value={})) as balances:
   self.assertEqual(self.runasync(c.check_connection('coinbase'))['coinbase']['status'],'verified_read');balances.assert_awaited_once()
 def test_specialists_require_separate_key(self):
  from fastapi.testclient import TestClient
  with TestClient(j.app) as client:
   r=client.post('/agents/marketing/ask',json={'message':'Test'},headers={'x-api-key':'test-local-only'});self.assertEqual(r.status_code,401)
 def test_specialist_cannot_invoke_actions(self):
  from fastapi.testclient import TestClient
  with patch.dict(os.environ,{'SPECIALIST_AGENT_KEY':'special-test'}),patch.object(c,'collaborative_analysis',new=AsyncMock(return_value={'executed_actions':False})) as ai,TestClient(j.app) as client:
   r=client.post('/agents/marketing/ask',json={'message':'Draft'},headers={'x-api-key':'special-test'});self.assertEqual(r.status_code,200);self.assertFalse(r.json()['executed_actions']);ai.assert_awaited_once()
   self.assertEqual(client.post('/agents/buy/ask',json={'message':'Buy'},headers={'x-api-key':'special-test'}).status_code,404)
 def test_changed_credentials_invalidate_verified_status(self):
  with patch.dict(os.environ,{'OPENAI_API_KEY':'old'}),patch.object(c,'request',new=AsyncMock(return_value={})):
   self.runasync(c.check_connection('openai'));self.assertEqual(c.configuration()['openai']['check']['status'],'verified_read')
   with patch.dict(os.environ,{'OPENAI_API_KEY':'new'}):self.assertEqual(c.configuration()['openai']['check']['status'],'not_tested')
 def test_restored_budget_cannot_go_backwards(self):
  c.reserve('test');snap=j.snapshot();c.reserve('test');j.restore_snapshot(snap,dry_run=False)
  self.assertEqual(c.load()['usage']['calls'],2)
 def test_bad_backup_fails_before_storage_change(self):
  snap=j.snapshot();snap['connections']['usage']=[]
  with self.assertRaises(ValueError):j.restore_snapshot(snap,dry_run=False)
 def test_restricted_status_hides_key_values(self):
  from fastapi.testclient import TestClient
  with patch.dict(os.environ,{**META,'SPECIALIST_AGENT_KEY':'special-test'}),TestClient(j.app) as client:
   self.assertEqual(client.get('/agents/status').status_code,401)
   r=client.get('/agents/status',headers={'x-api-key':'special-test'});self.assertEqual(r.status_code,200)
   self.assertNotIn('test-meta-secret',r.text);self.assertNotIn('credential_signature',r.text)
 def test_confirmcode_never_queued(self):
  from fastapi.testclient import TestClient
  msg={'message_id':1,'text':'/confirmarred 1 654321','chat':{'id':123,'type':'private'},'from':{'id':123,'is_bot':False}}
  with patch.object(j,'TG_SECRET','secret'),patch.object(c,'command',new=AsyncMock()),patch.object(j,'_tg_enqueue',side_effect=AssertionError('code queued')),TestClient(j.app) as client:
   response=client.post('/telegram',json={'update_id':90001,'message':msg},headers={'x-telegram-bot-api-secret-token':'secret'});self.assertEqual(response.status_code,200)

if __name__=='__main__':unittest.main()
