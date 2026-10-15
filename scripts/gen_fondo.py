"""Genera el FONDO ambiental ORIGINAL de Jarvis (solo síntesis numpy; sin muestras ni temas existentes):

desktop/ui/audio/fondo.wav — 32 s en bucle perfecto: drone grave (re), colchón cinematográfico lento
con quintas y novenas, brillo aireado y filtrado, respiración lenta. Mezclado a ~-24 dBFS RMS para ir
debajo de la voz; startup.js lo atenúa mientras Jarvis habla. JARVIS_FONDO=off lo apaga.
No sustituye ni cambia ambiente.wav/encendido.wav (gen_encendido.py)."""
import pathlib, wave
import numpy as np

SR = 22050; LOOP = 32.0; N = int(SR * LOOP)
t = np.arange(N) / SR
rng = np.random.default_rng(2026)
TARGET_DBFS = -24.0


def hz(m): return 440.0 * 2 ** ((m - 69) / 12)


def loop_freq(f):                       # frecuencia ajustada a ciclos enteros en el bucle: sin costura
    return round(f * LOOP) / LOOP


def lfo(cycles, phase=0.0):            # LFO con número entero de ciclos por bucle
    return np.sin(2 * np.pi * cycles * t / LOOP + phase)


def voice(m, detunes=(-0.06, 0.0, 0.07), amp=1.0, breath=1, ph=0.0):
    out = np.zeros(N)
    for d in detunes:
        f = loop_freq(hz(m + d))
        out += np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) + 0.25 * np.sin(2 * np.pi * 2 * f * t)
    return out / len(detunes) * amp * (0.75 + 0.25 * lfo(breath, ph))


def lowpass_fft(x, cutoff):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / (1 + (f / cutoff) ** 4); return np.fft.irfft(X, len(x))


def reverb_circ(x, secs=3.5):
    k = int(secs * SR); tt = np.arange(k) / SR
    ir = rng.standard_normal(k) * np.exp(-tt * 6.9 / secs); ir[:int(0.02 * SR)] = 0
    ir = lowpass_fft(np.pad(ir, (0, N - k)), 3500)
    return np.fft.irfft(np.fft.rfft(x) * np.fft.rfft(ir), N) / np.sqrt(np.sum(ir ** 2))


def render():
    drone = voice(26, amp=1.0, breath=1) + voice(38, amp=0.6, breath=2, ph=1.0)          # D1 + D2
    pad = (voice(50, amp=0.35, breath=2) + voice(57, amp=0.30, breath=3, ph=2.0)           # D3, A3
           + voice(64, amp=0.18, breath=1, ph=4.0) + voice(65, amp=0.10, breath=4, ph=0.5))  # E4 (9.ª), F4
    air = lowpass_fft(rng.standard_normal(N), 2500) * 0.05 * (0.5 + 0.5 * lfo(2, 1.3))
    shimmer = voice(76, detunes=(-0.03, 0.04), amp=0.05, breath=4, ph=3.0)
    mix = lowpass_fft(drone, 400) + lowpass_fft(pad, 1800) + air + shimmer
    mix = 0.6 * mix + 0.4 * reverb_circ(mix)
    mix -= mix.mean()
    rms = np.sqrt(np.mean(mix ** 2)); mix *= 10 ** (TARGET_DBFS / 20) / rms
    return np.clip(mix, -1, 1)


def write(path, x):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())


if __name__ == "__main__":
    out = pathlib.Path(__file__).resolve().parents[1] / "desktop" / "ui" / "audio" / "fondo.wav"
    x = render(); write(out, x)
    print(out, f"{len(x) / SR:.1f}s rms={20 * np.log10(np.sqrt(np.mean(x ** 2))):.1f}dBFS")
