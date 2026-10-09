#!/usr/bin/env python3
"""Mide la sincronización boca/audio con la app de escritorio REAL (desktop/app.py) en modo DEMO.

No llama a Render ni a Telegram. La voz es scripts/fake_tts_bursts.py: ráfagas en instantes conocidos, para
tener la verdad exacta de cuándo empieza y termina cada sonido. Requiere Playwright y Chromium.

  python3 scripts/measure_lipsync.py --runs 5 --out resultados.json --shots carpeta/

Mide, por ráfaga: retraso de apertura (boca >= 0.5 tras el inicio real del sonido) y de cierre (boca < 0.5 tras
su fin), en ms de reloj de pared, usando el currentTime del <audio> que suena como referencia. Positivo = la boca
va detrás del audio. Chromium sin altavoz: currentTime es el reloj del medio, no la salida física del Mac."""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "scripts" / "fake_tts_bursts.py"
THRESH = 0.5


def schedule():
    out = subprocess.run([sys.executable, str(FAKE), "--schedule"], stdout=subprocess.PIPE, check=True)
    return json.loads(out.stdout)


def start_app(home):
    cfg = Path(home) / "config.env"
    cfg.write_text("\n".join([
        "VOICE_DEMO=true", "VOICE_PORT=0", f"VOICE_HOME={home}", "VOICE_TTS_BACKEND=piper",
        f"VOICE_PIPER_BIN={FAKE}", f"VOICE_TTS_VOICE={FAKE}", "VOICE_STT_BACKEND=none"]) + "\n")
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG")}
    proc = subprocess.Popen([sys.executable, str(ROOT / "desktop" / "app.py"), "--config", str(cfg), "--no-browser"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    deadline = time.time() + 20
    for line in proc.stdout:
        m = re.search(r"(http://127\.0\.0\.1:\d+)/\?launch=\S+", line)
        if m:
            return proc, m.group(0), m.group(1)
        if time.time() > deadline:
            break
    proc.kill()
    raise RuntimeError("la app de escritorio no imprimió el enlace")


def fit_clock(main_log):
    """wall_ms = w0 + currentTime*1000 (ajuste por mínimos cuadrados con pendiente libre)."""
    pts = [(r[1], r[0]) for r in main_log if isinstance(r[0], (int, float)) and r[2] == 1 and r[1] > 0.02]
    if len(pts) < 10:
        raise RuntimeError("pocas muestras del reloj de audio")
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    w0 = my - slope * mx
    resid = [y - (w0 + slope * x) for x, y in zip(xs, ys)]
    return w0, slope, statistics.pstdev(resid)


def analyse(main_log, avatar_log, spans):
    w0, slope, jitter = fit_clock(main_log)
    env_ms = [r[1] for r in main_log if r and r[0] == "env"]
    rows = [r for r in avatar_log if r[0] >= w0 - 500]
    opens, closes = [], []
    for a, b in spans:
        t_on, t_off = w0 + a * slope, w0 + b * slope
        on = next((r[0] for r in rows if r[0] >= t_on - 150 and r[3] >= THRESH), None)
        off = next((r[0] for r in rows if r[0] >= t_off - 150 and r[3] < THRESH), None)
        opens.append(None if on is None else round(on - t_on, 1))
        closes.append(None if off is None else round(off - t_off, 1))
    # Deriva del reloj extrapolado del avatar frente al audio real.
    drift = [r[1] * 1000 - (r[0] - w0) * 1000 / slope for r in rows if r[4] == 1]
    frames = [b[0] - a[0] for a, b in zip(rows, rows[1:]) if 0 < b[0] - a[0] < 200]
    return {"open_ms": opens, "close_ms": closes, "envelope_ready_ms": env_ms,
            "clock_jitter_ms": round(jitter, 2), "clock_slope_ms_per_s": round(slope, 2),
            "avatar_vs_audio_position_ms": {"median": round(statistics.median(drift), 1) if drift else None,
                                            "max_abs": round(max(abs(d) for d in drift), 1) if drift else None},
            "avatar_frame_ms_median": round(statistics.median(frames), 1) if frames else None,
            "avatar_samples": len(rows)}


def summary(runs):
    def stats(key):
        vals = [v for r in runs for v in r[key] if v is not None]
        missing = sum(1 for r in runs for v in r[key] if v is None)
        if not vals:
            return {"n": 0, "missing": missing}
        vals.sort()
        return {"n": len(vals), "missing": missing, "median": round(statistics.median(vals), 1),
                "p90": round(vals[min(len(vals) - 1, int(0.9 * (len(vals) - 1) + 0.5))], 1),
                "min": vals[0], "max": vals[-1]}
    return {"apertura_ms": stats("open_ms"), "cierre_ms": stats("close_ms"),
            "envolvente_lista_ms": stats("envelope_ready_ms")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--out")
    ap.add_argument("--shots")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    spans = schedule()["spans"]
    home = tempfile.mkdtemp(prefix="jarvis-lipsync-")
    proc, link, base = start_app(home)
    console, results = [], []
    try:
        with sync_playwright() as p:
            exe = os.environ.get("CHROMIUM_PATH")
            browser = p.chromium.launch(executable_path=exe or None,
                                        args=["--autoplay-policy=no-user-gesture-required"])
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})   # CSP real: sin bypass_csp
            main_page = ctx.new_page()
            for pg_name, pg in (("conversación", main_page),):
                pg.on("console", lambda m, n=pg_name: console.append([n, m.type, m.text]) if m.type in ("error", "warning") else None)
            main_page.goto(link)
            main_page.goto(base + "/?medir=1")
            main_page.wait_for_timeout(800)
            if main_page.is_visible("#claim"):
                main_page.click("#claim")
            avatar = ctx.new_page()
            avatar.on("console", lambda m: console.append(["avatar", m.type, m.text]) if m.type in ("error", "warning") else None)
            avatar.goto(base + "/avatar?medir=1")
            avatar.wait_for_timeout(800)
            for run in range(a.runs):
                main_page.fill("#transcript", "estado del sistema")
                main_page.click("#send")
                t0 = time.time()
                while time.time() - t0 < 15:
                    main_page.wait_for_timeout(250)
                    if "VOZ REAL" in (avatar.text_content("#voice-status") or "") or main_page.evaluate(
                            "() => window.JarvisVoiceSync.log().length > 30"):
                        break
                if a.shots and run == 0:
                    Path(a.shots).mkdir(parents=True, exist_ok=True)
                    # 0.8 s después de que empezó a sonar: dentro de la segunda ráfaga (0.95-1.30 s)
                    avatar.wait_for_timeout(700)
                    avatar.screenshot(path=str(Path(a.shots) / "avatar-hablando.png"))
                    status_talking = avatar.text_content("#voice-status")
                main_page.wait_for_timeout(int((schedule()["duration"] + 1.5) * 1000))
                main_log = main_page.evaluate("() => window.JarvisVoiceSync.log()")
                avatar_log = avatar.evaluate("() => window.JarvisAvatar.syncLog()")
                res = analyse(main_log, avatar_log, spans)
                res["avatar_hidden"] = avatar.evaluate("() => document.hidden")
                results.append(res)
                avatar.evaluate("() => 0")
                main_page.wait_for_timeout(600)
            if a.shots:
                avatar.screenshot(path=str(Path(a.shots) / "avatar-callado.png"))
            final_status = avatar.text_content("#voice-status")
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    out = {"entorno": "local · Chromium headless (Playwright), app de escritorio real en DEMO, voz de prueba con ráfagas",
           "no_es": "Safari, Mac 2015, Render ni salida de altavoz real",
           "umbral_boca": THRESH, "rafagas_s": spans, "corridas": results, "resumen": summary(results),
           "estado_avatar_hablando": locals().get("status_talking"), "estado_avatar_final": final_status,
           "consola_errores_y_avisos": console}
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if a.out:
        Path(a.out).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
