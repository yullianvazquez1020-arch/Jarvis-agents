# Estado de las fases — 8 de octubre de 2026

## Disponible

- Voz Telegram local: Whisper tiny CPU/int8 y Piper, sin fallback a OpenAI/TTS externo.
- Preguntas por voz en solo lectura; acciones mediante revisión y `/dictado ID`.
- Memoria breve persistente: cuarenta mensajes, hasta diez turnos completos por sesión.
- Respuestas por reglas locales para saludos, agradecimientos, despedidas, hora, fecha y ayuda. No llaman a Claude. Solo coinciden con el mensaje completo; las acciones y aprobaciones no son atajos de conversación.
- Clientes, trabajos, inventario, cobros, libros, importación bancaria y práctica cripto ya existen; no se necesita activar trading real para usarlos.
- Límites $100 por operación/$300 por día, aprobación del dueño y `/confirmar` fuera de la cola.

## Requiere conexión o una decisión concreta

| Fase | Requisito para completarla | Estado actual |
|---|---|---|
| Chat libre local sin tokens | Equipo/servidor disponible, modelo medido y endpoint local autorizado | Las reglas reducen llamadas; las preguntas libres aún pueden llamar a Claude. No se instaló un LLM en los 512 MB de Render. |
| Historial cifrado | Clave AES-256 respaldada por el dueño y prueba de lectura/migración | Código disponible; no generar una clave sin plan de recuperación ni afirmar que el historial ya está cifrado. |
| SMS, WhatsApp, llamadas y correo | Cuentas/número/permisos del proveedor, costos aceptados, prueba con destinatario autorizado | Conectores o borradores existentes no equivalen a una cuenta conectada. Los envíos requieren aprobación. |
| Calendario | Cuenta y permisos autorizados y calendario destino | No afirmar que funciona solo por configurar una URL. |
| Alertas de flujo de caja | Libros y vencimientos completos, reglas de aviso y periodo de prueba | Los atajos existentes no son una predicción financiera validada. |
| Amazon y publicación en redes | Cuenta del vendedor/página y permisos, lectura antes de publicación | No activar compras ni publicar contenido automáticamente. |
| IA local 24/7 con visión/agentes | Inventario real del hardware, capacidad y modelo medidos | Proyecto distinto del bot de Render; requiere instalación en equipo accesible. |

OpenAI, TTS externo, trading real y ampliaciones de recursos no se activan por estas fases.
Las respuestas locales de esta entrega no convierten todo el chat en gratuito.
