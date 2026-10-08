# Conversación por voz local

Para conservar el historial tras un despliegue se necesita almacenamiento permanente, como el Upstash ya configurado en producción. El almacenamiento local efímero de Render se pierde al desplegar.

Requiere `LOCAL_VOICE_ENABLED=true`. Con `LOCAL_VOICE_AUTO_REPLY=true`, los saludos y preguntas reconocidos reciben una respuesta escrita y hablada sin escribir `/dictado ID`.

Las respuestas automáticas usan únicamente las herramientas de consulta existentes. No pueden cambiar registros, preparar o enviar acciones ni aprobarlas. Si la nota pide una acción, sigue pendiente: revisa la transcripción y procesa su número con `/dictado ID`. Las preguntas que incluyan una acción también se contestan en solo lectura. Una nota no reconocida como pregunta conserva el flujo manual.

La transcripción usa faster-whisper tiny en CPU, vocabulario orientativo para Jarvis, Yullian Vázquez, ISLAFIX PRO LLC y Puerto Rico, y búsqueda de tres candidatos. Esto ayuda al reconocimiento; no garantiza nombres correctos. No se sustituyen nombres automáticamente. Revisa cantidades y nombres antes de procesar acciones.

El historial breve existente guarda hasta 40 mensajes compartidos. Después de un reinicio, cada sesión recupera como máximo diez turnos completos propios, sin herramientas ni solicitudes incompletas. Nunca vuelve a ejecutar acciones del historial. Los textos se limitan a 2.000 caracteres por mensaje y se filtran secretos conocidos. No es una memoria ilimitada. La protección cifrada depende de configurar `DATA_ENCRYPTION_KEY`; sin ella el historial se guarda en claro.

Whisper y Piper siguen siendo locales. No hay fallback a OpenAI ni a TTS externo. Las respuestas de conversación siguen usando el proveedor de IA ya configurado y pueden consumir sus tokens. Estas mejoras no hacen gratuita toda la aplicación.

Para volver al flujo manual, establece `LOCAL_VOICE_AUTO_REPLY=false`. No cambies los límites financieros ni la configuración de aprobaciones.
