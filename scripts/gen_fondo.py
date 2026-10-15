"""Genera el FONDO ORIGINAL de Jarvis, v3 "pulso" (solo síntesis numpy; sin muestras, sin temas existentes).

desktop/ui/audio/fondo.wav — 32 s estéreo, 120 ppm (64 pulsos), bucle perfecto (todo circular):
  * bombo electrónico en cada pulso + palmada filtrada en 2 y 4 + hi-hat de ruido en corcheas;
  * bajo de sintetizador en semicorcheas con filtro y "sidechain" al bombo (pulso rock/electrónico ligero);
  * colchón supersaw de progresión propia Dm → B♭ → F → C, arpegio cristalino con eco ping-pong;
  * riser de ruido en el último compás de cada 8 s que cierra sobre el primero (energía sin costura).
Mezclado a ~-24 dBFS RMS para ir debajo de la voz; startup.js lo atenúa mientras Jarvis habla (ducking).
No cambia ambiente.wav/encendido.wav/arranque-rock.wav. JARVIS_FONDO=off lo apaga."""
import pathlib, sys, wave
import numpy as np

SR = 32000; LOOP = 32.0; N = int(SR * LOOP)
t = np.arange(N) / SR
rng = np.random.default_rng(3030)
TARGET_DBFS = -24.0
BEAT = 0.5
CHORDS = [(38, [50, 53, 57, 62]), (34, [46, 50, 53, 58]), (41, [53, 57, 60, 65]), (36, [48, 52, 55, 60])]
SEG = LOOP / 8                                  # 4 s por acorde, la progresión dos veces


def hz(m): return 440.0 * 2 ** ((m - 69) / 12)


def place(buf, ev, at):
    i = int(round(at * SR)) % N; n = len(ev)
    idx = (np.arange(n) + i) % N
    np.add.at(buf, idx, ev)


def lp(x, a):                                    # paso bajo de 1 polo, circular (2 pasadas para estado estable)
    y = np.empty_like(x); s = x[-1]
    for _ in range(2):
        for k in range(len(x)):
            s += a * (x[k] - s); y[k] = s
    return y


def chord_at(time): return CHORDS[int(time // SEG) % 4]


L = np.zeros(N); R = np.zeros(N)
# bombo
kt = np.arange(int(0.35 * SR)) / SR
kick = np.sin(2 * np.pi * (45 * kt + 90 * (1 - np.exp(-kt * 30)) / 30)) * np.exp(-kt * 9)
for b in range(64):
    place(L, kick * 0.9, b * BEAT); place(R, kick * 0.9, b * BEAT)
# palmada y hi-hat
ct = np.arange(int(0.18 * SR)) / SR
clap = rng.standard_normal(len(ct)) * np.exp(-ct * 22)
clap = np.diff(np.concatenate([[0], clap])) * 0.6
for b in range(1, 64, 2):
    place(L, clap * 0.5, b * BEAT + 0.003); place(R, clap * 0.5, b * BEAT)
ht = np.arange(int(0.05 * SR)) / SR
for e in range(128):
    h = np.diff(np.concatenate([[0], rng.standard_normal(len(ht))])) * np.exp(-ht * 70) * (0.16 if e % 2 else 0.09)
    place(L if e % 4 < 2 else R, h, e * BEAT / 2)
# sidechain (bombeo) circular
duck = 1 - 0.55 * np.exp(-((t % BEAT) / 0.11))
# bajo en semicorcheas
bass = np.zeros(N); st = np.arange(int(BEAT / 4 * SR)) / SR
for s in range(256):
    at = s * BEAT / 4; root = chord_at(at)[0] + (12 if s % 8 == 6 else 0)
    f = hz(root); saw = 2 * ((f * st) % 1) - 1
    env = np.exp(-st * 14) * 0.8 + 0.2
    place(bass, saw * env * 0.35, at)
bass = lp(bass, 0.08) * duck
# colchón supersaw
padL = np.zeros(N); padR = np.zeros(N)
for c in range(8):
    seg = (t >= c * SEG) & (t < (c + 1) * SEG)
    for m in chord_at(c * SEG)[1]:
        for v, d in enumerate((-0.12, -0.05, 0, 0.05, 0.12)):
            ph = rng.random()
            w = 2 * (((hz(m) * (1 + d / 100)) * t + ph) % 1) - 1
            (padL if v % 2 else padR)[seg] += w[seg] * 0.035
xf = np.minimum(1, np.minimum((t % SEG) / 0.25, (SEG - t % SEG) / 0.25))
padL = lp(padL * xf, 0.05) * duck; padR = lp(padR * xf, 0.05) * duck
# arpegio con eco ping-pong
arp = np.zeros(N); at_ = np.arange(int(0.3 * SR)) / SR
for s in range(128):
    at = s * BEAT / 2; notes = chord_at(at)[1]
    m = notes[[0, 2, 1, 3][s % 4]] + 12
    place(arp, np.sin(2 * np.pi * hz(m) * at_) * np.exp(-at_ * 12) * 0.12, at)
d = int(0.375 * SR)
arpL = arp + 0.35 * np.roll(arp, 2 * d); arpR = 0.5 * arp + 0.45 * np.roll(arp, d)
# riser en el último compás de cada bloque de 8 s
nz = rng.standard_normal(N); ph = (t % 8.0)
riser = np.where(ph > 6.0, (ph - 6.0) / 2.0, 0) ** 2 * 0.05 * nz
riser = np.diff(np.concatenate([[0], riser]))
L += bass + padL + arpL + riser; R += bass + padR + arpR + riser
x = np.stack([L, R], 1); x -= x.mean(0)
x *= 10 ** (TARGET_DBFS / 20) / np.sqrt(np.mean(x ** 2))
x = np.clip(x, -0.98, 0.98)
k = int(np.argmin(np.abs(x - np.roll(x, 1, 0)).max(1)[: SR // 4]))   # la costura cae en el punto más suave del 1.er cuarto de s
x = np.roll(x, -k, 0)

out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).parents[1] / "desktop" / "ui" / "audio" / "fondo.wav")
with wave.open(str(out), "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((x * 32767).astype("<i2").tobytes())
print(out, f"{20 * np.log10(np.sqrt(np.mean(x ** 2))):.1f} dBFS RMS")
