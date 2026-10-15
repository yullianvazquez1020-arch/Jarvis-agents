#!/usr/bin/env python3
"""Install the optional local hand pointer and diagnose it without moving it."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def python_path(home):
    return Path(home) / ".jarvis-control-venv" / "bin" / "python"


def launch_command(python):
    return [str(python), str(ROOT / "desktop" / "app.py"), "--hand-mouse"]


def voice_choice(listing):
    """Voz masculina en español (Juan es_MX → Jorge es_ES → Diego es_AR); nunca femenina."""
    sys.path.insert(0, str(ROOT / "desktop"))
    from audio.engines import choose_voices, parse_say_listing
    es, _en = choose_voices(listing)
    loc = next((l for n, l in parse_say_listing(listing) if n == es), "")
    return (es, loc) if es else ("", "")


def english_choice(listing):
    sys.path.insert(0, str(ROOT / "desktop"))
    from audio.engines import choose_voices
    return choose_voices(listing)[1]


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


LABEL = "com.jarvis.mouse-autonomo"
PROBE = (
    "import sys,os,json,ctypes\n"
    "r={'python':os.path.realpath(sys.executable)}\n"
    "try:\n import pyautogui, Quartz; r['modulos']=True\n"
    "except Exception as e:\n r['modulos']=False; r['error']=type(e).__name__+': '+str(e)\n"
    "ax=ctypes.CDLL('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')\n"
    "ax.AXIsProcessTrusted.restype=ctypes.c_bool; r['accesibilidad']=bool(ax.AXIsProcessTrusted())\n"
    "print(json.dumps(r))\n")


def _cursor(python):
    out = subprocess.run([str(python), "-c", "import Quartz;p=Quartz.CGEventGetLocation(Quartz.CGEventCreate(None));"
                          "print(int(p.x),int(p.y))"], capture_output=True, text=True, timeout=10)
    return tuple(int(v) for v in out.stdout.split()) if out.returncode == 0 and out.stdout.strip() else None


def mouse_report(python, probar=False):
    """Estado REAL del mouse: módulos, Accesibilidad del python del agente, LaunchAgent y, si probar, un movimiento."""
    if not python.exists():
        return "Mouse: NO instalado (falta %s). Ejecuta: python3 scripts/mac_setup.py --install" % python
    try:
        info = json.loads(subprocess.run([str(python), "-c", PROBE], capture_output=True, text=True, timeout=15).stdout)
    except (ValueError, subprocess.TimeoutExpired, OSError):
        info = {"modulos": False, "accesibilidad": False, "python": str(python)}
    lc = subprocess.run(["launchctl", "print", "gui/%d/%s" % (os.getuid(), LABEL)], capture_output=True, text=True)
    corriendo = lc.returncode == 0 and "state = running" in lc.stdout
    lineas = ["Mouse · python del agente: %s" % info.get("python"),
              "  módulos pyautogui+Quartz: %s" % ("OK" if info.get("modulos") else "FALTAN (%s)" % info.get("error", "")),
              "  Accesibilidad de ese python: %s" % ("concedida" if info.get("accesibilidad") else
                  "NO — añádelo en Ajustes → Privacidad y seguridad → Accesibilidad (botón +, Cmd+Shift+G y pega la ruta)"),
              "  LaunchAgent %s: %s" % (LABEL, "corriendo" if corriendo else ("cargado, no corre" if lc.returncode == 0 else "NO cargado"))]
    if probar and info.get("modulos") and corriendo:
        ctl = Path(os.environ.get("JARVIS_CONTROL_DIR") or Path.home() / ".jarvis-control")
        (ctl / "autonomo").mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", "-a", "Notes"]); time.sleep(2)
        started = time.time()
        with (ctl / "autonomo" / "entrada.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"agent": "jarvis", "action": "move", "x": 600, "y": 400}) + "\n")
        time.sleep(4)
        try:
            report = ctl / "ultimo_move.json"
            ult = json.loads(report.read_text(encoding="utf-8")) if report.stat().st_mtime >= started else {}
            if ult.get("pedido") != [600, 400]:
                ult = {}
        except (OSError, ValueError):
            ult = {}
        lineas.append("  Prueba de movimiento a (600,400) en la pantalla de Notes: %s (global %s, real %s)" % (
            "FUNCIONA" if ult.get("ok") else "NO se movió", ult.get("global"), ult.get("real") or _cursor(python)))
        if not ult:
            lineas.append("  El agente no registró el movimiento; mira tail ~/.jarvis-control/audit.jsonl")
    return "\n".join(lineas)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="install optional pointer dependencies in the local venv")
    parser.add_argument("--launch", action="store_true", help="open the panel; pointer remains inactive until enabled there")
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        print("Este instalador solo funciona en macOS; no se instaló ni activó nada.")
        return 2
    python = python_path(Path.home())
    try:
        if args.install or args.launch:
            # Siempre en el venv propio: el python3 del sistema (CommandLineTools 3.9) no trae Quartz.
            if not python.exists():
                run([sys.executable, "-m", "venv", str(python.parent.parent)])
            if subprocess.run([str(python), "-c", "import pyautogui, Quartz, ApplicationServices"],
                              capture_output=True).returncode != 0:
                run([str(python), "-m", "pip", "install", "-q", "pyautogui",
                     "pyobjc-framework-Quartz", "pyobjc-framework-ApplicationServices"])
            instalar = ROOT / "desktop" / "mac" / "instalar_mouse_autonomo.sh"
            subprocess.run(["bash", str(instalar), "instalar"], env=dict(os.environ, JARVIS_PYTHON=str(python)))
        print(mouse_report(python, probar=args.install))
        if shutil.which("say"):
            listing = run(["say", "-v", "?"], capture_output=True, text=True, timeout=10)
            voice, locale = voice_choice(listing.stdout)
            english = english_choice(listing.stdout)
        else:
            voice, locale, english = "", "", ""
        print("Voz elegida: %s · %s (español) · %s (inglés) · %s ppm" % (
            voice or "ninguna masculina instalada", locale or "sin idioma", english or "falta Daniel", os.getenv("JARVIS_VOZ_RATE", "180")))
        if not voice or not english:
            print("Instala Juan / Daniel: Ajustes del Sistema → Accesibilidad → Contenido leído → Voz del sistema → Gestionar voces.")
        if args.launch:
            env = dict(os.environ, VOICE_DEMO="false", VOICE_TTS_BACKEND="macos_say", VOICE_TTS_VOICE="auto-latino", VOICE_AUTO_CAMERA="true", VOICE_STARTUP_AUDIO="true")
            if Path("/Applications/Firefox.app").exists():
                env["BROWSER"] = "open -a Firefox %s"
            return subprocess.call(launch_command(python), env=env)
        return 0
    except subprocess.CalledProcessError as exc:
        print("No se completó la preparación. " + (getattr(exc, "stderr", None) or "Revisa el error anterior."), file=sys.stderr)
        print("Si falta Accesibilidad, habilita Terminal Y el python del agente (bash desktop/mac/diagnostico_mouse.sh te dice cuál) en Ajustes del Sistema → Privacidad y seguridad → Accesibilidad y vuelve a ejecutar. No se cambia ese permiso automáticamente.", file=sys.stderr)
        return 2
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        print("Diagnóstico incompleto: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
