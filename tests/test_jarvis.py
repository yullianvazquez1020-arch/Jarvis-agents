import os,sys,tempfile,importlib.util,asyncio,unittest,datetime,copy
from unittest.mock import patch
for name in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):os.environ.pop(name,None)
os.environ.update(ANTHROPIC_API_KEY='test-local-only',AGENT_API_KEY='test-local-only',DATA_DIR=tempfile.mkdtemp(),COINBASE_TRADING_ENABLED='false',TELEGRAM_OWNER_ID='123',TELEGRAM_OWNER_USER_ID='123')
ROOT=__import__('pathlib').Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('jarvis', ROOT/'main.py'); j=importlib.util.module_from_spec(spec);sys.modules['jarvis']=j;spec.loader.exec_module(j)
class Tests(unittest.TestCase):
 def setUp(self):
  j.DATA_DIR=__import__('pathlib').Path(tempfile.mkdtemp());j.USE_REDIS=False;j._seen_updates.clear(); j._rate_hits.clear();j._fence.update(mode="off",leader=True)
 def test_real_trading_disabled(self): self.assertFalse(j.CB_TRADING)
 def test_money_invalid(self):
  for v in [True,-1,0,'nan','inf',1e15]:
   with self.subTest(v=v),self.assertRaises(ValueError):j._money(v)
 def test_money_rounding(self): self.assertEqual(j._money('12.345'),12.35)
 def test_books(self):
  a=j.add_income(100);b=j.add_expense(30);self.assertEqual(j.finances_summary()['net_profit'],70)
 def test_job_payments_not_merged(self):
  c=j.add_client('Test',phone='7875551234');job=j.add_job(c['id'],'Repair',price=100)
  j.add_income(25,source='unrelated');j.record_job_payment(job['id'],25)
  self.assertEqual(len(j._bload()['income']),2)
 def test_overpayment(self):
  c=j.add_client('Test');job=j.add_job(c['id'],'Repair',price=100)
  with self.assertRaises(ValueError):j.record_job_payment(job['id'],101)
  self.assertEqual(j._cload()['jobs'][0]['balance'],100)
 def test_inventory(self):
  a=j.add_inventory_item('Paint',quantity=1,min_stock=2);self.assertEqual(len(j.collect_stock_alerts()),1)
  j.mark_stock_alert({'id':a['id']});self.assertEqual(j.collect_stock_alerts(),[])
  j.adjust_inventory(a['id'],5);j.adjust_inventory(a['id'],-5);self.assertEqual(len(j.collect_stock_alerts()),1)
 def test_inventory_negative(self):
  a=j.add_inventory_item('Paint',quantity=1)
  with self.assertRaises(ValueError):j.adjust_inventory(a['id'],-2)
 def test_pending_drafts_retained(self):
  c=j.add_client('Test',phone='7875551234')
  for n in range(35):j.prepare_client_message(c['id'],f'Test {n}')
  self.assertEqual(len(j._oload()['drafts']),35)
 def test_revise_draft(self):
  c=j.add_client('Test',phone='7875551234');m=j.prepare_client_message(c['id'],'Old');n=j.revise_client_message(m['id'],'New')
  self.assertGreater(n['id'],m['id']);self.assertEqual(j._oload()['drafts'][0]['status'],'replaced')
 def test_rsi_flat(self):self.assertEqual(j._rsi([100]*60),50)
 def test_paper_buy_sell(self):
  d=j._paper_new(1000);j._paper_buy(d,'BTC-USD',100,250,'test');self.assertEqual(d['cash'],750)
  t=j._paper_sell(d,'BTC-USD',110,'test');self.assertAlmostEqual(d['cash']-1000,t['pnl'],places=2)
  self.assertGreater(d['fees'],0);self.assertEqual(d['positions'],{})
 def test_paper_stops(self):
  d=j._paper_new(1000);j._paper_buy(d,'BTC-USD',100,250,'test')
  ev=j._paper_apply(d,{'BTC-USD':{'price':90,'sma20':100,'sma50':95,'trend':'bajista','rsi':30}})
  self.assertEqual(ev[0]['side'],'sell');self.assertLess(ev[0]['pnl'],0)
 def test_reminder_reactivated(self):
  due=(j._now()-datetime.timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M');r=j.add_reminder('test',due=due)
  j.mark_alert_sent({'kind':'reminder','id':r['id'],'due':due});j.edit_entry('reminder',r['id'],{'repeat':'daily'})
  alerts=j.collect_alerts();self.assertTrue(any(a['id']==r['id'] for a in alerts));j.mark_alert_sent(alerts[0]);self.assertGreater(j._due_dt(j._pload()['reminders'][0]['due']),j._now())
 def test_monthly_anchor(self):
  with patch.object(j,'_now',return_value=datetime.datetime(2026,2,28,12,tzinfo=j.TZ)):
   self.assertEqual(j._roll('2026-02-28 09:00','monthly',31),'2026-03-31 09:00')
 def test_midnight_forward(self):
  date=j._today()+datetime.timedelta(days=1)
  j.add_event('early',(date+datetime.timedelta(days=1)).isoformat(),time='00:15',duration_min=60)
  a=j.add_event('late',date.isoformat(),time='23:30',duration_min=120);self.assertIn('warning_conflicts',a)
 def test_midnight_backward(self):
  date=j._today()+datetime.timedelta(days=1);j.add_event('late',date.isoformat(),time='23:30',duration_min=120)
  a=j.add_event('early',(date+datetime.timedelta(days=1)).isoformat(),time='00:15',duration_min=60);self.assertIn('warning_conflicts',a)
 def test_gate_limits(self):
  g=j._gload();self.assertTrue(j.gate_limits_problem(g,101));j.gate_add_spent(g,250);self.assertTrue(j.gate_limits_problem(g,60))
 def test_tools_registered(self):
  for t in j.TOOLS:self.assertIn(t['name'],set(j.HANDLERS)|set(j.ASYNC_TOOLS))
 def test_provider_missing_id(self):
  class R:
   status_code=200
   def json(self):return {}
  class H:
   async def __aenter__(self):return self
   async def __aexit__(self,*a):pass
   async def post(self,*a,**kw):return R()
  with patch.object(j.httpx,'AsyncClient',return_value=H()):
   with self.assertRaises(RuntimeError):asyncio.run(j._send_sms('+17875551234','test'))
   with self.assertRaises(RuntimeError):asyncio.run(j._send_email('a@b.com','test','test',1))
 def test_webhook_reject_stranger(self):
  from fastapi.testclient import TestClient
  j.TG_SECRET='test-secret';client=TestClient(j.app)
  r=client.post('/telegram',headers={'x-telegram-bot-api-secret-token':'test-secret'},json={'update_id':1,'message':{'chat':{'id':123,'type':'private'},'from':{'id':999},'text':'/enviar 1'}})
  self.assertEqual(r.status_code,200);self.assertEqual(j._oload()['drafts'],[])
 def test_webhook_secret(self):
  from fastapi.testclient import TestClient
  j.TG_SECRET='test-secret';self.assertEqual(TestClient(j.app).post('/telegram',json={}).status_code,401)
 def test_health(self):
  from fastapi.testclient import TestClient
  self.assertFalse(TestClient(j.app).get('/').json()['coinbase']['trading'])
 def test_coinbase_double_approval(self):
  async def cb(method,path,**kw):
   if path.endswith('/preview'):return {'order_total':'20','commission_total':'0.2'}
   if path.endswith('/orders'):return {'success':True,'success_response':{'order_id':'mock-order'}}
   return {'price':'100'}
  # 4.0.3: real orders need the owner to have selected REAL mode (and variables that allow it)
  j.kv_set(j.M_KEY,{'mode':'real','epoch':1,'since':None,'by':'test','history':[]})
  with patch.object(j,'CB_ON',True),patch.object(j,'CB_TRADING',True),patch.object(j,'real_blockers',return_value=[]),patch.object(j,'_cb',side_effect=cb) as api:
   o=asyncio.run(j.coinbase_prepare_order('BTC','BUY',usd_amount=20));oid=o['order']
   self.assertEqual(j._xload()['orders'][0]['status'],'pending')
   msg=j.cb_approve_text(str(oid));code=__import__('re').search(r'\b\d{6}\b',msg).group()
   r=asyncio.run(j.cb_confirm_text(f'{oid} {code}'));self.assertIn('Orden enviada',r)
   again=asyncio.run(j.cb_confirm_text(f'{oid} {code}'));self.assertNotIn('Orden enviada',again)
   self.assertEqual(sum(c.args[1].endswith('/orders') for c in api.call_args_list),1)
 def test_market_invalid_ticker(self):
  now=j._now().timestamp();rows=[[int(now-3600*(n+2)),1,1,1,100,1] for n in range(65)]
  async def data(path,params=None):return rows if path.endswith('candles') else {}
  with patch.object(j,'_cb_public',side_effect=data):
   with self.assertRaises(ValueError):asyncio.run(j.paper_market('BTC'))
 def test_market_stale(self):
  async def data(path,params=None):return [[1,1,1,1,100,1]]*65
  with patch.object(j,'_cb_public',side_effect=data):
   with self.assertRaises(ValueError):asyncio.run(j.paper_market('BTC'))
 def test_market_valid(self):
  now=j._now();rows=[[int(now.timestamp()-3600*(n+2)),1,1,1,100+n%4,1] for n in range(65)]
  async def data(path,params=None):return rows if path.endswith('candles') else {'price':'105','time':now.isoformat()}
  with patch.object(j,'_cb_public',side_effect=data):self.assertEqual(asyncio.run(j.paper_market('BTC'))['price'],105)
 def test_multiday_conflict(self):
  date=j._today()+datetime.timedelta(days=1);j.add_event('long',date.isoformat(),time='10:00',duration_min=4000)
  a=j.add_event('during',(date+datetime.timedelta(days=2)).isoformat(),time='11:00',duration_min=60);self.assertIn('warning_conflicts',a)
if __name__=='__main__':unittest.main(verbosity=2)
