"""Elegir el python del mouse: el plist tiene que salir valido con y sin PYTHONPATH."""
import json
import os
import plistlib
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
MAC = RAIZ / "desktop" / "mac"
sys.path.insert(0, str(MAC))
import elegir_python_mouse as ele  # noqa: E402


def render(pythonpath):
    """Lo mismo que hace el instalador con sed, para comprobar el plist sin macOS."""
    plantilla = (MAC / "com.jarvis.mouse-autonomo.plist").read_text(encoding="utf-8")
    entrada = "<key>PYTHONPATH</key><string>%s</string>" % pythonpath if pythonpath else ""
    return (plantilla.replace("__PYTHON__", "/usr/bin/python3")
                     .replace("__EXECUTOR__", str(MAC / "agent_executor.py"))
                     .replace("__HOME__", "/Users/prueba")
                     .replace("__PYTHONPATH__", entrada))


class PlistValido(unittest.TestCase):
    def test_sin_pythonpath(self):
        d = plistlib.loads(render(None).encode())
        self.assertEqual(d["EnvironmentVariables"], {"JARVIS_AUTONOMO": "1"})
        self.assertEqual(d["ProgramArguments"][0], "/usr/bin/python3")
        self.assertNotIn("__", json.dumps(d))

    def test_con_pythonpath(self):
        ruta = "/Users/prueba/.jarvis-control-venv/lib/python3.9/site-packages"
        d = plistlib.loads(render(ruta).encode())
        self.assertEqual(d["EnvironmentVariables"]["PYTHONPATH"], ruta)
        self.assertEqual(d["EnvironmentVariables"]["JARVIS_AUTONOMO"], "1")

    def test_el_instalador_valida_la_carpeta_y_el_plist(self):
        sh = (MAC / "instalar_mouse_autonomo.sh").read_text(encoding="utf-8")
        self.assertIn('[ -d "$PP" ]', sh)        # no acepta una ruta inventada
        self.assertIn("plutil -lint", sh)        # no instala un plist roto
        self.assertIn('rm -f "$DEST"', sh)       # y lo borra si salio mal


class LaSonda(unittest.TestCase):
    def test_la_sonda_responde_json_valido_de_verdad(self):
        # Subproceso real: si la sonda tuviera un error de sintaxis, esto cae.
        p = subprocess.run([sys.executable, "-c", ele.SONDA], capture_output=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr.decode()[:300])
        r = json.loads(p.stdout.decode().strip().splitlines()[-1])
        for clave in ("version", "prefix", "accesibilidad", "Quartz", "pyautogui"):
            self.assertIn(clave, r)
        self.assertRegex(r["version"], r"^\d+\.\d+\.\d+$")

    def test_sondear_no_revienta_con_un_binario_que_no_existe(self):
        self.assertIn("error", ele.sondear("/no/existe/python3"))

    def test_los_candidatos_no_se_repiten_y_son_ejecutables(self):
        c = ele.candidatos()
        self.assertTrue(c)
        resueltos = [str(Path(x).resolve()) for x in c]
        self.assertEqual(len(resueltos), len(set(resueltos)))
        for x in c:
            self.assertTrue(os.access(str(x), os.X_OK))


class LaDecision(unittest.TestCase):
    def correr(self, respuestas, venv_sp=None):
        salida = []
        def sondear(py, pythonpath=None):
            return respuestas.get((str(py), pythonpath), {"error": "no preguntado"})
        with patch.object(ele.sys, "platform", "darwin"), \
             patch.object(ele, "candidatos", return_value=[Path(k[0]) for k in respuestas if k[1] is None]), \
             patch.object(ele, "sondear", side_effect=sondear), \
             patch.object(ele, "site_packages_del_venv", return_value=venv_sp), \
             patch("builtins.print", lambda *a, **k: salida.append(" ".join(str(x) for x in a))):
            codigo = ele.main()
        return codigo, "\n".join(salida)

    def test_elige_el_que_tiene_las_tres_cosas(self):
        bueno = {"version": "3.9.6", "accesibilidad": True, "Quartz": True, "pyautogui": True}
        malo = {"version": "3.9.6", "accesibilidad": False, "Quartz": True, "pyautogui": True}
        codigo, texto = self.correr({("/a/python3", None): malo, ("/b/python3", None): bueno})
        self.assertEqual(codigo, 0)
        self.assertIn("Este sirve: /b/python3", texto)
        self.assertIn('JARVIS_PYTHON="/b/python3"', texto)
        self.assertNotIn("JARVIS_PYTHONPATH", texto)

    def test_con_permiso_pero_sin_paquetes_reintenta_con_el_venv(self):
        sp = "/Users/prueba/.jarvis-control-venv/lib/python3.9/site-packages"
        codigo, texto = self.correr({
            ("/sistema/python3", None): {"version": "3.9.6", "accesibilidad": True, "Quartz": False, "pyautogui": False},
            ("/sistema/python3", sp): {"version": "3.9.6", "accesibilidad": True, "Quartz": True, "pyautogui": True},
        }, venv_sp=sp)
        self.assertEqual(codigo, 0)
        self.assertIn('JARVIS_PYTHONPATH="%s"' % sp, texto)
        self.assertIn('JARVIS_PYTHON="/sistema/python3"', texto)

    def test_sin_permiso_en_ninguno_dice_a_cual_concederselo(self):
        codigo, texto = self.correr({
            ("/venv/python", None): {"version": "3.9.6", "accesibilidad": False, "Quartz": True, "pyautogui": True}})
        self.assertEqual(codigo, 1)
        self.assertIn("NO el permiso: /venv/python", texto)
        self.assertIn("Accesibilidad", texto)
        self.assertNotIn("Este sirve", texto)

    def test_si_faltan_los_paquetes_lo_dice_sin_mandarlo_a_los_ajustes(self):
        codigo, texto = self.correr({
            ("/venv/python", None): {"version": "3.9.6", "accesibilidad": False, "Quartz": False, "pyautogui": False}})
        self.assertEqual(codigo, 1)
        self.assertIn("falta instalar los paquetes", texto)
        self.assertNotIn("Cmd+Shift+G", texto)

    def test_no_mueve_el_cursor_ni_cambia_permisos(self):
        fuente = (MAC / "elegir_python_mouse.py").read_text(encoding="utf-8")
        codigo = re.sub(r'""".*?"""', "", fuente, flags=re.S)
        for prohibido in ("CGWarp", "CGEventPost", "pyautogui.", "launchctl", "tccutil", "sudo"):
            self.assertNotIn(prohibido, codigo)


if __name__ == "__main__":
    unittest.main()
