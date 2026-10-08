# Gemini para Jarvis y MyClaw

Estado: rutas montadas en el arranque actual. No cambiar el comando de Uvicorn.
MyClaw se configura en su sesión existente. La sesión web de Gemini no autentica esta API.

## Jarvis

El comando de producción sigue siendo `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1`. No sustituirlo por
`jarvis_gemini_app:app`: ese cambio reinicia el worker y desconecta Telegram, la voz
y la sesión de MyClaw. Al importarse desde `main`, `jarvis_transit` llama a
`jarvis_gemini_boot.mount` para cargar el revisor. `install_transit` repite el montaje
idempotente por si `jarvis_transit` ya estaba importado. Si el módulo falla,
Jarvis arranca igual y `GEMINI_STATUS` queda en apagado.

Configurar en Render, nunca por chat ni en Git:

- `GEMINI_ENABLED=true` solamente al autorizar la prueba real.
- `GEMINI_API_KEY`: credencial de Google AI Studio del proyecto elegido.
- `GEMINI_MODEL`: identificador de modelo disponible para esa cuenta; no se impone
  uno ni se sustituye automáticamente por un modelo más caro.
- `GEMINI_REVIEW_ACCESS_KEY`: secreto aleatorio independiente, mínimo 32 caracteres.
  Nunca reutilizar AGENT_API_KEY, la clave de cifrado o una clave de proveedor.

GET `/gemini/status` y POST `/gemini/review` requieren el header `x-api-key` con
GEMINI_REVIEW_ACCESS_KEY. El POST acepta solamente `{"text":"texto público a revisar"}`.
La respuesta es una revisión sin ejecutar acciones. No se envían historial, perfil,
libros, herramientas ni archivos. No enviar datos privados sin autorización específica.
El estado de configuración no demuestra conectividad; solo un POST exitoso la prueba.

Hay un máximo global de 8 intentos diarios según la fecha de Jarvis, 8000 caracteres
de entrada y 800 tokens de salida, sin reintentos automáticos. Los fallos consumen
un intento. Este límite NO es un presupuesto monetario ni garantiza coste cero.
La facturación y las cuotas se comprueban en la cuenta del proveedor antes de activar.
Los topes monetarios $100/$300 de Jarvis y sus aprobaciones permanecen independientes.

No entregar la clave maestra de Jarvis a MyClaw. Si posteriormente se autoriza que
MyClaw invoque esta revisión, usar únicamente la credencial limitada anterior en su
almacén de secretos. El conector no permite acceder a /chat, /backup ni ejecutar tools.

## MyClaw

En la sesión existente de `jarvis-colaborator`, abrir configuración de modelos.
Comprobar la opción Google/Gemini y el método disponible: proveedor MyClaw o clave
propia. No sustituir el Claude principal, ni habilitar recargas automáticas o fallback
desconocido. Primero añadir Gemini como opción de revisión, si esa interfaz lo permite.
Confirmar modelo, precio y límites mostrados antes de guardar cambios con coste.
Si requiere clave propia, introducirla en su formulario seguro; no en un mensaje al bot.
No reiniciar el sign-in.

Validar con un texto público breve y verificar el proveedor/modelo real usado y el
consumo. Tener el sitio de Gemini abierto no conecta estos servicios entre sí.

## Fuentes oficiales

- https://ai.google.dev/api/generate-content
- https://ai.google.dev/gemini-api/docs/api-key
- https://myclaw.ai/

## Reversión

Poner `GEMINI_ENABLED=false` detiene nuevas solicitudes al cargar esa configuración.
No hace falta volver a `main:app`: ese ya es el comando.
