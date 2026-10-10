// Jarvis · Torre. Escena local: no consulta servidores, no usa cámara ni micrófono y no muestra métricas.
(function () {
  "use strict";
  const stage = document.getElementById("stage"), cam = document.getElementById("cam");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let playing = !reduce, t0 = performance.now(), pausedFor = 0, pauseAt = reduce ? t0 : 0;
  if (reduce) stage.classList.add("paused");

  // Luces de ventana sobre los pisos iluminados (porcentajes de la imagen).
  const lampHost = document.getElementById("lamps");
  const floors = [[20, 6], [27, 8], [34, 11], [41, 14], [48, 17], [55, 15], [62, 12], [70, 8], [79, 5], [88, 3]];
  floors.forEach(([y, half]) => {
    const n = Math.max(2, Math.round(half / 2.2));
    for (let i = 0; i < n; i++) {
      const el = document.createElement("div");
      el.className = "lamp";
      const w = 2.2 + Math.random() * 2.6;
      const x = 49.7 - half + (2 * half) * (i + 0.5) / n + (Math.random() - 0.5) * 2;
      el.style.left = (x - w / 2) + "%";
      el.style.top = (y - w * 0.45) + "%";
      el.style.width = w + "%";
      el.style.setProperty("--d", (3 + Math.random() * 6) + "s");
      el.style.setProperty("--delay", (-Math.random() * 6) + "s");
      el.style.setProperty("--lo", String(0.18 + Math.random() * 0.2));
      el.style.setProperty("--hi", String(0.6 + Math.random() * 0.4));
      lampHost.appendChild(el);
    }
  });

  // Estrellas en el cielo alto; van en la cámara para moverse con la escena.
  const sc = document.getElementById("stars"), sx = sc.getContext("2d");
  let stars = [];
  function sizeStars() {
    const r = sc.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
    sc.width = Math.max(1, r.width * dpr); sc.height = Math.max(1, r.height * dpr);
    stars = Array.from({ length: 170 }, () => {
      let x, y;
      do { x = Math.random(); y = Math.random() * 0.36; } while (Math.abs(x - 0.497) < 0.13 && y > 0.02);
      return { x, y, r: (Math.random() * 1.1 + 0.35) * dpr, p: Math.random() * 6.28, s: 0.6 + Math.random() * 1.8 };
    });
  }

  // Niebla en dos profundidades, delante de la escena.
  const fc = document.getElementById("fog"), fx = fc.getContext("2d");
  let puffs = [];
  function sizeFog() {
    const dpr = Math.min(1.5, devicePixelRatio || 1);
    fc.width = innerWidth * dpr; fc.height = innerHeight * dpr;
    puffs = Array.from({ length: 26 }, (_, i) => {
      const near = i % 3 === 0;
      return { x: Math.random() * 1.3 - 0.15, y: near ? 0.72 + Math.random() * 0.3 : 0.5 + Math.random() * 0.38,
               r: (near ? 0.22 : 0.14) + Math.random() * 0.12, v: (near ? 0.012 : 0.005) * (0.6 + Math.random()),
               a: near ? 0.16 : 0.09 };
    });
  }

  // Grano de película: una textura pequeña generada aquí (data: está permitido en img-src).
  (function () {
    const c = document.createElement("canvas"); c.width = c.height = 160;
    const g = c.getContext("2d"), d = g.createImageData(160, 160);
    for (let i = 0; i < d.data.length; i += 4) {
      const v = Math.random() * 255; d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = 255;
    }
    g.putImageData(d, 0, 0);
    document.getElementById("grain").style.backgroundImage = "url(" + c.toDataURL() + ")";
  })();

  // Relámpagos lejanos entre las nubes.
  const flash = document.getElementById("flash");
  function strike() {
    if (playing) {
      const left = Math.random() < 0.5;
      flash.style.setProperty("--fx", (left ? 8 + Math.random() * 22 : 72 + Math.random() * 22) + "%");
      flash.style.setProperty("--fy", (14 + Math.random() * 22) + "%");
      flash.classList.remove("on"); void flash.offsetWidth; flash.classList.add("on");
    }
    setTimeout(strike, 9000 + Math.random() * 14000);
  }
  if (!reduce) setTimeout(strike, 5500);

  // Camino de cámara: acercamiento lento, grúa suave y deriva, en ciclo de ~92 s.
  function camAt(s) {
    const k = (1 - Math.cos(s / 46 * Math.PI)) / 2;
    const scale = 1.04 + k * 0.2;
    const tx = Math.sin(s / 31) * 1.2, ty = -k * 2.2 + Math.sin(s / 23) * 0.5, rot = Math.sin(s / 37) * 0.35;
    return "translate(" + tx + "%," + ty + "%) scale(" + scale + ") rotate(" + rot + "deg)";
  }

  function frame(now) {
    const s = ((playing ? now : pauseAt) - t0 - pausedFor) / 1000;
    cam.style.transform = camAt(s);
    sx.clearRect(0, 0, sc.width, sc.height);
    for (const st of stars) {
      sx.globalAlpha = reduce ? 0.75 : 0.45 + 0.55 * Math.abs(Math.sin(st.p + s * st.s));
      sx.fillStyle = "#dfe8ff";
      sx.beginPath(); sx.arc(st.x * sc.width, st.y * sc.height, st.r, 0, 6.283); sx.fill();
    }
    fx.clearRect(0, 0, fc.width, fc.height);
    const W = fc.width, H = fc.height;
    for (const p of puffs) {
      const x = ((p.x + s * p.v) % 1.3 + 1.3) % 1.3 - 0.15;
      const R = p.r * Math.max(W, H * 1.6), cx = x * W, cy = p.y * H;
      const g = fx.createRadialGradient(cx, cy, 0, cx, cy, R);
      g.addColorStop(0, "rgba(176,190,215," + p.a + ")"); g.addColorStop(1, "rgba(176,190,215,0)");
      fx.fillStyle = g; fx.fillRect(cx - R, cy - R, R * 2, R * 2);
    }
    requestAnimationFrame(frame);
  }

  // Hora de Puerto Rico.
  const clock = document.getElementById("clock");
  const fmt = new Intl.DateTimeFormat("es-PR", { timeZone: "America/Puerto_Rico", hour: "2-digit", minute: "2-digit",
                                                 second: "2-digit", hour12: false });
  function tick() { clock.textContent = fmt.format(new Date()) + " AST"; }
  tick(); setInterval(tick, 1000);

  // Controles.
  const bPlay = document.getElementById("bPlay"), bHud = document.getElementById("bHud"), bFull = document.getElementById("bFull");
  if (reduce) bPlay.textContent = "Reproducir";
  bPlay.addEventListener("click", () => {
    const now = performance.now();
    if (playing) { playing = false; pauseAt = now; bPlay.textContent = "Reproducir"; }
    else { if (pauseAt) pausedFor += now - pauseAt; pauseAt = 0; playing = true; bPlay.textContent = "Pausa"; }
    stage.classList.toggle("paused", !playing);
  });
  bHud.addEventListener("click", () => {
    const off = stage.classList.toggle("nohud");
    bHud.textContent = off ? "Mostrar texto" : "Ocultar texto";
  });
  bFull.addEventListener("click", async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen(); else await stage.requestFullscreen();
    } catch (e) {
      bFull.textContent = "No disponible"; setTimeout(() => { bFull.textContent = "Pantalla completa"; }, 2200);
    }
  });
  document.addEventListener("fullscreenchange", () => {
    bFull.textContent = document.fullscreenElement ? "Salir" : "Pantalla completa";
  });
  document.addEventListener("keydown", (e) => {
    if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    if (e.key === " ") { e.preventDefault(); bPlay.click(); }
    else if (e.key === "f" || e.key === "F") bFull.click();
    else if (e.key === "h" || e.key === "H") bHud.click();
  });

  function resize() { sizeStars(); sizeFog(); }
  addEventListener("resize", resize);
  const img = cam.querySelector("img");
  const ready = img.complete ? Promise.resolve() : new Promise((r) => { img.addEventListener("load", r, { once: true });
                                                                       img.addEventListener("error", r, { once: true }); });
  ready.then(() => { resize(); requestAnimationFrame(frame); });
})();
