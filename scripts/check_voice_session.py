"""Exercise the installed local voice app without microphones, network or real speech."""
import importlib.util
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'desktop'))
spec = importlib.util.spec_from_file_location('voice_review_app', ROOT / 'desktop/app.py')
app = importlib.util.module_from_spec(spec); sys.modules[spec.name] = app; spec.loader.exec_module(app)
C = app.Companion
obj = C.__new__(C); obj.cfg = {'VOICE_WAKE_WORD_ENABLED': 'true', 'VOICE_WAKE_FOLLOW_S': '40'}
obj.lock = threading.RLock(); obj.last = {'text': 'Jarvis puede ayudarte con un informe.'}
with patch.object(app.time, 'monotonic', return_value=100):
    assert obj._wake_filter({'text': 'Yarvis. Hazme un informe'})['text'] == 'Jarvis. Hazme un informe'
    assert obj._wake_filter({'text': 'Amplía la introducción'})['text']
    assert obj._wake_filter({'text': 'Please, Jarvis, write an essay'})['text']
    assert obj._wake_filter({'text': 'Por favor Jarvis, escribe un informe'})['text']
    assert not obj._wake_filter({'text': 'Amplía la introducción'}, require_wake=True)['text']
    assert obj._wake_filter({'text': 'Jarvis puede ayudarte con un informe.'}, require_wake=True)['reason'] == 'playback_echo'
    assert not obj._wake_filter({'text': 'Jarvis.'})['text']
    obj.voice_follow(); assert obj._wake_until == 140
with patch.object(app.time, 'monotonic', return_value=141):
    assert not obj._wake_filter({'text': 'una conversación ajena'})['text']
obj.cfg['VOICE_WAKE_WORD_ENABLED'] = 'false'
assert not obj._wake_filter({'text': 'sin nombre'}, require_wake=True)['text']
assert obj._wake_filter({'text': 'sin nombre'})['text']

# Parallel HTTP requests cannot start concurrent whisper.cpp processes.
active = [0, 0]
def stt(wav, **kw):
    active[0] += 1; active[1] = max(active); time.sleep(.02); active[0] -= 1
    return {'text': 'Jarvis, hola'}
obj.home = ROOT; obj.retain = False; obj.stt = SimpleNamespace(transcribe=stt)
obj._playback_native = lambda: False
threads = [threading.Thread(target=obj.transcribe, args=(b'test',)) for _ in range(3)]
for thread in threads: thread.start()
for thread in threads: thread.join()
assert active[1] == 1
obj.stt.problem = lambda: ''
real_thread = threading.Thread; warm_threads = []
def track_thread(*args, **kwargs):
    thread = real_thread(*args, **kwargs); warm_threads.append(thread); return thread
with patch.object(app.threading, 'Thread', side_effect=track_thread):
    obj.prewarm_stt()
    worker = real_thread(target=obj.transcribe, args=(b'test',)); worker.start(); worker.join()
    for thread in warm_threads: thread.join()
assert active[1] == 1, 'warmup and real recognition must share the same lock'
obj.turns = {'cancel-test': {'state': 'consultando', 'cancelled': False}}
obj.stop_local_audio = Mock(); obj.emit = Mock()
obj.cancel_turn('cancel-test')
assert obj.turns['cancel-test']['state'] == 'cancelled'
assert obj.turns['cancel-test']['cancelled']

from audio import engines
voice = engines.MacSay('auto-latino'); voice._pair = ('Juan', 'Daniel')
assert voice.resolve_voice('Perfecto, gracias.') == 'Juan'
assert voice.resolve_voice('123') == 'Juan'
assert voice.resolve_voice('Sure, thanks.') == 'Daniel'
assert voice.resolve_voice('123') == 'Daniel'
import documentos
for text in ('Jarvis. Hazme una monografía', '¿Jarvis, me haces un informe?', 'Jarvis, can you write an essay?'):
    assert documentos.intent(text) == 'new', text
print('Wake aliases, playback echo gate, follow-up clock, STT serialization, cancellation and bilingual voice: OK')
