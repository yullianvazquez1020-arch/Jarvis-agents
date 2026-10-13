# British conversational voice

Set `JARVIS_REPLY_LANGUAGE=en-GB` for British English conversational responses and the local Telegram voice. Spanish input transcription remains available. Product and video scripts retain their selected language. The default without this variable remains Spanish.

Telegram uses Piper `en_GB-southern_english_female-low`, a 16 kHz voice. Source: https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_GB/southern_english_female/low . Dataset: OpenSLR 83 (http://www.openslr.org/83/), CC-BY-SA 4.0 International (https://creativecommons.org/licenses/by-sa/4.0/). Model and configuration downloads are SHA-256 pinned; model files are cached locally. It is a synthetic British voice, not the film actor's voice.

The cgroup memory guard still applies. If synthesis exceeds available memory, the written answer remains available; no paid speech provider is selected automatically. The British acknowledgement has a separate cache from the Spanish acknowledgement.

A Mac already running its own speech service has its own voice configuration: select an installed en_GB voice through `VOICE_TTS_VOICE` in the local config. Changing Render does not change that local file.
