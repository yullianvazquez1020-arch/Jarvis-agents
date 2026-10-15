/* Real Chromium UI integration with deterministic fake endpoints/devices; no AI calls. */
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES ? process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright' : 'playwright');
const http=require('node:http'), fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.join(__dirname,'..'), calls=[];
let owner=false;
const server=http.createServer((req,res)=>{
 const u=new URL(req.url,'http://localhost');calls.push(u.pathname);
 if(u.pathname==='/api/events')return; // event transport stays pending
 const json=x=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(x));};
 if(u.pathname==='/api/window/hello')return json({owner});
 if(u.pathname==='/api/audio/claim'){owner=true;return json({owner:true});}
 if(u.pathname==='/api/state')return json({prefs:{mic:true,rate:1},stt:{problem:''},tts:{problem:''},startup:{},server:{state:'ok'},processing:'Prueba local sin IA'});
 if(u.pathname==='/api/mouse-autonomo')return json({sesion:false,accesibilidad:{}});
 if(u.pathname==='/voice/transcribe')return json({text:'Abre Notas'});
 if(u.pathname.startsWith('/api/')||u.pathname.startsWith('/conversation/'))return json({});
 const file=u.pathname==='/'?path.join(root,'desktop/ui/index.html'):path.join(root,'desktop',u.pathname);
 if(!file.startsWith(path.join(root,'desktop/'))||!fs.existsSync(file)){res.statusCode=404;return res.end();}
 const ext=path.extname(file);res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.jpg':'image/jpeg'})[ext]||'application/octet-stream');res.end(fs.readFileSync(file));
});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
try{browser=await chromium.launch({executablePath:process.env.JARVIS_TEST_CHROME||undefined,headless:true,args:['--no-sandbox','--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
 const page=await browser.newPage({viewport:{width:1916,height:821}}), errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:'+server.address().port);await page.waitForFunction(()=>document.querySelector('#crystal-state').textContent==='LISTO');
 assert.equal(await page.locator('#claim').isVisible(),true);assert.equal(await page.locator('#talk').isDisabled(),true);
 const a=await page.locator('#crystal-motion').evaluate(c=>c.toDataURL());
 await page.waitForTimeout(500);const b=await page.locator('#crystal-motion').evaluate(c=>c.toDataURL());assert.notEqual(a,b,'rendered pixels must move');
 await page.screenshot({path:process.env.JARVIS_TEST_SCREENSHOT||'/tmp/jarvis-crystal-browser.png'});
 await page.locator('#claim').click();await page.waitForFunction(()=>document.querySelector('#crystal-state').textContent.startsWith('ESCUCHANDO'));
 await page.waitForFunction(()=>document.querySelector('#mic-source').options.length>1);
 assert.equal(await page.locator('#claim').isVisible(),false);
 await page.waitForTimeout(1200);await page.locator('#talk').click();await page.waitForFunction(()=>document.querySelector('#crystal-heard').textContent==='Abre Notas');
 assert(calls.includes('/voice/transcribe'));assert(calls.includes('/conversation/turns'));
 await page.emulateMedia({reducedMotion:'reduce'});await page.waitForTimeout(100);
 const still=await page.locator('#crystal-motion').evaluate(c=>c.toDataURL());await page.waitForTimeout(300);assert.equal(await page.locator('#crystal-motion').evaluate(c=>c.toDataURL()),still);
 assert.deepEqual(errors,[]);console.log('PASS: rendered motion, reduced motion, visible voice claim, fake mic capture, device selection and transcript-to-turn; zero page errors. STT response is a test stub.');
}finally{if(browser)await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));}})().catch(e=>{console.error(e);process.exitCode=1;});
