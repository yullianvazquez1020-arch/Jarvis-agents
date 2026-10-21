/* Que los numeros del panel se muevan en vez de saltar, y que se vea de cuando son los datos.
 *
 * El dueno, 19 oct: «el display tampoco tiene vida, esta muerto». Lo estaba por dos razones
 * concretas: la barra de mercado se refrescaba cada 60 s, y entre refresco y refresco los
 * numeros cambiaban de golpe, sin transicion, asi que nada se movia nunca.
 *
 * Esto NO inventa datos ni anima nada que no haya cambiado de verdad. Solo:
 *   - recorre el camino entre el valor viejo y el nuevo cuando el nuevo YA llego;
 *   - marca con un destello si subio o bajo;
 *   - dice la edad real del dato.
 * Si el texto no es un numero reconocible, no lo toca: lo deja tal cual.
 */
(function (raiz) {
  "use strict";

  var DURACION = 650;          // ms que tarda el numero en recorrer el camino
  var MINIMO_PARA_ANIMAR = 2;  // menos de 2 pasos no se nota: se pone directo

  // --- nucleo puro: sin DOM, sin reloj, para poder probarlo de verdad ---

  // Un numero dentro de un texto. El signo puede ir ANTES del simbolo de moneda ("-$54.43") o
  // pegado a los digitos ("$-54.43"); si no se mira a la izquierda, el signo se pierde y al
  // repintar sale "-$-58.10". Por eso se localizan primero los digitos y luego se camina hacia
  // atras por la moneda y el signo.
  var DIGITOS = /\d[\d,]*(?:\.\d+)?/;
  var MONEDAS = "$\u20ac\u00a3";

  function partir(texto) {
    texto = String(texto);
    var m = DIGITOS.exec(texto);
    if (!m) return null;
    var i = m.index, moneda = "", signo = "", huecoMoneda = "", huecoSigno = "";
    var j = i;
    while (j > 0 && texto.charAt(j - 1) === " ") { huecoMoneda = " " + huecoMoneda; j--; }
    if (j > 0 && MONEDAS.indexOf(texto.charAt(j - 1)) !== -1) { moneda = texto.charAt(j - 1); j--; }
    else { huecoMoneda = ""; j = i; }
    var k = j;
    while (k > 0 && texto.charAt(k - 1) === " ") { huecoSigno = " " + huecoSigno; k--; }
    if (k > 0 && "-\u2212+".indexOf(texto.charAt(k - 1)) !== -1) { signo = texto.charAt(k - 1); k--; }
    else { huecoSigno = ""; k = j; }
    return { prefijo: texto.slice(0, k), signo: signo, huecoSigno: huecoSigno,
             moneda: moneda, huecoMoneda: huecoMoneda, crudo: m[0],
             sufijo: texto.slice(i + m[0].length) };
  }

  function aNumero(parte) {
    if (parte == null) return null;
    var crudo = typeof parte === "string" ? parte : parte.crudo;
    var v = parseFloat(String(crudo).replace(/,/g, ""));
    if (!isFinite(v)) return null;
    if (typeof parte !== "string" && (parte.signo === "-" || parte.signo === "\u2212")) v = -v;
    return v;
  }

  function decimalesDe(crudo) {
    var p = String(crudo).indexOf(".");
    return p === -1 ? 0 : String(crudo).length - p - 1;
  }

  function llevaMiles(crudo) {
    return String(crudo).indexOf(",") !== -1;
  }

  /* Decide si dos textos se pueden recorrer. Devuelve null cuando NO se debe tocar:
     texto sin numero, texto cuyo alrededor cambio (otra unidad, otra frase), o mismo valor. */
  function planear(viejo, nuevo) {
    var a = partir(viejo), b = partir(nuevo);
    if (!a || !b) return null;
    // El texto de alrededor tiene que ser el mismo: si cambio, no se anima (seria mentir sobre
    // lo que dice). El SIGNO si puede cambiar: es parte del numero, no del texto.
    if (a.prefijo !== b.prefijo || a.sufijo !== b.sufijo || a.moneda !== b.moneda) return null;
    var desde = aNumero(a), hasta = aNumero(b);
    if (desde == null || hasta == null || desde === hasta) return null;
    return { prefijo: b.prefijo, sufijo: b.sufijo, moneda: b.moneda,
             huecoSigno: b.huecoSigno, huecoMoneda: b.huecoMoneda,
             masExplicito: b.signo === "+",
             desde: desde, hasta: hasta,
             decimales: decimalesDe(b.crudo), miles: llevaMiles(b.crudo) };
  }

  function conMiles(entero) {
    return String(entero).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  function pintar(valor, plan) {
    var abs = Math.abs(valor).toFixed(plan.decimales);
    var partes = abs.split(".");
    if (plan.miles) partes[0] = conMiles(partes[0]);
    // -0.00 no existe para el dueno: es cero.
    var cero = parseFloat(abs) === 0;
    var signo = cero ? (plan.masExplicito ? "+" : "") : valor < 0 ? "-" : plan.masExplicito ? "+" : "";
    return plan.prefijo + signo + (signo ? plan.huecoSigno : "") +
           plan.moneda + (plan.moneda ? plan.huecoMoneda : "") + partes.join(".") + plan.sufijo;
  }

  // Arranca rapido y frena al final: se lee mejor que una velocidad constante.
  function suavizar(t) {
    return t >= 1 ? 1 : 1 - Math.pow(1 - t, 3);
  }

  function valorEn(plan, t) {
    return plan.desde + (plan.hasta - plan.desde) * suavizar(t);
  }

  var nucleo = { planear: planear, pintar: pintar, suavizar: suavizar, valorEn: valorEn,
                 partir: partir, aNumero: aNumero };

  if (typeof module === "object" && module.exports) { module.exports = nucleo; return; }

  // --- la parte que toca la pagina ---

  /* Escribir dejando constancia de lo que escribimos NOSOTROS.
     Primero lo intente con un interruptor que se encendia y apagaba alrededor de la escritura,
     y no sirve: el observador corre en una microtarea, DESPUES, cuando ya esta apagado. Asi que
     cada cuadro de la animacion se tomaba por un dato nuevo y se animaba de vuelta; el numero
     acababa en un valor intermedio o directamente en el viejo.
     Guardar el ultimo texto propio en el elemento si funciona: el observador compara y calla. */
  function escribir(el, texto) {
    el.__vivoUltimo = texto;
    el.textContent = texto;
  }

  var animando = new (raiz.WeakMap || function () {
    this.set = function () {}; this.get = function () {}; this.has = function () { return false; };
  })();

  // viejo se pasa a proposito: cuando el observador se entera, el texto del elemento YA es el
  // nuevo, asi que leerlo de ahi comparaba el valor nuevo consigo mismo y no animaba nunca.
  function animar(el, nuevo, viejo) {
    var plan = planear(viejo == null ? el.textContent : viejo, nuevo);
    if (!plan) { escribir(el, nuevo); return false; }
    var pasos = Math.abs(plan.hasta - plan.desde) * Math.pow(10, plan.decimales);
    if (pasos < MINIMO_PARA_ANIMAR) { escribir(el, nuevo); return false; }
    var anterior = animando.get(el);
    if (anterior) cancelAnimationFrame(anterior);
    var t0 = 0;
    function cuadro(ahora) {
      if (!t0) t0 = ahora;
      var t = (ahora - t0) / DURACION;
      if (t >= 1) { escribir(el, nuevo); animando.set(el, 0); return; }   // termina EXACTO en el nuevo
      escribir(el, pintar(valorEn(plan, t), plan));
      animando.set(el, requestAnimationFrame(cuadro));
    }
    animando.set(el, requestAnimationFrame(cuadro));
    el.classList.remove("vivo-sube", "vivo-baja");
    void el.offsetWidth;                                   // reinicia la animacion de CSS
    el.classList.add(plan.hasta > plan.desde ? "vivo-sube" : "vivo-baja");
    return true;
  }

  /* Observa un elemento: cuando OTRO codigo le cambie el texto, se recorre el camino.
     Asi no hay que reescribir mercado.js ni app.js. */
  function seguir(el) {
    if (!el || el.__vivo || !raiz.MutationObserver) return;
    el.__vivo = true;
    el.__vivoUltimo = el.textContent;
    var obs = new MutationObserver(function () {
      var objetivo = el.textContent;
      if (objetivo === el.__vivoUltimo) return;   // lo escribimos nosotros: no es un dato nuevo
      var anterior = el.__vivoUltimo;
      el.__vivoUltimo = objetivo;
      animar(el, objetivo, anterior);
    });
    obs.observe(el, { childList: true, characterData: true, subtree: true });
  }

  function seguirTodo(selector) {
    var n = 0, lista = document.querySelectorAll(selector);
    for (var i = 0; i < lista.length; i++) { seguir(lista[i]); n++; }
    return n;
  }

  raiz.JarvisVivo = { planear: planear, pintar: pintar, valorEn: valorEn, suavizar: suavizar,
                      animar: animar, seguir: seguir, seguirTodo: seguirTodo, DURACION: DURACION };
})(typeof window !== "undefined" ? window : this);
