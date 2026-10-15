# Desktop fluency and English conversation

Based on main `4f8bc395cd87412bfb2812c711c92f84a6f68287` and the mouse bridge work in PR #137 (`9d5b9c050985dc091270be44f0fe7ed831f47b3c`). Existing routes, commands, gestures, business modules and financial approval rules are retained.

## Changes

- Core canvas supports device pixel ratios up to 2 rather than 1.5. WebGL retains automatic downscaling on slow hardware and can recover quality at a normal 60 Hz refresh rate. This improves rendering detail; it does not change the monitor's physical resolution.
- Ring angles integrate elapsed time, avoiding jumps when voice intensity changes. Parallax is independent of frame rate, long frames are capped, and hidden views skip drawing. WebGL initialization/context loss exposes the existing 2D fallback.
- Decorative reactor readouts are explicitly labelled VISUAL; they are not machine telemetry.
- Local speech defaults to 170 words per minute instead of 180. Existing speed controls and `JARVIS_VOZ_RATE` remain. English output is the default; `JARVIS_REPLY_LANGUAGE=auto` preserves automatic bilingual voice sessions, and explicit overrides remain supported.
- English interface labels and local voice controls accompany the original Spanish commands. Whisper input uses multilingual auto detection by default (`VOICE_STT_LANGUAGE` can override it). Business records are not rewritten or translated in storage.
- Conversation mode is on by default for this requested setup and remembers an explicit off choice. It resumes only when the active turn and its audio finish. Pending permission requests cannot create duplicate microphone streams, and late grants after Stop, Escape, microphone-off or window ownership loss are released.
- Browser permission/autoplay requirements still apply. An initial grant or gesture may be required by Safari. This does not silently enable operating-system permissions or install a recognition model.
- PR #137 connects panel orders to the already running LaunchAgent, using a fresh heartbeat, with session-based execution still supported. Queue append and batch rotation now share a file lock to prevent lost orders.
- Mouse coordinates follow the foreground window's monitor, including monitors left of the main display. Quartz motion is interpolated across 12 steps, checks STOP and emergency corners, and verifies arrival before clicking. The foreground application is rechecked during motion. No new per-move approval is added.
- Startup diagnostics check the actual agent Python and Accessibility state. A previous successful movement cannot be mistaken for the current diagnostic result.

## Operation on the Mac

After integrating this branch into the local checkout, use the existing setup/service commands. `python3 scripts/mac_setup.py --launch` prepares the existing pointer environment, loads its LaunchAgent and opens the panel. Do not discard a dirty local checkout to update it.

The microphone needs an installed STT engine, and the mouse needs macOS Accessibility permission for the agent's actual Python. The mouse bridge does not activate itself on a computer where the owner has not installed/enabled the agent. STOP remains effective. A new browser tab cannot take ownership of audio while another tab owns it.

## Validation and boundaries

Regression coverage includes long spoken replies, late microphone grants, duplicate permission requests, microphone-off, audio ownership transfer, English/Spanish local commands, secondary-monitor coordinates, arrival failure, STOP before and during movement, foreground changes and malformed mouse requests.

The full project validator uses real pinned Python dependencies and Redis. Browser controller tests use fake media devices; mouse tests use fake Quartz. These are not physical tests of the owner's Mac, installed voices, microphone, camera or monitor performance. Chromium rendering inspection could not run in this environment because the browser binary download failed. No claim of a physical Mac installation or production deployment is made.
