import sys,unittest,asyncio,datetime,os,json
from unittest.mock import patch,AsyncMock
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parent))
import test_jarvis as base
j=base.j;e=j._extensions
class ExtensionTests(base.Tests):
 def job(self,price=100):
  c=j.add_client('Ana <Company>',phone='7875551234');return j.add_job(c['id'],'Paint & Repair',price=price,advance=20)
 def test_note_long(self):
  n=e.save_note('Plan','z'*50000);self.assertEqual(e.get_note(n['id'])['body'],'z'*50000)
 def test_invoice_no_tax(self):
  doc=e.prepare_document(self.job()['id']);self.assertEqual(doc['total'],100);self.assertEqual(doc['balance'],80)
 def test_tax_missing(self):
  with self.assertRaises(ValueError):e.prepare_document(self.job()['id'],taxable=True)
 def test_tax_explicit(self):
  job=self.job();e.configure_business(ivu_percent=7.5);d=e.prepare_document(job['id'],taxable=True)
  self.assertEqual(d['total'],107.5);self.assertEqual(j._cload()['jobs'][0]['price'],100)
 def test_tax_validation(self):
  with self.assertRaises(ValueError):e.configure_business(ivu_percent=float('nan'))
  self.assertEqual(e.load()['settings'],{})
 def test_pdf_invoice(self):self.assertTrue(e.document_pdf(e.prepare_document(self.job()['id'])).startswith(b'%PDF-'))
 def test_pdf_report(self):self.assertTrue(e.report_pdf(e.business_report()).startswith(b'%PDF-'))
 def test_report_month(self):
  j.add_income(100,date='2026-09-01');j.add_income(200,date='2026-10-01');j.add_expense(30,date='2026-10-01')
  r=e.business_report('2026-10');self.assertEqual(r['net'],170)
 def test_client_report(self):
  job=self.job();j.record_job_payment(job['id'],10,date='2026-10-01');j.add_income(25,date='2026-10-01')
  r=e.business_report('2026-10',job['client_id']);self.assertEqual(r['income'],10);self.assertIsNone(r['net'])
 def test_recurring_once(self):
  job=self.job();e.add_recurring_invoice(job['id'],j._today().isoformat())
  a=e.recurring_due();b=e.recurring_due();self.assertEqual(len(a),1);self.assertEqual(len(b),1);self.assertEqual(a[0]['paid'],0)
 def test_recurring_month_anchor(self):self.assertEqual(e._next_date('2026-02-28','monthly',31),'2026-03-31')
 def test_receipt_atomic_once(self):
  d=e.load();d['receipts'].append({'id':1,'amount':12,'date':'2026-10-01','category':'materials','merchant':'Store','status':'pending'});e.save(d)
  e.approve_receipt(1)
  with self.assertRaises(ValueError):e.approve_receipt(1)
  self.assertEqual(len(j._bload()['expenses']),1)
 def test_receipt_requires_date(self):
  d=e.load();d['receipts'].append({'id':1,'amount':12,'date':'','category':'materials','merchant':'Store','status':'pending'});e.save(d)
  with self.assertRaises(ValueError):e.approve_receipt(1)
  self.assertEqual(j._bload()['expenses'],[])
 def test_edit_requires_approval(self):
  item=j.add_income(100);a=asyncio.run(j.run_tool('edit_entry',{'kind':'income','id':item['id'],'changes':{'amount':200}}))
  self.assertEqual(j._bload()['income'][0]['amount'],100)
  asyncio.run(e.execute_action(a['id']));self.assertEqual(j._bload()['income'][0]['amount'],200)
 def test_delete_requires_approval(self):
  item=j.add_income(100);a=asyncio.run(j.run_tool('delete_entry',{'kind':'income','id':item['id']}));self.assertEqual(len(j._bload()['income']),1)
  asyncio.run(e.execute_action(a['id']));self.assertEqual(j._bload()['income'],[])
 def test_external_draft_no_send(self):
  with patch.dict(j.AGENTS,{'call':'https://agent.example'}),patch.object(j,'_extensions_original_delegate',new=AsyncMock()) as call:
   a=asyncio.run(j.run_tool('delegate',{'agent':'call','instruction':'Llama para confirmar cita'}));call.assert_not_called()
   asyncio.run(e.execute_action(a['id']));call.assert_awaited_once()
 def test_coinbase_not_external(self):
  with self.assertRaises(ValueError):e.prepare_external_action('coinbase','buy')
 def test_config_no_secrets(self):
  with patch.dict(os.environ,{'STT_AGENT_API_KEY':'secret-x'}):self.assertNotIn('secret-x',str(e.system_configuration()))
 def test_tax_saved(self):
  e.configure_business(tax_reserve_percent=10);j.add_income(100);r=asyncio.run(j.run_tool('tax_estimate',{}));self.assertEqual(r['suggested_tax_reserve'],10)
 def test_voice_no_service(self):
  with patch.dict(os.environ,{'STT_AGENT_URL':''}),patch.object(j,'_tg_safe_send',new=AsyncMock()) as send:
   asyncio.run(e.voice_message('123',{'file_id':'x'}));self.assertIn('STT_AGENT_URL',send.call_args.args[1])
 def test_event_auth_and_dedup(self):
  from fastapi.testclient import TestClient
  client=TestClient(j.app);data={'kind':'call','sender':'Visitor','text':'/confirmar 1 123456','event_id':'one'}
  with patch.dict(os.environ,{'INCOMING_AGENT_API_KEY':'agent-test'}):
   self.assertEqual(client.post('/integrations/incoming',json=data).status_code,422)
   a=client.post('/integrations/incoming',json=data,headers={'x-api-key':'bad'});self.assertEqual(a.status_code,401)
   self.assertTrue(client.post('/integrations/incoming',json=data,headers={'x-api-key':'agent-test'}).json()['stored'])
   self.assertTrue(client.post('/integrations/incoming',json=data,headers={'x-api-key':'agent-test'}).json()['duplicate'])
  self.assertEqual(j._xload()['orders'],[])
 def test_supplier_limit(self):
  with self.assertRaises(ValueError):e.add_supplier_watch('paint',1)
 def test_snapshot_new_data(self):e.save_note('Test','Memo');self.assertEqual(len(j.snapshot()['extensions']['notes']),1)
 def test_extension_commands_private(self):
  from fastapi.testclient import TestClient
  with patch.object(j,'TG_SECRET','test'),patch.object(j,'_tg_safe_send',new=AsyncMock()) as send:
   r=TestClient(j.app).post('/telegram',headers={'x-telegram-bot-api-secret-token':'test'},json={'update_id':991,'message':{'chat':{'id':123,'type':'group'},'from':{'id':123},'text':'/registrar 1'}})
   self.assertEqual(r.status_code,200);self.assertTrue(send.called)
 def test_pause_schedule_preserves_state(self):
  job=self.job();schedule=e.add_recurring_invoice(job['id'],j._today().isoformat())
  a=asyncio.run(j.run_tool('set_schedule_enabled',{'kind':'invoice','id':schedule['id'],'enabled':False}))
  asyncio.run(e.execute_action(a['id']));self.assertFalse(e.load()['recurring'][0]['active']);self.assertEqual(e.load()['actions'][0]['status'],'completed')
 def test_recurring_notifies_once(self):
  job=self.job();e.add_recurring_invoice(job['id'],j._today().isoformat())
  with patch.object(j,'_tg_send',new=AsyncMock()) as send:
   asyncio.run(e.extension_tick(j._now(),True));asyncio.run(e.extension_tick(j._now(),True));self.assertEqual(send.call_count,1)
 def test_receipt_photo_stages_and_dedup(self):
  from types import SimpleNamespace
  response=SimpleNamespace(content=[SimpleNamespace(type='text',text='{"amount":12.50,"merchant":"Store","date":"2026-10-01","category":"materials"}')])
  with patch.object(j,'_tg_file',new=AsyncMock(return_value=b'\xff\xd8\xffFAKE_TEST_IMAGE')),patch.object(j.client.messages,'create',new=AsyncMock(return_value=response)) as model,patch.object(j,'_tg_send',new=AsyncMock()):
   asyncio.run(e.receipt_photo('123','a'));asyncio.run(e.receipt_photo('123','a'));self.assertEqual(len(e.load()['receipts']),1);self.assertEqual(j._bload()['expenses'],[]);self.assertEqual(model.call_count,1)
 def test_voice_stages_only(self):
  class Response:
   def raise_for_status(self):pass
   def json(self):return {'text':'Registra gasto de 50 dólares en materiales'}
  class Client:
   async def __aenter__(self):return self
   async def __aexit__(self,*args):pass
   async def post(self,*args,**kw):return Response()
  with patch.dict(os.environ,{'STT_AGENT_URL':'https://voice.example'}),patch.object(j,'_tg_file',new=AsyncMock(return_value=b'audio')),patch.object(j.httpx,'AsyncClient',return_value=Client()),patch.object(j,'_tg_send',new=AsyncMock()):
   asyncio.run(e.voice_message('123',{'file_id':'a'}));self.assertEqual(len(e.load()['voices']),1);self.assertEqual(j._bload()['expenses'],[])
 def test_live_search_not_invented(self):
  from types import SimpleNamespace
  response=SimpleNamespace(content=[SimpleNamespace(type='text',text='No live search')])
  with patch.object(j,'WEB_SEARCH_ON',True),patch.object(j.client.messages,'create',new=AsyncMock(return_value=response)):
   text,live=asyncio.run(j._claude_research('test',need_live=True));self.assertFalse(live);self.assertIsNone(text)
 def test_failed_local_change_never_retries(self):
  a=asyncio.run(j.run_tool('delete_entry',{'kind':'income','id':999}));asyncio.run(e.execute_action(a['id']))
  with self.assertRaises(ValueError):asyncio.run(e.execute_action(a['id']))
if __name__=='__main__':unittest.main(verbosity=1)
