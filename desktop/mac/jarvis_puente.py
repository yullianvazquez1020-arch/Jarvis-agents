#!/usr/bin/env python3
"""La Mac ejecuta solo propuestas de Jarvis, y solo tras confirmación.

No llama a Render, no envía WhatsApp y no escribe a clientes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import agent_executor as ex


def load(path: Path) -> list[dict]:
    actions = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        action = json.loads(raw)
        if not isinstance(action, dict) or action.get("agent") not in (None, "jarvis"):
            raise ValueError(f"linea {line_no}: solo jarvis")
        action["agent"] = "jarvis"
        actions.append(action)
    return actions


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Puente local de Jarvis. Siempre supervisado.")
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--minutes", type=int, default=10)
    args = parser.parse_args(argv)
    actions = load(args.file)
    staged = Path(ex.control_dir()) / "jarvis-lote.jsonl"
    staged.write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in actions), encoding="utf-8")
    if ex.read_lock() and ex.read_lock()["agent"] != "jarvis":
        print("OCUPADO")
        return 2
    if ex.take_lock("jarvis", args.minutes) != 0:
        return 2
    try:
        if args.dry_run:
            return ex.run_actions(staged, dry=True, libre=False)
        pointer = ex.MacPointer()
        return ex.run_actions(staged, dry=False, libre=False, pointer=pointer)
    finally:
        ex.release_lock("jarvis")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
