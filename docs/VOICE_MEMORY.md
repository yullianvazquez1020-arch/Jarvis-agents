# Memoria de voz en Render

El 8 de octubre de 2026 Render confirmó `oomKilled` con límite de 512 MiB durante una respuesta de voz. Whisper registró picos de 265–285 MB; Piper llegó a 241 MB en otra respuesta. Son picos de hijos distintos, no una medición del total del contenedor ni prueba de concurrencia.

Se mantiene `LOCAL_VOICE_AUTO_REPLY=false` y `WHISPER_BEAM=1`. El dictado local sigue disponible; `/dictado ID` procesa el texto revisado con los controles existentes. No se activan APIs de pago ni se cambia el plan del servidor.

Las respuestas habladas se limitan a 200 caracteres y se etiquetan como parciales cuando corresponde. El texto completo se envía primero; una falla de síntesis nunca repite acciones.

Los procesos de Whisper, Piper y conversión consultan el uso total del cgroup Linux. No inician con menos de 96 MiB libres; durante ejecución se revisa cada 100 ms y se detiene el hijo al quedar menos de 64 MiB. Las tuberías se drenan y el proceso se recoge antes de liberar el candado compartido. No modifica el límite de memoria ni permisos.

Es una protección por muestreo, no una garantía frente a una asignación instantánea. Sin cgroup legible o con límite ilimitado, no inventa mediciones ni rechaza por un límite ficticio. La prueba real debe comprobar dictado, audio corto, `peak_memory_mb`, salud del servicio y eventos de Render antes de reactivar preguntas automáticas. El contenido de videos conserva sus límites existentes; solo cambia la vigilancia del proceso de síntesis.
