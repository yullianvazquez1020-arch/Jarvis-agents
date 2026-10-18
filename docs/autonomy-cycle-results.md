# Resultados del ciclo autónomo

El interruptor BRAIN_ENABLED indica configuración, no trabajo terminado.
El panel Estado, autonomy_status y /brain estado muestran el último intento y su resultado.

- running: se inició la consulta, sin respuesta confirmada todavía.
- response_delivered: la ruta de chat respondió y Telegram aceptó el envío. Esto no demuestra que los entregables o publicaciones se hayan completado.
- failed: la consulta o la entrega falló. El contador diario conserva el intento para limitar costos.
- interrupted: el proceso canceló un ciclo. Se deben revisar sus efectos antes de repetir acciones.
- not_run: todavía no hay intento registrado.

Se conserva el último envío exitoso aunque un intento posterior falle o se reinicie el proceso. Solo se guardan fecha, estado y error redactado, nunca el contenido del reporte. Los errores internos ya no se convierten en éxitos del ciclo. La conversación normal conserva sus respuestas de error habituales. Una respuesta fija que bloquea el ciclo también se registra como fallo.

El ciclo conserva el límite diario, el interruptor del dueño y los permisos de cada herramienta. No se activan conexiones, publicaciones ni movimientos de dinero. La respuesta fija de autonomía describe las capacidades actuales en vez de negar todo trabajo autónomo.

Validación local: pruebas de IA apagada, error de modelo, fallo de Telegram, falta de respuesta, reinicio, caché inválida y diagnóstico sin escrituras. Las integraciones reales y la Mac requieren comprobación en sus entornos.
