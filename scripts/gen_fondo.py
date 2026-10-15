"""Genera el FONDO cinematográfico ORIGINAL de Jarvis, v2 (solo síntesis numpy; sin muestras, sin temas existentes).

desktop/ui/audio/fondo.wav — 32 s estéreo, bucle perfecto (todo se calcula de forma circular):
  * colchón por capas: progresión original Dm(add9) → B♭maj7 → Gm9 → A(sus4→3), osciladores "supersaw"
    aditivos (7 voces desafinadas, estéreo ancho) con filtro que se abre y se cierra despacio;
  * sub-bajo senoidal que sigue la raíz y respira con cada acorde;
  * pulso sutil tipo latido (60 ppm, golpe grave filtrado) que hace "bombear" el colchón muy poco;
  * movimiento suave: campanas cristalinas (notas del acorde) con eco ping-pong y aire filtrado;
  * reverb de sala grande circular distinta en L/R.
Mezclado a ~-24 dBFS RMS para ir debajo de la voz; startup.js lo atenúa mientras Jarvis habla (ducking).
No sustituye ni cambia ambiente.wav/encendido.wav (gen_encendido.py). JARVIS_FONDO=off lo apaga."""
import pathlib, sys, wave
import numpy as np

SR = 32000; LOOP = 32.0; N = int(SR * LOOP)
t = np.arange(N) / SR
rng = np.random.default_rng(2026)
TARGET_DBFS = -24.0
BEAT = 1.0                                   # 60 ppm: 32 pulsos exactos por bucle
CHORDS = [  # (raíz MIDI del bajo, notas del colchón, notas de campana)
    (38, [50, 53, 57, 64, 69], [74, 77, 81, 76]),      # Dm(add9)
    (34, [46, 50, 53, 57, 62], [74, 77, 81, 69]),      # B♭maj7
    (31, [43, 50, 53, 57, 58], [70, 74, 77, 81]),      # Gm9
    (33, [45, 52, 57, 62, 64], [76, 81, 74, 73]),      # A sus4 → 3
]
SEG = LOOP / len(CHORDS)


def hz(m): return 440.0 * 2 ** ((m - 69) / 12)


def wrap_add(dst, x, start):                  # suma circular: lo que se pasa del final entra por el principio
    idx = (np.arange(len(x)) + start) % N
    np.add.at(dst, idx, x)


def lowpass_fft(x, cutoff, order=4):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / np.sqrt(1 + (f / cutoff) ** (2 * order)); return np.fft.irfft(X, len(x))


def highpass_fft(x, cutoff):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 - 1 / np.sqrt(1 + (f / cutoff) ** 4); return np.fft.irfft(X, len(x))


def saw_voice(f0, n, cutoff_curve, phase):  # diente de sierra aditivo con filtro variable en el tiempo (sin aliasing)
    tt = np.arange(n) / SR; out = np.zeros(n)
    for k in range(1, 40):
        if k * f0 > 9000: break
        g = (1.0 / k) / np.sqrt(1 + (k * f0 / cutoff_curve) ** 6)
        out += g * np.sin(2 * np.pi * k * f0 * tt + phase * k)
    return out


def pad_layer():
    L = np.zeros(N); R = np.zeros(N)
    seg_n = int(SEG * SR); tail = int(3.0 * SR); n = seg_n + tail
    tt = np.arange(n) / SR
    env = np.clip(tt / 2.2, 0, 1) ** 1.5 * np.clip((n / SR - tt) / 3.0, 0, 1) ** 1.5   # entra y sale despacio (cruce largo)
    for c, (_, notes, _) in enumerate(CHORDS):
        cutoff = 700 + 900 * (0.5 - 0.5 * np.cos(2 * np.pi * tt / (n / SR)))            # el filtro se abre a mitad del acorde
        for i, m in enumerate(notes):
            amp = 0.5 if i < 2 else 0.33
            for v, d in enumerate(np.linspace(-0.11, 0.11, 7)):                      # 7 voces desafinadas, abiertas en estéreo
                x = saw_voice(hz(m + d), n, cutoff, rng.uniform(0, 6.28)) * env * amp / 7
                pan = (v / 6.0)
                wrap_add(L, x * np.cos(pan * np.pi / 2), c * seg_n - tail // 2)
                wrap_add(R, x * np.sin(pan * np.pi / 2), c * seg_n - tail // 2)
    return L, R


def sub_layer():
    out = np.zeros(N); seg_n = int(SEG * SR); tail = int(2.0 * SR); n = seg_n + tail; tt = np.arange(n) / SR
    env = np.clip(tt / 1.0, 0, 1) * np.clip((n / SR - tt) / 2.0, 0, 1)
    for c, (root, _, _) in enumerate(CHORDS):
        f = hz(root - 12)
        x = (np.sin(2 * np.pi * f * tt) + 0.18 * np.sin(2 * np.pi * 2 * f * tt)) * env * (0.85 + 0.15 * np.sin(2 * np.pi * tt / 4))
        wrap_add(out, x, c * seg_n - tail // 2)
    return out


def pulse_layer():
    out = np.zeros(N); n = int(0.6 * SR); tt = np.arange(n) / SR
    for k, (delay, amp) in enumerate(((0.0, 1.0), (0.26, 0.55))):                     # "lub-dub" muy suave
        f = 46 + 30 * np.exp(-tt * 30)
        thump = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 9) * np.clip(tt / 0.008, 0, 1) * amp
        for b in range(int(LOOP / BEAT)):
            wrap_add(out, thump, int((b * BEAT + delay) * SR))
    duck = np.ones(N)                                                                   # bombeo sutil del colchón
    for b in range(int(LOOP / BEAT)):
        nn = int(0.7 * SR); tt2 = np.arange(nn) / SR
        wrap_add(duck, -0.12 * np.exp(-tt2 * 6) * np.clip(tt2 / 0.02, 0, 1), int(b * BEAT * SR))
    return lowpass_fft(out, 160), duck


def bell_layer():
    L = np.zeros(N); R = np.zeros(N); n = int(4.0 * SR); tt = np.arange(n) / SR
    for c, (_, _, bells) in enumerate(CHORDS):
        for j, m in enumerate(bells):
            f = hz(m); start = int((c * SEG + j * 2.0 + 0.5) * SR)
            x = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * f * 2.76 * tt) * np.exp(-tt * 3)
                 + 0.12 * np.sin(2 * np.pi * f * 5.4 * tt) * np.exp(-tt * 6))
            x *= np.exp(-tt * 1.4) * np.clip(tt / 0.006, 0, 1) * (0.9 if j % 2 == 0 else 0.7)
            pan = 0.3 if j % 2 == 0 else 0.7
            wrap_add(L, x * np.cos(pan * np.pi / 2), start); wrap_add(R, x * np.sin(pan * np.pi / 2), start)
    d = int(0.75 * SR)                                                                   # eco ping-pong circular
    eL, eR = L.copy(), R.copy(); fbL, fbR = L.copy(), R.copy()
    for k in range(1, 6):
        fbL, fbR = np.roll(fbR, d) * 0.5, np.roll(fbL, d) * 0.5
        eL += lowpass_fft(fbL, 5000 - 600 * k); eR += lowpass_fft(fbR, 5000 - 600 * k)
    return eL, eR


def air_layer(seed):
    r = np.random.default_rng(seed)
    x = highpass_fft(lowpass_fft(r.standard_normal(N), 3200), 600)
    return x * (0.55 + 0.45 * np.sin(2 * np.pi * 2 * t / LOOP + seed))


def reverb_circ(x, secs, seed):
    r = np.random.default_rng(seed); k = int(secs * SR); tt = np.arange(k) / SR
    ir = r.standard_normal(k) * np.exp(-tt * 6.9 / secs); ir[:int(0.025 * SR)] = 0
    ir = lowpass_fft(np.pad(ir, (0, N - k)), 4200)
    return np.fft.irfft(np.fft.rfft(x) * np.fft.rfft(ir), N) / np.sqrt(np.sum(ir ** 2))


def render():
    pL, pR = pad_layer(); sub = sub_layer(); pulse, duck = pulse_layer(); bL, bR = bell_layer()
    aL, aR = air_layer(1), air_layer(2)
    pL, pR = pL / np.std(pL + pR), pR / np.std(pL + pR)
    bscale = np.std(bL + bR); bL, bR = bL / bscale, bR / bscale
    sub /= np.std(sub); pulse /= np.std(pulse); aL /= np.std(aL); aR /= np.std(aR)
    dryL = pL * duck * 1.0 + bL * 0.32 + aL * 0.10
    dryR = pR * duck * 1.0 + bR * 0.32 + aR * 0.10
    wetL = reverb_circ(dryL, 4.5, 11); wetR = reverb_circ(dryR, 4.5, 12)
    low = sub * 0.30 + pulse * 0.24                                                     # graves en el centro, secos
    L = 0.55 * dryL + 0.6 * wetL + low; R = 0.55 * dryR + 0.6 * wetR + low
    x = np.stack([L, R], 1); x -= x.mean(0)
    rms = np.sqrt(np.mean(x ** 2)); x *= 10 ** (TARGET_DBFS / 20) / rms
    return np.clip(x, -1, 1)


def write(path, x):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(np.round(x * 32767).astype("<i2").tobytes())


if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1] / "desktop" / "ui" / "audio" / "fondo.wav"
    x = render(); write(out, x)
    print(out, f"{len(x) / SR:.1f}s rms={20 * np.log10(np.sqrt(np.mean(x ** 2))):.1f}dBFS peak={20*np.log10(np.abs(x).max()):.1f}dBFS")
