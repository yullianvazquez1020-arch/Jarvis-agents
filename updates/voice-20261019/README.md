# Voz continua — panel-unico del dueño

Base revisada: ZIP `jarvis-voz-actual.zip`, rama local `panel-unico`, último commit declarado `c750dd1`. El paquete se aplica únicamente si las huellas de los archivos coinciden con los recibidos. No sustituye la rama ni importa el display antiguo de main.

## Comportamiento

- Captura continua con el mismo dispositivo y AudioContext en modo conversación. Se separan frases de 350 ms de silencio; cada una pasa por Whisper local. Una transcripción activa y hasta dos frases pendientes; la cola llena pide repetir la última frase. En modo de una sola intervención se cierra la captura después de la frase.
- Si el modelo está procesando, una nueva instrucción espera y se envía una sola vez después de terminar la respuesta anterior. Hasta dos instrucciones pendientes; apagar el micrófono descarta las pendientes.
- Durante el audio se exige «Jarvis» para interrumpir, incluso dentro del seguimiento de 40 segundos. Se filtran transcripciones contenidas en la propia respuesta. Se detiene la salida anterior y se ignora su audio tardío. Cancelar marca el turno local como cancelado; no revierte solicitudes que ya llegaron al servidor ni garantiza detener su consumo.
- La cancelación de eco del navegador sigue activa. El filtrado de texto es una protección adicional, no una identificación biométrica del hablante. Debe comprobarse con el micrófono y volumen reales; el tiempo de reconocimiento de Whisper limita cuándo puede actuar una interrupción.
- El seguimiento se renueva al terminar la reproducción en el navegador; la salida nativa usa su duración estimada. «Jarvis» solo abre la ventana de seguimiento y no envía una consulta vacía al modelo.
- Se conserva la optimización `-ac` y los hilos configurados por Claude. El instalador pone `VOICE_STT_LANGUAGE=auto` y `JARVIS_REPLY_LANGUAGE=auto`; conserva los demás ajustes.
- Voz por idioma del texto, con vocabulario de respuestas cortas ampliado y último idioma como desempate en el mismo proceso. No entrena un modelo ni implica adaptación biométrica.
- Incluye la corrección revisada de PR167 para «Jarvis. Hazme un documento…». Guarda DOCX/Markdown y revisiones mediante la función existente.
- Se conserva el arranque actual y su música breve, sin reactivar la música de fondo que el dueño revirtió. Una interrupción válida también puede detener la introducción nativa.

## Instalación

Después de obtener el commit revisado mediante git fetch, guardar `scripts/install_voice_continuity.py` desde ese mismo commit y ejecutarlo con `--commit SHA_COMPLETO`. `--check` comprueba compatibilidad sin instalar. La instalación respalda los archivos y la configuración con permisos privados, aplica el parche validado, actualiza las huellas y reinicia el servicio. Si falla una escritura o el reinicio, restaura los archivos anteriores. Rechaza archivos cambiados o rutas simbólicas en lugar de sobrescribir trabajo nuevo.

Pruebas del paquete instalado:

```
python3 scripts/check_voice_session.py
node scripts/check_voice_continuity.cjs
```

Se probaron también la instalación sobre la copia exacta recibida, el respaldo, la repetición sin cambios y el rechazo de archivos modificados. Las pruebas automáticas usan audio/transcripciones simuladas; la aceptación final de reconocimiento, eco y latencia requiere la Mac del dueño.
