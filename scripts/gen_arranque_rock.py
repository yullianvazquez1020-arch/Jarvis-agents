"""Genera desktop/ui/audio/arranque-rock.wav: intro de hard rock ORIGINAL (~18 s), síntesis propia con numpy.
Riff propio en Mi (power chords E5/G5/A5/D5/C5), guitarras distorsionadas L/R, bajo, batería sintetizada,
reverb de sala corta, fade final. Sin samples ni melodías de canciones existentes.
Uso: python3 scripts/gen_arranque_rock.py [carpeta_salida]"""
import pathlib, sys, wave
import numpy as np

SR = 44100; BPM = 126; B = 60 / BPM; E8 = B / 2
rng = np.random.default_rng(7)

def lp(x, fc):  # paso bajo 1 polo vectorizado vía FFT
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(X / np.sqrt(1 + (f / fc) ** 2), len(x))

def eq(x, pts):  # curva EQ por puntos (Hz, dB) en dominio de frecuencia
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
    g = np.interp(np.log10(f + 1), np.log10([p[0] for p in pts]), [p[1] for p in pts])
    return np.fft.irfft(X * 10 ** (g / 20), len(x))

def saw(freq, n, det=0.0):
    t = np.arange(n) / SR; ph = rng.random()
    return 2 * ((freq * (1 + det) * t + ph) % 1) - 1

def power_chord(root_hz, dur, mute):
    n = int(dur * SR); t = np.arange(n) / SR
    x = sum(saw(root_hz * m, n, d) for m, d in ((1, 0), (1.5, .002), (2, -.003), (1, .004)))
    att = np.minimum(1, t / .004)
    dec = np.exp(-t / (0.09 if mute else 0.9))
    rel = np.minimum(1, (dur - t) / .015).clip(0)
    x = x * att * dec * rel
    x = x + 0.15 * rng.standard_normal(n) * np.exp(-t / .01)  # púa
    return lp(x, 2200 if mute else 3500)

def amp(x, drive):
    y = np.tanh(drive * x) ; y = np.tanh(1.5 * y + 0.1 * y ** 2)
    return eq(y, [(20, -30), (80, -6), (120, 0), (400, -2), (800, -4), (2000, 3), (3500, 2), (5500, -10), (9000, -30), (22050, -40)])

NOTES = {"E": 82.41, "G": 98.0, "A": 110.0, "D": 73.42, "C": 65.41, "B": 61.74}
# riff propio de 2 compases en corcheas: (acorde|-, muteado)
RIFF_A = [("E",1),("E",1),("E",0),("-",0),("E",1),("G",0),("E",1),("A",0),
          ("E",1),("E",1),("E",0),("-",0),("D",0),("D",1),("C",0),("-",0)]
RIFF_B = [("E",1),("E",1),("E",0),("-",0),("E",1),("G",0),("E",1),("A",0),
          ("A",0),("A",1),("G",0),("G",1),("D",0),("-",0),("E",0),("E",0)]
BARS = [RIFF_A, RIFF_B] * 4  # 8 x 2 compases... recortado abajo

def track(seq, start, length, drive, det):
    out = np.zeros(length)
    for i, (c, m) in enumerate(seq):
        if c == "-": continue
        p = int((start + i * E8) * SR)
        dur = E8 * (0.9 if m else 1.0)
        if not m:  # sostener hasta el siguiente silencio/acorde distinto
            j = i + 1
            while j < len(seq) and seq[j][0] == c and not seq[j][1] and False: j += 1
        x = power_chord(NOTES[c] * (1 + det), dur + (0 if m else 0.05), m)
        x = amp(x * 0.6, drive)[: length - p]
        out[p:p + len(x)] += x
    return out

def kick(n):
    t = np.arange(n) / SR; f = 50 + 110 * np.exp(-t / .03)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / .22) + 0.3 * lp(rng.standard_normal(n), 3000) * np.exp(-t / .004)
def snare(n):
    t = np.arange(n) / SR
    return 0.5 * np.sin(2 * np.pi * 190 * t) * np.exp(-t / .06) + eq(rng.standard_normal(n), [(20,-30),(800,0),(5000,2),(12000,-6),(22050,-20)]) * np.exp(-t / .13) * 0.7
def hat(n, op=False):
    t = np.arange(n) / SR
    return eq(rng.standard_normal(n), [(20,-60),(6000,-12),(9000,0),(22050,-3)]) * np.exp(-t / (.18 if op else .035)) * 0.35
def crash(n):
    t = np.arange(n) / SR
    return eq(rng.standard_normal(n), [(20,-60),(3000,-6),(8000,0),(22050,-4)]) * np.exp(-t / 1.4) * 0.45

def put(buf, x, sec, g=1.0):
    p = int(sec * SR); x = x[: len(buf) - p]; buf[p:p + len(x)] += g * x

def render():
    bar = 4 * B; nbars = 9; total = 0.3 + nbars * bar + 2.5; N = int(total * SR)
    L = np.zeros(N); R = np.zeros(N); bass = np.zeros(N); dr = np.zeros(N)
    t0 = 0.3
    seq = (RIFF_A + RIFF_B) * 2 + RIFF_A[:8]  # 8 compases riff
    # compás 0-1: guitarra L sola; luego entra R + bajo; batería: hats en compás 2, completa desde 4
    gl = track(seq, t0, N, 9, 0); gr = track(seq, t0, N, 11, 0.003)
    gr[: int((t0 + 2 * bar) * SR)] = 0
    L += gl + 0.25 * gr; R += gr + 0.25 * gl
    # acorde final sostenido E5
    fin = amp(power_chord(NOTES["E"], 2.6, 0) * 0.6, 10)
    put(L, fin, t0 + 8 * bar); put(R, fin, t0 + 8 * bar, 0.95)
    # bajo: raíz una octava abajo siguiendo el riff desde compás 2
    for i, (c, m) in enumerate(seq):
        s = t0 + i * E8
        if c == "-" or s < t0 + 2 * bar: continue
        n = int(E8 * SR); tt = np.arange(n) / SR; f = NOTES[c] / 2
        x = (np.sin(2*np.pi*f*tt) + 0.4*np.tanh(3*np.sin(2*np.pi*2*f*tt))) * np.exp(-tt/0.4) * np.minimum(1,(E8-tt)/.01)
        put(bass, x, s, 0.55)
    put(bass, (np.sin(2*np.pi*41.2*np.arange(int(2.6*SR))/SR))*np.exp(-np.arange(int(2.6*SR))/SR/1.0), t0+8*bar, .55)
    # batería
    for b in range(8):
        s = t0 + b * bar
        if b >= 2:
            for k in range(8): put(dr, hat(6000, k == 7 and b % 2 == 1), s + k * E8, 0.6 if k % 2 else 0.9)
        if b == 3:  # redoble de entrada
            for k in range(8): put(dr, snare(8000), s + 2 * B + k * B / 4, 0.3 + 0.08 * k)
        if b >= 4:
            if b == 4: put(dr, crash(SR * 3), s)
            for kp in (0, 1.5, 2.5): put(dr, kick(12000), s + kp * B, 0.9)
            for sp in (1, 3): put(dr, snare(14000), s + sp * B, 0.8)
    put(dr, crash(SR * 3), t0 + 8 * bar); put(dr, kick(12000), t0 + 8 * bar); 
    # mezcla
    dL = dr * 1.0; dRr = dr * 1.0
    mixL = 0.55 * L + 0.6 * bass + dL; mixR = 0.55 * R + 0.6 * bass + dRr
    # reverb de sala: IR de ruido decayente 0.6 s
    n = int(0.6 * SR); ir = rng.standard_normal((2, n)) * np.exp(-np.arange(n) / SR / 0.18); ir[:, :int(.012*SR)] = 0
    def conv(x, h):
        m = len(x) + len(h); return np.fft.irfft(np.fft.rfft(x, m) * np.fft.rfft(h, m), m)[: len(x)]
    wetL = eq(conv(mixL, ir[0]), [(20,-30),(300,0),(5000,-3),(22050,-20)]); wetR = eq(conv(mixR, ir[1]), [(20,-30),(300,0),(5000,-3),(22050,-20)])
    mixL += 0.012 * wetL; mixR += 0.012 * wetR
    st = np.stack([mixL, mixR])
    fade = np.ones(N); fl = int(2.0 * SR); fade[-fl:] = np.linspace(1, 0, fl) ** 2; st *= fade
    st[:, :int(0.01*SR)] *= np.linspace(0, 1, int(0.01*SR))
    # compresión suave + limitador
    st = st / np.max(np.abs(st)); st = np.tanh(1.6 * st) / np.tanh(1.6)
    return st

def loud_gain(st, target=-14.0):  # aproximación ITU-R BS.1770 (K-weight vía EQ) sin compuertas
    k = np.stack([eq(c, [(20,-12),(60,-1),(100,0),(1500,0),(3000,3),(22050,4)]) for c in st])
    lufs = -0.691 + 10 * np.log10(np.mean(k ** 2) * 2)
    return 10 ** ((target - lufs) / 20)

def write(path, st):
    st = st * loud_gain(st); pk = np.max(np.abs(st))
    if pk > 0.95: st = np.tanh(st / 0.95 * 1.2) / np.tanh(1.2) * 0.95 if pk < 2 else st / pk * 0.95
    pcm = (np.clip(st.T, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())

if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1] / "desktop/ui/audio"
    write(out / "arranque-rock.wav", render()); print(out / "arranque-rock.wav")
