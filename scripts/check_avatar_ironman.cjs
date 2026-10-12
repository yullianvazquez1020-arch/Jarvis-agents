/* Torre de Aincrad (desktop/ui/aincrad.js): cien pisos, cinco sectores, cuentas y rótulo de demo.
   Datos ficticios; no toca el servidor, la red ni dinero. Uso: node scripts/check_avatar_ironman.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const A = require('../desktop/ui/aincrad.js');

// 1. Cien pisos en cinco sectores de veinte.
const demo = A.demoFloors();
assert.equal(A.FLOORS, 100);
assert.equal(demo.length, 100, 'la torre tiene cien pisos');
assert.equal(A.SECTORS.length, 5);
const perSector = {};
demo.forEach(f => { perSector[f.sector] = (perSector[f.sector] || 0) + 1; });
assert.deepEqual(Object.values(perSector), [20, 20, 20, 20, 20], 'veinte pisos por sector');
assert.equal(A.sectorIndex(1), 0); assert.equal(A.sectorIndex(20), 0);
assert.equal(A.sectorIndex(21), 1); assert.equal(A.sectorIndex(100), 4);
assert.throws(() => A.sectorIndex(0)); assert.throws(() => A.sectorIndex(101));
console.log('PASS: 100 pisos, 5 sectores de 20, rangos validados');

// 2. La demo es determinista: la misma semilla da los mismos números.
assert.deepEqual(A.demoFloors(7)[0], A.demoFloors(7)[0]);
assert.notEqual(A.demoFloors(7)[0].gross, A.demoFloors(8)[0].gross);
assert.deepEqual(A.demoFloors()[42], A.demoFloors()[42], 'misma semilla, mismas cifras');
console.log('PASS: cifras de demostración deterministas');

// 3. Cuentas: neto = bruto - costos, y los totales cuadran con la suma pisos a piso.
const f = { floor: 3, sector: 'x', name: 'x', gross: 100.5, cost: 40.25, demo: true };
assert.equal(A.net(f), 60.25, 'neto = bruto - costos');
const t = A.totals(demo);
assert.equal(t.floors, 100); assert.equal(t.counted, 100);
const sumG = Math.round(demo.reduce((a, x) => a + x.gross, 0) * 100) / 100;
const sumC = Math.round(demo.reduce((a, x) => a + x.cost, 0) * 100) / 100;
assert.equal(t.gross, sumG); assert.equal(t.cost, sumC);
assert.equal(t.net, Math.round((sumG - sumC) * 100) / 100, 'el neto total cuadra');
assert.ok(demo.every(x => x.cost < x.gross), 'ningún piso de demo pierde dinero por error de signo');
console.log(`PASS: cuentas correctas · bruto ${A.money(t.gross)} · costos ${A.money(t.cost)} · neto ${A.money(t.net)}`);

// 4. Sin cifras no se inventa nada: ni neto, ni totales, ni texto de dinero.
const empty = A.emptyFloors();
assert.equal(empty.length, 100);
assert.equal(A.net(empty[0]), null, 'sin datos no hay neto');
const te = A.totals(empty);
assert.equal(te.counted, 0); assert.equal(te.gross, 0); assert.equal(te.net, 0);
assert.equal(A.money(null), 'sin datos');
assert.equal(A.money(undefined), 'sin datos');
assert.equal(A.money(NaN), 'sin datos');
console.log('PASS: pisos sin datos no producen cifras inventadas');

// 5. La ficha siempre dice de dónde salen las cifras.
const cardDemo = A.floorCard(demo[0]);
assert.equal(cardDemo.demo, true);
assert.match(cardDemo.notice, /[Dd]atos demo/);
assert.equal(cardDemo.rows.length, 3);
assert.deepEqual(cardDemo.rows.map(r => r.label), ['Ingreso bruto', 'Costos', 'Ganancia neta']);
assert.match(cardDemo.title, /^Piso 1 · /);
assert.match(cardDemo.sector, /pisos 1–20/);
const cardReal = A.floorCard(empty[99]);
assert.equal(cardReal.demo, false);
assert.match(cardReal.notice, /[Ss]in datos reales por piso/);
assert.equal(cardReal.rows[2].value, 'sin datos', 'un piso sin libro no muestra una ganancia falsa');
assert.match(cardReal.sector, /Sector 5 · .* · pisos 81–100/);
console.log('PASS: cada ficha declara si es demo o si no hay datos reales');

// 6. Geometría de la torre: sube monótona y se estrecha arriba (Aincrad).
assert.equal(A.floorHeight(1), 0); assert.equal(A.floorHeight(100), 1);
let prevY = -1, prevR = 99;
for (let n = 1; n <= 100; n++) {
  const y = A.floorHeight(n), r = A.floorRadius(n);
  assert.ok(y > prevY || n === 1, 'cada piso queda más alto');
  assert.ok(r <= prevR + 1e-9, 'cada piso es igual o más angosto');
  assert.ok(r > 0.3 && r <= 1, 'radio dentro de rango dibujable');
  prevY = y; prevR = r;
}
console.log('PASS: cien pisos apilados y estrechándose hacia la cima');

// 7. El brillo del núcleo sigue la amplitud y nunca se sale de rango.
assert.ok(A.IDLE_GLOW > 0 && A.IDLE_GLOW < 1, 'en reposo el núcleo ni se apaga ni se satura');
assert.equal(A.coreGlow(0), A.IDLE_GLOW);
assert.equal(A.coreGlow(1), 1);
assert.equal(A.coreGlow(5), 1, 'recorta por encima de 1');
assert.equal(A.coreGlow(-2), A.IDLE_GLOW, 'recorta por debajo de 0');
assert.equal(A.coreGlow('x'), A.IDLE_GLOW, 'una amplitud inválida no apaga la escena');
assert.ok(A.coreGlow(0.5) > A.coreGlow(0.2), 'más voz, más brillo');
console.log('PASS: amplitud de Piper -> brillo, con recorte');

// 8. Guardas de la vista: nada de TTS externo, nada de CDN, nada de innerHTML.
const files = ['desktop/ui/aincrad.js', 'desktop/ui/ironman.js', 'desktop/ui/ironman.html', 'desktop/ui/ironman.css'];
for (const name of files) {
  const src = fs.readFileSync(name, 'utf8');
  for (const bad of ['ttsEndpoint', 'ttsApikey', 'speechSynthesis', 'SpeechSynthesisUtterance',
                     'openai', 'googleapis', 'elevenlabs', 'innerHTML', 'outerHTML',
                     'insertAdjacentHTML', 'document.write', 'eval(']) {
    assert.ok(!src.includes(bad), `${name} no debe contener ${bad}`);
  }
  assert.ok(!/https?:\/\//.test(src), `${name} no debe pedir nada a internet`);
}
const scene = fs.readFileSync('desktop/ui/ironman.js', 'utf8');
assert.ok(scene.includes('setPixelRatio(1)'), 'pixelRatio fijo en 1 para el Mac 2015');
for (const pass of ['EffectComposer', 'UnrealBloomPass', 'BloomPass', 'postprocessing']) {
  assert.ok(!scene.includes(pass), `sin posproceso: ${pass} fundiría el Mac 2015`);
}
assert.ok(scene.includes('document.hidden'), 'la pestaña oculta detiene el dibujo');
assert.ok(scene.includes('visibilitychange'), 'se escucha el cambio de visibilidad');
assert.ok(scene.includes('./vendor/three/three.module.js'), 'Three.js se carga local');
assert.ok(/no mueve dinero/i.test(scene), 'la vista declara que solo muestra');
console.log('PASS: sin TTS externo, sin CDN, sin innerHTML, pixelRatio 1 y pausa por pestaña oculta');

console.log(`RESUMEN: ${demo.length} pisos de demostración, ${A.SECTORS.length} sectores, 8 bloques de comprobación.`);

// Regresión: los totales demo desaparecen al consultar los paneles.
const vm = require('node:vm');
const noticeSource = scene.slice(scene.indexOf('function refreshNotice()'), scene.indexOf('/* ---------------------------------------------------------------- lista'));
const totalNode = {textContent: ''};
const context = {A, realData: false, floors: A.demoFloors(), dataNotice: {classList: {toggle(){}}},
  noticeText: () => '', say: (node, text) => {node.textContent = text;}, el: () => totalNode};
vm.createContext(context);
vm.runInContext(noticeSource + '\nrefreshNotice();', context);
assert.match(totalNode.textContent, /^DEMO/);
context.realData = true; context.floors = A.emptyFloors();
vm.runInContext('refreshNotice();', context);
assert.match(totalNode.textContent, /sin datos reales/);
assert.ok(!totalNode.textContent.includes('$'));
context.realData = false; context.floors = A.demoFloors();
vm.runInContext('refreshNotice();', context);
assert.match(totalNode.textContent, /^DEMO/);

// Regresión: pausa congela el shader, elimina parpadeo y conserva respuesta al audio.
const frameSource = scene.slice(scene.indexOf('function frame(now)'), scene.indexOf('function start()'));
const uniforms = {uTime:{value:0}, uLevel:{value:0}, uGlow:{value:0}, uBlink:{value:0}};
Object.assign(context, {running:true, requestAnimationFrame(){}, document:{hidden:false}, last:1,
  paused:true, motionTime:2, voiceLevel:()=>0.5, coreMat:{uniforms}, blink:1,
  core:{scale:{setScalar(v){context.scale=v;}}}, renderer:{render(){}}, scene:{}, camera:{}});
vm.runInContext(frameSource + '\nframe(100); frame(200);', context);
assert.equal(uniforms.uTime.value, 2);
assert.equal(uniforms.uBlink.value, 0);
assert.equal(context.scale, 1.05);
console.log('PASS: totales demo separados y pausa sin parpadeos con audio conservado');
