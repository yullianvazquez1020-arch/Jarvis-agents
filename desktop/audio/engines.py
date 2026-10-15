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
FEMALE_VOICES = {"paulina", "monica", "mónica", "soledad", "marisol", "angelica", "angélica", "francisca",
                 "luciana", "isabela", "esperanza", "sandy", "shelley", "grandma", "flo", "kate", "serena",
                 "stephanie", "martha", "samantha", "karen", "moira", "tessa", "fiona", "victoria", "allison",
                 "ava", "susan", "zoe", "catherine", "veena", "mei-jia", "carmit", "ellen", "laura", "joana"}
ES_PREFERRED = (("Juan", "es_MX"), ("Jorge", "es_ES"), ("Diego", "es_AR"))
EN_PREFERRED = (("Daniel", "en_GB"), ("Oliver", "en_GB"), ("Arthur", "en_GB"))
DEFAULT_WPM = 160                         # 160 ppm: pausado y claro (Yullian), JARVIS_VOZ_RATE lo cambia


def is_female(name):
    base = re.sub(r"\s*\(.*\)$", "", str(name or "")).strip().lower()
    return base in FEMALE_VOICES


def parse_say_listing(listing):
    out = []
    for line in str(listing or "").splitlines():
        m = re.match(r"^(.+?)\s+([a-z]{2}_[A-Z0-9]{2,3})\s+#", line)
        if m:
            out.append((m.group(1).strip(), m.group(2)))
    return out


def choose_voices(listing):
    """(voz_es, voz_en) masculinas instaladas; JARVIS_VOZ_ES / JARVIS_VOZ_EN mandan si existen."""
    voices = parse_say_listing(listing)
    names = {n for n, _ in voices}

    def pick(env, preferred, prefix, fallback_locales):
        forced = os.getenv(env, "").strip()
        if forced:
            return forced
        for name, _loc in preferred:
            if name in names:
                return name
        for loc in fallback_locales:
            for name, l in voices:
                if l == loc and not is_female(name):
                    return name
        for name, l in voices:
            if l.startswith(prefix) and not is_female(name):
                return name
        return ""
    es = pick("JARVIS_VOZ_ES", ES_PREFERRED, "es_", ("es_MX", "es_US", "es_CO", "es_AR", "es_CL", "es_ES"))
    en = pick("JARVIS_VOZ_EN", EN_PREFERRED, "en_GB", ("en_GB",))
    return es, en


_EN_WORDS = set("the you your is are and of to what how hello sir i it this that with for have has be will "
                "can do not we my me on in at today guess much money made".split())
_ES_WORDS = set("el la los las de que y en un una es por para con no se lo como qué hola señor tu su "
                "estoy está están hoy cuánto dinero hemos muy bien sí ya pero más".split())


def detect_lang(text):
    t = str(text or "").lower()
    if re.search(r"[ñáéíóú¿¡]", t):
        return "es"
    words = re.findall(r"[a-z']+", t)
    en = sum(w in _EN_WORDS for w in words); es = sum(w in _ES_WORDS for w in words)
    return "es" if es > en else "en"          # inglés (Daniel) es el idioma principal; español solo si lo es


def speech_rate(default=DEFAULT_WPM):
    try:
        return max(90, min(int(float(os.getenv("JARVIS_VOZ_RATE", "") or default)), 300))
    except ValueError:
        return default


# Juan/Daniel/auto en la config: siempre Daniel (en-GB). Juan solo si no hay ninguna voz inglesa instalada.
ROUTED_VOICES = {"auto-latino", "auto", "Juan", "Daniel"}


class MacSay:
    name = "macos_say"
    BASE_WPM = DEFAULT_WPM

    def __init__(self, voice=""):
        voice = (voice or "").strip()
        # Una voz femenina nunca se usa: se trata como auto (masculina bilingüe).
        self.voice = "auto-latino" if (not voice or is_female(voice)) else voice
        self._resolved_voice = None
        self._pair = None

    def voices(self):
        if self._pair is None:
            try:
                result = subprocess.run(["say", "-v", "?"], capture_output=True,
                                        text=True, timeout=5, check=True)
            except (OSError, subprocess.SubprocessError):
                raise EngineError("no pude consultar las voces locales de macOS") from None
            self._pair = choose_voices(result.stdout)
        return self._pair

    def resolve_voice(self, text=""):
        """Voz masculina según el idioma: Juan (es) / Daniel (en_GB); nunca descarga ni elige femenina."""
        if self.voice not in ROUTED_VOICES:
            return self.voice                            # voz personalizada explícita: se respeta
        try:
            es, en = self.voices()
        except EngineError:
            if self.voice in ("Juan", "Daniel"):
                return "Daniel"                          # sin listado de voces: Daniel, sin fallar
            raise
        if en:
            return en                                    # SOLO inglés británico (Daniel), nunca Juan
        if es:
            self._resolved_voice = es
            return es
        raise EngineError("no hay una voz masculina en español instalada (instala Juan en Ajustes → Accesibilidad → Contenido leído)")

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
        chosen = self.resolve_voice(text)
        wpm = speech_rate(DANIEL_WPM if chosen == "Daniel" else self.BASE_WPM)
        key = (chosen, int(wpm * rate), text)
        cache = self.__dict__.setdefault("_cache", {})
        if key in cache:                                  # saludo y frases repetidas: sin volver a generar el audio
            return cache[key], "audio/wav"
        with tempfile.TemporaryDirectory(prefix="jarvis-tts-") as tmp:
            src = Path(tmp) / "in.txt"; src.write_text(text, encoding="utf-8")   # text via file, never argv
            out = Path(tmp) / "out.wav"
            cmd = ["say", "-r", str(int(wpm * rate)), "-o", str(out), "--file-format=WAVE",
                   "--data-format=LEI16@44100", "-f", str(src)]
            if chosen:
                cmd[1:1] = ["-v", chosen]
            _run(cmd, timeout=60)
            data = out.read_bytes()
        if len(cache) > 32:
            cache.pop(next(iter(cache)))
        cache[key] = data
        return data, "audio/wav"


class Piper:
    name = "piper"

    def __init__(self, binary, model, length_scale=1.18):
        self.binary = binary or "piper"; self.model = model or ""
        try:                                              # 1.1 = pausado y claro
            self.length_scale = max(0.5, min(float(length_scale), 2.5))
        except (TypeError, ValueError):
            self.length_scale = 1.18

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
                  f"{self.length_scale / max(0.5, min(rate, 2.0)):.2f}"], timeout=60, stdin=text.encode("utf-8"))
            return out.read_bytes(), "audio/wav"


class NoTTS:
    name = "none"

    def problem(self):
        return "voz local no configurada (VOICE_TTS_BACKEND=none); las respuestas se muestran en texto"

    def synthesize(self, text, rate=1.0):
        raise EngineError(self.problem())


def pick_tts(cfg, platform=None, which=None, exists=None):
    """auto: macOS -> say; si hay piper y voz .onnx -> piper; si no, none (la respuesta queda en pantalla)."""
    platform = platform or sys.platform; which = which or shutil.which
    exists = exists or (lambda p: bool(p) and os.path.isfile(p))
    voice = str(cfg.get("VOICE_TTS_VOICE") or "")
    binary = cfg.get("VOICE_PIPER_BIN", "piper")
    if voice.endswith(".onnx") and exists(voice) and (which(binary) or exists(binary)):
        return "piper"
    if platform == "darwin" and which("say"):
        return "macos_say"
    if (which(binary) or exists(binary)) and exists(cfg.get("VOICE_TTS_VOICE", "")):
        return "piper"
    return "none"


DANIEL_WPM = 160                         # Daniel (say en la Mac): pausado y claro
# Voces femeninas conocidas en inglés: nunca se usan como respaldo en en-GB (Jarvis es voz masculina).
FEMALE_EN = {"samantha", "karen", "kate", "serena", "moira", "tessa", "victoria", "allison", "ava", "susan",
             "fiona", "veena", "zoe", "stephanie", "martha", "flo", "sandy", "shelley", "grandma",
             "en_gb-jenny_dioco-medium.onnx", "en_gb-cori-high.onnx", "en_gb-cori-medium.onnx",
             "en_gb-southern_english_female-low.onnx", "en_gb-semaine-medium.onnx", "en_gb-alba-medium.onnx"}


def is_female_en(voice):
    return os.path.basename(str(voice or "")).strip().lower() in FEMALE_EN


ALAN = "en_GB-alan-medium.onnx"          # voz británica masculina (igual que "Alan" del PR #116)


def default_voice(cfg, exists=None):
    """Con JARVIS_REPLY_LANGUAGE=en-GB y sin voz elegida: Alan (Piper) o Daniel (say en la Mac)."""
    exists = exists or os.path.isfile
    if cfg.get("VOICE_TTS_VOICE"):
        return cfg["VOICE_TTS_VOICE"]
    if str(cfg.get("JARVIS_REPLY_LANGUAGE", "")).lower().replace("_", "-") != "en-gb":
        return ""
    dirs = [cfg.get("VOICE_PIPER_DIR", ""), os.path.join(cfg.get("VOICE_HOME", ""), "voices"),
            os.path.expanduser("~/piper-voices"), "/workspace/piper-voices"]
    for d in dirs:
        if d and exists(os.path.join(d, ALAN)):
            return os.path.join(d, ALAN)
    return ""


def build(cfg):
    cfg = dict(cfg)
    if str(cfg.get("JARVIS_REPLY_LANGUAGE", "")).lower().replace("_", "-") == "en-gb" and is_female_en(cfg.get("VOICE_TTS_VOICE")):
        cfg["VOICE_TTS_VOICE"] = ""                    # en-GB: nunca voz femenina; cae a Alan o Daniel
    if not cfg.get("VOICE_TTS_VOICE"):
        v = default_voice(cfg)
        if v:
            cfg["VOICE_TTS_VOICE"] = v
        elif str(cfg.get("JARVIS_REPLY_LANGUAGE", "")).lower().startswith("en") and sys.platform == "darwin":
            cfg["VOICE_TTS_VOICE"] = "Daniel"
    stt = cfg.get("VOICE_STT_BACKEND", "none")
    tts = cfg.get("VOICE_TTS_BACKEND", "none")
    s = (WhisperCpp(cfg.get("VOICE_WHISPER_BIN", "whisper-cli"), cfg.get("VOICE_STT_MODEL_PATH", ""),
                    cfg.get("VOICE_STT_THREADS", "4"), language=cfg.get("VOICE_STT_LANGUAGE", "auto")) if stt == "whisper_cpp" else NoSTT())
    if tts == "auto":                                  # voz siempre lista: say en la Mac, Piper donde exista
        tts = pick_tts(cfg)
    if tts == "macos_say":
        t = MacSay(cfg.get("VOICE_TTS_VOICE", "auto-latino"))
    elif tts == "piper":
        t = Piper(cfg.get("VOICE_PIPER_BIN", "piper"), cfg.get("VOICE_TTS_VOICE", ""), cfg.get("VOICE_PIPER_LENGTH_SCALE", "1.18"))
    else:
        t = NoTTS()
    return s, t
