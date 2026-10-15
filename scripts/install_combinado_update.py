#!/usr/bin/env python3
"""Install a tested combined-desktop revision without changing the source checkout."""
import argparse
import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

BASE = 'efb583222762f5179788a24600b87acf2a2b2345'
AUDIO = {'desktop/ui/startup.js', 'desktop/ui/arranque.js'}

def git(root, *args, **kw):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, **kw).stdout

def merge_local(local, base, incoming):
    if local == base or local == incoming:
        return incoming
    if incoming == base:
        return local
    with tempfile.TemporaryDirectory(prefix='jarvis-merge-') as folder:
        paths = [Path(folder) / name for name in ('local', 'base', 'incoming')]
        for path, data in zip(paths, (local, base, incoming)):
            path.write_bytes(data)
        result = subprocess.run(['git', 'merge-file', '-p', *map(str, paths)], capture_output=True)
        if result.returncode:
            raise RuntimeError('Local changes overlap this update; source files remain unchanged.')
        return result.stdout

def prepare(source, target, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if git(source, 'rev-parse', 'HEAD').decode().strip() != BASE:
        raise RuntimeError('Source version changed. This installer expects efb5832; nothing was installed.')
    if destination.exists():
        raise RuntimeError('Destination already exists; it will not be overwritten.')
    target = git(source, 'rev-parse', '--verify', target + '^{commit}').decode().strip()
    changed = git(source, 'diff', '--name-only', 'HEAD', '-z').decode().split('\0')
    overrides = {}
    for name in filter(None, changed):
        path = source / name
        if not path.is_file() or path.is_symlink():
            raise RuntimeError('Unsupported local change: ' + name)
        base = git(source, 'show', BASE + ':' + name)
        incoming = git(source, 'show', target + ':' + name)
        # The owner explicitly requested replacement of continuous music with a bounded intro.
        # Both originals are retained in the untouched source checkout and in the backup.
        overrides[name] = incoming if name in AUDIO else merge_local(path.read_bytes(), base, incoming)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = source / 'backups' / ('before-combinado-update-' + stamp)
    backup.mkdir(parents=True, mode=0o700)
    for name in filter(None, changed):
        out = backup / name; out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, out)
    git(source, 'worktree', 'add', '--detach', str(destination), target)
    for name, data in overrides.items():
        (destination / name).write_bytes(data)
    for name in ('desktop/config.env', '.env'):
        original = source / name
        if original.is_file():
            out = destination / name
            shutil.copy2(original, out); out.chmod(0o600)
    (backup / 'INSTALL.txt').write_text('Source: ' + str(source) + '\nDestination: ' + str(destination) + '\nCommit: ' + target + '\n')
    # Compile into a temporary cache: validates syntax without changing the working tree.
    with tempfile.TemporaryDirectory(prefix='jarvis-compile-') as cache:
        env = dict(os.environ, PYTHONPYCACHEPREFIX=cache)
        subprocess.run([sys.executable, '-m', 'compileall', '-q', str(destination / 'desktop'),
                        str(destination / 'scripts')], env=env, check=True)
    return backup

def service(root, action):
    return subprocess.run([sys.executable, str(Path(root) / 'scripts/mac_service.py'), action]).returncode

def running_from(destination):
    result = subprocess.run(['launchctl', 'print', 'gui/' + str(os.getuid()) + '/com.jarvis.desktop'], capture_output=True, text=True)
    if result.returncode or str(destination / 'scripts/mac_setup.py') not in result.stdout or 'state = running' not in result.stdout:
        return False
    listeners = subprocess.run(['/usr/sbin/lsof', '-nP', '-t', '-iTCP:8765', '-sTCP:LISTEN'], capture_output=True, text=True)
    own_listener = False
    for pid in listeners.stdout.split():
        if not pid.isdigit():
            continue
        command = subprocess.run(['ps', '-p', pid, '-o', 'command='], capture_output=True, text=True)
        if str(destination / 'desktop/app.py') in command.stdout:
            own_listener = True
    if not own_listener:
        return False
    try:
        with urllib.request.urlopen('http://127.0.0.1:8765/', timeout=2) as response:
            body = response.read(2048)
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            return False
        body = exc.read(2048)
    except OSError:
        return False
    return b'<title>Jarvis</title>' in body

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--target', required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise RuntimeError('Run this installer on the Mac that runs Jarvis.')
    source = Path(args.repo).expanduser().resolve()
    target = git(source, 'rev-parse', '--verify', args.target + '^{commit}').decode().strip()
    destination = source.parent / ('Jarvis-combinado-' + target[:8])
    backup = prepare(source, target, destination)
    print('Prepared with original combined design. Backup:', backup, flush=True)
    # Preflight dependencies before stopping the existing panel.
    subprocess.run([sys.executable, str(destination / 'scripts/mac_setup.py')], check=True)
    if service(source, 'stop'):
        raise RuntimeError('Could not stop the old service; new service was not started.')
    try:
        if service(destination, 'start'):
            raise RuntimeError('New service did not start.')
        for _ in range(20):
            if running_from(destination):
                print('INSTALLED AND RESPONDING:', target)
                print('Desktop:', destination)
                print('Original files preserved:', source)
                return
            time.sleep(1)
        raise RuntimeError('New desktop has not confirmed that it is responding.')
    except Exception:
        service(destination, 'stop')
        result = service(source, 'start')
        print('Original service restart requested.' if result == 0 else 'Original service also needs attention; inspect Library/Logs/Jarvis/panel-error.log.')
        raise

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Installation stopped:', str(exc), file=sys.stderr)
        sys.exit(1)
