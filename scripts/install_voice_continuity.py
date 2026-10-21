#!/usr/bin/env python3
"""Install the reviewed voice-only patch on the owner's exact panel snapshot."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from datetime import datetime

ALLOWED = frozenset(('desktop/app.py', 'desktop/documentos.py', 'desktop/audio/engines.py',
                     'desktop/ui/app.js', 'scripts/check_voice_session.py', 'scripts/check_voice_continuity.cjs'))
PREFIX = 'updates/voice-20261019/'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def atomic(path, data, mode=0o600):
    fd, tmp = tempfile.mkstemp(prefix='.jarvis-voice-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.chmod(tmp, mode); os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def checked_path(root, name):
    path = root / name
    if Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('Ruta inesperada')
    current = path
    while current != root:
        if current.is_symlink(): raise ValueError('Ruta simbólica inesperada: ' + name)
        current = current.parent
    return path

def language_config(raw):
    text = raw.decode('utf-8')
    for key in ('VOICE_STT_LANGUAGE', 'JARVIS_REPLY_LANGUAGE'):
        pattern = re.compile(r'^' + key + r'=.*$', re.M)
        if len(pattern.findall(text)) > 1: raise ValueError('Configuración de idioma duplicada: ' + key)
        if pattern.search(text): text = pattern.sub(key + '=auto', text)
        else: text = text.rstrip() + '\n' + key + '=auto\n'
    return text.encode('utf-8')

def prepare(root, manifest, patch):
    root = Path(root).resolve()
    if manifest.get('format') != 1 or sha(patch) != manifest.get('patch_sha256'):
        raise ValueError('Paquete de actualización inválido')
    entries = manifest.get('files', [])
    names = [e.get('path') for e in entries]
    if set(names) != ALLOWED or len(names) != len(ALLOWED): raise ValueError('Lista de archivos inesperada')
    # Already applied is a no-op; mixed or newer edits require review rather than guessing.
    current = {}
    for entry in entries:
        path = checked_path(root, entry['path'])
        current[entry['path']] = path.read_bytes() if path.exists() else None
    if all(value is not None and sha(value) == entry['after']
           for entry in entries for value in [current[entry['path']]]):
        return {}
    for entry in entries:
        data = current[entry['path']]
        if (sha(data) if data is not None else None) != entry['before']:
            raise ValueError('El archivo cambió desde la revisión: ' + entry['path'] + '. No se modificó nada.')
    with tempfile.TemporaryDirectory(prefix='jarvis-voice-check-') as folder:
        candidate = Path(folder)
        for name, data in current.items():
            if data is not None:
                path = candidate / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        result = subprocess.run(['git', '-C', str(candidate), 'apply', '--check', '-'], input=patch, capture_output=True)
        if result.returncode: raise ValueError('El parche no corresponde a esta versión. No se modificó nada.')
        subprocess.run(['git', '-C', str(candidate), 'apply', '-'], input=patch, check=True, capture_output=True)
        updated = {}
        for entry in entries:
            data = (candidate / entry['path']).read_bytes()
            if sha(data) != entry['after']: raise ValueError('La comprobación del resultado falló')
            if entry['path'].endswith('.py'): ast.parse(data, feature_version=(3, 9))
            updated[root / entry['path']] = data
    manifest_path = checked_path(root, 'SHA256SUMS.txt')
    if manifest_path.exists():
        rows = [line for line in manifest_path.read_text().splitlines() if line.split(maxsplit=1)[-1] not in names]
        rows += [e['after'] + '  ' + e['path'] for e in entries]
        updated[manifest_path] = ('\n'.join(sorted(rows, key=lambda row: row.split(maxsplit=1)[-1])) + '\n').encode()
    return updated

def install(root, manifest, patch, home, check=False, restart=False):
    root = Path(root).resolve(); home = Path(home)
    changes = prepare(root, manifest, patch)
    if not changes: return 'La actualización ya está instalada; no se cambió nada.'
    config = checked_path(home / '.jarvis-desktop', 'config.env')
    if config.exists(): changes[config] = language_config(config.read_bytes())
    if check: return 'Versión compatible. Captura continua, interrupciones y documentos listos para instalar.'
    backups = home / '.jarvis-desktop/update-backups'; backups.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = Path(tempfile.mkdtemp(prefix='voz-' + datetime.now().strftime('%Y%m%d-%H%M%S-'), dir=str(backups)))
    originals = {}
    for path in changes:
        originals[path] = (path.read_bytes(), path.stat().st_mode & 0o777) if path.exists() else None
        if originals[path]:
            relative = Path('config.env') if path == config else path.relative_to(root)
            dest = backup / relative; dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic(dest, originals[path][0])
    service = [sys.executable, str(root / 'scripts/mac_service.py')]
    if restart: subprocess.run(service + ['stop'], check=True)
    written = []
    try:
        for path, data in changes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic(path, data, originals[path][1] if originals[path] else 0o600); written.append(path)
        if restart: subprocess.run(service + ['start'], check=True)
    except Exception:
        for path in reversed(written):
            original = originals[path]
            if original: atomic(path, original[0], original[1])
            else: path.unlink(missing_ok=True)
        if restart: subprocess.run(service + ['start'], check=False)
        raise
    return 'Actualización de voz instalada' + (' y servicio reiniciado' if restart else '') + '. Respaldo: ' + str(backup)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=str(Path.home() / 'Jarvis-agents'))
    parser.add_argument('--commit', required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-f0-9]{40}', args.commit): parser.error('Se requiere el SHA completo revisado.')
    if sys.platform != 'darwin' and not args.check: parser.error('Esta instalación es para la Mac del dueño.')
    def read(name):
        return subprocess.check_output(['git', '-C', args.repo, 'show', args.commit + ':' + PREFIX + name])
    print(install(args.repo, json.loads(read('manifest.json')), read('voice.patch'), Path.home(),
                  check=args.check, restart=not args.check))

if __name__ == '__main__': main()
