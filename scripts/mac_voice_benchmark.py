#!/usr/bin/env python3
"""Measure installed local recognition options; optionally apply a qualified winner.

No microphone, account keys, model downloads, cloud inference, or business actions.
Synthetic speech is a screening test, not proof of real conversation quality.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import unicodedata

PHRASES = ('La ventana está abierta y la puerta está cerrada.',
           'Primero escucha mi pregunta y después responde con calma.')
KEYS = ('VOICE_STT_MODEL_PATH', 'VOICE_STT_THREADS', 'VOICE_STT_FAST')


def words(text):
    text = unicodedata.normalize('NFKD', text.lower())
    return re.findall(r'[a-z0-9]+', ''.join(c for c in text if not unicodedata.combining(c)))


def accuracy(expected, actual):
    a, b = words(expected), words(actual)
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        new = [i]
        for k, y in enumerate(b, 1):
            new.append(min(new[-1] + 1, row[k] + 1, row[k-1] + (x != y)))
        row = new
    return max(0, 1 - row[-1] / max(1, len(a)))


def choose(results, baseline):
    """Require two accurate samples, <=2 s each and >=25% median improvement."""
    if len(baseline) != 2 or any('error' in r for r in baseline):
        return None
    before = statistics.median(r['seconds'] for r in baseline)
    qualified = [r for r in results if len(r['samples']) == 2 and all(
        'error' not in s and s['accuracy'] >= .90 and s['seconds'] <= 2.0
        for s in r['samples']) and statistics.median(s['seconds'] for s in r['samples']) <= before * .75]
    return min(qualified, key=lambda r: statistics.median(s['seconds'] for s in r['samples'])) if qualified else None


def active_repo(home):
    path = home / 'Library/LaunchAgents/com.jarvis.desktop.plist'
    with path.open('rb') as f:
        p = plistlib.load(f)
    candidates = [Path(a).resolve().parents[1] for a in p.get('ProgramArguments', [])
                  if str(a).endswith('/scripts/mac_setup.py')]
    if len(candidates) != 1 or not (candidates[0] / 'desktop/app.py').is_file():
        raise RuntimeError('No se pudo identificar la instalación activa; no se cambió nada.')
    return candidates[0]


def config(home, repo):
    for path in (home / '.jarvis-desktop/config.env', repo / 'desktop/config.env'):
        if path.is_file():
            raw = path.read_text()
            values = {}
            for line in raw.splitlines():
                if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    values[k.strip()] = v.strip().strip('\"').strip("'")
            return path, raw, values
    raise RuntimeError('No se encontró la configuración activa; no se cambió nada.')


def replace_settings(raw, settings):
    lines = [s for s in raw.splitlines() if s.partition('=')[0].strip() not in settings]
    return '\n'.join(lines + [k + '=' + str(v) for k, v in settings.items()]) + '\n'


def atomic_write(path, text):
    fd, name = tempfile.mkstemp(prefix='voice-config-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(text)
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def run_sample(binary, candidate, sample, expected, directory, language):
    output = directory / 'recognition'
    if output.with_suffix('.txt').exists():
        output.with_suffix('.txt').unlink()
    cmd = [binary, '-m', candidate['model'], '-f', str(sample), '-l', language,
           '-t', str(candidate['threads']), '-nt', '-otxt', '-of', str(output)]
    if candidate['fast']:
        cmd += ['-bs', '1', '-bo', '1']
    start = time.perf_counter()
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=60)
        elapsed = time.perf_counter() - start
        if p.returncode or not output.with_suffix('.txt').is_file():
            return {'error': 'recognizer_failed', 'seconds': round(elapsed, 3)}
        # Keep only numerical engine timings; never persist raw process output.
        timing = {name: float(ms) for name, ms in re.findall(
            r'([a-z_]+) time\s*=\s*([\d.]+)\s*ms', p.stderr.decode(errors='replace'))}
        return {'seconds': round(elapsed, 3), 'accuracy': round(accuracy(expected, output.with_suffix('.txt').read_text()), 3),
                'engine_ms': timing}
    except subprocess.TimeoutExpired:
        return {'error': 'timeout', 'seconds': 60}


def restart_and_check(repo):
    spec = importlib.util.spec_from_file_location('voice_installer_check', repo / 'scripts/install_combinado_update.py')
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    if helper.service(repo, 'stop') or helper.service(repo, 'start'):
        return False
    for _ in range(20):
        if helper.running_from(repo):
            return True
        time.sleep(1)
    return False


def apply_choice(path, original, candidate, repo):
    if path.is_symlink() or path.read_text() != original:
        raise RuntimeError('La configuración cambió durante la prueba; no se sobrescribió.')
    backup = path.with_name('config.before-voice-benchmark-' + str(time.time_ns()) + '.env')
    shutil.copyfile(path, backup); backup.chmod(0o600)
    settings = dict(zip(KEYS, (candidate['model'], candidate['threads'], str(candidate['fast']).lower())))
    atomic_write(path, replace_settings(original, settings))
    try:
        if restart_and_check(repo):
            return {'applied': True}
    except Exception:
        pass
    atomic_write(path, original)
    try:
        healthy = restart_and_check(repo)
    except Exception:
        healthy = False
    return {'applied': False, 'rollback_healthy': healthy}


def recent_stages(home):
    path = home / '.jarvis-desktop/latencia.log'
    rows = []
    if path.is_file():
        for line in path.read_text().splitlines()[-30:]:
            try:
                r = json.loads(line)
                if 'stt_ms' in r:
                    rows.append(r)
            except (ValueError, TypeError):
                pass
    return {k: round(statistics.median(r[k] for r in rows if isinstance(r.get(k), (int, float))), 1)
            for k in ('stt_ms', 'llm_first_token_ms', 'tts_first_audio_ms', 'total_ms')
            if any(isinstance(r.get(k), (int, float)) for r in rows)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)
    if sys.platform != 'darwin':
        raise RuntimeError('Esta prueba debe ejecutarse en la Mac de Jarvis.')
    home = Path.home(); repo = active_repo(home)
    path, original, cfg = config(home, repo)
    if cfg.get('VOICE_STT_BACKEND') != 'whisper_cpp' or cfg.get('VOICE_STT_LANGUAGE', 'es') not in ('es', 'auto'):
        raise RuntimeError('La configuración cambió; esta prueba requiere Whisper local en español o automático.')
    if any(os.environ.get(k) for k in KEYS + ('VOICE_WHISPER_BIN', 'VOICE_STT_LANGUAGE')):
        raise RuntimeError('Hay ajustes de voz en el entorno; no se cambiará el archivo sin resolver esa diferencia.')
    binary = cfg.get('VOICE_WHISPER_BIN', '')
    model = Path(cfg.get('VOICE_STT_MODEL_PATH', ''))
    if not os.access(binary, os.X_OK) or not model.is_file():
        raise RuntimeError('Falta el ejecutable o modelo configurado; no se descargó ni cambió nada.')
    current = dict(model=str(model), threads=int(cfg.get('VOICE_STT_THREADS', 4)),
                   fast=cfg.get('VOICE_STT_FAST', 'true').lower() in ('true', '1', 'yes'))
    candidates = [current]
    models = [model] + [p for p in (model.parent/'ggml-tiny.bin', model.parent/'ggml-tiny-q5_1.bin') if p.is_file() and p != model]
    for m in models:
        for threads in (2, 4):
            c = dict(model=str(m), threads=threads, fast=True)
            if c not in candidates:
                candidates.append(c)
    report = {'version': 1, 'scope': 'synthetic_local_recognition_only', 'repo': str(repo),
              'recent_stage_medians_ms': recent_stages(home), 'results': [], 'applied': False,
              'natural_conversation_verified': False}
    print('Prueba local: no hables con Jarvis durante la medición. No se usará el micrófono.', flush=True)
    with tempfile.TemporaryDirectory(prefix='jarvis-voice-benchmark-') as folder:
        tmp = Path(folder); samples = []
        for n, phrase in enumerate(PHRASES):
            aiff, wav = tmp/f'sample{n}.aiff', tmp/f'sample{n}.wav'
            subprocess.run(['say', '-v', 'Juan', '-r', '160', '-o', str(aiff), phrase], check=True, capture_output=True, timeout=30)
            subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1', str(aiff), str(wav)], check=True, capture_output=True, timeout=30)
            samples.append(wav)
        for c in candidates:
            print('Midiendo', Path(c['model']).name, '· hilos', c['threads'], flush=True)
            results = [run_sample(binary, c, sample, text, tmp, cfg.get('VOICE_STT_LANGUAGE', 'es')) for sample, text in zip(samples, PHRASES)]
            report['results'].append(dict(candidate=c, samples=results))
            print(json.dumps(results), flush=True)
    winner = choose(report['results'][1:], report['results'][0]['samples'])
    report['selected'] = winner['candidate'] if winner else None
    if winner and args.apply:
        report.update(apply_choice(path, original, winner['candidate'], repo))
        if report['applied']:
            print('Ajuste aplicado y panel respondiendo. Falta validar tu voz real.', flush=True)
        else:
            print('El panel no confirmó arranque; configuración anterior restaurada.', flush=True)
    elif not winner:
        print('NINGUNA ALTERNATIVA CUMPLE: <=2 s por frase, >=90% precisión y >=25% mejora. No se cambió nada.', flush=True)
    result = home / '.jarvis-desktop' / ('voice-benchmark-' + str(time.time_ns()) + '.json')
    result.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(result, json.dumps(report, indent=2))
    print('INFORME:', result, flush=True)
    print('Esto no certifica latencia del servidor, conversación natural ni autonomía completa.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Prueba detenida:', type(exc).__name__, str(exc) if isinstance(exc, RuntimeError) else 'revisa la disponibilidad del motor local', file=sys.stderr)
        sys.exit(1)
