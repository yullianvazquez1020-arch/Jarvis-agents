#!/usr/bin/env python3
"""Dice QUE binario de Python tiene permiso de Accesibilidad, en vez de adivinarlo.

macOS concede Accesibilidad **por binario**, no por programa. El LaunchAgent del mouse corre
~/.jarvis-control-venv/bin/python, pero el permiso puede estar concedido a otro python. El agente
arranca, el latido dice accesibilidad: true, y el cursor no se mueve.

Esto prueba cada python candidato de verdad: le pide a cada uno que responda tres cosas sobre SI
MISMO (AXIsProcessTrusted, y si puede importar Quartz y pyautogui) y arma una tabla. No mueve el
cursor, no instala nada, no cambia ningun permiso.

    python3 desktop/mac/elegir_python_mouse.py
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CASA = Path(os.path.expanduser("~"))

# Lo que se le pide a cada candidato sobre si mismo. Sin argumentos ni rutas: solo responde.
SONDA = (
    "import json,sys\n"
    "r={'version':'%d.%d.%d'%sys.version_info[:3],'prefix':sys.prefix}\n"
    "try:\n"
    "    from ApplicationServices import AXIsProcessTrusted\n"
    "    r['accesibilidad']=bool(AXIsProcessTrusted())\n"
    "except Exception as e:\n"
    "    r['accesibilidad']=None; r['accesibilidad_error']=type(e).__name__\n"
    "for m in ('Quartz','pyautogui'):\n"
    "    try:\n"
    "        __import__(m); r[m]=True\n"
    "    except Exception as e:\n"
    "        r[m]=False; r[m+'_error']=type(e).__name__\n"
    "print(json.dumps(r))\n"
)


def candidatos():
    """Los python que pueden existir en su Mac, sin repetir y sin seguir enlaces a ciegas."""
    rutas = [
        CASA / ".jarvis-control-venv/bin/python",
        Path("/Library/Developer/CommandLineTools/usr/bin/python3"),
        Path("/usr/bin/python3"),
        Path("/usr/local/bin/python3"),
        Path("/opt/homebrew/bin/python3"),
        Path(sys.executable),
    ]
    enc = shutil.which("python3")
    if enc:
        rutas.append(Path(enc))
    vistos, salida = set(), []
    for r in rutas:
        try:
            clave = str(r.resolve())
        except OSError:
            clave = str(r)
        if clave in vistos or not os.access(str(r), os.X_OK):
            continue
        vistos.add(clave)
        salida.append(r)
    return salida


def sondear(py, pythonpath=None):
    entorno = dict(os.environ)
    entorno.pop("PYTHONHOME", None)
    if pythonpath:
        entorno["PYTHONPATH"] = pythonpath
    else:
        entorno.pop("PYTHONPATH", None)
    try:
        p = subprocess.run([str(py), "-c", SONDA], capture_output=True, timeout=25, env=entorno)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"error": type(e).__name__}
    if p.returncode != 0:
        return {"error": (p.stderr.decode("utf-8", "replace").strip().splitlines() or ["sin salida"])[-1][:120]}
    try:
        return json.loads(p.stdout.decode("utf-8", "replace").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": "respuesta ilegible"}


def site_packages_del_venv():
    """Para que un python del sistema con permiso pueda usar los paquetes del venv."""
    base = CASA / ".jarvis-control-venv/lib"
    if not base.is_dir():
        return None
    for d in sorted(base.glob("python3*/site-packages")):
        return str(d)
    return None


def marca(v):
    return {True: "si", False: "NO", None: "?"}.get(v, "?")


def main():
    if sys.platform != "darwin":
        print("Esto solo tiene sentido en macOS: AXIsProcessTrusted no existe en otros sistemas.")
        return 2
    venv_sp = site_packages_del_venv()
    filas = []
    for py in candidatos():
        r = sondear(py)
        # Si tiene el permiso pero le faltan los paquetes, se reintenta con los del venv.
        if venv_sp and r.get("accesibilidad") and not (r.get("Quartz") and r.get("pyautogui")):
            con = sondear(py, venv_sp)
            if con.get("Quartz") and con.get("pyautogui"):
                con["usa_pythonpath"] = venv_sp
                r = con
        filas.append((py, r))

    print("%-56s %-8s %-6s %-7s %s" % ("python", "version", "acces.", "Quartz", "pyautogui"))
    print("-" * 92)
    for py, r in filas:
        if "error" in r and "accesibilidad" not in r:
            print("%-56s %s" % (str(py)[:56], "no se pudo preguntar: " + str(r["error"])))
            continue
        print("%-56s %-8s %-6s %-7s %s%s" % (
            str(py)[:56], r.get("version", "?"), marca(r.get("accesibilidad")),
            marca(r.get("Quartz")), marca(r.get("pyautogui")),
            "   (con PYTHONPATH del venv)" if r.get("usa_pythonpath") else ""))

    buenos = [(py, r) for py, r in filas
              if r.get("accesibilidad") and r.get("Quartz") and r.get("pyautogui")]
    print()
    if not buenos:
        conceder = [(py, r) for py, r in filas if r.get("Quartz") and r.get("pyautogui")]
        print("Ninguno tiene las tres cosas a la vez.")
        if conceder:
            py = conceder[0][0]
            print("Tiene los paquetes pero NO el permiso: %s" % py)
            print()
            print("Concedele Accesibilidad a ESE binario: Ajustes del Sistema > Privacidad y")
            print("seguridad > Accesibilidad > +, y en el dialogo pulsa Cmd+Shift+G y pega:")
            print("    %s" % py)
            print("Despues vuelve a correr este script para confirmar que dice si.")
        else:
            print("Y a ninguno le funcionan Quartz y pyautogui: falta instalar los paquetes en el venv.")
        return 1

    py, r = buenos[0]
    print("Este sirve: %s" % py)
    print()
    print("Reinstala el LaunchAgent con el, una sola linea:")
    extra = 'JARVIS_PYTHONPATH="%s" ' % r["usa_pythonpath"] if r.get("usa_pythonpath") else ""
    print('    %sJARVIS_PYTHON="%s" bash "$HOME/Jarvis-agents/desktop/mac/instalar_mouse_autonomo.sh" instalar'
          % (extra, py))
    return 0


if __name__ == "__main__":
    sys.exit(main())
