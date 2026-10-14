// Jarvis · Negocios y cripto en el panel principal. Cifras de negocio DEMO; precios públicos sin claves.
(function () {
  "use strict";
  function el(t, c, txt) { var e = document.createElement(t); if (c) e.className = c; if (txt != null) e.textContent = txt; return e; }
  function money(v) { return v == null ? "—" : "$" + Number(v).toLocaleString("en-US", {maximumFractionDigits: 2}); }
  function get(u) { return fetch(u, {credentials: "same-origin"}).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }); }
  var box = el("section", "neg"); box.id = "negocios"; box.setAttribute("aria-label", "Negocios");
  var anchor = document.querySelector("header.top");
  (anchor && anchor.parentNode ? anchor.parentNode.insertBefore(box, anchor.nextSibling) : document.body.appendChild(box));
  function render(t, m, mo) {
    box.textContent = "";
    var h = el("h2", null, "NEGOCIOS · TORRE DE AINCRAD "); h.appendChild(el("span", "demo", t ? t.etiqueta : "")); box.appendChild(h);
    if (t) {
      box.appendChild(el("div", null, "Controlador: " + t.controlador + " · Pisos conquistados " + t.conquistados + "/" + t.total_pisos));
      var ul = el("ul");
      t.negocios.forEach(function (n) {
        var li = el("li"); li.setAttribute("data-negocio", n.id); li.appendChild(el("span", null, "Piso " + n.piso + " · " + n.nombre + " (" + n.estado + ")"));
        var bar = el("span", "bar"), i = el("i"); i.style.width = (n.meta_mes_usd ? Math.min(100, 100 * n.real_mes_usd / n.meta_mes_usd) : 0) + "%";
        bar.appendChild(i); li.appendChild(bar); li.appendChild(el("span", null, money(n.real_mes_usd) + " / " + money(n.meta_mes_usd)));
        ul.appendChild(li);
      });
      box.appendChild(ul);
    }
    if (mo) {
      var ms = mo.stop ? "STOP activo" : mo.sesion ? "sesión de " + mo.agente + " hasta " + mo.vence : "en espera (la abre el dueño en la Mac)";
      box.appendChild(el("div", mo.stop ? "off" : null, "Mouse autónomo: " + ms + " · Parada: " + mo.parada));
    }
    var c = el("h2", null, "CRIPTO · PRÁCTICA (sin trading real)"); box.appendChild(c);
    if (!m || !m.conectado) { box.appendChild(el("div", "off", "Precios sin conexión" + (m && m.error ? " (" + m.error + ")" : ""))); return; }
    var mx = Math.max.apply(null, m.precios.map(function (p) { return p.usd || 0; }));
    var ul2 = el("ul");
    m.precios.forEach(function (p) {
      var li = el("li"); li.setAttribute("data-cripto", String(p.par).split(/[-\/ ]/)[0].toUpperCase()); li.appendChild(el("span", null, p.par));
      var bar = el("span", "bar"), i = el("i"); i.style.width = (p.usd ? Math.max(4, 100 * Math.log10(p.usd) / Math.log10(mx)) : 0) + "%";
      bar.appendChild(i); li.appendChild(bar); li.appendChild(el("span", p.usd == null ? "off" : null, p.usd == null ? "sin conexión" : money(p.usd)));
      ul2.appendChild(li);
    });
    box.appendChild(ul2); box.appendChild(el("div", "demo", m.fuente));
  }
  /* rayos del núcleo: resalta la entrada apuntada (escaneo + contorno), también desde otra ventana */
  function marcar(sel) { try { var e = document.querySelector(sel); if (!e) return; e.classList.remove("jarvis-scan"); void e.offsetWidth; e.classList.add("jarvis-scan");
    setTimeout(function () { e.classList.remove("jarvis-scan"); }, 4500); } catch (x) {} }
  window.JarvisMarcar = marcar;
  try { new BroadcastChannel("jarvis-rayos").onmessage = function (ev) { if (ev.data && ev.data.sel) marcar(ev.data.sel); }; } catch (x) {}
  function tick() {
    Promise.all([get("/api/negocios").catch(function () { return null; }), get("/api/cripto").catch(function () { return null; }),
                 get("/api/mouse-autonomo").catch(function () { return null; })])
      .then(function (r) { render(r[0], r[1], r[2]); });
  }
  tick(); setInterval(tick, 60000);
})();
