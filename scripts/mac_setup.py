#!/usr/bin/env python3
"""Install the optional local hand pointer and diagnose it without moving it."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

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
        if args.install:
            if not python.exists():
                run([sys.executable, "-m", "venv", str(python.parent.parent)])
            run([str(python), "-m", "pip", "install", "pyautogui", "pyobjc-framework-Quartz"])
        if not python.exists():
            print("Falta el entorno del mouse. Ejecuta este script con --install.")
            return 2
        # MacPointer checks Accessibility and reads display dimensions only.
        probe = "import sys,json;sys.path.insert(0,sys.argv[1]);from hand_mouse import MacPointer;p=MacPointer();print(json.dumps({'screen':p.size()}))"
        result = run([str(python), "-c", probe, str(ROOT / "desktop")], capture_output=True, text=True, timeout=15)
        screen = json.loads(result.stdout.strip())["screen"]
        print("Mouse instalado · Accesibilidad concedida · pantalla %s × %s. No se movió el puntero." % tuple(screen))
        if shutil.which("say"):
            listing = run(["say", "-v", "?"], capture_output=True, text=True, timeout=10)
            voice, locale = voice_choice(listing.stdout)
            english = english_choice(listing.stdout)
        else:
            voice, locale, english = "", "", ""
        print("Voz elegida: %s · %s (español) · %s (inglés) · %s ppm" % (
            voice or "ninguna masculina instalada", locale or "sin idioma", english or "falta Daniel", os.getenv("JARVIS_VOZ_RATE", "170")))
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
        print("Si falta Accesibilidad, habilita Terminal en Preferencias del Sistema → Seguridad y privacidad → Accesibilidad y vuelve a ejecutar. No se cambia ese permiso automáticamente.", file=sys.stderr)
        return 2
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        print("Diagnóstico incompleto: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
