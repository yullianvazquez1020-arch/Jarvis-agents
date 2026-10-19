#!/usr/bin/env python3
"""Measure local CLI vs resident whisper.cpp and apply only a qualified improvement.

Uses generated ES/EN samples, never the microphone or a remote speech API.
Existing model, voice, capture UI, and business credentials are preserved.
"""
import argparse
import ast
from datetime import datetime
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import unicodedata

KNOWN_ENGINES = {'4be1d40f76b57f1d7ea9277bb4c45ed0bd62748a8b1e8de2cf291dc38e609ffa', '27e0b3696434dc76a1544daec1a3214bee497c2a2f21b40fe2c50888098987c0'}
HOOK = '''    if stt == "whisper_resident":
        from .resident import ResidentWhisper
        fallback = WhisperCpp(cfg.get("VOICE_WHISPER_BIN", "whisper-cli"), cfg.get("VOICE_STT_MODEL_PATH", ""),
            cfg.get("VOICE_STT_THREADS", "4"), language=cfg.get("VOICE_STT_LANGUAGE", "auto"),
            fast=str(cfg.get("VOICE_STT_FAST", "true")).lower() in ("true", "1", "yes"))
        s = ResidentWhisper(cfg.get("VOICE_WHISPER_SERVER_BIN", ""), cfg.get("VOICE_STT_MODEL_PATH", ""),
            cfg.get("VOICE_STT_THREADS", "4"), language=cfg.get("VOICE_STT_LANGUAGE", "auto"),
            fast=str(cfg.get("VOICE_STT_FAST", "true")).lower() in ("true", "1", "yes"), fallback=fallback)
'''
PHRASES = [('es', 'Juan', 'Jarvis, la puerta está abierta y necesito revisar el proyecto mañana.'),
           ('en', 'Daniel', 'Jarvis, the door is open and I need to review the project tomorrow.')]


def sha(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def accuracy(expected, actual):
    def words(value):
        value = unicodedata.normalize('NFKD', value.lower())
        return re.findall(r'[a-z0-9]+', ''.join(c for c in value if not unicodedata.combining(c)))
    a, b = words(expected), words(actual); row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        out = [i]
        for k, y in enumerate(b, 1): out.append(min(out[-1]+1, row[k]+1, row[k-1]+(x != y)))
        row = out
    return max(0, 1-row[-1]/max(1,len(a)))


def qualifies(before, after):
    return (len(before) == len(after) == 4 and all('error' not in x for x in before+after)
            and all(x['accuracy'] >= .90 for x in after)
            and statistics.median(x['seconds'] for x in after) <= .75*statistics.median(x['seconds'] for x in before)
            and all(x['seconds'] < 5 for x in after))


def config(home, repo):
    path = next((p for p in (home/'.jarvis-desktop/config.env', repo/'desktop/config.env') if p.is_file()), None)
    if path is None or path.is_symlink(): raise ValueError('No encuentro una configuración local válida')
    raw = path.read_bytes(); cfg = {}
    for line in raw.decode().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1); cfg[k.strip()] = v.strip().strip('"').strip("'")
    for key in ('VOICE_WHISPER_BIN','VOICE_STT_MODEL_PATH','VOICE_STT_THREADS','VOICE_STT_FAST','VOICE_STT_LANGUAGE'):
        if os.environ.get(key): cfg[key] = os.environ[key]
    return path, raw, cfg


def replace_settings(raw, values):
    lines = raw.decode().splitlines()
    for key, value in values.items():
        matches = [i for i, line in enumerate(lines) if line.partition('=')[0].strip() == key]
        if len(matches) > 1: raise ValueError('Preferencia duplicada: ' + key)
        if matches: lines[matches[0]] = key+'='+str(value)
        else: lines.append(key+'='+str(value))
    return ('\n'.join(lines)+'\n').encode()


def patched_engine(raw):
    if HOOK.encode() in raw: return raw
    if sha(raw) not in KNOWN_ENGINES: raise ValueError('El motor local cambió desde la revisión; no se modifica')
    marker = b'    if tts == "auto":'
    if raw.count(marker) != 1: raise ValueError('No encuentro el punto de instalación revisado')
    result = raw.replace(marker, HOOK.encode()+marker, 1); ast.parse(result, feature_version=(3,9)); return result


def atomic(path, data, mode=0o600):
    fd, name = tempfile.mkstemp(prefix='.jarvis-resident-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as out: out.write(data); out.flush(); os.fsync(out.fileno())
        os.chmod(name, mode); os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)


def apply(repo, home, cfg_path, cfg_raw, engine_raw, module, binary):
    engine = repo/'desktop/audio/engines.py'; target = repo/'desktop/audio/resident.py'
    if engine.is_symlink() or target.is_symlink(): raise ValueError('Ruta simbólica inesperada')
    if target.exists() and target.read_bytes() != module: raise ValueError('Ya existe otro motor residente; se conserva')
    if engine.read_bytes() != engine_raw or cfg_path.read_bytes() != cfg_raw: raise ValueError('Los archivos cambiaron durante la prueba')
    updated_engine = patched_engine(engine_raw)
    changes = {engine:updated_engine, target:module, cfg_path:replace_settings(cfg_raw, {
        'VOICE_STT_BACKEND':'whisper_resident','VOICE_WHISPER_SERVER_BIN':str(binary),'VOICE_STT_LANGUAGE':'auto'})}
    manifest = repo/'SHA256SUMS.txt'
    if manifest.is_symlink(): raise ValueError('Manifest simbólico inesperado')
    if manifest.exists():
        names = ['desktop/audio/engines.py','desktop/audio/resident.py']
        rows = [line for line in manifest.read_text().splitlines() if line.split(maxsplit=1)[-1] not in names]
        rows += [sha(updated_engine)+'  '+names[0], sha(module)+'  '+names[1]]
        changes[manifest] = ('\n'.join(sorted(rows,key=lambda r:r.split(maxsplit=1)[-1]))+'\n').encode()
    backups = home/'.jarvis-desktop/update-backups'; backups.mkdir(parents=True,exist_ok=True,mode=0o700)
    backup = Path(tempfile.mkdtemp(prefix='resident-'+datetime.now().strftime('%Y%m%d-%H%M%S-'),dir=str(backups)))
    originals = {}
    for path in changes:
        originals[path] = (path.read_bytes(),path.stat().st_mode & 0o777) if path.exists() else None
        if originals[path]: atomic(backup/path.name,originals[path][0])
    written = []
    try:
        for path, data in changes.items():
            atomic(path,data,originals[path][1] if originals[path] else 0o600); written.append(path)
    except Exception:
        restore(originals); raise
    return originals, backup


def restore(originals):
    for path, value in originals.items():
        if value: atomic(path,value[0],value[1])
        else: path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',default=str(Path.home()/'Jarvis-agents'))
    parser.add_argument('--commit',required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--build-existing',action='store_true')
    args = parser.parse_args()
    if sys.platform != 'darwin': parser.error('Esta medición necesita la Mac y sus voces instaladas')
    if not re.fullmatch(r'[a-f0-9]{40}',args.commit): parser.error('Usa el commit completo revisado')
    repo = Path(args.repo).resolve(); home = Path.home()
    cfg_path, cfg_raw, cfg = config(home,repo)
    engine_raw = (repo/'desktop/audio/engines.py').read_bytes(); patched_engine(engine_raw)
    module = subprocess.check_output(['git','-C',str(repo),'show',args.commit+':desktop/audio/resident.py'])
    ast.parse(module,feature_version=(3,9))
    cli = Path(shutil.which(cfg.get('VOICE_WHISPER_BIN','whisper-cli')) or cfg.get('VOICE_WHISPER_BIN','')).resolve()
    model = Path(cfg.get('VOICE_STT_MODEL_PATH','')).expanduser().resolve()
    if not cli.is_file() or not model.is_file() or model.name.endswith('.en.bin'): raise ValueError('No encuentro el motor/modelo multilingüe actual')
    binary = cli.with_name('whisper-server')
    if not binary.is_file() and args.build_existing:
        source = model.parent.parent; build = source/'build'
        if not (source/'CMakeLists.txt').is_file() or not (build/'CMakeCache.txt').is_file():
            raise ValueError('No hay un proyecto whisper.cpp ya configurado para compilar whisper-server')
        print('Compilando whisper-server desde tu instalación existente, sin descargar modelos...',flush=True)
        subprocess.run(['cmake','--build',str(build),'--target','whisper-server','-j','2'],check=True)
        binary = build/'bin/whisper-server'
    if not binary.is_file(): raise ValueError('Falta whisper-server; se conserva tu motor actual')
    service = [sys.executable,str(repo/'scripts/mac_service.py')]
    changed = {}; resident = None; stopped = False
    with tempfile.TemporaryDirectory(prefix='jarvis-voice-measure-') as directory:
        temp = Path(directory); audio = temp/'desktop/audio'; audio.mkdir(parents=True)
        (temp/'desktop/__init__.py').write_text(''); (audio/'__init__.py').write_text('')
        for name in ('engines.py','wav.py'): (audio/name).write_bytes((repo/'desktop/audio'/name).read_bytes())
        (audio/'resident.py').write_bytes(module)
        sys.path.insert(0,str(temp))
        engines = importlib.import_module('desktop.audio.engines')
        Resident = importlib.import_module('desktop.audio.resident').ResidentWhisper
        fast = cfg.get('VOICE_STT_FAST','true').lower() in ('true','1','yes')
        threads = int(cfg.get('VOICE_STT_THREADS','4'))
        baseline = engines.WhisperCpp(str(cli),str(model),threads,language='auto',fast=fast)
        resident = Resident(str(binary),str(model),threads,language='auto',fast=fast)
        try:
            print('Pausando el panel para medir sin competir con su audio y animación...',flush=True)
            subprocess.run(service+['stop'],check=True); stopped = True
            samples = []
            for lang, voice, text in PHRASES:
                phrase = temp/(lang+'.txt'); phrase.write_text(text)
                wav = temp/(lang+'.wav')
                subprocess.run(['say','-v',voice,'-r','160','-o',str(wav),'--file-format=WAVE','--data-format=LEI16@16000','-f',str(phrase)],check=True)
                samples.append((lang,text,wav.read_bytes()))
            print('Cargando una vez el mismo modelo local...',flush=True); resident.start()
            before = []; after = []
            for engine, results in ((baseline,before),(resident,after)):
                for lang,text,wav in samples*2:
                    started = time.perf_counter()
                    try:
                        result = engine.transcribe(wav)
                        sample = {'seconds':round(time.perf_counter()-started,3),'accuracy':round(accuracy(text,result['text']),3),'language':lang}
                    except engines.EngineError:
                        sample = {'error':'recognizer_failed','seconds':round(time.perf_counter()-started,3),'language':lang}
                    results.append(sample); print(json.dumps({'engine':engine.name,**sample}),flush=True)
            qualified = qualifies(before,after)
            print(json.dumps({'qualified':qualified,'same_model':True,'synthetic_samples_only':True}),flush=True)
            if qualified and args.apply:
                changed, backup = apply(repo,home,cfg_path,cfg_raw,engine_raw,module,binary)
                print('Motor residente instalado. Respaldo: '+str(backup),flush=True)
            else:
                print('Configuración conservada: '+('prueba sin --apply' if qualified else 'no alcanzó precisión y mejora mínima'),flush=True)
        finally:
            if resident is not None: resident.close()
            if stopped:
                try: subprocess.run(service+['start'],check=True)
                except Exception:
                    if changed: restore(changed); subprocess.run(service+['start'],check=False)
                    raise
    print('Prueba terminada. Falta medir tu voz real en latencia.log; esto no certifica respuesta instantánea.',flush=True)

if __name__ == '__main__':
    try: main()
    except (ValueError,RuntimeError,OSError,subprocess.SubprocessError) as exc:
        print('No se pudo completar la prueba ('+type(exc).__name__+'). Se conserva o restaura la configuración anterior.',file=sys.stderr)
        raise SystemExit(1)
