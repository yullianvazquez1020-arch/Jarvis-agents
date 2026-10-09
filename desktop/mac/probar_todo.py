#!/usr/bin/env python3
"""Corre todas las pruebas locales. No abre la cámara ni llama a WhatsApp."""
from __future__ import annotations

import os
import sys
import tempfile

import agent_executor
import credito
import estudiar
import gestos
import parada
import web_leer
import whatsapp_jarvis


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["JARVIS_CONTROL_DIR"] = tmp
        for name, module in (
            ("ejecutor", agent_executor),
            ("gestos", gestos),
            ("whatsapp", whatsapp_jarvis),
            ("web", web_leer),
            ("parada", parada),
            ("credito", credito),
            ("estudiar", estudiar),
        ):
            print(name)
            if module.self_test() != 0:
                return 1
    print("TODO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
