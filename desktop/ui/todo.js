/* Las cuatro pantallas en una pestana.
 *
 * Cada vista es su PROPIA pagina dentro de un marco del mismo origen. No se copia ni se
 * reescribe el codigo de ninguna: lo que ya andaba sigue andando igual, y si manana cambia
 * /mercado, esta pagina no hay que tocarla.
 *
 * Se cargan al abrirlas por primera vez y se quedan vivas al cambiar de pestana, para no perder
 * su estado (la conversacion, el microfono, la curva a medio dibujar).
 */
(function () {
  "use strict";

  var RECUERDO = "jarvis-todo-vista";
  var tabs = document.getElementById("tabs");
  var lienzo = document.getElementById("lienzo");
  var marcos = {};

  function botones() {
    return Array.prototype.slice.call(tabs.querySelectorAll(".todo-tab"));
  }

  function crear(boton) {
    var f = document.createElement("iframe");
    f.src = boton.getAttribute("data-src");
    f.title = boton.textContent.trim();
    // El panel es el unico que pide microfono y camara; sin esto el navegador las niega
    // dentro del marco aunque ya esten concedidas para la pagina.
    f.setAttribute("allow", "microphone; camera; autoplay; fullscreen");
    lienzo.appendChild(f);
    return f;
  }

  function mostrar(vista, recordar) {
    var cual = null;
    botones().forEach(function (b) {
      var suya = b.getAttribute("data-vista") === vista;
      b.setAttribute("aria-selected", suya ? "true" : "false");
      if (suya) cual = b;
    });
    if (!cual) return false;
    if (!marcos[vista]) marcos[vista] = crear(cual);      // se crea la primera vez que se abre
    Object.keys(marcos).forEach(function (k) { marcos[k].hidden = k !== vista; });
    if (recordar !== false) { try { localStorage.setItem(RECUERDO, vista); } catch (e) { /* sin memoria */ } }
    return true;
  }

  tabs.addEventListener("click", function (ev) {
    var b = ev.target.closest ? ev.target.closest(".todo-tab") : null;
    if (b) mostrar(b.getAttribute("data-vista"));
  });

  addEventListener("keydown", function (ev) {
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    var activo = document.activeElement;
    if (activo && /^(INPUT|TEXTAREA|SELECT)$/.test(activo.tagName)) return;   // esta escribiendo
    var i = "1234".indexOf(ev.key);
    if (i === -1) return;
    var b = botones()[i];
    if (b) { ev.preventDefault(); mostrar(b.getAttribute("data-vista")); }
  });

  var guardada = null;
  try { guardada = localStorage.getItem(RECUERDO); } catch (e) { guardada = null; }
  if (!guardada || !mostrar(guardada, false)) mostrar("panel", false);

  window.JarvisTodo = {
    mostrar: mostrar,
    abiertas: function () { return Object.keys(marcos); },
    actual: function () {
      var b = tabs.querySelector('.todo-tab[aria-selected="true"]');
      return b ? b.getAttribute("data-vista") : null;
    }
  };
})();
