/* La decision de interrumpir, probada sin microfono ni navegador.

   Lo que importa aqui no es que corte: es que NO se corte solo. Si la voz del propio Jarvis
   lo calla, el resultado es peor que no tener interrupcion. */
const assert = require("assert");
const { Decisor } = require("../desktop/ui/barge-in.js");

function correr(d, muestras, paso) {   // muestras: niveles; paso: ms entre cada una
  let t = 0, corto = false;
  d.empezar(t);
  for (const nivel of muestras) { t += paso; if (d.push(nivel, t)) { corto = true; break; } }
  return { corto, t };
}
const d = () => new Decisor({ umbral: 0.18, gracia: 450, sostenido: 180 });
const rep = (n, v) => Array(n).fill(v);

// 1. Silencio: nunca corta.
assert.strictEqual(correr(d(), rep(100, 0.0), 20).corto, false, "cortó con silencio");

// 2. Eco de su propia voz: por debajo del umbral aunque dure mucho.
assert.strictEqual(correr(d(), rep(200, 0.12), 20).corto, false, "el eco propio lo calló");

// 3. El dueño habla: fuerte y sostenido -> corta.
const hablando = correr(d(), rep(100, 0.45), 20);
assert.strictEqual(hablando.corto, true, "no cortó cuando el dueño habló");

// 4. Un golpe suelto (tos, clic, portazo): fuerte pero corto -> NO corta.
assert.strictEqual(correr(d(), [...rep(30, 0.0), 0.9, 0.9, ...rep(60, 0.0)], 20).corto, false,
  "un golpe suelto lo calló");

// 5. Periodo de gracia: ni gritando corta en los primeros 450 ms.
const temprano = new Decisor({ umbral: 0.18, gracia: 450, sostenido: 180 });
temprano.empezar(0);
for (let t = 20; t <= 440; t += 20) assert.strictEqual(temprano.push(0.9, t), false,
  "cortó dentro del periodo de gracia");

// 6. Pasada la gracia, tarda lo sostenido y ni un paso menos.
const tras = new Decisor({ umbral: 0.18, gracia: 450, sostenido: 180 });
tras.empezar(0);
assert.strictEqual(tras.push(0.9, 500), false);          // primera por encima: arranca la cuenta
assert.strictEqual(tras.push(0.9, 600), false);          // 100 ms: todavia no
assert.strictEqual(tras.push(0.9, 680), true);           // 180 ms: ahora si

// 7. La voz entrecortada reinicia la cuenta: no se suman trozos sueltos.
const roto = new Decisor({ umbral: 0.18, gracia: 0, sostenido: 180 });
roto.empezar(0);
let cortoRoto = false;
for (let i = 1; i <= 40; i++) if (roto.push(i % 2 ? 0.9 : 0.0, i * 40)) cortoRoto = true;
assert.strictEqual(cortoRoto, false, "sumó trozos sueltos como si fueran voz continua");

// 8. Sin haber empezado a hablar Jarvis, nada corta.
const quieto = new Decisor();
assert.strictEqual(quieto.push(0.9, 9999), false, "cortó sin que Jarvis estuviera hablando");

// 9. Umbral mas alto = mas dificil cortarlo (lo que el dueño sube si se corta solo).
assert.strictEqual(correr(new Decisor({ umbral: 0.5, gracia: 450, sostenido: 180 }), rep(100, 0.45), 20).corto,
  false, "el umbral alto no protegió");

console.log("interrumpir: 9 comprobaciones OK");
