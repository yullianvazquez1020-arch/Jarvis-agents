/* El nucleo de los numeros vivos: sin DOM, sin reloj, sin navegador. */
const assert = require("assert");
const V = require("../desktop/ui/vivo.js");
let n = 0;
const ok = (c, m) => { assert.ok(c, m); n++; };
const eq = (a, b, m) => { assert.strictEqual(a, b, m); n++; };

// 1. Un numero con prefijo y sufijo se parte bien y se vuelve a armar igual.
const p = V.planear("$945.57", "$951.20");
eq(p.prefijo, "", "no hay texto antes del numero");
eq(p.moneda, "$", "la moneda viaja con el numero, no con el texto");
eq(p.sufijo, "", "sufijo");
eq(p.desde, 945.57, "desde");
eq(p.hasta, 951.2, "hasta");
eq(V.pintar(951.2, p), "$951.20", "al final pinta exactamente el valor nuevo");
eq(V.pintar(945.57, p), "$945.57", "y al principio el viejo");

// 2. NO se anima cuando el texto de alrededor cambia: seria mentir sobre lo que dice.
eq(V.planear("$945.57", "No disponible"), null, "texto sin numero");
eq(V.planear("No disponible", "$945.57"), null, "antes no habia numero");
eq(V.planear("8 operaciones", "8 trades"), null, "cambio el sufijo");
eq(V.planear("hoy $3.93", "ayer $3.93"), null, "cambio el prefijo");
eq(V.planear("$3.93", "3.93 USD"), null, "cambio la moneda de sitio");
eq(V.planear("—", "—"), null, "sin numero ninguno de los dos");
eq(V.planear("$945.57", "$945.57"), null, "mismo valor: nada que animar");

// 2b. El signo es parte del NUMERO, no del texto: puede ir antes de la moneda.
//     Fallo encontrado al probar: "-$54.43" perdia el signo y repintaba "-$-58.10".
for (const [a, b] of [["-$54.43 (-5.44 %)", "-$58.10 (-5.44 %)"], ["$945.57", "$951.20"],
                      ["+$37.57", "+$40.00"], ["$1,000.00", "$1,234.50"], ["6.28%", "7.00%"],
                      ["8", "11"], ["- $12.00", "- $15.00"]]) {
  const q = V.planear(a, b);
  ok(q !== null, "se puede animar " + a + " -> " + b);
  eq(V.pintar(q.desde, q), a, "el extremo de abajo se repinta igual: " + a);
  eq(V.pintar(q.hasta, q), b, "el extremo de arriba se repinta igual: " + b);
}

// 2c. Cruzar el cero no deja ni "-0.00" ni dos signos.
const cruza = V.planear("-$5.00", "$3.00");
ok(cruza !== null, "de negativo a positivo se anima");
eq(V.pintar(0, cruza), "$0.00", "en el cero no hay signo");
eq(V.pintar(-0.001, cruza), "$0.00", "casi cero tampoco lleva signo");
eq(V.pintar(3, cruza), "$3.00", "y llega al nuevo");

// 3. Negativos, porcentajes y miles.
const neg = V.planear("-$54.43 (-5.44 %)", "-$58.10 (-5.44 %)");
ok(neg !== null, "el primer numero manda");
eq(neg.desde, -54.43, "el signo entra en el valor");
eq(V.pintar(-58.1, neg), "-$58.10 (-5.44 %)", "negativo con sufijo intacto");
const miles = V.planear("$1,000.00", "$1,234.50");
eq(V.pintar(1234.5, miles), "$1,234.50", "separador de miles conservado");
eq(V.pintar(1000, miles), "$1,000.00", "y en el extremo de abajo tambien");
const pct = V.planear("6.28%", "7.00%");
eq(V.pintar(7, pct), "7.00%", "porcentaje con sus dos decimales");
const entero = V.planear("8", "11");
eq(V.pintar(11, entero), "11", "entero sin decimales inventados");

// 4. El recorrido empieza en el viejo y TERMINA exactamente en el nuevo.
eq(V.valorEn(p, 0), 945.57, "t=0 -> el viejo");
eq(V.valorEn(p, 1), 951.2, "t=1 -> el nuevo exacto");
ok(V.valorEn(p, 0.5) > 945.57 && V.valorEn(p, 0.5) < 951.2, "a la mitad, en medio");
let previo = -Infinity, monotono = true;
for (let t = 0; t <= 1.0001; t += 0.05) {
  const v = V.valorEn(p, t);
  if (v < previo - 1e-9) monotono = false;
  previo = v;
}
ok(monotono, "el numero nunca retrocede por el camino");
eq(V.suavizar(1), 1, "la suavizacion termina en 1");
eq(V.suavizar(1.4), 1, "y pasado el final se queda en 1, no se pasa");
ok(V.suavizar(0.5) > 0.5, "arranca rapido y frena");

// 5. Bajando tambien, y sin cruzar el valor final.
const baja = V.planear("$951.20", "$945.57");
eq(V.valorEn(baja, 1), 945.57, "baja hasta el nuevo exacto");
ok(V.valorEn(baja, 0.5) < 951.2 && V.valorEn(baja, 0.5) > 945.57, "a la mitad, en medio");

// 6. Un cambio minusculo no merece animacion (lo decide quien anima, pero el plan existe).
const chico = V.planear("$945.57", "$945.58");
ok(chico !== null && Math.abs(chico.hasta - chico.desde) < 0.02, "cambio de un centavo");

console.log("vivo: " + n + " comprobaciones OK");
