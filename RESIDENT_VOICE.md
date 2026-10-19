# Medir antes de activar Whisper residente

Los ocho turnos recibidos del dueño el 19 de octubre muestran reconocimiento entre 6,7 y 8,3 s; consulta al servidor entre 3,8 y 6,3 s; síntesis inicial entre 0,26 y 0,32 s. La etiqueta existente `llm_first_token_ms` mide la llamada HTTP completa al servidor, no un primer token de streaming. Esta fase aborda el reconocimiento; no elimina el tiempo de la IA ni certifica interrupción por voz.

`desktop/audio/resident.py` mantiene el mismo modelo multilingüe cargado en un `whisper-server` privado. Usa exclusivamente 127.0.0.1, puerto y prefijo aleatorios, WAV validado, sin conversión ffmpeg ni modelos descargados. No usa proxies ni sigue redirecciones. El servidor recibe muestras en memoria y su salida no se registra. Un supervisor con tubería de propiedad detiene el modelo si desaparece el panel. Las solicitudes se serializan. Si falla el residente en uso normal, el motor CLI anterior sirve de respaldo y la respuesta declara ese motor.

El protocolo fue revisado en el código oficial `ggml-org/whisper.cpp`, `examples/server/server.cpp` y su README: `/health`, `/inference`, multipart `file`, `language`, `audio_ctx`, `best_of`, `beam_size`, `response_format=json`. Se usa `language=auto` para cada frase y se descarta un tono sintético inicial en español para preparar el contexto del encoder. El código oficial hace detección de idioma antes de establecer el contexto de audio de la solicitud; el proceso residente evita partir de un estado nuevo en cada frase. La mejora real depende del binario, modelo y CPU de la Mac y se mide allí.

## Prueba en la Mac

Guardar `scripts/qualify_resident_voice.py` desde el commit revisado y ejecutarlo con `--commit SHA --build-existing --apply`. Busca el binario hermano del CLI; si falta y hay un build de whisper.cpp ya configurado junto al modelo, compila únicamente el target `whisper-server`. No descarga código ni modelos. Si ese target o el protocolo no están disponibles, termina sin activar el residente.

La prueba pausa el panel, genera dos frases públicas fijas con Juan y Daniel y compara cuatro reconocimientos por motor, alternando ambos idiomas. Mantiene el mismo modelo, hilos y parámetros rápidos. Solo aplica si todas las muestras residentes alcanzan 90 % de exactitud de palabras, cada una tarda menos de 5 s y la mediana mejora al menos 25 %. La carga inicial del servidor se informa como preparación y no cuenta como latencia caliente. El reconocimiento con voces generadas no certifica la precisión con voz real.

La aplicación comprueba las huellas de los motores enviados por el dueño, añade un enlace al adaptador, respalda configuración/código/huellas y cambia solo backend, ruta del servidor e idioma STT automático. No cambia el display, la captura por turnos recuperada, la voz de salida ni el modelo. Si no califica, conserva la configuración. Si falla el reinicio después de aplicar, restaura los archivos anteriores y vuelve a intentar arrancar el servicio anterior.

Después del reinicio puede haber una primera espera mientras carga el modelo. Medir al menos dos turnos reales posteriores en `~/.jarvis-desktop/latencia.log`. La consulta a la IA es una etapa independiente y sigue pendiente de optimización.

## Validación

Pruebas con servidor local simulado comprueban protocolo multipart, reutilización del proceso, cierre por la tubería del dueño, rechazo de WAV inválido, silencio sin cargar modelo, respaldo CLI, aislamiento de proxies y los criterios que impiden activar una opción lenta o imprecisa. No se presentan esas pruebas como inferencia real de Whisper. La validación de voz y rendimiento reales solo puede completarse en la Mac del dueño.
