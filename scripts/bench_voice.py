#!/usr/bin/env python3
"""Banco de la voz local de Jarvis con Piper BAJO DEMANDA (el mismo código del servidor; no deja el modelo cargado).

No llama a Telegram ni a ninguna API de pago. Texto ficticio. Mide, por corrida: síntesis (Piper), Opus, total,
memoria máxima del proceso de Piper (la que él mismo informa), y la memoria CONJUNTA muestreada cada 20 ms:
este proceso + sus hijos, y el cgroup del contenedor si existe (en Render es el límite real de 512 MB).

  python3 scripts/bench_voice.py --modo escenas      # 8 escenas de 400 caracteres en una llamada (narración)
  python3 scripts/bench_voice.py --modo respuestas   # 8 respuestas habladas seguidas (vista de 200 caracteres)
  python3 scripts/bench_voice.py --modo ambos --out resultado.json

En Render (variable RENDER presente) exige --confirmo-render: comparte memoria con el servicio en vivo. La guarda de
memoria existente detiene a Piper si el contenedor queda a menos de 64 MB del límite; el servicio no se toca."""
import argparse
import asyncio
import json
import os
import platform
import statistics
import sys
import threading
import time
from pathlib import Path

# JARVIS_ROOT permite copiarlo solo (por ejemplo a /tmp en el shell de Render) sin desplegar este commit.
ROOT = Path(os.environ.get("JARVIS_ROOT") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
MIB = 1024 * 1024

FRASES = ("Hoy tienes dos visitas de obra y un cobro pendiente de ejemplo.",
          "La cuenta de ejemplo vence el viernes; revisa el saldo antes de pagar.",
          "El trabajo de pintura de prueba quedó entregado y espera tu confirmación.",
          "No hay mensajes esperando envío; los borradores siguen sin mandar.",
          "La práctica de cripto es simulada y no mueve dinero real.",
          "Mañana a las nueve hay una cita de evaluación en una casa de ejemplo.",
          "El inventario de tornillos de prueba está por debajo del mínimo.",
          "Recuerda que el brief solo muestra lo cobrado y la meta si existe.")


def texto(n_chars, salto=0):
    out, i = "", salto
    while len(out) < n_chars:
        out += (" " if out else "") + FRASES[i % len(FRASES)]
        i += 1
    cut = out[:n_chars]
    return cut.rsplit(" ", 1)[0] if " " in cut and len(out) > n_chars else cut


def rss_kb(pid):
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return 0


def children(pid):
    found, todo = [], [pid]
    while todo:
        p = todo.pop()
        try:
            kids = [int(x) for x in Path(f"/proc/{p}/task/{p}/children").read_text().split()]
        except (OSError, ValueError):
            # Some PID namespaces expose status but no /task/.../children.
            kids = []
            for status in Path("/proc").glob("[0-9]*/status"):
                try:
                    fields = dict(line.split(":", 1) for line in status.read_text().splitlines() if ":" in line)
                    if int(fields.get("PPid", -1)) == p:
                        kids.append(int(fields["Pid"]))
                except (OSError, ValueError, KeyError):
                    continue
        found += kids; todo += kids
    return found


def cgroup_bytes():
    for used, limit in (("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.max"),
                        ("/sys/fs/cgroup/memory/memory.usage_in_bytes", "/sys/fs/cgroup/memory/memory.limit_in_bytes")):
        try:
            cur = int(Path(used).read_text().strip())
            raw = Path(limit).read_text().strip()
            lim = None if raw == "max" or int(raw) >= 1 << 60 else int(raw)
            return cur, lim
        except (OSError, ValueError):
            continue
    return None, None


class Sampler:
    """Memoria conjunta (padre + hijos) y del cgroup, cada 20 ms, en un hilo aparte."""
    def __init__(self, every=0.02):
        self.every, self.stop_flag, self.peak = every, threading.Event(), {}
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        # /proc may expose host PIDs while os.getpid() uses a nested PID namespace.
        # Resolve the PID in the same /proc mount used for RSS and child traversal.
        me = os.getpid()
        try:
            for line in Path("/proc/self/status").read_text().splitlines():
                if line.startswith("Pid:"):
                    me = int(line.split()[1]); break
        except (OSError, ValueError):
            pass
        while not self.stop_flag.is_set():
            parent = rss_kb(me)
            kids = sum(rss_kb(k) for k in children(me))
            cg, lim = cgroup_bytes()
            for key, val in (("padre_mb", parent / 1024), ("hijos_mb", kids / 1024), ("conjunta_mb", (parent + kids) / 1024),
                             ("cgroup_mb", cg / MIB if cg else None)):
                if val is not None and val > self.peak.get(key, 0):
                    self.peak[key] = val
            if lim:
                self.peak["cgroup_limite_mb"] = lim / MIB
            time.sleep(self.every)

    def __enter__(self):
        self.thread.start(); return self

    def __exit__(self, *exc):
        self.stop_flag.set(); self.thread.join()
        self.peak = {k: round(v, 1) for k, v in self.peak.items()}


class PeakLog:
    """Lee el peak_memory_mb que el propio proceso de Piper informa en el registro."""
    def __init__(self):
        import logging
        self.values = []
        outer = self
        class H(logging.Handler):
            def emit(self, record):
                msg = record.getMessage()
                if "peak_memory_mb=" in msg:
                    try:
                        outer.values.append(int(msg.rsplit("peak_memory_mb=", 1)[1].split()[0]))
                    except ValueError:
                        pass
        self.handler = H()
        logging.getLogger("jarvis_local_tts").addHandler(self.handler)
        logging.getLogger("jarvis_local_tts").setLevel(logging.INFO)


async def una(chars, peaks, salto=0):
    import jarvis_chat_voice as cv
    t0 = time.perf_counter()
    with Sampler() as s:
        wav = await cv.speak_local(texto(chars, salto))
        t1 = time.perf_counter()
        ogg = await cv.to_opus(wav)
        t2 = time.perf_counter()
    import io, wave
    with wave.open(io.BytesIO(wav)) as w:
        audio_s = w.getnframes() / w.getframerate()
    return {"caracteres": len(texto(chars, salto)), "escenas": len(cv.speech_chunks(texto(chars, salto))),
            "sintesis_s": round(t1 - t0, 3), "opus_s": round(t2 - t1, 3), "total_s": round(t2 - t0, 3),
            "audio_s": round(audio_s, 2), "ogg_kb": round(len(ogg) / 1024, 1),
            "piper_pico_mb": peaks.values[-1] if peaks.values else None, "memoria_pico": s.peak}


def resumen(rows):
    def med(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return {"p50": round(statistics.median(vals), 3), "max": max(vals)} if vals else None
    conj = [r["memoria_pico"].get("conjunta_mb") for r in rows if r["memoria_pico"].get("conjunta_mb")]
    cg = [r["memoria_pico"].get("cgroup_mb") for r in rows if r["memoria_pico"].get("cgroup_mb")]
    return {"sintesis_s": med("sintesis_s"), "opus_s": med("opus_s"), "total_s": med("total_s"),
            "piper_pico_mb": med("piper_pico_mb"), "conjunta_pico_mb": max(conj) if conj else None,
            "cgroup_pico_mb": max(cg) if cg else None}


async def correr(modo, n):
    import jarvis_chat_voice as cv
    import jarvis_local_tts as tts
    peaks = PeakLog()
    t0 = time.perf_counter()
    await asyncio.to_thread(tts.ensure_model, tts.model_dir())       # una descarga, si falta, NO cuenta como latencia
    prep = round(time.perf_counter() - t0, 2)
    out = {"preparar_modelo_s": prep}
    if modo in ("escenas", "ambos"):
        # 8 escenas x 400 caracteres = el máximo que acepta Piper por llamada (MAX_CHARS 3200).
        out["escenas_8"] = [await una(cv.MAX_CHARS, peaks)]
        out["escenas_8_resumen"] = resumen(out["escenas_8"])
    if modo in ("respuestas", "ambos"):
        rows = []
        for i in range(n):                                            # seguidas, como notas consecutivas
            rows.append(await una(cv.MAX_SPOKEN_REPLY, peaks, salto=i))
        out["respuestas_consecutivas"] = rows
        out["respuestas_resumen"] = resumen(rows)
        out["primera_vs_resto_total_s"] = {"primera": rows[0]["total_s"],
                                           "resto_p50": round(statistics.median(r["total_s"] for r in rows[1:]), 3)
                                           if len(rows) > 1 else None}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=("escenas", "respuestas", "ambos"), default="ambos")
    ap.add_argument("-n", type=int, default=8)
    ap.add_argument("--out")
    ap.add_argument("--confirmo-render", action="store_true")
    a = ap.parse_args(argv)
    en_render = bool(os.environ.get("RENDER"))
    if en_render and not a.confirmo_render:
        print("Estás en Render: este banco comparte los 512 MB con el servicio en vivo. Córrelo en un momento "
              "tranquilo y repite con --confirmo-render.", file=sys.stderr)
        return 2
    import logging
    logging.basicConfig(level=logging.WARNING)
    res = asyncio.run(correr(a.modo, max(1, min(a.n, 20))))
    res["entorno"] = {"donde": "render" if en_render else "local", "python": platform.python_version(),
                      "sistema": platform.platform(), "cpus": os.cpu_count(),
                      "commit": os.environ.get("RENDER_GIT_COMMIT", "")[:12] or None,
                      "piper": "bajo demanda (un proceso por llamada; el modelo no queda residente)",
                      "telegram": "no se llamó"}
    text = json.dumps(res, ensure_ascii=False, indent=2)
    if a.out:
        Path(a.out).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
