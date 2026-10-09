#!/usr/bin/env python3
"""Escribe ~/.jarvis-control/STOP. El ejecutor se detiene al verlo."""
from __future__ import annotations

import argparse
import os
import sys

from agent_executor import control_dir, judge, stopped, write_lock


def pulsar() -> None:
    path = control_dir() / "STOP"
    path.write_text("1", encoding="utf-8")


def escuchar() -> int:
    try:
        from pynput import keyboard
    except Exception as exc:
        print(f"Falta pynput ({type(exc).__name__}). Puedes crear el archivo STOP a mano.")
        return 2
    print("Ctrl+Alt+J detiene. Ctrl+C sale.")

    def on_hotkey():
        pulsar()
        print("STOP")
        return False

    with keyboard.GlobalHotKeys({"<ctrl>+<alt>+j": on_hotkey}) as hotkeys:
        hotkeys.join()
    return 0


def self_test() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["JARVIS_CONTROL_DIR"] = tmp
        write_lock("jarvis", 5)
        pulsar()
        assert stopped()
        assert judge({"agent": "jarvis", "action": "wait", "seconds": 0}, []) == ("BLOQUEADO", "stop")
    print("SELFTEST OK")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Parada de emergencia.")
    parser.add_argument("--escuchar", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.escuchar:
        return escuchar()
    pulsar()
    print("STOP")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
