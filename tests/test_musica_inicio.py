"""Música de inicio: archivo local del dueño en <VOICE_HOME>/musica/, 404 si falta, sin path traversal."""
import os, pathlib, sys, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_desktop_companion import CompanionBase, desk  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


class MusicaInicio(CompanionBase):
    def put(self, name, data=b"ID3fake-music"):
        d = pathlib.Path(self.home) / "musica"; d.mkdir(exist_ok=True)
        (d / name).write_bytes(data); return d / name

    def test_404_sin_archivo(self):
        st, _, _, _ = self.req("GET", "/api/startup-music")
        self.assertEqual(st, 404)

    def test_sirve_archivo_local(self):
        self.put("inicio.ogg", b"OggS-x"); self.put("inicio.mp3")
        st, _, r, b = self.req("GET", "/api/startup-music")
        self.assertEqual((st, b, r.getheader("Content-Type").split(";")[0]), (200, b"ID3fake-music", "audio/mpeg"))

    def test_sin_sesion_no_sirve(self):
        self.put("inicio.mp3")
        st, _, _, b = self.req("GET", "/api/startup-music", cookie=False)
        self.assertNotEqual(b, b"ID3fake-music")

    def test_rechaza_traversal(self):
        secret = pathlib.Path(self.home) / "secreto.mp3"; secret.write_bytes(b"SECRET")
        for path in ("/api/startup-music/../secreto.mp3", "/api/startup-music?f=../secreto.mp3",
                     "/api/startup-music/%2e%2e/secreto.mp3", "/api/startup-music/inicio.mp3"):
            st, _, _, b = self.req("GET", path)
            self.assertNotIn(b"SECRET", b, path)
        d = pathlib.Path(self.home) / "musica"; d.mkdir(exist_ok=True)
        os.symlink(secret, d / "inicio.mp3")          # symlink fuera de la carpeta: ignorado
        self.assertIsNone(desk.startup_music({"VOICE_HOME": self.home}))
        st, _, _, b = self.req("GET", "/api/startup-music")
        self.assertEqual(st, 404); self.assertNotIn(b"SECRET", b)

    def test_ui_encendida_por_defecto_y_sin_audio_en_git(self):
        js = (ROOT / "desktop" / "ui" / "startup.js").read_text()
        self.assertIn("saved('jarvis-startup-music',true)", js)
        self.assertIn("/api/startup-music", js)
        tracked = os.popen(f"git -C {ROOT} ls-files").read().split()
        self.assertFalse([f for f in tracked if "musica/" in f and f.endswith((".mp3", ".m4a", ".ogg"))])


if __name__ == "__main__":
    unittest.main()
