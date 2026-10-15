"""Latencia por etapa de cada turno de voz -> ~/.jarvis-desktop/latencia.log (una línea JSON por turno).

Etapas: vad_ms (silencio de fin de frase), stt_ms, llm_first_token_ms, tts_first_audio_ms, total_ms.
Solo números y el id del turno; nunca texto, audio ni datos personales.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

VAD_SILENCE_MS = 350          # igual que desktop/ui/app.js (Detector silenceMs)


def log_path() -> Path:
    return Path(os.getenv("JARVIS_LATENCIA_LOG") or (Path.home() / ".jarvis-desktop" / "latencia.log"))


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def write(turn: str, stages: dict) -> dict:
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "turn": str(turn)[:64]}
    for k, v in stages.items():
        if isinstance(v, (int, float)):
            rec[k] = round(float(v), 1)
    keys = ("vad_ms", "stt_ms", "llm_first_token_ms", "tts_first_audio_ms")
    rec["complete_voice_turn"] = all(k in rec for k in keys)
    rec["total_ms"] = round(sum(rec.get(k, 0.0) for k in keys), 1)
    try:
        p = log_path(); p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass
    return rec
