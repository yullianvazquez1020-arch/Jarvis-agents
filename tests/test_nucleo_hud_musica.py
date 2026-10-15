"""Núcleo HUD en WebGL con respaldo 2D, un solo bucle, y música original en bucle (PR fix/voz-musica-nucleo-real)."""
import sys
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "desktop"))
import app  # noqa: E402

UI = ROOT / "desktop/ui"


class NucleoHUD(unittest.TestCase):
    def test_webgl_con_respaldo(self):
        gl = (UI / "nucleo-gl.js").read_text("utf-8")
        for need in ("UnrealBloomPass", "EffectComposer", "TubeGeometry", "MeshPhysicalMaterial", "PMREMGenerator", "rays", "hazeMat", "boltEnv", "hex(", "texture2D(tDiffuse,vUv+off)"):
            self.assertIn(need, gl)
        self.assertIn("N.gl = true", gl); self.assertIn("webglOk", gl)
        self.assertIn("nucleo-gl.js", app.UI_FILES)
        for page in ("index.html", "nucleo.html"):
            self.assertIn('<script type="module" src="/ui/nucleo-gl.js"></script>', (UI / page).read_text("utf-8"))

    def test_un_solo_bucle_y_rendimiento(self):
        n = (UI / "nucleo.js").read_text("utf-8"); gl = (UI / "nucleo-gl.js").read_text("utf-8")
        self.assertNotIn("requestAnimationFrame(", gl)              # el bucle es el de nucleo.js
        self.assertIn("Math.min(1.5", n); self.assertIn("DPR_MAX = 2", gl); self.assertIn("p95 > 18", gl)
        self.assertIn("bloomRes", gl); self.assertIn("ACESFilmicToneMapping", gl); self.assertIn("coc", gl); self.assertIn("function adapt", gl)
        self.assertIn('classList.contains("nucleo-home")', (UI / "cielo.js").read_text("utf-8"))

    def test_hud_procedural_sin_asignar_por_fotograma(self):
        gl = (UI / "nucleo-gl.js").read_text("utf-8")
        self.assertIn("hudMat", gl); self.assertIn("fwidth", gl); self.assertIn("uLv", gl)
        paso = gl[gl.index("N.paso = function"):]
        for bad in ("new THREE.", "dispose(", ".clone()", "TubeGeometry"):
            self.assertNotIn(bad, paso)                                # nada se crea ni libera en el bucle
        self.assertNotIn("rig.remove(", gl); self.assertNotIn("Math.random()", paso); self.assertIn("Math.exp(-dt", paso); self.assertIn("fps=1", gl); self.assertIn("uPh", gl); self.assertNotIn("*sp", gl); self.assertIn("p95 > 18", gl); self.assertNotIn("setTimeout", gl); self.assertNotIn("getElementById(\"estado\")", paso)


class Musica(unittest.TestCase):
    def test_bucle_original(self):
        with wave.open(str(UI / "audio/ambiente.wav")) as w:
            self.assertAlmostEqual(w.getnframes() / w.getframerate(), 40.0, places=1); self.assertEqual(w.getnchannels(), 2)
        js = (UI / "startup.js").read_text("utf-8")
        self.assertIn("/api/ambient-music", js); self.assertIn("src.loop=true", js); self.assertIn("speaking?.025:.12", js)
        self.assertIn('"/api/ambient-music"', (ROOT / "desktop/app.py").read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
