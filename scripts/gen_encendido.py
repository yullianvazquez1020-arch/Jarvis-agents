"""Genera la música ORIGINAL de Jarvis, solo síntesis numpy (sin muestras ni melodías de películas):

* desktop/ui/audio/ambiente.wav  — 40 s en bucle perfecto (96 ppm, 16 compases): pulso de sub-bajo,
  colchones analógicos cálidos, arpegio brillante, ritmo electrónico suave y crecida cinematográfica.
  Suena bajo la voz y se atenúa mientras Jarvis habla (startup.js).
* desktop/ui/audio/encendido.wav — ~6 s: crecida + impacto + acorde, la apertura del mismo tema.

Progresión y notas propias (re menor: Dm9 – B♭maj7 – Gm9 – A7sus4); no reproduce ningún tema existente."""
import pathlib, wave
import numpy as np

SR = 22050
BPM = 96; BEAT = 60 / BPM; BARS = 16; LOOP = BARS * 4 * BEAT        # 40.0 s
rng = np.random.default_rng(1020)


def hz(m): return 440.0 * 2 ** ((m - 69) / 12)


CHORDS = [  # (bajo, notas del colchón, notas del arpegio) — MIDI
    (38, (50, 53, 57, 64), (62, 65, 69, 72, 76, 72, 69, 65)),          # Dm9
    (34, (50, 53, 57, 58), (58, 62, 65, 69, 74, 69, 65, 62)),          # B♭maj7
    (31, (50, 53, 55, 57), (55, 58, 62, 65, 69, 65, 62, 58)),          # Gm9
    (33, (50, 52, 55, 57), (57, 62, 64, 67, 69, 67, 64, 62)),          # A7sus4
]


def lp_fast(x, a):
    k = max(1, int(SR / (a * 2.5))); return np.convolve(x, np.ones(k) / k, mode="same")


def sweep(x, k, lo, hi):            # filtro que se abre: mezcla de dos pasabajos
    return lp_fast(x, lo) * (1 - k) + lp_fast(x, hi) * k


def reverb_circ(x, secs=2.8, seed=7):
    """Reverb por convolución circular (FFT) con respuesta de ruido que decae: la cola envuelve al inicio,
    así el bucle no tiene costura."""
    n = len(x); r = np.random.default_rng(seed); k = int(secs * SR); tt = np.arange(k) / SR
    ir = r.standard_normal(k) * np.exp(-tt * 6.9 / secs); ir = lp_fast(ir, 5000); ir[:int(0.012 * SR)] = 0
    h = np.zeros(n); h[:k] = ir / np.sqrt((ir ** 2).sum())
    return np.real(np.fft.ifft(np.fft.fft(x) * np.fft.fft(h)))


def saw(f, t, det=(-0.006, 0.0, 0.0055)):
    return sum(2 * ((f * (1 + d) * t + i * 0.31) % 1) - 1 for i, d in enumerate(det)) / len(det)


def ambiente():
    n = int(LOOP * SR); t = np.arange(n) / SR; L = np.zeros(n); R = np.zeros(n)
    bar = 4 * BEAT
    for b in range(BARS):
        bass, pad, arp = CHORDS[b % 4]
        a0 = int(b * bar * SR); a1 = int((b + 1) * bar * SR); tt = t[a0:a1] - b * bar
        # colchón cálido: sierras desafinadas filtradas, entrada/salida suave por compás (sin clics)
        e = np.minimum(1, tt / 0.6) * np.minimum(1, (bar - tt) / 0.6) * 0.5 + 0.5
        p = sum(saw(hz(m), tt) for m in pad) / len(pad)
        p = lp_fast(p, 900 + 500 * np.sin(np.pi * b / BARS))
        L[a0:a1] += 0.22 * p * e; R[a0:a1] += 0.22 * np.roll(p, 37) * e
        # pulso de sub-bajo en corcheas con "bombeo"
        for k in range(8):
            s = int((b * bar + k * BEAT / 2) * SR); d = int(BEAT / 2 * SR); x = np.arange(d) / SR
            env = np.exp(-x * 7) * np.minimum(1, x / 0.004)
            v = np.sin(2 * np.pi * hz(bass) * x) * env * (1.0 if k % 2 == 0 else 0.6)
            L[s:s + d] += 0.35 * v; R[s:s + d] += 0.35 * v
        # arpegio brillante en semicorcheas (FM suave), paneo alterno
        for k in range(16):
            s = int((b * bar + k * BEAT / 4) * SR); d = int(BEAT * 0.9 * SR); x = np.arange(d) / SR
            f = hz(arp[k % 8] + 12)
            v = np.sin(2 * np.pi * f * x + 1.2 * np.exp(-x * 10) * np.sin(2 * np.pi * f * 2 * x)) * np.exp(-x * 9)
            gain = 0.05 + 0.04 * (b >= 8); pan = 0.5 + 0.35 * np.sin(k * 0.9)
            e2 = min(d, n - s); L[s:s + e2] += gain * (1 - pan) * v[:e2]; R[s:s + e2] += gain * pan * v[:e2]
        # ritmo electrónico sutil: bombo suave en 1 y 3 (desde el compás 4), hats filtrados
        for k in range(4):
            s = int((b * bar + k * BEAT) * SR); d = int(0.35 * SR); x = np.arange(d) / SR
            if b >= 4 and k in (0, 2):
                kick = np.sin(2 * np.pi * np.cumsum(45 + 90 * np.exp(-x * 30)) / SR) * np.exp(-x * 9)
                L[s:s + d] += 0.3 * kick; R[s:s + d] += 0.3 * kick
            if b >= 2:
                for h in (0.5,) if b < 8 else (0.25, 0.5, 0.75):
                    hs = s + int(h * BEAT * SR); hd = int(0.05 * SR)
                    hn = np.diff(rng.standard_normal(hd + 1)) * np.exp(-np.arange(hd) / SR * 80) * 0.02
                    L[hs:hs + hd] += hn; R[hs:hs + hd] += hn * 0.8
    # crecida cinematográfica: ruido y tono ascendente en los 2 últimos compases, vuelve al inicio del bucle
    s = int((BARS - 2) * bar * SR); x = t[s:] - t[s]; k = x / x[-1]
    sw = sweep(rng.standard_normal(len(x)), k, 400, 3400) * k ** 2 * 0.12
    sw += np.sin(2 * np.pi * np.cumsum(110 * 2 ** (k * 2)) / SR) * k ** 3 * 0.06
    L[s:] += sw; R[s:] += sw
    # capa rock-electrónica áspera: quinta de potencia saturada en negras, muy filtrada, desde el compás 8
    grit = np.zeros(n)
    for b in range(8, BARS):
        root = CHORDS[b % 4][0] + 12
        for k in range(4):
            s0 = int((b * bar + k * BEAT) * SR); d = int(BEAT * 0.95 * SR); x = np.arange(d) / SR
            v = saw(hz(root), x) + 0.7 * saw(hz(root + 7), x)
            grit[s0:s0 + d] += np.tanh(v * 3.0) * np.exp(-x * 3.5)
    grit = lp_fast(grit, 700) * 0.09
    L += grit; R += np.roll(grit, 90)
    # reverb estéreo (dos semillas = ancho real) para colchones/arpegio
    L += 0.32 * reverb_circ(L, seed=7); R += 0.32 * reverb_circ(R, seed=11)
    # eco estéreo (brillo) envuelto al principio: bucle sin costuras
    for src, dst, dly in ((L, R, 3 * BEAT / 4), (R, L, BEAT / 2)):
        dd = int(dly * SR); dst += 0.28 * np.roll(src, dd)
    st = np.stack([L, R], 1)
    st = st - st.mean(0)                                        # sin corriente continua
    st = np.tanh(st / np.percentile(np.abs(st), 99.7) * 0.9)   # limitador suave (sin recorte duro)
    f1, f2 = int(0.008 * SR), int(0.04 * SR)             # unión del bucle sin clic
    st[:f1] *= np.linspace(0, 1, f1)[:, None]; st[-f2:] *= np.linspace(1, 0, f2)[:, None]
    return (st / np.max(np.abs(st)) * 0.89 * 32767).astype(np.int16)   # pico −1 dBFS


def encendido(loop):
    d = int(6.0 * SR); x = np.arange(d) / SR; k = np.minimum(1, x / 3.2)
    riser = sweep(rng.standard_normal(d), k, 300, 4300) * k ** 2 * (x < 3.3) * 0.5
    riser += np.sin(2 * np.pi * np.cumsum(55 * 2 ** (k * 3)) / SR) * k ** 2 * (x < 3.3) * 0.3
    m = x >= 3.3; y = (x - 3.3).clip(0)
    hit = np.sin(2 * np.pi * np.cumsum((36 + 60 * np.exp(-y * 12)) * m) / SR) * np.exp(-y * 1.6) * m
    chord = sum(saw(hz(mm), x) for mm in (38, 50, 57, 62, 65, 69)) / 6 * np.exp(-y * 0.7) * m
    mono = riser + 0.9 * hit + 0.5 * lp_fast(chord, 1500)
    st = np.stack([mono, np.roll(mono, 60)], 1)
    head = loop[: d].astype(float) / 32767 * np.clip((x - 3.3) / 2.0, 0, 1)[:, None] * 0.5
    st = np.tanh(st / np.max(np.abs(st)) * 1.3) + head
    st[-int(0.3 * SR):] *= np.linspace(1, 0, int(0.3 * SR))[:, None]
    return (st / np.max(np.abs(st)) * 0.9 * 32767).astype(np.int16)


def write(path, data):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(data.tobytes())
    print(path)


if __name__ == "__main__":
    out = pathlib.Path(__file__).resolve().parents[1] / "desktop/ui/audio"
    amb = ambiente()
    write(out / "ambiente.wav", amb)
    write(out / "encendido.wav", encendido(amb))
