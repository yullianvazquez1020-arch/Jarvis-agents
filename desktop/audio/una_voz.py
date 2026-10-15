"""Una sola voz de Jarvis en la Mac, aunque hablen varios procesos (panel, voz_loop, standby).

Cada proceso que va a reproducir voz llama claim() (corta la voz anterior registrada por OTRO proceso)
y luego register(pid) del reproductor. Solo se corta un pid registrado que siga vivo y sea un reproductor
de voz conocido (say/afplay/piper/sh); nunca toca otros procesos. Archivo local, sin red.
"""
from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

PLAYERS = ("say", "afplay", "piper", "sh", "aplay", "paplay", "ffplay")


def lock_path() -> Path:
    return Path(os.getenv("JARVIS_VOZ_LOCK") or (Path.home() / ".jarvis-desktop" / "voz-actual.pid"))


def _cmd_name(pid: int) -> str:
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    return os.path.basename(out.strip())


def claim(kill=os.kill, name_of=_cmd_name) -> bool:
    """Corta la voz registrada previamente (si sigue sonando). Devuelve True si cortó algo."""
    p = lock_path()
    try:
        owner, pid = p.read_text().split()
        pid = int(pid); owner = int(owner)
    except (OSError, ValueError):
        return False
    if pid <= 1 or pid == os.getpid() or name_of(pid) not in PLAYERS:
        return False
    try:
        kill(pid, signal.SIGTERM)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def register(pid) -> None:
    if not isinstance(pid, int) or pid <= 1:
        return
    p = lock_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"{os.getpid()} {int(pid)}")
    except OSError:
        pass
