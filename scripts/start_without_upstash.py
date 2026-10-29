#!/usr/bin/env python3
"""Safe single-instance entrypoint for Jarvis without Upstash (Linux VPS).

This does not migrate Redis data or provision a persistent disk.
Mount durable storage and back up existing data BEFORE using it.
"""
import fcntl
import os
from pathlib import Path
import subprocess
import sys

def main():
    if os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("UPSTASH_REDIS_REST_TOKEN"):
        sys.exit("REFUSED: remove BOTH Upstash environment variables to select local mode.")
    raw = os.getenv("DATA_DIR", "")
    if not raw or not os.path.isabs(raw):
        sys.exit("REFUSED: DATA_DIR must be an absolute path to an existing persistent mount.")
    data = Path(raw).resolve(strict=True)
    if not data.is_dir() or data.is_symlink():
        sys.exit("REFUSED: DATA_DIR must be an existing real directory.")
    # This is a user-supplied deployment assertion, not a durability detector.
    if os.getenv("JARVIS_PERSISTENT_STORAGE_CONFIRMED") != "YES":
        sys.exit("REFUSED: confirm durable mounted storage with JARVIS_PERSISTENT_STORAGE_CONFIRMED=YES.")
    if not os.access(data, os.R_OK | os.W_OK | os.X_OK):
        sys.exit("REFUSED: DATA_DIR is not readable/writable.")
    lock = data / ".jarvis-single-instance.lock"
    fd = os.open(str(lock), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        sys.exit("REFUSED: another Jarvis process already owns this data directory.")
    # Ensure a real fsync-capable writable directory; do not delete any user data.
    probe = data / (".jarvis-probe-%d" % os.getpid())
    try:
        with probe.open("x", encoding="utf-8") as out:
            out.write("ok")
            out.flush()
            os.fsync(out.fileno())
    finally:
        probe.unlink(missing_ok=True)
    if not any(data.glob("*.json")) and os.getenv("JARVIS_ALLOW_EMPTY_STORE") != "YES":
        sys.exit("REFUSED: no JSON state found. Restore/migrate existing state, or explicitly authorize new empty state.")
    port = os.getenv("PORT", "8000")
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        sys.exit("REFUSED: invalid PORT")
    print("Jarvis local persistent mode: preflight passed; one instance only.", flush=True)
    try:
        return subprocess.call(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0",
             "--port", port, "--workers", "1"],
            pass_fds=(fd,),
            env=os.environ.copy(),
        )
    finally:
        os.close(fd)

if __name__ == "__main__":
    raise SystemExit(main())
