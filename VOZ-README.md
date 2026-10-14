# Voz con Jarvis

## 1. Notas de voz en Telegram (ya existe en el servidor)
- Le mandas una nota de voz al bot. Jarvis la transcribe y te devuelve el texto como "Dictado #N".
- Las preguntas ("qué", "cómo", "cuánto"...) se contestan solas, en solo lectura, con texto y nota de voz (sendVoice).
- Las acciones nunca se hacen por voz: revisas el texto y escribes `/dictado N`. `/confirmar`, `/aprobar` y `/enviar` siempre se escriben.
- Variables en Render (Environment): `LOCAL_VOICE_ENABLED=true`, `LOCAL_VOICE_AUTO_REPLY=true` (Whisper local, sin API de pago; ojo con los 512 MB del plan gratis), o bien `STT_AGENT_URL` + `STT_AGENT_API_KEY` y `TTS_AGENT_URL` + `TTS_AGENT_API_KEY` para un servicio externo.

## 2. Conversación en tiempo real en la Mac (`desktop/voz_loop.py`)
Micrófono → detector de voz (webrtcvad) → transcripción local (faster-whisper) → Jarvis por `POST /api/encargo` → voz (Piper, o `say` de macOS).
Si hablas mientras Jarvis habla, se calla (barge-in). La respuesta completa te llega por Telegram.

Rechaza sin enviar nada: lo que empiece con `/`, lo que diga confirmar/aprobar, y cualquier número de 4 a 8 cifras o "código/clave/pin".

Instalación (MacBook Pro 2015, Monterey, Python 3.9):
```bash
pip3 install faster-whisper webrtcvad sounddevice numpy requests
export JARVIS_URL=https://jarvis-agents.onrender.com
export JARVIS_ENCARGO_SECRET=...   # el mismo valor que en Render; nunca en Git
python3 desktop/voz_loop.py
```
Opcional: `PIPER_MODEL=/ruta/es_MX-claude-high.onnx` (si tienes `piper`), `WHISPER_SIZE=tiny` si va lento, `JARVIS_SAY_VOICE=Paulina`.
Requiere que `/api/encargo` esté desplegado y `JARVIS_ENCARGO_SECRET` puesto en Render.

## 3. Autopublicación en tus redes (apagada por defecto)
Con `AUTO_PUBLISH_OWN_SOCIAL=true` en Render, Jarvis publica solo SUS videos y posts en TUS cuentas, sin /confirmarred, con tope diario compartido `AUTO_PUBLISH_MAX_DAY` (6) y aviso por Telegram con el enlace. `/brain off` lo detiene. Nunca DMs, comentarios a terceros, anuncios ni boosts.
- Facebook/Instagram: `META_PAGE_ID`, `META_INSTAGRAM_ACCOUNT_ID`, `META_PAGE_ACCESS_TOKEN`, `SOCIAL_PUBLISH_ENABLED=true`.
- YouTube: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`, `YOUTUBE_CHANNEL_ID`. Si la app de Google no está verificada, los videos quedan privados.
- TikTok: `TIKTOK_ACCESS_TOKEN` (o `TIKTOK_CLIENT_KEY` + `TIKTOK_CLIENT_SECRET` + `TIKTOK_REFRESH_TOKEN`). Sin auditoría de TikTok solo se puede publicar en privado (`SELF_ONLY`); después de la auditoría, `TIKTOK_PRIVACY=PUBLIC_TO_EVERYONE`.
Pagos (/aprobar + /confirmar, $100/$300) y mensajes a clientes (/enviar) siguen igual.
