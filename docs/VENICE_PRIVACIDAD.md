# Venice: límites y operación

Venice es un proveedor externo en https://api.venice.ai/api/v1. No es IA local.
Usarlo implica enviar los mensajes aprobados por los filtros a ese proveedor.
Solo debe usarse para información pública; no introducir datos de clientes, personales,
financieros ni secretos. La detección por patrones y coincidencia de claves conocidas
NO garantiza reconocer toda información privada. No se certifica ausencia absoluta de filtraciones.

## Habilitación

Apagado por defecto. Se requieren VENICE_ENABLED=1 y VENICE_API_KEY.
El chat directo requiere además DATA_ENCRYPTION_KEY válida y cifrado no pausado.
JARVIS_ROUTER_ENABLED controla el router general, no el comando directo.
Venice ya no es una alternativa predeterminada: incluirlo en JARVIS_API_ORDER requiere
una decisión explícita además de VENICE_ENABLED. No activar durante revisión.
No se genera, cambia ni muestra DATA_ENCRYPTION_KEY.

## Historial y recuperación

Los nuevos historiales van a jarvis:venice_history, con el cifrado, diagnóstico,
migración y recuperación existentes. Se incluyen en respaldo privado. Los respaldos
anteriores siguen siendo aceptados y no borran historiales nuevos.
El chat falla cerrado si el historial no abre, está en claro o falta la clave.
No manda perfiles del dueño, archivos, herramientas ni datos empresariales automáticamente.
Las respuestas con patrones sensibles se descartan, sin conservarlas en historial.

Los historiales antiguos jarvis:venice:<hash> NO se envían ni migran automáticamente.
La sesión queda bloqueada hasta /venice reset, que vacía su historial antiguo y elimina
su entrada nueva. No borra otras sesiones antiguas, backups ni copias del proveedor.
Reset funciona sin la clave API de Venice, pero requiere que el cifrado existente abra.
No se debe prometer borrado de copias externas o de todos los datos anteriores de PR63.

Las consultas y reset se serializan dentro del proceso; las escrituras conservan la
protección de líder existente. No es un bloqueo distribuido nuevo.
Máximo 100 sesiones y 20 mensajes por sesión; máximo de caracteres antes de cada envío.
Los errores nuevos solo registran el tipo de excepción.

## Verificación

Ejecutar test_jarvis_router.py, test_venice_privacy.py, test_seal_migration.py y
 test_private_backup.py; verificar SHA256SUMS.txt. Las pruebas usan datos ficticios y
no llaman proveedores externos. La suite completa y el entorno de producción deben
validarse antes de habilitar. El parche no habilita pagos, herramientas, envíos a clientes,
OpenAI, TTS externo ni modifica topes o aprobaciones.
