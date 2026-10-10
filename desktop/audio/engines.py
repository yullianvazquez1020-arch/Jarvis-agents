"""Local speech engines behind small adapters. Python 3.8+, standard library only.

STT: "whisper_cpp" (runs the whisper.cpp command-line program you build/install) or "none".
TTS: "macos_say" (voices already installed in macOS, offline), "piper" (classic piper CLI) or "none".
Nothing here downloads models or calls a paid service. An engine that is not installed reports itself as
unavailable; it is never presented as connected."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .wav import check_wav


class EngineError(RuntimeError):
    pass


# --- text that is safe to speak ---------------------------------------------------------------------
_SECRET_RX = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(-----END [A-Z ]*PRIVATE KEY-----|$)", re.S),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bjd1\.\d+\.[A-Za-z0-9_-]{20,}"),
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35})"),
    re.compile(r"(?<![\d-])(?:\d[ -]?){13,19}(?![\d-])"),
)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")


def speakable(text, limit=600):
    t = str(text or "")
    for rx in _SECRET_RX:
        t = rx.sub(" ", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = _EMOJI.sub(" ", t)
    t = re.sub(r"[*_`#>|•\[\]{}<>]+", " ", t)
    # Keep sentence pauses when a displayed list is read by the local voice.
    t = re.sub(r"(?<=[^\s.!?:;])\s*\n+", ". ", t)
    return re.sub(r"\s+", " ", t).strip()[:limit]


def _run(cmd, timeout, stdin=None, cwd=None):
    try:
        p = subprocess.run(cmd, input=stdin, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise EngineError("el motor tardó demasiado") from None
    except OSError as e:
        raise EngineError(f"no pude ejecutar el motor ({type(e).__name__})") from None
    if p.returncode != 0:
        raise EngineError(f"el motor terminó con error ({p.returncode})")
    return p


# --- STT ------------------------------------------------------------------------------------------
class WhisperCpp:
    name = "whisper_cpp"

    def __init__(self, binary, model, threads=4, language="es"):
        self.binary = binary or ""; self.model = model or ""; self.threads = int(threads); self.language = language

    def problem(self):
        if not self.binary or not (shutil.which(self.binary) or os.access(self.binary, os.X_OK)):
            return "no encuentro el programa de whisper.cpp (VOICE_WHISPER_BIN)"
        if not self.model or not Path(self.model).is_file():
            return "no encuentro el modelo (VOICE_STT_MODEL_PATH)"
        if Path(self.model).name.endswith(".en.bin"):
            return "ese modelo es solo inglés (.en); usa un modelo multilingüe para español"
        return ""

    def transcribe(self, wav_bytes, retain_dir=None):
        seconds = check_wav(wav_bytes)
        why = self.problem()
        if why:
            raise EngineError(why)
        with tempfile.TemporaryDirectory(prefix="jarvis-stt-") as tmp:   # per request, always deleted
            src = Path(tmp) / "in.wav"; src.write_bytes(wav_bytes)
            out = Path(tmp) / "out"
            _run([self.binary, "-m", self.model, "-f", str(src), "-l", self.language, "-t", str(self.threads),
                  "-nt", "-np", "-otxt", "-of", str(out)], timeout=max(30, int(seconds * 6)))
            txt = out.with_suffix(".txt")
            text = txt.read_text(encoding="utf-8", errors="replace") if txt.is_file() else ""
            if retain_dir:
                Path(retain_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copy(src, Path(retain_dir) / f"{os.urandom(6).hex()}.wav")
        text = re.sub(r"\[(BLANK_AUDIO|MUSIC|NOISE|Música|música)\]|\((música|ruido)\)", " ", text)
        return {"text": re.sub(r"\s+", " ", text).strip(), "language": self.language, "duration_s": seconds,
                "engine": self.name}


class NoSTT:
    name = "none"

    def problem(self):
        return "reconocimiento de voz local no configurado (VOICE_STT_BACKEND=none); puedes escribir"

    def transcribe(self, wav_bytes, retain_dir=None):
        raise EngineError(self.problem())


# --- TTS ------------------------------------------------------------------------------------------
class MacSay:
    name = "macos_say"
    BASE_WPM = 175

    def __init__(self, voice=""):
        self.voice = voice or ""
        self._resolved_voice = None

    def resolve_voice(self):
        """Choose an installed Latin-American Spanish voice; never download one."""
        if self.voice != "auto-latino":
            return self.voice
        if self._resolved_voice is not None:
            return self._resolved_voice
        try:
            result = subprocess.run(["say", "-v", "?"], capture_output=True,
                                    text=True, timeout=5, check=True)
        except (OSError, subprocess.SubprocessError):
            raise EngineError("no pude consultar las voces locales de macOS") from None
        voices = []
        for line in result.stdout.splitlines():
            match = re.match(r"^(.+?)\s+(es_[A-Z]{2})\s+#", line)
            if match:
                voices.append((match.group(1).strip(), match.group(2)))
        for locale in ("es_PR", "es_MX", "es_CO", "es_AR", "es_CL", "es_ES"):
            chosen = next((name for name, loc in voices if loc == locale), None)
            if chosen:
                self._resolved_voice = chosen
                return chosen
        raise EngineError("no hay una voz española instalada; selecciona una en macOS")

    def problem(self):
        if sys.platform != "darwin" or not shutil.which("say"):
            return "la voz del sistema solo existe en macOS (comando say)"
        return ""

    def synthesize(self, text, rate=1.0):
        why = self.problem()
        if why:
            raise EngineError(why)
        text = speakable(text)
        if not text:
            raise EngineError("no hay texto que leer")
        with tempfile.TemporaryDirectory(prefix="jarvis-tts-") as tmp:
            src = Path(tmp) / "in.txt"; src.write_text(text, encoding="utf-8")   # text via file, never argv
            out = Path(tmp) / "out.wav"
            cmd = ["say", "-r", str(int(self.BASE_WPM * rate)), "-o", str(out), "--file-format=WAVE",
                   "--data-format=LEI16@22050", "-f", str(src)]
            chosen = self.resolve_voice()
            if chosen:
                cmd[1:1] = ["-v", chosen]
            _run(cmd, timeout=60)
            return out.read_bytes(), "audio/wav"


class Piper:
    name = "piper"

    def __init__(self, binary, model):
        self.binary = binary or "piper"; self.model = model or ""

    def problem(self):
        if not (shutil.which(self.binary) or os.access(self.binary, os.X_OK)):
            return "no encuentro el programa piper (VOICE_PIPER_BIN)"
        if not self.model or not Path(self.model).is_file():
            return "no encuentro la voz de Piper (VOICE_TTS_VOICE = ruta al .onnx)"
        return ""

    def synthesize(self, text, rate=1.0):
        why = self.problem()
        if why:
            raise EngineError(why)
        text = speakable(text)
        if not text:
            raise EngineError("no hay texto que leer")
        with tempfile.TemporaryDirectory(prefix="jarvis-tts-") as tmp:
            out = Path(tmp) / "out.wav"
            _run([self.binary, "--model", self.model, "--output_file", str(out), "--length_scale",
                  f"{1 / max(0.5, min(rate, 2.0)):.2f}"], timeout=60, stdin=text.encode("utf-8"))
            return out.read_bytes(), "audio/wav"


class NoTTS:
    name = "none"

    def problem(self):
        return "voz local no configurada (VOICE_TTS_BACKEND=none); las respuestas se muestran en texto"

    def synthesize(self, text, rate=1.0):
        raise EngineError(self.problem())


def build(cfg):
    stt = cfg.get("VOICE_STT_BACKEND", "none")
    tts = cfg.get("VOICE_TTS_BACKEND", "none")
    s = (WhisperCpp(cfg.get("VOICE_WHISPER_BIN", "whisper-cli"), cfg.get("VOICE_STT_MODEL_PATH", ""),
                    cfg.get("VOICE_STT_THREADS", "4")) if stt == "whisper_cpp" else NoSTT())
    if tts == "macos_say":
        t = MacSay(cfg.get("VOICE_TTS_VOICE", ""))
    elif tts == "piper":
        t = Piper(cfg.get("VOICE_PIPER_BIN", "piper"), cfg.get("VOICE_TTS_VOICE", ""))
    else:
        t = NoTTS()
    return s, t
