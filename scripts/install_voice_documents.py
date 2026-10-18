"""Install the document hook without replacing the owner's custom voice panel.

Run from an explicitly fetched, reviewed commit. No dependency installation,
configuration edits, service restart, or frontend replacement.
"""
import argparse
import ast
import hashlib
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

KNOWN = {'57aaa01e83b02f7e3301af8eb9934ca0576c30ed3c5044162c8b07d270b1f2bf',
         '26880b3780e26df7279f61ea7dfe48133ba8e19dffc2a13e1ff154d867de0902'}
IMPORT = b'import documentos                                # noqa: E402\n'
HOOK = b'documentos.install(Companion)\n\n'

def digest(data): return hashlib.sha256(data).hexdigest()

def patch_app(raw):
    if IMPORT in raw and HOOK in raw:
        original = raw.replace(IMPORT, b'', 1).replace(HOOK, b'', 1)
        if digest(original) not in KNOWN:
            raise ValueError('El panel cambió; hay que revisar esa versión antes de modificarla.')
        return raw
    if digest(raw) not in KNOWN:
        raise ValueError('Versión del panel distinta a la revisada; no se cambió nada.')
    lines = raw.splitlines(keepends=True)
    indexes = [i for i, line in enumerate(lines) if re.match(br'^import intents\s', line)]
    if len(indexes) != 1 or raw.count(b'\nINDEX_401 = ') != 1:
        raise ValueError('Puntos de instalación inesperados; no se cambió nada.')
    lines.insert(indexes[0] + 1, IMPORT)
    result = b''.join(lines).replace(b'\nINDEX_401 = ', b'\n' + HOOK + b'INDEX_401 = ', 1)
    ast.parse(result, feature_version=(3, 9))
    return result

def atomic(path, data, mode):
    fd, temp = tempfile.mkstemp(dir=str(path.parent), prefix='.jarvis-documentos-')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.chmod(temp, mode); os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def install(root, module, backup_root, check=False):
    root = Path(root); app = root / 'desktop/app.py'; target = root / 'desktop/documentos.py'
    manifest = root / 'SHA256SUMS.txt'
    for path in (app, target, manifest):
        if path.is_symlink(): raise ValueError('Ruta simbólica inesperada: ' + path.name)
    raw = app.read_bytes(); patched = patch_app(raw)
    ast.parse(module, feature_version=(3, 9))
    if target.exists() and target.read_bytes() != module:
        raise ValueError('Ya existe otro módulo de documentos; no se sobrescribe.')
    changes = {app: patched, target: module}
    if manifest.exists():
        rows = manifest.read_text().splitlines()
        rows = [line for line in rows if line.split(maxsplit=1)[-1] not in ('desktop/app.py', 'desktop/documentos.py')]
        rows += [digest(patched) + '  desktop/app.py', digest(module) + '  desktop/documentos.py']
        changes[manifest] = ('\n'.join(sorted(rows, key=lambda row: row.split(maxsplit=1)[-1])) + '\n').encode()
    changes = {p: data for p, data in changes.items() if not p.exists() or p.read_bytes() != data}
    if not changes: return 'Ya está instalado; no se cambió nada.'
    if check: return 'Compatible: se añadirá el módulo y dos líneas al panel; display y micrófono intactos.'
    backup_root = Path(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = Path(tempfile.mkdtemp(prefix=datetime.now().strftime('%Y%m%d-%H%M%S-'), dir=str(backup_root)))
    originals = {}
    for path in changes:
        originals[path] = (path.read_bytes(), path.stat().st_mode & 0o777) if path.exists() else None
        if originals[path]: atomic(backup / path.name, originals[path][0], 0o600)
    # Module first so a concurrent service launch never imports a missing module.
    order = sorted(changes, key=lambda p: 0 if p == target else 1)
    written = []
    try:
        for path in order:
            atomic(path, changes[path], originals[path][1] if originals[path] else 0o600)
            written.append(path)
    except Exception:
        for path in reversed(written):
            old = originals[path]
            if old: atomic(path, old[0], old[1])
            else: path.unlink()
        raise
    return 'Documentos instalados. Respaldo: ' + str(backup)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default=str(Path.home() / 'Jarvis-agents'))
    parser.add_argument('--commit', required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-f0-9]{40}', args.commit): parser.error('Usa el SHA completo del commit revisado.')
    module = subprocess.check_output(['git', '-C', args.repo, 'show', args.commit + ':desktop/documentos.py'])
    print(install(args.repo, module, Path.home() / '.jarvis-desktop/update-backups', args.check))

if __name__ == '__main__': main()
