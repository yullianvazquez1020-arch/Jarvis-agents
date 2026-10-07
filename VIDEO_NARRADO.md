# Narración local de Jarvis

La narración de video usa Piper por defecto (`VIDEO_TTS_PROVIDER=piper`). Genera los WAV en CPU, sin enviar el texto a OpenAI ni usar una API de inferencia. No hay precio por solicitud de voz. Render y las otras conexiones de IA que ya existan mantienen sus propios costos.

En el servicio existente se dejó OPENAI_API_KEY vacía, TTS_AGENT_URL vacía y VIDEO_TTS_PROVIDER=piper. Esto desactiva los análisis y revisiones de OpenAI. Los análisis pueden seguir usando la conexión de Claude existente; no se ha convertido toda la inteligencia de Jarvis a local. No se añadieron créditos, tarjetas ni servicios nuevos.

`/mejorarvideo 1` crea otra revisión de la historia y envía la vista previa. Conserva el video original y su enlace privado. Subir/publicar requiere los comandos explícitos anteriores.

Voz: es_ES-sharvard-medium, locutora F (speaker_id 1), español de España. No es la voz anterior ni se promete acento boricua. Modelo público descargado una vez por instancia y validado con SHA-256. Después, la síntesis usa los archivos locales. Las descargas pueden repetirse al reemplazar una instancia efímera.

Piper 1.3.0 (GPLv3) ejecuta un proceso aislado, con un hilo de CPU. Ese proceso termina antes de codificar el video. La prueba real de seis escenas alcanzó aproximadamente 276 MB de memoria. Fallar la voz local no activa una API de pago. La instalación actual solo admite planes en español.

Atribución del modelo/dataset: Piper sharvard, corpus Sharvard, University of Edinburgh, CC BY 3.0. https://datashare.ed.ac.uk/handle/10283/574 ; https://creativecommons.org/licenses/by/3.0/ ; modelo: https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_ES/sharvard/medium . Esta atribución se incluye en la descripción del cuento y en los metadatos MP4. La voz es sintética.

Verificación: rutas sin llamadas de pago, sin respaldo automático a OpenAI, descarga cacheada sin red, validación de textos e idioma, seis audios reales y video H.264 + AAC. La calidad se revisa en la vista previa antes de subir.

## Ilustración y movimiento revisados
El render local usa personajes originales con vientre, mejillas y ojos con brillo; parpadeos, saludo y saltos del coquí, patas y pinzas móviles del juey, y cola de la iguana. La playa tiene olas para los jueyes y el jardín flores para las iguanas. Hay entradas suaves y breves fundidos entre escenas, nubes y mariposa móvil. El título se ajusta al ancho disponible sin cortar palabras. Sigue siendo animación 2D vectorial a 960 × 540, 12 fps, sin proveedores de imágenes ni nuevas dependencias o llamadas pagadas.

La nueva vista previa se obtiene con `/mejorarvideo 5`; no cambia el video ya publicado. El identificador nuevo se recibe en Telegram y requiere su propio comando de subida tras revisar.
