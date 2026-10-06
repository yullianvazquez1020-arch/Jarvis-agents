import asyncio, copy, datetime, os, unittest
from unittest.mock import AsyncMock, patch
import test_extensions as base
j=base.j;g=j._growth
COSTS=dict(unit_cost=3,units=100,shipping_total=100,duties_total=20,other_total=30,sale_price=15,referral_percent=15,fulfillment_per_unit=3,ads_per_unit=1,returns_percent=5,fixed_monthly=40,expected_monthly_units=100)
def plan():
 return dict(title='Contamos tres estrellas',description='Una historia original de números.',language='es',scenes=[dict(text=f'{i} estrellas',narration=f'Contemos {i} estrellas.',color='#F5B841',shape='star',count=i,seconds=4) for i in (1,2,3)])
class GrowthTests(base.ExtensionTests):
 def test_costs(self):
  v=g.product_economics(**COSTS);self.assertEqual(v['landed_per_unit'],4.5);self.assertEqual(v['net_per_unit'],3.1);self.assertEqual(v['scenario_monthly_profit'],310)
 def test_bad_costs(self):
  for key,value in [('unit_cost',float('nan')),('units',0),('units',1.5),('referral_percent',100),('shipping_total',-1)]:
   with self.subTest(key=key),self.assertRaises(ValueError):g.product_economics(**{**COSTS,key:value})
 def test_supplier_domain(self):
  with self.assertRaises(ValueError):g.save_product_candidate('Test','https://alibaba.com.evil.example/x',COSTS)
 def test_saved_product(self):
  g.save_product_candidate('Test','https://www.alibaba.com/product-detail/test',COSTS);self.assertEqual(len(g.list_products()['products']),1)
 def test_growth_backup(self):
  g.growth_settings(target_margin_percent=30);self.assertEqual(j.snapshot()['growth']['settings']['target_margin_percent'],30)
 def test_margin_floor(self):
  c=j.add_client('Test');job=j.add_job(c['id'],'Trabajo',price=100,cost=60);self.assertEqual(g.job_margin(job['id'],25)['minimum_price_for_target'],80)
 def test_followup_dedupe(self):
  c=j.add_client('Test',phone='7875551234');job=j.add_job(c['id'],'Test',price=100)
  d=j._cload();d['jobs'][0]['created']=(j._today()-datetime.timedelta(days=10)).isoformat();j._csave(d)
  a=g.prepare_growth_message('quote',job['id']);b=g.prepare_growth_message('quote',job['id']);self.assertEqual(a['id'],b['existing_draft']);self.assertEqual(j._oload()['drafts'][0]['status'],'pending')
 def test_eval_initial(self):self.assertIn('insuficiente',g.paper_evaluation()['sample_assessment'])
 def test_paper_risk_stops_buys(self):
  d=j._paper_new(1000);d['risk']={'day':j._now().date().isoformat(),'day_start':1000,'peak':1200,'entries':0}
  events=g.paper_apply(d,{'BTC-USD':dict(price=100,sma20=101,sma50=99,trend='alcista',rsi=55)});self.assertEqual(events,[]);self.assertEqual(d['risk']['pause_reason'],'drawdown')
 def test_backtest_flat(self):
  rows=[[1700000000+i*3600,100,100,100,100] for i in range(150)];r=g.backtest_rows(rows);self.assertEqual(r['net_pnl'],0);self.assertEqual(r['closed_trades'],0)
 def test_backtest_minimum(self):
  with self.assertRaises(ValueError):g.backtest_rows([])
 def test_plan(self):self.assertTrue(g.validate_plan(plan())['made_for_kids'])
 def test_bad_plan(self):
  for k,v in [('count',1.5),('color','red'),('shape','mickey'),('seconds',200)]:
   p=plan();p['scenes'][0][k]=v
   with self.subTest(k=k),self.assertRaises(ValueError):g.validate_plan(p)
 def test_youtube_no_credentials(self):
  with patch.dict(os.environ,{'YOUTUBE_API_KEY':''}),self.assertRaises(ValueError):asyncio.run(g.youtube_research('colors'))
 def test_youtube_metadata(self):
  responses=[{'items':[{'id':{'videoId':'abc'}}]},{'items':[{'id':'abc','snippet':{'title':'Original','publishedAt':'2025-01-01T00:00:00Z'},'statistics':{'viewCount':'1000000'}}]}]
  with patch.dict(os.environ,{'YOUTUBE_API_KEY':'fake'}),patch.object(g,'_json_request',new=AsyncMock(side_effect=responses)):
   r=asyncio.run(g.youtube_research('colors'));self.assertEqual(r['videos'][0]['views'],1000000);self.assertIn('No he visto',r['limitations'])
 def test_amazon_approval_not_model_tool(self):
  self.assertNotIn('publish_listing',j.ASYNC_TOOLS);self.assertNotIn('upload_youtube',j.ASYNC_TOOLS)
 def test_amazon_preview(self):
  r=g.prepare_amazon_listing('SKU',{'productType':'TEST','attributes':{}})
  with patch.object(g,'_amazon_config',return_value=('seller','market','https://example.com')),patch.object(g,'_amazon_token',new=AsyncMock(return_value='fake')),patch.object(g,'_json_request',new=AsyncMock(return_value={'status':'VALID','issues':[]})) as req:
   self.assertTrue(asyncio.run(g.validate_amazon_listing(r['id']))['valid']);self.assertEqual(req.call_args.kwargs['params']['mode'],'VALIDATION_PREVIEW')
 def test_listing_no_duplicate_after_unknown(self):
  r=g.prepare_amazon_listing('SKU',{'productType':'TEST','attributes':{}});d=g.load();d['listings'][0].update(status='validated',seller='seller',market='market',validated_at=g.stamp());g.save(d)
  with patch.object(g,'_amazon_config',return_value=('seller','market','https://example.com')),patch.object(g,'_amazon_token',new=AsyncMock(return_value='fake')),patch.object(g,'_json_request',new=AsyncMock(side_effect=ValueError('timeout'))) as req:
   with self.assertRaises(ValueError):asyncio.run(g.publish_listing(r['id']))
   with self.assertRaises(ValueError):asyncio.run(g.publish_listing(r['id']))
   self.assertEqual(req.await_count,1);self.assertEqual(g.load()['listings'][0]['status'],'unknown')
 def test_channel_mismatch(self):
  with patch.dict(os.environ,{'YOUTUBE_CHANNEL_ID':'mine'}),patch.object(g,'_json_request',new=AsyncMock(return_value={'items':[{'id':'other'}]})),self.assertRaises(ValueError):asyncio.run(g._verify_channel('fake'))
if __name__=='__main__':unittest.main()
