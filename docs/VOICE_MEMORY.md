# Memoria de voz en Render

El 8 de octubre de 2026 Render confirmó `oomKilled` con límite de 512 MiB durante una respuesta de voz. Whisper registró picos de 265–285 MB; Piper llegó a 241 MB en otra respuesta. Son picos de hijos distintos, no una medición del total del contenedor ni prueba de concurrencia.

Se mantiene `LOCAL_VOICE_AUTO_REPLY=false` y `WHISPER_BEAM=1`. El dictado local sigue disponible; `/dictado ID` procesa el texto revisado con los controles existentes. No se activan APIs de pago ni se cambia el plan del servidor.

Las respuestas habladas se limitan a 200 caracteres y se etiquetan como parciales cuando corresponde. El texto completo se envía primero; una falla de síntesis nunca repite acciones.

Los procesos de Whisper, Piper y conversión consultan el cgroup Linux y estiman su conjunto de trabajo: uso total menos caché inactiva de archivos limpia. No se descuenta caché activa, memoria anónima ni contadores inconsistentes. Sin contadores válidos se mantiene el uso total. No inician con menos de 96 MiB disponibles estimados; durante ejecución se revisa cada 100 ms y se detiene el hijo al quedar menos de 64 MiB. Las tuberías se drenan y el proceso se recoge antes de liberar el candado compartido. No modifica el límite de memoria ni permisos.

El dueño autorizó posteriormente activar `LOCAL_VOICE_AUTO_REPLY=true`, conservando `WHISPER_BEAM=1`. La prueba de las 01:17 PR transcribió con pico de 279 MB y respondió en texto, pero no entregó audio. No hay un evento nuevo de OOM en esa prueba; el log genérico `ValueError` no acredita la causa. Ahora se registran etapas constantes (síntesis, Opus, Telegram) y errores específicos de la protección de memoria, sin serializar mensajes privados de excepciones. La misma respuesta se sintetizó y convirtió realmente en local, con pico de Piper de 201 MB. La corrección de caché evita rechazos conservadores indebidos; no se afirma que el caso de Render ya esté resuelto hasta probarlo allí.

Referencia del cálculo de conjunto de trabajo: https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/ y contadores del kernel: https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html .

Es una protección por muestreo, no una garantía frente a una asignación instantánea. Sin cgroup legible o con límite ilimitado, no inventa mediciones ni rechaza por un límite ficticio. La prueba real debe comprobar dictado, audio corto, `peak_memory_mb`, salud del servicio y eventos de Render antes de reactivar preguntas automáticas. El contenido de videos conserva sus límites existentes; solo cambia la vigilancia del proceso de síntesis.
