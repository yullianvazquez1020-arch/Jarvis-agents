# Jarvis 4.1.0 + Fase A (revisada): listo para deploy

Base: GitHub `main` en `40b911c` (4.1.0; ese commit solo cambió los videos). Encima va el paquete `jarvis-main-corregido.zip`, sin tocar, y luego 5 correcciones aditivas, cada una en su propio commit.
`VERSION` sigue en `4.1.0`, como decidiste.
**No se subió a GitHub ni se desplegó. El trading real sigue apagado.**

## Qué estaba bien (se conserva)

- Los ganchos no tocan el money gate. Se mantienen $100/$300, el código de un uso, `/confirmar` fuera de la cola y la IA sin herramientas de dinero.
- `/fase-a` exige la llave maestra por cabecera.
- La llamada ya no inventa un borrador. No hay envío automático de Twilio ni cliente de Grok (`XAI_API_KEY` no se lee en ningún archivo).
- El sellado usa AES-256-GCM con *nonce* aleatorio y AAD. La cola, el líder, el gate y el modo cripto **no** se sellan.
- El historial se filtra con el secret guard y se limita a 40 entradas.
- El techo del perfil se revisa en `/aprobar` y en `/confirmar`.
- `.env.example` va vacío, sin secretos.

## Qué estaba mal (comprobado ejecutando el ZIP) y cómo quedó

| # | Problema | Efecto real | Corrección |
|---|---|---|---|
| A1 | `jarvis_transit` trataba como «no HTTPS» cualquier petición sin `X-Forwarded-Proto`, y filtraba `/health` por host | El chequeo de salud de Render llega por HTTP: con un health check configurado, Render **cancela el deploy** a los 15 minutos o reinicia el servicio cada 60 s. Rompía 73 de las 493 pruebas. | Solo rechaza lo que el proxy marca como `http`. GET y HEAD de `/health` y `/` nunca se filtran por host. Ahora es middleware ASGI puro, así las tareas en segundo plano del webhook corren igual. |
| A2 | Si faltaba `jarvis_seal.py`, **toda** escritura fallaba | Jarvis no podía guardar nada, ni siquiera el gate. | Solo las llaves selladas pasan por el sello. |
| A2 | Sin `DATA_ENCRYPTION_KEY` el historial **no** se guardaba (decía «se guarda en claro») | Historial vacío sin aviso. | Ahora sí se guarda en claro. Con una llave mal puesta se rechaza, para no creer que está cifrado. Lo ya sellado nunca se pisa en claro. `kv_set_many` también sella. |
| A3 | El atajo respondía a cualquier mensaje con «cash», «flujo» o que empezara con «llamar» | «Anota 50 de cash para gasolina» recibía el texto genérico y **el gasto no se anotaba**. | Solo responde si todo el mensaje es esa pregunta. |
| A4 | El historial se guardaba dentro del bucle principal | 4 llamadas a Upstash por mensaje bloqueaban al resto de Jarvis, incluido el webhook. | Se guarda en un hilo aparte; si falla, el chat sigue. |
| A5 | Techo `0` dejaba pasar $100; un texto lanzaba excepción; `NaN` se ignoraba | Mensaje genérico «No pude hacerlo», o un techo que no protegía. | Una sola función para ambos pasos: solo baja, nunca pasa de $100, y ante un valor dañado bloquea con un mensaje claro. |

**Ningún gancho rompía el gate, así que no hizo falta quitar ninguno.**

## Voz local por Telegram (`jarvis_chat_voice.py`, revisado)

Se engancha en `voice_message` **solo si `STT_AGENT_URL` está vacía y `LOCAL_VOICE_ENABLED=true`**. Con la URL puesta, el camino de siempre no cambia. Viene **apagada**.

| Se mantuvo de tu versión | Se corrigió |
|---|---|
| faster-whisper `tiny`, CPU, int8, español | Se negaba a transcribir si `OPENAI_API_KEY` estaba puesta, aunque este camino nunca la usa |
| El dictado queda `pending`; no se llama a `_handle_tg` | Llamaba a un `ffmpeg` del sistema que Render no trae; ahora usa `imageio-ffmpeg`, como los videos |
| La respuesta hablada usa `jarvis_local_tts.local_narration` | Mandaba WAV a `sendVoice`, que espera OGG/Opus: la voz nunca habría salido. Ahora se convierte a Opus |
| Si falla la voz, el texto ya salió | No revisaba `/producirvideo`. Ahora comparte su candado: nunca corren a la vez |
| Ninguna API de pago | Los procesos hijos recibían todas las llaves de Jarvis; ahora no reciben ninguna |
| | Sin límite de duración: ahora hasta 60 s, revisado antes de descargar, con tiempo límite en cada paso |
| | Cargaba Piper en cada nota; la frase fija ahora se genera una vez y queda guardada |

**¿Cabe en 512 MB? Probablemente sí, pero justo, y no está medido.** faster-whisper no se pudo instalar aquí. Su documentación solo publica memoria del modelo `small` int8 (1,477 MB); `tiny` es unas 6 veces más pequeño. Whisper, Piper y el video nunca corren a la vez.

Cada transcripción deja `Local whisper ready: peak_memory_mb=…` en los logs de Render, para medirlo de verdad. La primera nota después de cada deploy descarga el modelo `tiny` (unos 75 MB) a `whisper_models/`.

**`faster-whisper==1.2.1` ya está en `requirements.txt`, porque lo aprobaste.** Render lo instala en el próximo deploy: más tiempo de build y disco, pero nada de RAM mientras la voz esté apagada. No pude comprobar aquí que pip resuelva sus dependencias junto a `onnxruntime==1.30.0`; revisa que el build de Render termine bien.

**Para prenderla:**
1. Pon `LOCAL_VOICE_ENABLED=true` en Render.
2. Manda una nota de menos de 20 segundos y mira en el log `peak_memory_mb`, y que el servicio no se reinicie.

## Revisión del repo (commit 40b911c): hallazgos

Cada hallazgo indica qué está implementado, qué se probó aquí y qué está desplegado. **Desplegado** = lo que está en `40b911c`. Lo de esta rama **no** está desplegado.

| # | Tema | Hallazgo (archivo y función) | Estado |
|---|---|---|---|
| 1 | Límites de dinero | `main.py`: `HARD_MAX_ORDER_USD=100` y `HARD_MAX_DAY_USD=300`; `_lower_only` solo permite bajarlos. Las variables `CRYPTO_PRACTICE_ONLY=true` y `COINBASE_TRADING_ENABLED=false` bloquean `_cb` y el envío real. El techo del perfil (A5) solo baja. | Bien. Implementado, probado, desplegado. |
| 2 | Voz de video | `jarvis_growth.video_narration`: con `VIDEO_TTS_PROVIDER=piper` (por defecto) usa `jarvis_local_tts.local_narration`, y si falla da error, sin respaldo. OpenAI solo se usa con `VIDEO_TTS_PROVIDER=openai` puesto a propósito; `TTS_AGENT_URL` solo con otro proveedor. | Bien. Desplegado. |
| 3 | Voz de Telegram | `jarvis_extensions.voice_message` exige `STT_AGENT_URL`; `audio_reply` (`/audio`) exige `TTS_AGENT_URL`. No se mezclan con los videos. En esta rama, `voice_message` usa la voz local si la URL está vacía y `LOCAL_VOICE_ENABLED=true`. `audio_reply` no cambió. | Rama: implementado y probado. No desplegado. |
| 4 | `/mejorarvideo` | `improve_video_plan` crea un plan nuevo (`revision_of`), con id y archivo propios; `validate_plan` no copia `youtube_id` ni el estado. **No pisa el video publicado.** Error menor: creaba la revisión aunque ya se estuviera produciendo otro video, y quedaba huérfana. | Corregido en Y2. |
| 5 | `/publicaryoutube` | `publish_youtube` atrapaba **cualquier** excepción con `except Exception … from None`. El `ValueError` de `_json_request` («El servicio respondió HTTP …»), una falla de red o un error de token terminaban en el mismo «Publicación sin confirmar», sin guardar ni registrar el motivo. | Corregido en Y1. |
| 6 | 512 MB | Ver la sección de voz local. En `40b911c` nada impedía que coincidieran con `/producirvideo`; en esta rama comparten candado. | Rama. |

**Plan 51:** su motivo real **no se puede recuperar**. El código desplegado no lo guardó ni lo escribió en el log. `/video 51` debería mostrar el estado `unknown_publish`, pero no lo pude verificar, porque no tengo acceso a Upstash.

La causa más probable, sin confirmar: Google restringe a privado los videos subidos por la API desde proyectos no verificados creados después del 28 de julio de 2020, hasta pasar una auditoría ([YouTube Data API: videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert)). Que tú pusieras el video 5 en público a mano en YouTube Studio es coherente con eso.

Con Y1 desplegado, el próximo intento guardará el código y el mensaje exactos de Google. No reintenté ni cambié nada en el plan 51.

## Variables (Render)

| Variable | Qué poner |
|---|---|
| `DATA_ENCRYPTION_KEY` | Opcional. Para sellar el historial y el perfil, genera una con `python3 -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"` y guárdala aparte, porque si la pierdes lo sellado no abre. Vacía = en claro. |
| `LOCAL_VOICE_ENABLED` | `false` (déjala así hasta probar la voz local). |
| `WHISPER_MODEL_DIR` | Opcional; vacía = `whisper_models/` junto al código. |
| `PUBLIC_HOST` | Opcional; mejor vacía por ahora. Si la pones, que sea **exactamente** `jarvis-agents.onrender.com`. Con otro valor, Telegram y `/chat` reciben 400. |

Todas las demás variables siguen igual.

## Archivos para el deploy

`main.py`, `jarvis_seal.py`, `jarvis_transit.py`, `jarvis_phase_a.py`, `jarvis_chat_voice.py`, `jarvis_extensions.py` (3 líneas), `jarvis_growth.py` (Y1, Y2), `requirements.txt`, `.gitignore` y `.env.example`, junto a los que ya están en GitHub: `jarvis_extensions.py`, `jarvis_growth.py`, `jarvis_connections.py`, `jarvis_desktop_api.py` y los demás. Esos no se tocaron, salvo el gancho de voz en `jarvis_extensions.py` y Y1/Y2 en `jarvis_growth.py`.

## Verificar después del deploy

1. `GET /health` → 200 y `version: 4.1.0`.
2. `/diagnostico` en Telegram muestra la línea `HTTPS/host: activo · Fase A: activa · sellado: …`.
3. Escribe `perfil` (respuesta local, sin tokens). Luego `anota 5 de cash de prueba`: debe anotarse. Bórralo después.
4. `/aprobar 0` y `/confirmar 0 CÓDIGO` (la práctica del gate) siguen funcionando.

## Volver atrás

En Render: *Rollback* al deploy anterior. Las llaves nuevas (`jarvis:history`, `jarvis:profile`) la versión anterior las ignora.

## Pruebas

**532 pruebas, 532 OK**: las 493 de GitHub `main`, 23 nuevas en `tests/test_fase_a.py`, 9 en `tests/test_chat_voice.py` y 7 en `tests/test_youtube_publish.py`. Estas últimas usan ffmpeg real y un faster-whisper falso que corre en un subproceso real. Incluye el arranque real en un subproceso (`test_deployment_http`).

En este entorno no hay PyPI. FastAPI, el SDK de Anthropic, python-dotenv e imageio-ffmpeg se reemplazaron por imitaciones mínimas solo para probar. Los módulos que faltaban en el ZIP se tomaron de GitHub `main`, solo para correr las pruebas. **No se probó contra Render, Upstash, Telegram ni Coinbase reales.**

## Verificación con dependencias reales (7 oct 2026)

Cotejado contra el árbol completo de GitHub `40b911c55621de4909ee6ab45833ca70b934d299`: el diff incluido reproduce exactamente el repo del ZIP, sin eliminaciones. Se instaló `pip install -r requirements.txt` en un entorno limpio Python 3.12; faster-whisper 1.2.1 y onnxruntime 1.30.0 se importan y `pip check` no detecta conflictos.

La primera ejecución tuvo 528 éxitos, 1 falla y 3 omisiones: `ChatVoice.test_status_and_diagnostics` asumía que faster-whisper no estaba instalado. Se corrigió únicamente esa prueba para simular de forma explícita ambos estados. Con Redis 7.0.15 local, la nueva ejecución pasó las 532 pruebas, sin omisiones, en 40.251 segundos. Python emitió al salir un ResourceWarning por un socket de pruebas; la suite terminó con código 0.

La transcripción de los tests sigue usando un Whisper simulado en un subproceso, con ffmpeg real. Esto no mide el modelo tiny real ni demuestra que cabe en los 512 MB de Render. La voz local permanece apagada por defecto; esta entrega es solo un PR, sin fusión, despliegue ni cambios de variables del servicio. La respuesta hablada de esta fase es un acuse fijo para revisar el dictado, no una conversación hablada completa.
