# British conversational voice (JARVIS butler style)

Set `JARVIS_REPLY_LANGUAGE=en-GB` for British English replies and the British local voice. Without it, Jarvis stays in Spanish (default unchanged). Product and video scripts keep their own language.

## Voices (stock synthetic voices; no actor is cloned or imitated)

| Component | Default with `en-GB` | Override |
|---|---|---|
| Telegram / server (Piper, offline) | `en_GB-alan-medium` (British **male**, 22 kHz, ~63 MB) | `JARVIS_BRITISH_VOICE=alan` or `southern_english_female` (previous default) |
| Pace | `length_scale` 1.08 (measured, unhurried); Spanish stays 1.0 | `JARVIS_VOICE_PACE` (0.8–1.4) |
| Mac `desktop/voz_loop.py` (`say`) | `Daniel` (en_GB male); Spanish stays `Paulina` | `JARVIS_SAY_VOICE` |
| Mac with Piper | whatever `PIPER_MODEL` points to | use `en_GB-alan-medium.onnx` |

Source: https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_GB/alan/medium (licence: see its MODEL_CARD; dataset Mycroft mimic3 `apope`). Downloads are SHA-256 pinned and cached; first use downloads ~63 MB (under the 90 MB guard). The cached British acknowledgement was renamed (`respuesta-nota-british-alan-v2.ogg`) so the old female clip is not reused.

## Tone

With `en-GB`, the system prompt asks for a refined British AI-butler manner: measured, polite, unflappable, light dry understatement, "sir" used sparingly, never flippant about money, safety or clients.

## Spanish

An English voice reading Spanish mangles the words, so Spanish replies keep the Spanish Piper voice (`es_MX-ald-medium`, male). To keep the British character everywhere, use `en-GB` replies.

The cgroup memory guard still applies; if synthesis fails the written answer is still sent. No paid speech provider is used. A Mac with its own speech service has its own voice config; Render variables don't change it.
