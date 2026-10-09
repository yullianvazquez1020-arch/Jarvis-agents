#!/usr/bin/env python3
"""SOLO PARA MEDIR la sincronización de la boca. Imita la línea de comandos de piper (--output_file) y escribe
un WAV con ráfagas de tono en instantes conocidos. No es una voz ni se usa en producción.

Uso: VOICE_TTS_BACKEND=piper VOICE_PIPER_BIN=scripts/fake_tts_bursts.py VOICE_TTS_VOICE=<cualquier archivo>"""
import json
import math
import struct
import sys
import wave

RATE = 22050
LEAD = 0.40
BURSTS = [(0.25, 0.30), (0.35, 0.20), (0.20, 0.35), (0.40, 0.25), (0.30, 0.30), (0.25, 0.20),
          (0.45, 0.30), (0.20, 0.40)]          # (duración de la ráfaga, silencio después), segundos
RAMP = 0.008


def schedule():
    out, at = [], LEAD
    for dur, gap in BURSTS:
        out.append((round(at, 4), round(at + dur, 4)))
        at += dur + gap
    return out, at


def main(argv):
    out = argv[argv.index("--output_file") + 1]
    sys.stdin.read()                                   # el texto se ignora: las ráfagas son la verdad conocida
    spans, total = schedule()
    n = int(total * RATE)
    frames = bytearray()
    for i in range(n):
        t = i / RATE
        v = 0.0
        for a, b in spans:
            if a <= t < b:
                env = min(1.0, (t - a) / RAMP, (b - t) / RAMP)
                v = env * 0.45 * (math.sin(2 * math.pi * 180 * t) + 0.5 * math.sin(2 * math.pi * 360 * t)
                                  + 0.25 * math.sin(2 * math.pi * 720 * t)) / 1.75
                break
        frames += struct.pack("<h", int(max(-1, min(1, v)) * 32767))
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(bytes(frames))
    return 0


if __name__ == "__main__":
    if "--schedule" in sys.argv:
        print(json.dumps({"spans": schedule()[0], "duration": schedule()[1]}))
        sys.exit(0)
    sys.exit(main(sys.argv))
