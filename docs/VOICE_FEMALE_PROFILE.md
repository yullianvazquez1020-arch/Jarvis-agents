# JARVIS Command Center / GOD'S EYE - macOS voice profile (opt-in)

This change adds a **configuration-only local female voice option** to the existing JARVIS desktop speech modules. It does not replace the voice pipeline, activate paid APIs, enable wake-word recognition, deploy services, or change permissions.

## Existing behavior retained
- Legacy defaults remain male (Juan for Spanish, Daniel for English where installed).
- Existing local STT (whisper.cpp/Whisper resident) and macOS `say` remain in place.
- Bar﻿ge-in, device pairing, read-only voice scopes, and manual approvals remain unchanged.
- The GOD'S EYE module is **not verified in this repository**; its application-specific voice commands require a separately confirmed source/location.

## Enable a female voice locally (Mac only)

Edit `~/.jarvis-desktop/config.env` after testing the available system voices:

```ini
JARVIS_VOICE_STYLE=female
VOICE_TTS_BACKEND=auto
VOICE_TTS_VOICE=auto-latino
JARVIS_VOZ_ES=Paulina
JARVIS_VOZ_EN=Serena
JARVIS_VOZ_RATE=160
```

Check installed voices using `say -v '?'`. Install a Spanish and English voice through macOS accessibility/spoken content settings as necessary. The selected voice must exist on the Mac.

To return to the original behavior: set `JARVIS_VOICE_STYLE=male` and remove any explicit `JARVIS_VOZ_ES` / `JARVIS_VOZ_EN` overrides.

**Scope:** this only changes desktop synthesis. The standalone `desktop/voz_loop.py` reads the corresponding environment variables; provide the same values when launching it if you use that path. The separate Telegram/Render voice system is not changed.

## Validation and rollout

1. Run `python3 -m unittest discover -s tests -p 'test_female_voice_profile.py'`.
2. Run existing desktop/voice regressions, notably `test_idioma_unico.py`, `test_interrumpir.py`, and `test_resident_voice.py`.
3. Check speech with real Spanish/English phrases on the actual Mac, including interruptions and playback stop.
4. Measure latency and memory before choosing an always-on mode.
5. Keep `VOICE_WAKE_WORD_ENABLED=false` until a wake-word engine is independently tested.
6. Keep cloud providers disabled until credentials, billing and consent are configured securely.
7. Never enable paid services or production deployment through this change.

## Future optional providers (not implemented)

- ElevenLabs for expressive cloud TTS; requires API key kept server-side, budget cap, consent and privacy review.
- OpenAI voice realtime for full-duplex conversation; use a separate explicit paid-session toggle.
- Local Piper voices as offline fallback if compatible voice packages are installed.

Require a provider abstraction, cancellation support, an offline fallback, and an explicit display of connection state before shipping.
