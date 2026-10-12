# Conector supervisado de Safari

Jarvis propone un paso concreto sobre los controles visibles de una ventana dedicada. El conector local muestra la página, elemento y texto, pide un código de un uso y ejecuta ese paso. Puede hacer clic y rellenar campos de texto. Es una sesión supervisada: no trabaja solo en segundo plano.

## Preparación en la Mac

Requiere Python 3.9 o posterior y el emparejamiento del panel con Jarvis ya hecho. El token se reutiliza desde `~/.jarvis-desktop/device.json`; no lo copies al chat. El servidor debe tener `DESKTOP_API_ENABLED=true`.

En Safari, habilita las funciones para desarrolladores y **Permitir JavaScript desde eventos de Apple**. Dependiendo de tu versión aparece en Desarrollo o en los ajustes de Desarrollador. macOS también puede pedir que Terminal controle Safari: autorízalo en la Mac. El conector no cambia estos permisos automáticamente.

Desde tu repositorio actualizado:

```bash
cd "$HOME/Jarvis-agents"
git pull --ff-only
python3 scripts/browser_mac.py --url https://gumroad.com
```

Se abre una ventana dedicada con una pestaña. Puedes iniciar sesión personalmente en esa ventana antes de pedirle el siguiente paso. No se capturan ni escriben contraseñas. Mantén una sola pestaña en la ventana dedicada y conserva la Terminal abierta.

Escribe una petición corta, por ejemplo «abre el editor de productos». Jarvis recibe URL, título y etiquetas de hasta 80 controles, y propone una acción. Revisa Safari y el texto mostrado: un clic puede publicar o enviar, y escribir en un campo puede guardar automáticamente. Solo escribe el código si apruebas esa acción exacta. Enter cancela. La confirmación vence en 90 segundos.

`/ver` muestra los controles localmente sin llamar al modelo. `/salir` termina el conector y deja Safari abierto. El archivo `~/.jarvis-control/STOP` bloquea pasos nuevos. Si la página cambia durante la revisión, solicita una propuesta nueva. Un error o timeout no se reintenta automáticamente: comprueba el resultado en Safari antes de repetir.

## Alcance y estado

- El servidor solo propone texto JSON, sin herramientas para ejecutar acciones ni acceso a libros/clientes. Cada propuesta usa el presupuesto de especialistas existente. No se guarda el contenido de la página en el historial de Jarvis.
- Las etiquetas de controles de una cuenta pueden contener datos privados. Al pedir un paso autorizas compartir esa vista limitada con el proveedor de IA configurado. No se envían valores de campos, cookies ni el contenido completo de la página.
- El token de dispositivo viaja solo al servidor Jarvis mediante HTTPS. No se añade al navegador.
- Se bloquean campos de contraseña, archivos y códigos; bancos, pasarelas y páginas de pagos quedan fuera del control. Configura PayPal y pagos personalmente.
- Safari comparte el perfil de navegación del usuario; no es un aislamiento de seguridad. Otro programa bajo el mismo usuario de macOS podría controlar Safari si recibe los mismos permisos.
- Sitios con iframes, shadow DOM o que exijan eventos de teclado/clic de hardware pueden no funcionar. No se promete compatibilidad con Fiverr/Gumroad hasta probar sus flujos reales. Una acción ejecutada no demuestra publicación exitosa: verifica el resultado visible.
- Las pruebas automatizadas cubren validación, emparejamiento, caducidad, cambios de página, cancelación y ausencia de reintentos. El permiso de Apple Events, inicio de sesión y funcionamiento real en Safari requieren validación en la Mac; no se han confirmado desde el entorno Linux.

Referencia de Apple: https://developer.apple.com/documentation/safari-developer-tools/developer-settings
