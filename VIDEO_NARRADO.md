# Videos con narración y personajes originales

`/mejorarvideo ID` crea una revisión nueva y envía su MP4 a Telegram. El video original conserva su estado y enlace de YouTube. La revisión debe subirse explícitamente con `/subiryoutube NUEVO_ID` y publicarse explícitamente después de revisarla.

Para el cuento «Tres amigos de Puerto Rico: coquí, juey e iguana», la revisión contiene seis escenas originales de conteo y cooperación, con ilustraciones vectoriales de los animales, fondo tropical, nubes y movimiento suave. Es una animación 2D sencilla, no video 3D.

Narración: primero se usa TTS_AGENT_URL si está configurado. Si no hay adaptador y existe OPENAI_API_KEY, se usa el endpoint de voz oficial de OpenAI con gpt-4o-mini-tts y coral, español latinoamericano para planes es e inglés para planes en. VIDEO_TTS_PROVIDER=none permite desactivar este uso; VIDEO_TTS_VOICE permite cambiar la voz incorporada. No se necesitan nuevas credenciales para OpenAI.

Cada escena consume una petición de voz de pago y una reserva del límite diario compartido SPECIALIST_DAILY_CALL_LIMIT (30 por defecto). La revisión de seis escenas usa seis peticiones. Los errores no se convierten silenciosamente en un video sin voz. Se declara voz generada por IA en la vista previa y descripción del cuento.

Verificación: pruebas del esquema, conservación del original, solicitudes de voz y límites con proveedor simulado, rechazo de error de voz, y codificación real de MP4 H.264 + AAC con WAV sintético. La calidad de la voz real y el nuevo video se revisan en Telegram al ejecutarlo con las credenciales del servicio.

Corrección de compatibilidad: el MP3 también se admite cuando OpenAI devuelve application/octet-stream. Se exige firma MP3 para ese formato binario; JSON y archivos vacíos se rechazan. Los errores HTTP informan problemas de credenciales, permisos o cuota sin copiar el cuerpo del proveedor ni secretos. Prueba de regresión: MP3 real recibido como binario, procesado por video_narration y codificado a MP4 H.264 + AAC.
