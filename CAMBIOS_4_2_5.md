# Jarvis 4.2.5 — autocorrección

Aditivo, sobre `b406f9c`. Archivo nuevo `jarvis_selfcheck.py`, su carga protegida en `main.py` y `tests/test_selfcheck.py`.
Si el módulo no carga, Jarvis arranca igual y `/diagnostico` dice `Autocorrección: apagado (…)`.

## Qué hace

1. **Revisa cada respuesta antes de enviarla.** No usa un modelo extra.
   - Si la respuesta dice que Jarvis pagó, compró, transfirió, publicó, aprobó, ejecutó una orden o le escribió a un cliente, agrega una corrección: Jarvis no puede hacer eso, solo prepara.
   - Si da una cifra en dólares que no sale de tus mensajes, de las herramientas de la conversación ni de los topes, avisa que es estimada. Cuentan las sumas, las restas y el triple de un dato. No cuentan las cifras que Jarvis dijo antes por su cuenta.
2. **Aprende de tus correcciones.** Si escribes «te equivocaste», «eso está mal», «de ahora en adelante…» o «recuerda que…», la frase se guarda como lección y entra en las instrucciones de Jarvis en cada respuesta.
   - Se rechaza y no se guarda una lección que toque topes, aprobaciones, `/confirmar`, `/enviar`, «sin preguntarme», pagar, comprar, publicar, dinero real, modo real o claves.
   - Las claves se borran antes de guardar.
   - Solo se guardan desde tu chat completo. La voz y los canales de solo lectura no escriben lecciones.
   - Máximo 30 lecciones y 280 caracteres cada una. Entran las 12 más recientes.
3. **Comandos de tu chat privado:** `/lecciones` muestra las lecciones y cuántos avisos hubo. `/olvidar N` borra una.

## Qué no cambia

- Topes de $100 y $300, `/confirmar` fuera de la cola, sin autoenvío y sin autopublicación.
- Sin OpenAI, sin voz de pago y sin pagos reales. No se toca la clave de cifrado.
- `VERSION` sigue en 4.2.4. Subirla queda a criterio de quien integra.

## Pruebas

- `tests/test_selfcheck.py` añade 16 pruebas: 856 en total, 853 pasan.
- Las 3 que fallan ya fallaban antes del cambio y son del contenedor:
  - `test_real_audio_decoder_accepts_whisper_metadata_errors`: falta `faster_whisper`.
  - `test_boot_with_desktop_disabled` y `test_boot_with_desktop_enabled`: el subproceso no encuentra FastAPI.
- Se rompió el código a propósito (quitar el aviso de acciones, el de cifras o el candado de lecciones, y sacar las lecciones del prompt) y las pruebas lo detectaron.
- Sin probar en Render, con Upstash real ni con el modelo real.
