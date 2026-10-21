"""Genera desktop/ui/audio/arranque-rock.wav (v2): intro de hard rock ORIGINAL (~19 s) con instrumentos reales
de soundfont libre (FluidR3_GM, licencia MIT): Distortion Guitar x2 (L/R), bajo con púa, batería GM; amp/cab y
mezcla con pedalboard (Spotify). Mismo riff propio de v1 (E5/G5/A5/D5/C5); no copia ninguna canción ni usa samples
de grabaciones. Requisitos solo para regenerar: fluidsynth, fluid-soundfont-gm, pip mido pedalboard numpy, ffmpeg.
Uso: python3 scripts/gen_arranque_rock.py [carpeta_salida]"""
import json, pathlib, re, subprocess, sys, tempfile, wave
import numpy as np, mido
from pedalboard import (Pedalboard, HighpassFilter, LowpassFilter, PeakFilter, LowShelfFilter, Distortion,
                        Compressor, Reverb, Gain, Limiter)

SF2 = "/usr/share/sounds/sf2/FluidR3_GM.sf2"; SR = 44100; BPM = 126; TPB = 480; E8 = TPB // 2
ROOT = {"E": 40, "G": 43, "A": 45, "D": 38, "C": 36}  # E2 = 40
RIFF_A = [("E",1),("E",1),("E",0),("-",0),("E",1),("G",0),("E",1),("A",0),
          ("E",1),("E",1),("E",0),("-",0),("D",0),("D",1),("C",0),("-",0)]
RIFF_B = [("E",1),("E",1),("E",0),("-",0),("E",1),("G",0),("E",1),("A",0),
          ("A",0),("A",1),("G",0),("G",1),("D",0),("-",0),("E",0),("E",0)]
SEQ = (RIFF_A + RIFF_B) * 2 + RIFF_A[:8]  # 8 compases
BAR = 8 * E8; PRE = TPB // 2  # 0.24 s de entrada

def midi(events, prog, ch, path):
    """events: (tick, nota, vel, dur_ticks)."""
    m = mido.MidiFile(ticks_per_beat=TPB); t = mido.MidiTrack(); m.tracks.append(t)
    t.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(BPM)))
    if ch != 9: t.append(mido.Message("program_change", program=prog, channel=ch))
    msgs = []
    for tk, n, v, d in events:
        msgs += [(tk, 1, mido.Message("note_on", note=n, velocity=v, channel=ch)),
                 (tk + d, 0, mido.Message("note_off", note=n, velocity=0, channel=ch))]
    now = 0
    for tk, _, msg in sorted(msgs, key=lambda x: (x[0], x[1])):
        msg.time = tk - now; now = tk; t.append(msg)
    m.save(path)

def render(mid, wav):
    subprocess.run(["fluidsynth", "-ni", "-g", "0.8", "-r", str(SR), "-F", wav, SF2, mid], check=True, capture_output=True)
    with wave.open(wav) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").reshape(-1, 2).T.astype(np.float32) / 32768
    return x.mean(0)

def guitar(start_bar, human):
    ev = []; rng = np.random.default_rng(human)
    for i, (c, mute) in enumerate(SEQ):
        tk = PRE + i * E8
        if c == "-" or tk < PRE + start_bar * BAR: continue
        r = ROOT[c]; jit = int(rng.integers(-6, 7)) if human else 0
        dur = int(E8 * (0.55 if mute else 0.95)); vel = (88 if mute else 118) + int(rng.integers(-5, 5))
        for k, n in enumerate((r, r + 7, r + 12)):
            ev.append((max(0, tk + jit + k * 4), n, vel, dur))
    fin = PRE + 8 * BAR
    ev += [(fin + k * 6, n, 120, 5 * TPB) for k, n in enumerate((40, 47, 52, 55 + 4))]  # E5 + 3ª mayor alta (G#) final
    return ev

def bass():
    ev = []
    for i, (c, mute) in enumerate(SEQ):
        tk = PRE + i * E8
        if c == "-" or tk < PRE + 2 * BAR: continue
        ev.append((tk, ROOT[c] - 12 + 12, 100 if mute else 112, int(E8 * 0.85)))  # E2 en bajo = 40-? usa octava del bajo
    ev.append((PRE + 8 * BAR, 28 + 12, 115, 5 * TPB))
    return ev

def drums():
    K, S, HH, OH, CR = 36, 38, 42, 46, 49; ev = []
    for b in range(8):
        s = PRE + b * BAR
        if b >= 2:
            for k in range(8): ev.append((s + k * E8, OH if (k == 7 and b % 2) else HH, 100 if k % 2 == 0 else 70, 60))
        if b == 3:
            for k in range(8): ev.append((s + 2 * TPB + k * TPB // 4, S, 60 + 8 * k, 60))
        if b >= 4:
            if b == 4: ev.append((s, CR, 120, 60))
            for kp in (0, 3 * E8, 5 * E8): ev.append((s + kp, K, 120, 60))
            for sp in (2 * E8, 6 * E8): ev.append((s + sp, S, 122, 60))
    f = PRE + 8 * BAR; ev += [(f, CR, 127, 60), (f, K, 127, 60), (f, 57, 110, 60)]
    return ev

def pan(x, p):  # p: -1 izq .. 1 der, ley de potencia constante
    a = (p + 1) * np.pi / 4; return np.stack([x * np.cos(a), x * np.sin(a)])

def build():
    with tempfile.TemporaryDirectory() as d:
        st = {}
        for name, ev, prog, ch in (("gl", guitar(0, 1), 30, 0), ("gr", guitar(2, 2), 29, 1), ("ba", bass(), 34, 2), ("dr", drums(), 0, 9)):
            midi(ev, prog, ch, f"{d}/{name}.mid"); st[name] = render(f"{d}/{name}.mid", f"{d}/{name}.wav")
    n = max(len(v) for v in st.values()); st = {k: np.pad(v, (0, n - len(v))) for k, v in st.items()}
    amp = lambda drv, mid: Pedalboard([HighpassFilter(90), Distortion(drv), LowShelfFilter(180, -3), PeakFilter(400, -3, 1.0),
                                       PeakFilter(mid, 2, 0.8), LowpassFilter(7500), Compressor(-18, 3, 5, 80)])
    gl = amp(10, 2800)(st["gl"], SR); gr = amp(12, 3300)(st["gr"], SR)
    ba = Pedalboard([HighpassFilter(45), LowShelfFilter(90, -3), Distortion(6), PeakFilter(900, 3, 1), LowpassFilter(3500), Compressor(-20, 4, 5, 100)])(st["ba"], SR)
    dr = Pedalboard([HighpassFilter(40), PeakFilter(60, -2, 1), PeakFilter(4000, 3, 1), Compressor(-16, 4, 3, 60), Gain(3)])(st["dr"], SR)
    nrm = lambda x: x / (np.sqrt(np.mean(x[np.abs(x) > 1e-4] ** 2)) + 1e-9)
    mix = 0.30 * pan(nrm(gl), -0.8) + 0.30 * pan(nrm(gr), 0.8) + 0.12 * pan(nrm(gl), 0.3) + 0.30 * pan(nrm(ba), 0) + 0.33 * pan(nrm(dr), 0)
    mix = Pedalboard([Reverb(room_size=0.25, damping=0.6, wet_level=0.08, dry_level=1.0, width=1.0)])(mix.astype(np.float32), SR)
    mix = Pedalboard([HighpassFilter(35), Compressor(-12, 2, 10, 120)])(mix, SR)
    end = int((PRE + 8 * BAR) / TPB * 60 / BPM * SR) + int(2.6 * SR); mix = mix[:, :end]
    fl = int(2.0 * SR); mix[:, -fl:] *= np.linspace(1, 0, fl) ** 2
    return mix

def lufs(path):
    o = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", o)[-1]), float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", o)[-1])

def write(path, x):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x.T, -1, 1) * 32767).astype("<i2").tobytes())

if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1] / "desktop/ui/audio"
    mix = build(); p = out / "arranque-rock.wav"
    mix = (mix / np.max(np.abs(mix))).astype(np.float32); lo, hi = -24.0, 0.0  # umbral del limitador (JUCE normaliza a 0 dBFS)
    for _ in range(10):  # búsqueda binaria del umbral para -14 LUFS; techo final -1.5 dBFS
        t = (lo + hi) / 2; y = Pedalboard([Limiter(t, 80)])(mix, SR) * 10 ** (-1.5 / 20)
        write(p, y); i2, pk = lufs(str(p))
        if abs(i2 + 14) < 0.2: break
        lo, hi = (lo, t) if i2 < -14 else (t, hi)
    if i2 > -14:  # ya pasa de -14 sin limitar: solo bajar ganancia (los picos bajan también)
        write(p, y * 10 ** ((-14 - i2) / 20)); i2, pk = lufs(str(p))
    print(json.dumps({"archivo": str(p), "LUFS": i2, "true_peak_dBFS": pk}))
