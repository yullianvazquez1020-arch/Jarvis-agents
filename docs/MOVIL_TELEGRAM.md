# Fotos, clips, voz y avisos

Parche aditivo. Conserva versión, cifrado, aprobaciones, $100 por operación y $300 diarios.

## Uso

- `/movil`: configuración real (no prueba las credenciales de proveedores).
- `/movil prueba`: ida y vuelta de texto, sin IA. No prueba sonido ni pantalla bloqueada.
- Con `TELEGRAM_MEDIA_ENABLED=true`, enviar una foto con una pregunta produce un análisis visual.
- Para preparar un gasto se debe añadir `/recibo` como pie de la foto. El gasto sigue sujeto a aprobación.
- Clips MP4/MOV: máximo 5 MB; los videos declarados de más de 60 segundos se rechazan.
  Se extraen hasta cuatro cuadros de los primeros 60 segundos. No se transcribe su audio,
  ni se garantiza detectar todo lo sucedido entre cuadros. Archivos enviados como documentos
  carecen de duración fiable: el decodificador limita la lectura a los primeros 60 segundos.
- El análisis utiliza el cliente visual Claude existente, puede consumir su API, no lleva
  herramientas ni historial personal y no guarda los bytes en kv. Temporales eliminados al terminar.
  No se envían imágenes a Venice. No enviar imágenes con claves: quitar metadatos no elimina
  secretos visibles en los píxeles. La cola existente conserva los identificadores de Telegram.

## Voz y avisos

`LOCAL_VOICE_ENABLED=true` habilita el transcriptor y sintetizador locales existentes;
`LOCAL_VOICE_AUTO_REPLY=true` permite contestar preguntas de voz en modo de solo lectura.
No permite aprobar pagos mediante dictado. Los modelos públicos se descargan al primer uso.
`TELEGRAM_NOTICE_VOICE=true` añade voz local a recordatorios, resumen diario y avisos entrantes.
El audio se intenta después de confirmar/registrar la entrega de texto; un fallo de voz no
vuelve a ejecutar el evento. La memoria, duración y concurrencia siguen limitadas.

El teléfono recibe una nota de audio, no una llamada ni reproducción forzada. La recepción de
notificaciones y su sonido dependen de permisos, modo silencio y configuración del teléfono.
La Mac no necesita estar encendida para Telegram en Render; las manos y la voz del escritorio son locales.

## Conexiones externas pendientes

Los mensajes de otras aplicaciones no se leen por instalar este parche. El endpoint autenticado
`/integrations/incoming` existente admite eventos de conectores autorizados, pero configurar
Twilio para SMS/WhatsApp y un conector de correo requiere cuentas y credenciales del dueño.
Resend es envío de correo: no equivale a leer Gmail. No se habilita el envío automático a clientes.

## Validación y reversión

Pruebas sintéticas: aislamiento de herramientas/historial, propietario privado, secretos en pie,
límites, errores sin datos, normalización de imágenes y decodificación real de un clip corto.
Validación completa en CI antes de desplegar. Prueba en teléfono pendiente hasta confirmar
recepción real de imagen, video, nota y aviso; no inferirla de una prueba unitaria.
Para desactivar solo lo nuevo: `TELEGRAM_MEDIA_ENABLED=false`, `TELEGRAM_NOTICE_VOICE=false`.
Para apagar voz: `LOCAL_VOICE_ENABLED=false`. No cambiar claves ni borrar datos.
