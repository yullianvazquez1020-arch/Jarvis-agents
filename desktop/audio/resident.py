"""Private, model-resident whisper.cpp server; same local model, no cloud audio.

Starts one supervised child on loopback with a random private route. Transcripts
and process output are never logged. The supervisor closes the server when the
panel exits, including an unexpected parent exit (EOF on the ownership pipe).
"""
import atexit
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

from .engines import EngineError
from .wav import check_wav, make_wav, RATE


def has_voice_energy(data):
    import io, struct, wave
    with wave.open(io.BytesIO(data), "rb") as source:
        pcm = source.readframes(source.getnframes())
    active = 0
    for offset in range(0, len(pcm), 640):
        block = pcm[offset:offset+640]
        if len(block) < 640: continue
        energy = sum(v[0] ** 2 for v in struct.iter_unpack("<h", block)) / 320
        if energy >= (32768 * .002) ** 2:
            active += 1
            if active >= 5: return True
    return False


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class ResidentWhisper:
    name = 'whisper_resident'

    def __init__(self, binary, model, threads=4, language='auto', fast=True, fallback=None):
        self.binary = str(binary); self.model = str(model)
        self.threads = max(1, min(16, int(threads))); self.language = language; self.fast = bool(fast)
        self.fallback = fallback; self._lock = threading.RLock(); self._proc = None
        self._url = ''; self._tmp = None
        self._http = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        atexit.register(self.close)

    def problem(self):
        if not os.path.isfile(self.binary) or not os.access(self.binary, os.X_OK):
            return self.fallback.problem() if self.fallback else 'No encuentro whisper-server local'
        if not Path(self.model).is_file() or self.model.endswith('.en.bin'):
            return 'Se necesita el mismo modelo multilingüe local'
        return ''

    def _json(self, path, data=None, content_type=None, timeout=2):
        request = urllib.request.Request(self._url + path, data=data)
        if content_type: request.add_header('Content-Type', content_type)
        try:
            with self._http.open(request, timeout=timeout) as response:
                raw = response.read(1_048_577)
                if len(raw) > 1_048_576: raise ValueError('response too large')
            value = json.loads(raw)
            if not isinstance(value, dict): raise ValueError('invalid response')
            return value
        except (OSError, ValueError, urllib.error.URLError):
            raise EngineError('El reconocedor residente no respondió correctamente') from None

    def start(self):
        with self._lock:
            if self._proc is not None and self._proc.poll() is None: return
            self.close()
            why = self.problem()
            if why: raise EngineError(why)
            try:
                help_run = subprocess.run([self.binary, '--help'], capture_output=True, timeout=10)
                help_text = (help_run.stdout + help_run.stderr).decode(errors='replace')
                if '--request-path' not in help_text or '--host' not in help_text:
                    raise EngineError('Esta versión de whisper-server no admite la ruta privada requerida')
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
                prefix = '/jarvis-' + secrets.token_hex(16)
                self._url = 'http://127.0.0.1:' + str(port) + prefix
                self._tmp = tempfile.TemporaryDirectory(prefix='jarvis-whisper-')
                command = [self.binary, '-m', self.model, '-t', str(self.threads), '-l', self.language,
                           '--host', '127.0.0.1', '--port', str(port), '--request-path', prefix, '-nt']
                if '--no-context' in help_text: command += ['-nc']
                if '--public' in help_text: command += ['--public', self._tmp.name]
                self._proc = subprocess.Popen([sys.executable, '-m', 'desktop.audio.resident', '--supervise'] + command,
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    cwd=str(Path(__file__).resolve().parents[2]))
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    if self._proc.poll() is not None: raise EngineError('whisper-server terminó al arrancar')
                    try:
                        if self._json('/health').get('status') == 'ok': break
                    except EngineError: pass
                    time.sleep(.1)
                else: raise EngineError('whisper-server no terminó de cargar el modelo')
                # Prime the same reduced encoder context before automatic language detection.
                tone = make_wav([int(1500 * math.sin(2 * math.pi * 220 * i / RATE)) for i in range(int(RATE * .4))])
                self._infer(tone, language='es')  # discarded synthetic signal, never microphone audio
            except Exception as exc:
                self.close()
                if isinstance(exc, EngineError): raise
                raise EngineError('No pude arrancar el reconocedor residente local') from None

    def _infer(self, wav, language=None):
        seconds = check_wav(wav)
        boundary = 'jarvis' + secrets.token_hex(20)
        fields = {'response_format': 'json', 'language': language or self.language,
                  'audio_ctx': str(min(1500, max(512, int(seconds * 50) + 64))),
                  'no_context': 'true', 'translate': 'false'}
        if self.fast: fields.update(beam_size='1', best_of='1')
        parts = []
        for key, value in fields.items():
            parts.append(('--' + boundary + '\r\nContent-Disposition: form-data; name="' + key + '"\r\n\r\n' + value + '\r\n').encode())
        parts += [('--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="phrase.wav"\r\nContent-Type: audio/wav\r\n\r\n').encode(), wav,
                  ('\r\n--' + boundary + '--\r\n').encode()]
        value = self._json('/inference', b''.join(parts), 'multipart/form-data; boundary=' + boundary,
                           timeout=max(30, int(seconds * 6)))
        text = value.get('text')
        if not isinstance(text, str) or len(text) > 20000: raise EngineError('Respuesta de reconocimiento inválida')
        text = re.sub(r'\[(?:BLANK_AUDIO|MUSIC|NOISE|Música|música)\]|\((?:música|ruido)\)', ' ', text)
        return {'text': re.sub(r'\s+', ' ', text).strip(), 'language': self.language,
                'duration_s': seconds, 'engine': self.name}

    def transcribe(self, wav_bytes, retain_dir=None):
        seconds = check_wav(wav_bytes)
        if not has_voice_energy(wav_bytes):
            return {'text': '', 'reason': 'no_voice_energy', 'language': self.language,
                    'duration_s': seconds, 'engine': self.name}
        with self._lock:
            try:
                self.start(); result = self._infer(wav_bytes)
            except EngineError:
                self.close()
                if self.fallback is not None:
                    return self.fallback.transcribe(wav_bytes, retain_dir=retain_dir)
                raise
            if retain_dir:
                path = Path(retain_dir); path.mkdir(parents=True, exist_ok=True, mode=0o700)
                target = path / (secrets.token_hex(6) + '.wav')
                fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as out: out.write(wav_bytes)
            return result

    def close(self):
        with self._lock:
            proc = self._proc; self._proc = None
            if proc is not None:
                if proc.stdin:
                    try: proc.stdin.close()
                    except OSError: pass
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try: proc.wait(timeout=5)
                    except subprocess.TimeoutExpired: proc.kill(); proc.wait()
            if self._tmp is not None: self._tmp.cleanup(); self._tmp = None
            self._url = ''


def supervise(command):
    """Do not leave a model process behind if the owning panel disappears."""
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    child = subprocess.Popen(command, stdin=subprocess.DEVNULL)
    def watch_owner():
        sys.stdin.buffer.read(1); stop.set()
    threading.Thread(target=watch_owner, daemon=True).start()
    try:
        while child.poll() is None and not stop.wait(.1): pass
    finally:
        if child.poll() is None:
            child.terminate()
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
    return child.returncode or 0

if __name__ == '__main__':
    if len(sys.argv) < 3 or sys.argv[1] != '--supervise': raise SystemExit('Private supervisor entry point')
    raise SystemExit(supervise(sys.argv[2:]))
