import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from desktop_helpers import DesktopBase,D,j
from browser_control import public_url,snapshot,proposal
from scripts import browser_mac as mac

PAGE={'url':'https://example.com/editor','title':'Editor','elements':[
 {'id':0,'tag':'input','type':'text','label':'Título','href':''},
 {'id':1,'tag':'button','type':'submit','label':'Publicar','href':''}]}
CLICK={'action':'click','target':1,'reason':'Publicar el contenido revisado'}

class Policy(unittest.TestCase):
    def test_private_financial_and_secret_urls(self):
        for url in ['file:///etc/passwd','https://127.0.0.1','https://paypal.com',
                    'https://example.com/checkout','https://example.com/?%74oken=abc',
                    'https://u:p@example.com','https://a.local','https://example.com:99']:
            with self.subTest(url=url),self.assertRaises(ValueError):public_url(url)

    def test_no_arbitrary_action_or_unobserved_target(self):
        for action in [{'action':'shell','text':'ls'},{'action':'click','target':44},
                       {'action':'click','target':True},{'action':'fill','target':1,'text':'x'}]:
            with self.subTest(action=action),self.assertRaises(ValueError):proposal(action,PAGE)

    def test_values_and_unknown_fields_never_leave_snapshot(self):
        page=copy.deepcopy(PAGE);page['cookies']='secret';page['elements'][0]['value']='secret'
        self.assertNotIn('secret',json.dumps(snapshot(page)))

    def test_private_fields_and_links_rejected(self):
        for change in [{'type':'password'},{'label':'Código OTP'},{'href':'https://example.com/?session=secret'}]:
            page=copy.deepcopy(PAGE);page['elements'][0].update(change)
            with self.assertRaises(ValueError):snapshot(page)

class LocalApproval(unittest.TestCase):
    def setUp(self):
        self.stop=patch.object(mac,'stopped',return_value=False);self.stop.start();self.addCleanup(self.stop.stop)
        self.print=patch('builtins.print');self.print.start();self.addCleanup(self.print.stop)
        self.browser=Mock();self.browser.observe.return_value=PAGE

    def approve(self,prompt):return prompt.split()[1]

    def test_cancel_performs_nothing(self):
        self.assertEqual(mac.approve_and_execute(self.browser,CLICK,PAGE,ask=lambda _:''),'cancelled')
        self.browser.act.assert_not_called()

    def test_exact_local_code_executes_once(self):
        self.assertEqual(mac.approve_and_execute(self.browser,CLICK,PAGE,ask=self.approve),'executed')
        self.browser.act.assert_called_once_with(CLICK,PAGE)

    def test_changed_page_stops(self):
        self.browser.observe.return_value={**PAGE,'title':'Changed'}
        with self.assertRaises(RuntimeError):mac.approve_and_execute(self.browser,CLICK,PAGE,ask=self.approve)
        self.browser.act.assert_not_called()

    def test_expiry_and_stop_after_approval(self):
        with self.assertRaises(RuntimeError):
            mac.approve_and_execute(self.browser,CLICK,PAGE,ask=self.approve,clock=Mock(side_effect=[0,91]))
        with patch.object(mac,'stopped',side_effect=[False,True]),self.assertRaises(RuntimeError):
            mac.approve_and_execute(self.browser,CLICK,PAGE,ask=self.approve)
        self.browser.act.assert_not_called()

    def test_timeout_does_not_retry(self):
        self.browser.act.side_effect=RuntimeError('unknown')
        with self.assertRaises(RuntimeError):mac.approve_and_execute(self.browser,CLICK,PAGE,ask=self.approve)
        self.browser.act.assert_called_once()

    def test_script_is_fixed_and_data_is_not_shell_code(self):
        browser=object.__new__(mac.Safari);browser.window='123';browser.current_url=Mock(return_value=PAGE['url'])
        browser._call=Mock(return_value='hecho')
        value='"; alert(1); // `$(touch bad)`'
        browser.act({'action':'fill','target':0,'text':value},PAGE)
        script=browser._call.call_args.args[2]
        self.assertIn(json.dumps(value),script)
        self.assertIn('JSON.stringify(state)!==JSON.stringify(expected)',script)

class BrowserAPI(DesktopBase):
    def send(self,token='',page=None):
        return self.client.post('/browser/v1/propose',headers=self.hdr(token),json={'task':'Prepara el título','page':page or PAGE})

    def test_missing_revoked_and_disabled_pairing(self):
        self.assertEqual(self.send().status_code,401)
        token,dev_id=self.pair()
        with patch.object(D,'ENABLED',False):self.assertEqual(self.send(token).status_code,404)
        data=D.load();data['devices'][dev_id]['revoked']=True;D.save(data)
        self.assertEqual(self.send(token).status_code,401)

    def test_proposal_has_no_execution_or_business_tools(self):
        token,_=self.pair()
        out=SimpleNamespace(text=json.dumps({'action':'fill','target':0,'text':'Servicio IslaFix'}),tokens=20,truncated=False)
        with patch.object(j,'AI_READY',True),patch.object(j,'llm_text',new=AsyncMock(return_value=out)) as ai,patch.object(j,'run_tool',new=AsyncMock(side_effect=AssertionError('no tools'))) as tool:
            r=self.send(token)
        self.assertEqual(r.status_code,200);self.assertFalse(r.json()['executed'])
        self.assertEqual(r.json()['proposal']['text'],'Servicio IslaFix')
        tool.assert_not_called();self.assertEqual(len(ai.call_args.args),4)

    def test_invalid_model_output_never_passes(self):
        token,_=self.pair()
        out=SimpleNamespace(text='{"action":"shell","command":"whoami"}',tokens=1,truncated=False)
        with patch.object(j,'AI_READY',True),patch.object(j,'llm_text',new=AsyncMock(return_value=out)):
            self.assertEqual(self.send(token).status_code,400)

    def test_body_size_and_bad_page_before_ai(self):
        token,_=self.pair()
        with patch.object(j,'llm_text',new=AsyncMock()) as ai:
            r=self.client.post('/browser/v1/propose',headers=self.hdr(token),content='x'*32001)
            self.assertEqual(r.status_code,413)
            self.assertEqual(self.send(token,{**PAGE,'url':'https://paypal.com'}).status_code,400)
        ai.assert_not_called()
