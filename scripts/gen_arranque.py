"""Genera desktop/ui/audio/arranque.wav: sonido ORIGINAL de arranque (~5 s), solo síntesis numpy, sin muestras.
Barrido ascendente de sintetizador + tres golpes de acorde de quinta con distorsión tipo rock."""
import wave, pathlib
import numpy as np

SR = 44100
def t(sec): return np.arange(int(SR * sec)) / SR

def saw(f, x): return 2 * ((f * x) % 1.0) - 1

def sweep(dur=2.6):
    x = t(dur); f = 55 * (2 ** (x / dur * 4))                  # A1 -> A5
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = 0.5 * np.sin(ph) + 0.25 * np.sign(np.sin(ph * 1.003)) + 0.15 * np.sin(ph * 2)
    noise = np.random.default_rng(7).standard_normal(len(x)) * (x / dur) ** 2 * 0.15
    return (s + noise) * np.linspace(0.05, 1, len(x)) ** 1.5

def power_chord(root, dur):
    x = t(dur); env = np.exp(-x * 2.2) * (1 - np.exp(-x * 400))
    s = sum(saw(root * m * d, x) for m in (1, 1.5, 2) for d in (0.997, 1.003))
    s = np.tanh(s * 2.5) * env                                    # distorsión suave
    kick = np.sin(2 * np.pi * 60 * x * np.exp(-x * 8)) * np.exp(-x * 9)
    return 0.7 * s + 0.8 * kick

def build():
    out = np.zeros(int(SR * 5.2))
    sw = sweep(); out[:len(sw)] += sw * 0.6
    for start, root, dur in ((2.6, 110.0, 0.55), (3.15, 130.81, 0.55), (3.7, 146.83, 1.5)):   # A, C, D
        pc = power_chord(root, dur); i = int(SR * start); out[i:i + len(pc)] += pc[: len(out) - i]
    out[-int(SR * 0.3):] *= np.linspace(1, 0, int(SR * 0.3))
    out /= np.max(np.abs(out)) * 1.12
    return (out * 32767).astype(np.int16)

if __name__ == "__main__":
    dest = pathlib.Path(__file__).resolve().parents[1] / "desktop/ui/audio/arranque.wav"
    with wave.open(str(dest), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
        w.writeframes(build()[::2].tobytes())
    print(dest)
