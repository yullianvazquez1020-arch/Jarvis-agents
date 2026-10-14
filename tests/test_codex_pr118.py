"""Arreglos de la revisión Codex PR #118 (datos ficticios, sin red)."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
import app as desk                      # noqa: E402
import mouse_autonomo as ma             # noqa: E402


class CicloEnv(unittest.TestCase):
    def test_voice_ciclo_y_dir_desde_entorno(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"VOICE_CICLO": "false", "VOICE_CICLO_DIR": d}):
            cfg = desk.load_config(path=str(Path(d) / "no-existe.env"))
        self.assertEqual(cfg["VOICE_CICLO"], "false")
        self.assertEqual(cfg["VOICE_CICLO_DIR"], d)


class FakeProc:
    vivos = []

    def __init__(self, cmd, **kw):
        self.cmd = cmd; self.done = threading.Event(); FakeProc.vivos.append(self)

    def poll(self):
        return 0 if self.done.is_set() else None

    def wait(self, timeout=None):
        if not self.done.wait(timeout):
            raise desk.subprocess.TimeoutExpired(self.cmd, timeout)

    def terminate(self):
        self.done.set()

    kill = terminate


class VozLocal(unittest.TestCase):
    def make(self, d):
        c = desk.Companion.__new__(desk.Companion)
        c.cfg = {"VOICE_SERVER_PLAYBACK": "auto"}; c.home = Path(d)
        return c

    def test_cola_serializa_y_stop_corta(self):
        FakeProc.vivos = []
        with tempfile.TemporaryDirectory() as d, patch.object(desk, "local_player", return_value=["fakeplay"]), \
                patch.object(desk.subprocess, "Popen", FakeProc):
            c = self.make(d)
            c._play_local(b"RIFF1"); c._play_local(b"RIFF2"); c._play_local(b"RIFF3")
            time.sleep(0.3)
            self.assertEqual(len(FakeProc.vivos), 1)          # una sola frase sonando, sin solapes
            c.stop_local_audio()                                # stop: corta y descarta la cola
            time.sleep(0.3)
            self.assertTrue(FakeProc.vivos[0].done.is_set())
            self.assertEqual(len(FakeProc.vivos), 1)
            c._play_local(b"RIFF4"); time.sleep(0.3)
            self.assertEqual(len(FakeProc.vivos), 2)
            c.stop_local_audio()


class OrdenAtomica(unittest.TestCase):
    def test_siguiente_json_atomico_y_unico(self):
        with tempfile.TemporaryDirectory() as d:
            ses = {"agent": "jarvis"}
            with patch.object(ma.ae, "stopped", return_value=False), patch.object(ma.auto, "read_session", return_value=ses), \
                    patch.object(ma.auto, "auto_dir", return_value=Path(d)), patch.object(ma, "precheck", return_value=None), \
                    patch.object(ma.os, "replace", wraps=os.replace) as rep:
                res = []
                hs = [threading.Thread(target=lambda: res.append(ma.encargar({"action": "abrir", "url": "https://example.com"})))
                      for _ in range(8)]
                [h.start() for h in hs]; [h.join() for h in hs]
            self.assertEqual(sum(r["ok"] for r in res), 1)
            self.assertTrue(rep.called)
            self.assertEqual(json.loads((Path(d) / "siguiente.json").read_text())["action"], "abrir")
            self.assertEqual([p.name for p in Path(d).iterdir()], ["siguiente.json"])


class VozAlan(unittest.TestCase):
    def test_length_scale_y_sin_voz_femenina(self):
        from audio import engines
        self.assertEqual(engines.Piper("piper", "x.onnx").length_scale, 1.18)
        self.assertEqual(engines.DANIEL_WPM, 165)
        cfg = {"JARVIS_REPLY_LANGUAGE": "en-GB", "VOICE_TTS_VOICE": "Samantha", "VOICE_TTS_BACKEND": "none"}
        self.assertTrue(engines.is_female_en("Samantha")); self.assertFalse(engines.is_female_en("Daniel"))
        self.assertFalse(engines.is_female_en("/x/en_GB-alan-medium.onnx"))
        engines.build(cfg)                                   # no debe fallar; la voz femenina se descarta



class RayosObjetivo(unittest.TestCase):
    def test_temas_de_voz_solo_etiquetas(self):
        self.assertEqual(desk.speech_topics("Sir, BTC is up and Ethereum is flat"), ["BTC", "ETH"])
        self.assertEqual(desk.speech_topics("Todo en orden"), [])
        js = (Path(__file__).resolve().parents[1] / "desktop/ui/torre-cine.js").read_text("utf-8")
        for k in ("raysMode", "cripto", "negocio", "jarvis-rayos", "drawBeam", "speaking_topics", "uLvl", "updReactor", "bezel", "updBolts", "DEMO", "boltR"):
            self.assertIn(k, js, k)
        neg = (Path(__file__).resolve().parents[1] / "desktop/ui/negocios.js").read_text("utf-8")
        self.assertIn("data-negocio", neg); self.assertIn("data-cripto", neg); self.assertIn("jarvis-scan", neg)



class Revision2(unittest.TestCase):
    """Codex PR #118, revisión de ff3f2fe."""

    def make(self, d, mode="auto"):
        c = desk.Companion.__new__(desk.Companion)
        c.cfg = {"VOICE_SERVER_PLAYBACK": mode}; c.home = Path(d); c.lock = threading.Lock(); c.windows = {}
        return c

    def test_auto_una_sola_salida(self):
        with tempfile.TemporaryDirectory() as d, patch.object(desk, "local_player", return_value=["fakeplay"]):
            c = self.make(d)
            self.assertTrue(c._playback_native())                    # sin ventana: altavoces
            c.owner = "w1"; c.windows["w1"] = time.time()
            self.assertFalse(c._playback_native())                   # con ventana dueña viva: solo el navegador
            c.windows["w1"] = time.time() - desk.WINDOW_STALE - 1
            self.assertTrue(c._playback_native())
            self.assertTrue(self.make(d, "true")._playback_native())
            self.assertFalse(self.make(d, "false")._playback_native())

    def test_stop_entre_comprobacion_y_lanzamiento(self):
        FakeProc.vivos = []
        with tempfile.TemporaryDirectory() as d, patch.object(desk, "local_player", return_value=["fakeplay"]):
            c = self.make(d)
            orig = Path.write_bytes
            def lento(self_, data):                                   # el stop llega mientras escribe el wav
                r = orig(self_, data); c.stop_local_audio(); return r
            with patch.object(desk.subprocess, "Popen", FakeProc), patch.object(Path, "write_bytes", lento):
                c._play_local(b"RIFF1"); time.sleep(0.4)
            self.assertEqual(FakeProc.vivos, [])                     # nunca se lanza tras el stop

    def test_scroll_y_wait_malformados_se_rechazan(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("autonomo_t", Path(__file__).resolve().parents[1] / "desktop/mac/autonomo.py")
        au = importlib.util.module_from_spec(spec); spec.loader.exec_module(au)
        ses = {"agent": "jarvis"}
        with patch.object(au.ae, "denial", return_value=None):
            for bad in ({"action": "scroll", "dy": "down"}, {"action": "scroll", "dy": float("nan")}, {"action": "scroll", "dy": 9999},
                        {"action": "scroll", "dy": True}, {"action": "wait", "seconds": "pronto"}, {"action": "wait", "seconds": float("inf")},
                        {"action": "wait", "seconds": -1}, {"action": "wait", "seconds": [1]}):
                bad = dict(bad, agent="jarvis")
                self.assertIn(au.validate(bad, ses, (1440, 900), "Safari"), ("desplazamiento", "espera"), bad)
            self.assertIsNone(au.validate({"action": "scroll", "dy": -5, "agent": "jarvis"}, ses, (1440, 900), "Safari"))
            self.assertIsNone(au.validate({"action": "wait", "seconds": "2.5", "agent": "jarvis"}, ses, (1440, 900), "Safari"))



class Revision3(unittest.TestCase):
    """Codex PR #118, revisión de f0ce9b6."""

    def test_ciclo_no_reprocesa_mas_de_500(self):
        import ciclo
        with tempfile.TemporaryDirectory() as d:
            home = Path(d); cola = [{"id": f"e{i}", "tipo": "shell"} for i in range(620)]   # tipo no permitido: barato
            (home / "encargos.jsonl").write_text("\n".join(json.dumps(e) for e in cola), encoding="utf-8")
            c = ciclo.Ciclo(home, base=home, emit=lambda e: None, speak=lambda t: None, stopped=lambda: False)
            self.assertEqual(len(c.vuelta()), 620)
            self.assertEqual(c.vuelta(), [])                                  # nada se repite
            (home / "encargos.jsonl").write_text(json.dumps(cola[0]), encoding="utf-8")     # cola compactada
            self.assertEqual(c.vuelta(), [])
            self.assertEqual(json.loads((home / "encargos_hechos.json").read_text()), ["e0"])

    def test_habla_sin_ventana_duena_por_altavoces(self):
        with tempfile.TemporaryDirectory() as d, patch.object(desk, "local_player", return_value=["fakeplay"]):
            c = desk.Companion.__new__(desk.Companion)
            c.cfg = {"VOICE_SERVER_PLAYBACK": "auto"}; c.home = Path(d); c.lock = threading.Lock(); c.windows = {}
            c.owner = None; c.prefs = {"discreet": False, "rate": 1.0}; c.turns = {}; c.audio = {}; c.last = {}
            class T:
                def problem(self): return ""
                def synthesize(self, text, rate=1.0):
                    from audio.wav import make_wav
                    return make_wav(b"\x00\x00" * 1600), "audio/wav"
            c.tts = T(); played, ev = [], []; c._play_local = lambda a, g=None: played.append(a); c.emit = ev.append
            self.assertIsNotNone(c.speak("Hola, señor"))
            self.assertEqual(len(played), 1); self.assertFalse(any(e.get("type") == "audio.play" for e in ev))



class Revision4(unittest.TestCase):
    """Codex PR #118, revisión de 320f7da."""

    def test_claves_estables_sin_id(self):
        import ciclo
        with tempfile.TemporaryDirectory() as d:
            home = Path(d); cola = [{"tipo": "shell", "n": 1}, {"tipo": "shell", "n": 2}]
            (home / "encargos.jsonl").write_text("\n".join(json.dumps(e) for e in cola), encoding="utf-8")
            c = ciclo.Ciclo(home, base=home, emit=lambda e: None, speak=lambda t: None, stopped=lambda: False)
            self.assertEqual(len(c.vuelta()), 2)
            (home / "encargos.jsonl").write_text(json.dumps(cola[1]), encoding="utf-8")      # se quita la primera línea
            self.assertEqual(c.vuelta(), [])                                                 # la segunda no se repite

    def test_dueno_caducado_con_otra_ventana_viva_usa_altavoces(self):
        with tempfile.TemporaryDirectory() as d, patch.object(desk, "local_player", return_value=["fakeplay"]):
            c = desk.Companion.__new__(desk.Companion)
            c.cfg = {"VOICE_SERVER_PLAYBACK": "auto"}; c.home = Path(d); c.lock = threading.Lock()
            c.owner = "vieja"; c.windows = {"vieja": time.time() - desk.WINDOW_STALE - 5, "otra": time.time()}
            self.assertTrue(c._playback_native())
            c.owner = None; self.assertTrue(c._playback_native())

    def test_cola_de_voz_unica_con_hilos(self):
        with tempfile.TemporaryDirectory() as d, patch.object(desk, "local_player", return_value=["fakeplay"]), \
                patch.object(desk.subprocess, "Popen", FakeProc):
            c = desk.Companion.__new__(desk.Companion); c.cfg = {"VOICE_SERVER_PLAYBACK": "auto"}; c.home = Path(d)
            arranques = []; orig = threading.Thread.start
            def contar(th):
                arranques.append(th); return orig(th)
            with patch.object(threading.Thread, "start", contar):
                hs = [threading.Thread(target=c._play_local, args=(b"RIFF",)) for _ in range(8)]
                [orig(h) for h in hs]; [h.join() for h in hs]
            self.assertEqual(len(arranques), 1)                                              # un solo worker
            c.stop_local_audio()



class Revision5(unittest.TestCase):
    """Codex PR #118, revisión de 379fa3c."""

    def au(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("autonomo_r5", Path(__file__).resolve().parents[1] / "desktop/mac/autonomo.py")
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

    def test_puntero_solo_en_apps_verificadas(self):
        au = self.au(); ses = {"agent": "jarvis"}; sz = (1440, 900)
        with patch.object(au.ae, "denial", return_value=None):
            click = {"agent": "jarvis", "action": "click", "x": 500, "y": 400}
            for app in ("Microsoft Outlook", "Slack", "Mail", "Messages"):
                self.assertEqual(au.validate(dict(click), ses, sz, app), "app_frente", app)
            self.assertEqual(au.validate(dict(click), ses, sz, "Safari"), "sitio_no_verificado")
            self.assertEqual(au.validate(dict(click), ses, sz, "Safari", {"web_ok": True}), "sitio_no_verificado")
            ok = {"opened_host": "github.com", "page_url": "https://github.com/ejemplo/repo"}
            self.assertIsNone(au.validate(dict(click), ses, sz, "Safari", ok))
            otra = {"opened_host": "github.com", "page_url": "https://mail.google.com/mail"}
            self.assertEqual(au.validate(dict(click), ses, sz, "Safari", otra), "sitio_no_verificado")
            self.assertEqual(au.validate({"agent": "jarvis", "action": "type", "text": "hola"}, ses, sz, "Safari", {"web_ok": True}), "texto_en_navegador")
            self.assertIsNone(au.validate({"agent": "jarvis", "action": "type", "text": "hola"}, ses, sz, "Notes"))

    def test_piper_si_la_voz_es_onnx_y_la_torre_mini_gana(self):
        import audio.engines as engines
        cfg = {"VOICE_TTS_VOICE": "/tmp/en_GB-alan-medium.onnx", "VOICE_PIPER_BIN": "piper"}
        self.assertEqual(engines.pick_tts(cfg, platform="darwin", which=lambda c: c == "say", exists=lambda p: p.endswith(".onnx") or p == "piper"), "piper")
        css = (Path(__file__).resolve().parents[1] / "desktop/ui/torre-aincrad.css").read_text(encoding="utf-8")
        self.assertIn("#aincrad.aincrad-mini", css)

    def test_scroll_normalizado(self):
        au = self.au(); ses = {"agent": "jarvis"}
        with patch.object(au.ae, "denial", return_value=None):
            for v in ("1.0", "1e0", 1.0):
                a = {"agent": "jarvis", "action": "scroll", "dy": v}
                self.assertIsNone(au.validate(a, ses, (1440, 900), "Safari")); self.assertEqual(a["dy"], 1); self.assertIs(type(a["dy"]), int)

    def test_stop_antes_de_encolar_invalida_audio(self):
        FakeProc.vivos = []
        with tempfile.TemporaryDirectory() as d, patch.object(desk, "local_player", return_value=["fakeplay"]), \
                patch.object(desk.subprocess, "Popen", FakeProc):
            c = desk.Companion.__new__(desk.Companion); c.cfg = {"VOICE_SERVER_PLAYBACK": "auto"}; c.home = Path(d)
            gen0 = getattr(c, "_voz_gen", 0)
            c.stop_local_audio()                                   # stop llega antes de que exista la cola
            c._play_local(b"RIFF", gen0); time.sleep(0.3)
            self.assertEqual(FakeProc.vivos, [])
            c._play_local(b"RIFF2"); time.sleep(0.3)
            self.assertEqual(len(FakeProc.vivos), 1); c.stop_local_audio()


if __name__ == "__main__":
    unittest.main()
