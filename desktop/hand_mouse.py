"""Owner-driven, local pointer movement trial. No clicks, keys, scrolling or agents."""
import math
import secrets
import sys
import threading
import time


class MacPointer:
    def __init__(self):
        if sys.platform != "darwin":
            raise RuntimeError("La prueba del puntero solo está disponible en macOS.")
        try:
            import pyautogui
            import Quartz
        except ImportError as exc:
            raise RuntimeError("Inicia Jarvis con el Python de .jarvis-control-venv.") from exc
        import ctypes
        services = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        trusted = services.AXIsProcessTrusted
        trusted.argtypes = []
        trusted.restype = ctypes.c_bool
        if not trusted():
            raise RuntimeError("Falta el permiso de Accesibilidad de Terminal en macOS.")
        self.gui, self.quartz = pyautogui, Quartz
        self.gui.FAILSAFE = True

    def size(self):
        return tuple(self.gui.size())

    def position(self):
        return tuple(self.gui.position())

    def escape(self):
        return bool(self.quartz.CGEventSourceKeyState(self.quartz.kCGEventSourceStateCombinedSessionState, 53))

    def move(self, x, y):
        self.gui.moveTo(x, y, duration=0)


class HandMouse:
    TTL = 60.0
    FRESH = 0.4

    def __init__(self, enabled=False, pointer_factory=MacPointer, clock=time.monotonic,
                 wall=time.time, threaded=True):
        self.enabled = enabled
        self.factory, self.clock, self.wall, self.threaded = pointer_factory, clock, wall, threaded
        self.lock = threading.RLock()
        self.closed = threading.Event()
        self.thread = None
        self.pointer = None
        self.lease = self.owner = ""
        self.deadline = 0
        self.target = None
        self.last_seq = -1
        self.reason = "Apagado. Solo movimiento; sin clics."

    def _stop(self, reason):
        self.lease = self.owner = ""
        self.target = None
        self.reason = reason

    def _expire(self):
        if self.lease and self.clock() >= self.deadline:
            self._stop("Prueba de 60 segundos terminada. Actívala de nuevo manualmente.")

    def status(self):
        with self.lock:
            self._expire()
            return {"enabled": self.enabled, "active": bool(self.lease), "reason": self.reason,
                    "remaining": max(0, round(self.deadline - self.clock())) if self.lease else 0}

    def arm(self, owner, data):
        if data != {"confirm": "SOLO_MOVER_60S"}:
            raise ValueError("Confirma la prueba de solo movimiento.")
        with self.lock:
            if not self.enabled or self.closed.is_set():
                raise RuntimeError("Reinicia el panel local con --hand-mouse para habilitar esta prueba.")
            self._expire()
            if self.lease:
                raise RuntimeError("Ya hay una prueba activa. Detén esa prueba primero.")
            if not owner:
                raise ValueError("Falta sesión local.")
            if self.pointer is None:
                self.pointer = self.factory()
            if self.pointer.escape():
                raise RuntimeError("Suelta Escape antes de activar la prueba.")
            w, h = self.pointer.size()
            if w < 100 or h < 100:
                raise RuntimeError("No se pudo medir la pantalla principal.")
            self.width, self.height = w, h
            self.owner, self.lease = owner, secrets.token_urlsafe(24)
            self.deadline = self.clock() + self.TTL
            self.last_seq = -1
            self.target = None
            self.reason = "Solo movimiento en la pantalla principal. Escape detiene."
            if self.threaded and self.thread is None:
                self.thread = threading.Thread(target=self._loop, daemon=True)
                self.thread.start()
            return dict(self.status(), lease=self.lease, width=w, height=h)

    def _authorized(self, owner, lease):
        self._expire()
        return bool(self.lease and self.owner == owner and isinstance(lease, str)
                    and secrets.compare_digest(self.lease, lease))

    def frame(self, owner, data):
        if set(data) != {"lease", "seq", "x", "y", "captured_ms"}:
            raise ValueError("Solo se aceptan coordenadas; ninguna otra acción.")
        with self.lock:
            if not self._authorized(owner, data["lease"]):
                raise ValueError("Prueba apagada, vencida o de otra sesión.")
            seq = data["seq"]
            if type(seq) is not int or seq <= self.last_seq:
                raise ValueError("Cuadro repetido o fuera de orden.")
            for key in ("x", "y", "captured_ms"):
                if type(data[key]) not in (int, float) or not math.isfinite(data[key]):
                    raise ValueError("Coordenadas inválidas.")
            if not (0 <= data["x"] <= 1 and 0 <= data["y"] <= 1):
                raise ValueError("Coordenadas fuera de la pantalla.")
            age = self.wall() - data["captured_ms"] / 1000
            if age < -0.1 or age > self.FRESH:
                self.target = None
                raise ValueError("Cuadro vencido; no se mueve el puntero.")
            self.last_seq = seq
            # Keep targets away from physical fail-safe corners; preserve original capture age.
            self.target = (12 + data["x"] * (self.width - 25),
                           12 + data["y"] * (self.height - 25), self.clock() - max(0, age))
            return self.status()

    def stop(self, owner, lease):
        with self.lock:
            if self._authorized(owner, lease):
                self._stop("Detenido por el dueño.")
            return self.status()

    def tick(self):
        with self.lock:
            self._expire()
            if not self.lease:
                return
            try:
                if self.pointer.escape():
                    self._stop("Detenido con Escape.")
                    return
                px, py = self.pointer.position()
                if not (2 < px < self.width - 3 and 2 < py < self.height - 3):
                    self._stop("Detenido al llevar el puntero al borde o a otra pantalla.")
                    return
                if not self.target or self.clock() - self.target[2] > self.FRESH:
                    self.target = None
                    return
                tx, ty, _ = self.target
                dx, dy = (tx - px) * 0.25, (ty - py) * 0.25
                distance = math.hypot(dx, dy)
                if distance > 60:
                    dx, dy = dx * 60 / distance, dy * 60 / distance
                if math.hypot(dx, dy) >= 1:
                    self.pointer.move(round(px + dx), round(py + dy))
            except Exception:
                self._stop("El control del puntero falló y se apagó. Revisa Accesibilidad.")

    def _loop(self):
        while not self.closed.wait(0.05):
            self.tick()

    def close(self):
        self.closed.set()
        with self.lock:
            self._stop("Panel cerrado.")
        if self.thread:
            self.thread.join(timeout=1)
