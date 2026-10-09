#!/usr/bin/env python3
"""Borrador de gestos. No abre la cámara y no mueve el mouse.

--dry-run lee fotogramas ficticios. --controlar solo pide el turno gestos.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

CONFIRM = {"Thumb_Up": "confirmar", "Closed_Fist": "cancelar", "Open_Palm": "pausa"}


class OneEuro:
    def __init__(self, freq: float = 15.0, mincutoff: float = 1.0, beta: float = 0.007, dcutoff: float = 1.0):
        self.freq = freq
        self.mincutoff = mincutoff
        self.beta = beta
        self.dcutoff = dcutoff
        self.x_prev = None
        self.dx_prev = 0.0

    def _alpha(self, cutoff: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        te = 1.0 / self.freq
        return 1.0 / (1.0 + tau / te)

    def filter(self, value: float) -> float:
        if self.x_prev is None:
            self.x_prev = value
            return value
        dx = (value - self.x_prev) * self.freq
        dx_hat = self._alpha(self.dcutoff) * dx + (1 - self._alpha(self.dcutoff)) * self.dx_prev
        cutoff = self.mincutoff + self.beta * abs(dx_hat)
        hat = self._alpha(cutoff) * value + (1 - self._alpha(cutoff)) * self.x_prev
        self.x_prev = hat
        self.dx_prev = dx_hat
        return hat


class Cursor:
    def __init__(self, width: int = 1440, height: int = 900):
        self.width = width
        self.height = height
        self.fx = OneEuro()
        self.fy = OneEuro()
        self.x = None
        self.y = None
        self.zone = (0.25, 0.25, 0.75, 0.75)

    def recenter(self, nx: float, ny: float) -> None:
        self.zone = (nx - 0.2, ny - 0.2, nx + 0.2, ny + 0.2)

    def update(self, nx: float, ny: float) -> tuple[int, int] | None:
        x0, y0, x1, y1 = self.zone
        mx = min(1.0, max(0.0, (nx - x0) / max(0.05, x1 - x0)))
        my = min(1.0, max(0.0, (ny - y0) / max(0.05, y1 - y0)))
        x = max(0, min(self.width - 1, round(self.fx.filter(mx) * (self.width - 1))))
        y = max(0, min(self.height - 1, round(self.fy.filter(my) * (self.height - 1))))
        if self.x is not None and abs(x - self.x) < 3 and abs(y - self.y) < 3:
            return None
        self.x, self.y = x, y
        return x, y


class Pinch:
    def __init__(self):
        self.closed = False
        self.since = None

    def update(self, distance: float, t: float) -> str | None:
        if not self.closed and distance <= 0.045:
            self.closed = True
            self.since = t
            return None
        if self.closed and distance >= 0.065:
            held = 0.0 if self.since is None else t - self.since
            self.closed = False
            self.since = None
            return None if held >= 0.4 - 1e-9 else "clic"
        if self.closed and self.since is not None and t - self.since >= 0.4 - 1e-9:
            return "arrastrar"
        return None


class GestureHold:
    def __init__(self):
        self.name = None
        self.since = None
        self.ready_at = 0.0

    def update(self, name: str | None, t: float) -> str | None:
        if t < self.ready_at or name not in CONFIRM:
            if name not in CONFIRM:
                self.name = None
                self.since = None
            return None
        if name != self.name:
            self.name = name
            self.since = t
            return None
        if self.since is not None and t - self.since >= 0.6 - 1e-9:
            self.ready_at = t + 1.5
            self.name = None
            self.since = None
            return CONFIRM[name]
        return None


def distance(a: dict, b: dict) -> float:
    return math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))


def dry_run(path: Path) -> int:
    cursor, pinch, holds = Cursor(), Pinch(), GestureHold()
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        frame = json.loads(raw)
        t = float(frame["t"])
        events = []
        if "calibrar" in frame:
            cursor.recenter(float(frame["x"]), float(frame["y"]))
            events.append("zona")
        elif "x" in frame and "y" in frame:
            point = cursor.update(float(frame["x"]), float(frame["y"]))
            if point:
                events.append(f"cursor {point[0]} {point[1]}")
        if "pinch" in frame:
            choice = pinch.update(float(frame["pinch"]), t)
            if choice:
                events.append(choice)
        elif "landmarks" in frame:
            points = frame["landmarks"]
            choice = pinch.update(distance(points[4], points[8]), t)
            if choice:
                events.append(choice)
        choice = holds.update(frame.get("gesture"), t)
        if choice:
            events.append(choice)
        if choice in ("confirmar", "cancelar"):
            from agent_executor import note_gesture
            events.append(note_gesture(choice == "confirmar"))
        print(f"{line_no} " + (", ".join(events) if events else "nada"))
    return 0


def self_test() -> int:
    holds = GestureHold()
    assert holds.update("Thumb_Up", 0.0) is None
    assert holds.update("Thumb_Up", 0.5) is None
    assert holds.update("Thumb_Up", 0.6) == "confirmar"
    assert holds.update("Thumb_Up", 1.0) is None
    assert holds.update("Closed_Fist", 2.2) is None
    assert holds.update("Closed_Fist", 2.8) == "cancelar"
    pinch = Pinch()
    assert pinch.update(0.08, 0.0) is None
    assert pinch.update(0.04, 0.1) is None
    assert pinch.update(0.04, 0.3) is None
    assert pinch.update(0.08, 0.35) == "clic"
    pinch = Pinch()
    assert pinch.update(0.04, 1.0) is None
    assert pinch.update(0.04, 1.5) == "arrastrar"
    cursor = Cursor()
    assert cursor.update(0.5, 0.5) == (720, 450)
    assert cursor.update(0.501, 0.501) is None
    cursor = Cursor(100, 100)
    cursor.recenter(0.5, 0.5)
    assert cursor.update(0.5, 0.5) == (50, 50)
    assert mano_a_puntero(True, (10, 10)) == "propuesto"
    assert mano_a_puntero(False, (10, 10)) == "nada"
    print("SELFTEST OK")
    return 0


def mano_a_puntero(control: bool, point) -> str:
    """La mano propone. No mueve el puntero: eso solo lo hace el ejecutor."""
    if not control or point is None:
        return "nada"
    return "propuesto"


def camera_loop(index: int, control: bool) -> int:
    """Abre la cámara solo si se pide. No guarda fotos y no mueve el mouse."""
    from agent_executor import control_dir, note_gesture, stopped
    try:
        import cv2
        import mediapipe as mp
    except Exception as exc:
        print(f"Falta la cámara local ({type(exc).__name__}). En el Intel: pip install -r requirements-mac.txt")
        return 2
    model = control_dir() / "gesture_recognizer.task"
    if not model.exists():
        import urllib.request
        urllib.request.urlretrieve(
            "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
            "gesture_recognizer/float16/1/gesture_recognizer.task",
            model,
        )
    options = mp.tasks.vision.GestureRecognizerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=1,
    )
    recognizer = mp.tasks.vision.GestureRecognizer.create_from_options(options)
    cap = cv2.VideoCapture(index)
    holds, cursor = GestureHold(), Cursor()
    paused = False
    started = cv2.getTickCount()
    try:
        while not stopped():
            ok, frame = cap.read()
            if not ok:
                print("Sin cuadro de cámara")
                return 2
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            stamp_ms = int((cv2.getTickCount() - started) * 1000 / cv2.getTickFrequency())
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = recognizer.recognize_for_video(image, stamp_ms)
            name = None
            if result.gestures:
                name = result.gestures[0][0].category_name
            event = holds.update(name, stamp_ms / 1000)
            if event == "pausa":
                paused = not paused
            elif event == "confirmar":
                print(note_gesture(True))
            elif event == "cancelar":
                print(note_gesture(False))
            if control and not paused and result.hand_landmarks:
                tip = result.hand_landmarks[0][8]
                point = cursor.update(1 - tip.x, tip.y)
                if point:
                    print(mano_a_puntero(True, point))
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        recognizer.close()
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Gestos locales. No graba.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--controlar", action="store_true")
    parser.add_argument("--avisar", action="store_true")
    parser.add_argument("--camara", type=int, default=0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.dry_run:
        if args.file is None:
            print("Falta --file")
            return 2
        return dry_run(args.file)
    if args.controlar:
        from agent_executor import release_lock, take_lock
        code = take_lock("gestos", 10)
        if code != 0:
            return code
        try:
            return camera_loop(args.camara, True)
        finally:
            release_lock("gestos")
    if args.avisar:
        return camera_loop(args.camara, False)
    print("Usa --avisar para confirmar con la mano, o --dry-run --file. --controlar pide el turno y no mueve el mouse.")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
