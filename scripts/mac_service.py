#!/usr/bin/env python3
"""Mantiene el panel local con launchd. No ejecuta ni autoriza órdenes del mouse."""
import argparse
import os
from pathlib import Path
import plistlib
import socket
import subprocess
import sys

import mac_setup

LABEL = "com.jarvis.desktop"
ROOT = Path(__file__).resolve().parents[1]


def service_definition(home):
    home = Path(home)
    logs = home / "Library" / "Logs" / "Jarvis"
    return {
        "Label": LABEL,
        "ProgramArguments": [str(mac_setup.python_path(home)), "-u", str(ROOT / "scripts" / "mac_setup.py"), "--launch"],
        "WorkingDirectory": str(ROOT),
        "EnvironmentVariables": {"HOME": str(home), "PYTHONUNBUFFERED": "1"},
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "StandardOutPath": str(logs / "panel.log"),
        "StandardErrorPath": str(logs / "panel-error.log"),
        "ProcessType": "Interactive",
    }


def invoke(args):
    return subprocess.run(["launchctl"] + args, capture_output=True, text=True, timeout=15)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "status"))
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        print("Este servicio solo funciona en macOS.")
        return 2
    home = Path.home()
    plist = home / "Library" / "LaunchAgents" / (LABEL + ".plist")
    domain = "gui/" + str(os.getuid())
    target = domain + "/" + LABEL
    try:
        state = invoke(["print", target])
        if args.action == "status":
            print(state.stdout if state.returncode == 0 else "Servicio no cargado.")
            return 0 if state.returncode == 0 else 1
        if args.action == "stop":
            if state.returncode != 0:
                if plist.exists():
                    plist.rename(plist.with_suffix(".plist.disabled"))
                print("Servicio detenido; arranque al iniciar sesión desactivado.")
                return 0
            # Unload without deleting user files. A later explicit start restores it.
            result = invoke(["bootout", target])
            if result.returncode:
                print(result.stderr.strip())
                return 2
            if plist.exists():
                plist.rename(plist.with_suffix(".plist.disabled"))
            print("Panel detenido; arranque al iniciar sesión desactivado.")
            return 0
        if state.returncode == 0:
            print("Servicio ya cargado. Consulta: python3 scripts/mac_service.py status")
            return 0
        try:
            with socket.create_connection(("127.0.0.1", 8765), timeout=1):
                print("El puerto 8765 está ocupado. Cierra el panel anterior con Ctrl+C y repite start.")
                return 2
        except (ConnectionRefusedError, TimeoutError, socket.timeout):
            pass
        if mac_setup.main([]) != 0:
            return 2
        definition = service_definition(home)
        plist.parent.mkdir(parents=True, exist_ok=True)
        logs = Path(definition["StandardOutPath"]).parent
        logs.mkdir(parents=True, exist_ok=True)
        logs.chmod(0o700)
        for key in ("StandardOutPath", "StandardErrorPath"):
            log = Path(definition[key])
            log.touch(mode=0o600, exist_ok=True)
            log.chmod(0o600)
        pending = plist.with_suffix(".tmp")
        pending.write_bytes(plistlib.dumps(definition))
        pending.chmod(0o600)
        pending.replace(plist)
        result = invoke(["bootstrap", domain, str(plist)])
        if result.returncode:
            print("No se pudo cargar el servicio: " + result.stderr.strip())
            return 2
        print("Servicio cargado. El panel abrirá en el navegador y se reiniciará si termina.")
        print("También arrancará al iniciar sesión. La Mac debe permanecer encendida y despierta.")
        print("Comprueba el estado con: python3 scripts/mac_service.py status")
        print("Registros: " + str(logs))
        return 0
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("No se completó: " + str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
