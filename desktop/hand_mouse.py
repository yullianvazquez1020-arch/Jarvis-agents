"""Owner-driven local movement and explicit opt-in single-left-click trial."""
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
        self.button_held = False

    def size(self):
        return tuple(self.gui.size())

    def position(self):
        return tuple(self.gui.position())

    def escape(self):
        return bool(self.quartz.CGEventSourceKeyState(self.quartz.kCGEventSourceStateCombinedSessionState, 53))

    def move(self, x, y):
        if getattr(self, "button_held", False):
            self.gui.failSafeCheck()
            event = self.quartz.CGEventCreateMouseEvent(None, self.quartz.kCGEventLeftMouseDragged,
                                                       (x, y), self.quartz.kCGMouseButtonLeft)
            self.quartz.CGEventPost(self.quartz.kCGHIDEventTap, event)
        else:
            self.gui.moveTo(x, y, duration=0, _pause=False)

    def scroll(self, amount):
        self.gui.scroll(amount, _pause=False)

    def down(self):
        self.button_held = True
        self.gui.mouseDown(button="left", _pause=False)

    def up(self):
        # Release must still work at a FAILSAFE corner. Post only a left-button-up.
        point = self.quartz.CGEventGetLocation(self.quartz.CGEventCreate(None))
        event = self.quartz.CGEventCreateMouseEvent(None, self.quartz.kCGEventLeftMouseUp,
                                                   point, self.quartz.kCGMouseButtonLeft)
        self.quartz.CGEventPost(self.quartz.kCGHIDEventTap, event)
        self.button_held = False

    def click(self):
        self.gui.click(button="left", clicks=1)


class HandMouse:
    TTL = 60.0
    FRESH = 0.4
    HOLD = 0.35
    COOLDOWN = 1.0

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
        self.mode = "move"
        self.dragging = False
        self.scroll_anchor = None
        self.scroll_remainder = 0.0
        self.scroll_pending = 0
        self.scroll_at = -math.inf
        self.click_enabled = False
        self.last_click = -math.inf
        self._reset_gesture()
        self.reason = "Apagado. Solo movimiento; sin clics."

    def _reset_gesture(self):
        self.ready = False
        self.pinch_start = None
        self.pinch_frames = 0
        self.pinch_last = None
        self.frozen = False
        self.gesture = "Abre pulgar e índice"

    def _release_drag(self):
        if self.dragging:
            self.pointer.up()
            self.dragging = False

    def _stop(self, reason):
        self.lease = self.owner = ""
        self.target = None
        self.scroll_anchor = None
        self.scroll_remainder = 0.0
        self.scroll_pending = 0
        self._reset_gesture()
        self.reason = reason
        try:
            self._release_drag()
        except Exception:
            self.reason = "Control apagado; no se pudo confirmar que el botón se soltó. Usa el mouse físico."

    def _expire(self):
        if self.lease and self.clock() >= self.deadline:
            self._stop("Prueba de 60 segundos terminada. Actívala de nuevo manualmente.")

    def status(self):
        with self.lock:
            self._expire()
            return {"mode": self.mode, "dragging": self.dragging, "click_enabled": self.click_enabled, "gesture": self.gesture, "enabled": self.enabled, "active": bool(self.lease), "reason": self.reason,
                    "remaining": max(0, round(self.deadline - self.clock())) if self.lease else 0}

    def arm(self, owner, data):
        if data not in tuple({"confirm": c} for c in ("SOLO_MOVER_60S", "MOVER_Y_CLIC_60S", "DESPLAZAR_60S", "ARRASTRAR_60S")):
            raise ValueError("Confirma la prueba de solo movimiento.")
        with self.lock:
            if not self.enabled or self.closed.is_set():
                raise RuntimeError("Reinicia el panel local con --hand-mouse para habilitar esta prueba.")
            self._expire()
            if self.lease:
                raise RuntimeError("Ya hay una prueba activa. Detén esa prueba primero.")
            if self.dragging:
                self._release_drag()
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
            self.mode = {"SOLO_MOVER_60S":"move", "MOVER_Y_CLIC_60S":"click",
                         "DESPLAZAR_60S":"scroll", "ARRASTRAR_60S":"drag"}[data["confirm"]]
            self.click_enabled = self.mode in ("click", "drag")
            self.scroll_anchor = None
            self.scroll_remainder = 0.0
            self.scroll_pending = 0
            self.scroll_at = -math.inf
            self.last_click = -math.inf
            self._reset_gesture()
            self.reason = ("Movimiento y clic izquierdo por pinza. Escape detiene." if self.click_enabled
                           else "Solo movimiento en la pantalla principal. Escape detiene.")
            if self.threaded and self.thread is None:
                self.thread = threading.Thread(target=self._loop, daemon=True)
                self.thread.start()
            return dict(self.status(), lease=self.lease, width=w, height=h)

    def _authorized(self, owner, lease):
        self._expire()
        return bool(self.lease and self.owner == owner and isinstance(lease, str)
                    and secrets.compare_digest(self.lease, lease))

    def frame(self, owner, data):
        with self.lock:
            if not self._authorized(owner, data.get("lease")):
                raise ValueError("Prueba apagada, vencida o de otra sesión.")
            try:
                keys = {"lease", "seq", "x", "y", "captured_ms"}
                if self.click_enabled:
                    keys.add("pinch_ratio")
                if self.mode == "scroll":
                    keys.add("two_fingers")
                if set(data) != keys:
                    raise ValueError("Cuadro no permitido para este modo.")
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
                    raise ValueError("Cuadro vencido; no se mueve el puntero.")
                now = self.clock()
                captured = now - max(0, age)
                ratio = data.get("pinch_ratio")
                if self.click_enabled and ratio is not None:
                    if type(ratio) not in (int, float) or not math.isfinite(ratio) or ratio < 0:
                        raise ValueError("Pinza inválida.")
                self.last_seq = seq
                if self.mode == "scroll":
                    two = data["two_fingers"]
                    if type(two) is not bool:
                        raise ValueError("Gesto inválido.")
                    if not two:
                        self.scroll_anchor = None
                        self.scroll_remainder = 0.0
                        self.scroll_pending = 0
                        self.gesture = "Extiende índice y medio; recoge los otros dedos"
                    else:
                        if self.scroll_anchor is not None:
                            ay, at = self.scroll_anchor
                            if captured <= at:
                                raise ValueError("Captura repetida.")
                            if captured-at > self.FRESH:
                                self.scroll_remainder = 0.0
                                self.scroll_pending = 0
                            else:
                                self.scroll_remainder += data["y"] - ay
                                steps = math.trunc(self.scroll_remainder / .015)
                                if steps:
                                    self.scroll_remainder -= steps * .015
                                    self.scroll_pending = max(-3, min(3, self.scroll_pending - steps))
                        self.scroll_anchor = (data["y"], captured)
                        self.gesture = "Dos dedos detectados: mueve arriba o abajo"
                    self.target = (0, 0, captured)
                    return self.status()
                if self.click_enabled:
                    if ratio is None:
                        self._release_drag()
                        self.target = None
                        self._reset_gesture()
                        return self.status()
                    if self.pinch_last is not None and captured - self.pinch_last > self.FRESH:
                        self._release_drag()
                        self._reset_gesture()
                    if self.pinch_last is not None and captured <= self.pinch_last:
                        raise ValueError("Captura repetida o fuera de orden.")
                    self.pinch_last = captured
                    self.frozen = ratio < 0.6
                    if ratio >= 0.6:
                        self._release_drag()
                        self.ready = now - self.last_click >= self.COOLDOWN
                        self.pinch_start = None
                        self.pinch_frames = 0
                        self.gesture = ("Listo: junta pulgar e índice" if self.ready
                                        else "Espera un segundo y abre los dedos")
                    elif ratio <= 0.3 and self.ready:
                        if self.pinch_start is None:
                            self.pinch_start = captured
                        self.pinch_frames += 1
                        self.gesture = "Mantén la pinza; puntero inmóvil"
                    else:
                        self.pinch_start = None
                        self.pinch_frames = 0
                        self.gesture = "Abre pulgar e índice" if not self.ready else "Acerca los dedos"
                self.target = (12 + data["x"] * (self.width - 25),
                               12 + data["y"] * (self.height - 25), captured)
                return self.status()
            except (ValueError, TypeError):
                self._release_drag()
                self.scroll_anchor = None
                self.scroll_remainder = 0.0
                self.scroll_pending = 0
                self.target = None
                self._reset_gesture()
                raise

    def stop(self, owner, lease):
        with self.lock:
            if self._authorized(owner, lease):
                self._stop("Detenido por el dueño.")
            return self.status()

    def tick(self):
        with self.lock:
            self._expire()
            if not self.lease:
                if self.dragging:
                    try:
                        self._release_drag()
                    except Exception:
                        pass
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
                    self._release_drag()
                    self.scroll_anchor = None
                    self.scroll_remainder = 0.0
                    self.scroll_pending = 0
                    self.target = None
                    self._reset_gesture()
                    return
                if self.mode == "scroll":
                    if self.scroll_pending and self.clock() - self.scroll_at >= .12:
                        amount = 1 if self.scroll_pending > 0 else -1
                        self.scroll_pending -= amount
                        self.scroll_at = self.clock()
                        self.pointer.scroll(amount)
                    return
                if self.click_enabled and self.frozen and not self.dragging:
                    if (self.ready and self.pinch_start is not None and self.pinch_frames >= 3
                            and self.pinch_last - self.pinch_start >= self.HOLD
                            and self.clock() - self.last_click >= self.COOLDOWN):
                        # Consume before invoking native code: no queued or repeated click.
                        self.ready = False
                        self.pinch_start = None
                        self.pinch_frames = 0
                        self.last_click = self.clock()
                        self.gesture = "Clic realizado. Abre los dedos para rearmar"
                        if self.mode == "drag":
                            self.dragging = True
                            self.pointer.down()
                            self.gesture = "Arrastrando: abre los dedos para soltar"
                        else:
                            self.pointer.click()
                    return
                tx, ty, _ = self.target
                error = math.hypot(tx - px, ty - py)
                # Reject tiny tremor, damp near a target, catch up on long reaches.
                # Continuous gain avoids a speed jump at a threshold; no prediction.
                if error <= 2:
                    return
                gain = 0.18 + 0.27 * min(1.0, error / 300.0)
                dx, dy = (tx - px) * gain, (ty - py) * gain
                distance = math.hypot(dx, dy)
                if distance > 90:
                    dx, dy = dx * 90 / distance, dy * 90 / distance
                if math.hypot(dx, dy) >= 1:
                    self.pointer.move(round(px + dx), round(py + dy))
            except Exception:
                self._stop("El control del puntero falló y se apagó. Revisa Accesibilidad.")

    def _loop(self):
        while not self.closed.wait(0.025):
            self.tick()

    def close(self):
        self.closed.set()
        with self.lock:
            self._stop("Panel cerrado.")
        if self.thread:
            self.thread.join(timeout=1)
