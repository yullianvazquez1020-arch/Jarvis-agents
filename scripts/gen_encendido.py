"""Genera desktop/ui/audio/encendido.wav: encendido de traje ORIGINAL (~5 s), solo síntesis numpy, sin muestras
ni melodías de películas. Servos mecánicos, carga de turbina/repulsor ascendente, golpe de metales cálido,
colchón cinematográfico, impacto grave y pitidos de HUD. Estéreo 44.1 kHz."""
import pathlib, wave
import numpy as np

SR = 44100; DUR = 5.0; N = int(SR * DUR)
rng = np.random.default_rng(1020)
T = np.arange(N) / SR


def seg(a, b): return (T >= a) & (T < b)


def env(a, att, dec, b):
    e = np.zeros(N); m = seg(a, b); x = T[m] - a
    e[m] = np.minimum(1, x / att) * np.exp(-np.maximum(0, x - att) / dec); return e


def lowpass(x, k):
    return np.convolve(x, np.ones(k) / k, mode="same")


def servo(a, d, f0, f1):            # motor: tono con armónicos + chirrido de engranes modulado
    m = seg(a, a + d); x = (T - a).clip(0, d)
    f = f0 + (f1 - f0) * np.sin(np.pi * x / d / 2)
    ph = 2 * np.pi * np.cumsum(f * m) / SR
    tone = np.sin(ph) * 0.5 + np.sin(2 * ph) * 0.25 + np.sign(np.sin(3 * ph)) * 0.08
    grind = lowpass(rng.standard_normal(N), 6) * (0.5 + 0.5 * np.sin(2 * np.pi * 38 * T))
    shape = np.where(m, np.sin(np.pi * x / d) ** 0.6, 0)
    return (tone + 0.35 * grind) * shape


def turbine():                      # carga del repulsor: barrido ascendente con batido y aire filtrado
    m = seg(0.9, 3.35); x = (T - 0.9).clip(0, 2.45) / 2.45
    f = 90 * 2 ** (x ** 1.6 * 4.3)
    ph = 2 * np.pi * np.cumsum(f * m) / SR
    s = np.sin(ph) + 0.5 * np.sin(ph * 1.5 + 0.3) + 0.3 * np.sin(ph * 2.01)
    air = lowpass(rng.standard_normal(N), 3) * x ** 2
    out = (0.6 * s + 0.3 * air) * x ** 1.8 * m
    tail = seg(3.35, 3.45); out[tail] *= np.linspace(1, 0, tail.sum())
    return out


def brass(a, root, d):              # metales cálidos: sierra filtrada con ataque suave, quinta + octava
    e = env(a, 0.06, d, a + d * 4); out = np.zeros(N)
    for mult, g in ((1, 1), (1.5, 0.7), (2, 0.55), (3, 0.2)):
        for det in (-0.004, 0.0, 0.004):
            out += g * (2 * ((root * mult * (1 + det) * T) % 1) - 1)
    return lowpass(out, 14) * e


def pad(a):                          # colchón cinematográfico: triangulares desafinadas, entrada lenta
    e = np.clip((T - a) / 1.2, 0, 1) * np.where(T > 4.4, np.clip((DUR - T) / 0.6, 0, 1), 1)
    out = np.zeros(N)
    for f in (73.42, 110.0, 146.83, 220.0, 277.18):       # re, la, re, la, do# (acorde mayor abierto)
        for det in (-0.003, 0.003):
            out += 2 * np.abs(2 * ((f * (1 + det) * T) % 1) - 1) - 1
    return out * e * (T > a)


def impact(a):                       # impacto grave: caída de 70 a 32 Hz + ruido de choque
    m = T >= a; x = (T - a).clip(0)
    boom = np.sin(2 * np.pi * np.cumsum((32 + 38 * np.exp(-x * 9)) * m) / SR) * np.exp(-x * 2.6)
    crack = lowpass(rng.standard_normal(N), 4) * np.exp(-x * 30)
    return (boom + 0.5 * crack) * m


def bleeps():
    out = np.zeros(N)
    for a, f in ((0.15, 1760), (0.32, 2349), (0.5, 1975), (2.2, 2637), (2.32, 2637), (4.05, 3136), (4.2, 2349)):
        e = env(a, 0.004, 0.035, a + 0.09)
        out += np.sin(2 * np.pi * f * T) * e
    return out


def build():
    L = R = 0
    s1, s2, s3 = servo(0.05, 0.55, 180, 420), servo(0.45, 0.5, 240, 520), servo(0.95, 0.7, 150, 380)
    tur, br, pd, im, bl = turbine(), brass(3.35, 73.42, 0.35) + 0.6 * brass(3.35, 146.83, 0.3), pad(2.4), impact(3.35), bleeps()
    L = 0.45 * s1 + 0.2 * s2 + 0.35 * s3 + 0.5 * tur + 0.55 * br + 0.18 * pd + 0.9 * im + 0.12 * bl
    R = 0.2 * s1 + 0.45 * s2 + 0.35 * s3 + 0.5 * tur + 0.55 * br + 0.18 * pd + 0.9 * im + 0.12 * np.roll(bl, 400)
    st = np.stack([L, R], 1)
    st = np.tanh(st / np.max(np.abs(st)) * 1.6)            # pegamento suave tipo compresor
    st[-int(SR * 0.15):] *= np.linspace(1, 0, int(SR * 0.15))[:, None]
    st /= np.max(np.abs(st)) * 1.1
    return (st * 32767).astype(np.int16)


if __name__ == "__main__":
    dest = pathlib.Path(__file__).resolve().parents[1] / "desktop/ui/audio/encendido.wav"
    with wave.open(str(dest), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(build().tobytes())
    print(dest)
