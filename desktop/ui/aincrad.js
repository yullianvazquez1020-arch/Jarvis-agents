/* Torre de Aincrad: 100 pisos, cinco sectores de veinte. Solo datos y cuentas; no dibuja ni pide red.
   Las cifras de demostración son ficticias y deterministas (misma semilla, mismos números) y SIEMPRE se
   rotulan como demo: sin conexión comprobada, inventar ingresos del negocio está prohibido.
   Navegador: window.JarvisAincrad. Node (pruebas): module.exports. */
(function (root) {
  "use strict";
  var FLOORS = 100, PER_SECTOR = 20;

  /* Mismos cinco sectores y colores que el atlas de /avatar, para que la casa se vea igual en las dos vistas. */
  var SECTORS = [
    { name: "Servicio local", color: "#54ffbd" },
    { name: "Producto digital", color: "#ffd878" },
    { name: "Contenido educativo", color: "#36a8ff" },
    { name: "Tienda por validar", color: "#ffad38" },
    { name: "Afiliados", color: "#65eeff" }
  ];

  var IDLE_GLOW = 0.3;           // el núcleo late aunque no haya voz: nunca se apaga del todo
  var DEMO_NOTICE = "Datos demo · cifras ficticias, no son ingresos reales de ISLAFIX";
  var REAL_NOTICE = "Sin datos reales por piso: Jarvis no lleva un libro por negocio todavía";

  function sectorIndex(floor) {
    if (!(floor >= 1 && floor <= FLOORS)) throw new Error("piso fuera de rango: 1 a " + FLOORS);
    return Math.floor((floor - 1) / PER_SECTOR);
  }
  function sectorOf(floor) { return SECTORS[sectorIndex(floor)]; }

  /* Generador determinista (mulberry32): la demo no cambia entre recargas ni entre máquinas. */
  function rng(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  /* Cien pisos de demostración. gross y cost en dólares con dos decimales; nunca se presentan como reales. */
  function demoFloors(seed) {
    var r = rng(seed === undefined ? 2026 : seed), out = [];
    for (var n = 1; n <= FLOORS; n++) {
      var s = sectorIndex(n);
      var gross = Math.round((40 + r() * 760 + s * 55) * 100) / 100;
      var cost = Math.round(gross * (0.18 + r() * 0.42) * 100) / 100;
      out.push({ floor: n, sector: SECTORS[s].name, color: SECTORS[s].color,
                 name: SECTORS[s].name + " · piso " + n, gross: gross, cost: cost, demo: true });
    }
    return out;
  }

  /* Cien pisos sin cifras: lo que corresponde cuando el panel está conectado pero no hay libro por negocio. */
  function emptyFloors() {
    var out = [];
    for (var n = 1; n <= FLOORS; n++) {
      var s = sectorIndex(n);
      out.push({ floor: n, sector: SECTORS[s].name, color: SECTORS[s].color,
                 name: SECTORS[s].name + " · piso " + n, gross: null, cost: null, demo: false });
    }
    return out;
  }

  function net(floor) {
    if (!floor || floor.gross === null || floor.cost === null) return null;
    return Math.round((floor.gross - floor.cost) * 100) / 100;
  }

  function totals(floors) {
    var g = 0, c = 0, counted = 0;
    (floors || []).forEach(function (f) {
      if (f && f.gross !== null && f.cost !== null) { g += f.gross; c += f.cost; counted++; }
    });
    g = Math.round(g * 100) / 100; c = Math.round(c * 100) / 100;
    return { gross: g, cost: c, net: Math.round((g - c) * 100) / 100, counted: counted, floors: (floors || []).length };
  }

  function money(v) {
    if (v === null || v === undefined || !isFinite(v)) return "sin datos";
    try {
      return new Intl.NumberFormat("es-PR", { style: "currency", currency: "USD" }).format(v);
    } catch (e) {
      return "$" + Number(v).toFixed(2);
    }
  }

  /* Ficha de un piso: solo texto ya formateado, para escribirlo con textContent, nunca como HTML. */
  function floorCard(floor) {
    if (!floor) return null;
    var n = net(floor), real = floor.demo === false;
    return {
      title: "Piso " + floor.floor + " · " + floor.name,
      sector: "Sector " + (sectorIndex(floor.floor) + 1) + " · " + floor.sector +
              " · pisos " + (sectorIndex(floor.floor) * PER_SECTOR + 1) + "–" + ((sectorIndex(floor.floor) + 1) * PER_SECTOR),
      rows: [
        { label: "Ingreso bruto", value: money(floor.gross) },
        { label: "Costos", value: money(floor.cost) },
        { label: "Ganancia neta", value: money(n) }
      ],
      net: n,
      demo: !real,
      notice: real ? REAL_NOTICE : DEMO_NOTICE
    };
  }

  /* Altura relativa de un piso en la torre (0 abajo, 1 arriba) y radio: Aincrad se estrecha al subir. */
  function floorHeight(n) { return (n - 1) / (FLOORS - 1); }
  function floorRadius(n) { return 1 - 0.62 * Math.pow(floorHeight(n), 1.25); }

  /* Amplitud del audio (0..1) -> brillo del núcleo. Recorta fuera de rango; nunca devuelve NaN. */
  function coreGlow(rms) {
    var v = Number(rms);
    if (!isFinite(v) || v <= 0) return IDLE_GLOW;
    if (v > 1) v = 1;
    return Math.round((IDLE_GLOW + v * (1 - IDLE_GLOW)) * 1000) / 1000;
  }

  var api = { FLOORS: FLOORS, PER_SECTOR: PER_SECTOR, SECTORS: SECTORS, IDLE_GLOW: IDLE_GLOW, DEMO_NOTICE: DEMO_NOTICE,
              REAL_NOTICE: REAL_NOTICE, sectorIndex: sectorIndex, sectorOf: sectorOf, demoFloors: demoFloors,
              emptyFloors: emptyFloors, net: net, totals: totals, money: money, floorCard: floorCard,
              floorHeight: floorHeight, floorRadius: floorRadius, coreGlow: coreGlow };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.JarvisAincrad = api;
})(this);
