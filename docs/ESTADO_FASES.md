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
| Historial cifrado | Clave AES-256 respaldada por el dueño (docs/CIFRADO_HISTORIAL.md) y estado comprobado mediante `/cifrado` | Código integrado en main mediante PR #14; respaldo privado ampliado en PR #18. Esta revisión no verifica la configuración ni los datos actuales de producción. Consultar `/cifrado` antes de plantear otra migración; no regenerar la clave ni repetir la migración solo por este documento. |
| SMS, WhatsApp, llamadas y correo | Cuentas/número/permisos del proveedor, costos aceptados, prueba con destinatario autorizado | Conectores o borradores existentes no equivalen a una cuenta conectada. Los envíos requieren aprobación. |
| Calendario | Cuenta y permisos autorizados y calendario destino | No afirmar que funciona solo por configurar una URL. |
| Alertas de flujo de caja | Libros y vencimientos completos, reglas de aviso y periodo de prueba | Código integrado en main, con correcciones de cómputo en PR #20. Distingue saldo observado, libros y proyección; bloquea datos incompletos. El merge no acredita por sí solo el despliegue ni el periodo de prueba real. |
| Amazon y publicación en redes | Cuenta del vendedor/página y permisos, lectura antes de publicación | Investigación pública acotada y margen con costos del dueño preparados; no activan cuentas, compras ni publicaciones automáticas. Tarifas y métricas privadas requieren autorización. |
| Página del negocio | Nombre/oficio/zona confirmados, revisión y alojamiento; solicitudes habilitadas explícitamente | HTML estático y receptor opcional preparados. BUSINESS_REQUESTS_ENABLED=false por defecto; no se compró dominio ni se publicó. |
| IA local 24/7 con visión/agentes | Inventario real del hardware, capacidad y modelo medidos | Proyecto distinto del bot de Render; requiere instalación en equipo accesible. |

OpenAI, TTS externo, trading real y ampliaciones de recursos no se activan por estas fases.
Las respuestas locales de esta entrega no convierten todo el chat en gratuito.
## Corte 4.2.0 (PR #20 fusionado en main)

Commit de merge: `5902b1f02a39218901a57d54fc6ec791efebca6e`. La integración en Git está verificada; este documento no certifica el commit actualmente desplegado en Render.

Parche aditivo en `jarvis_v420.py`: reglas locales, historial con redacción y marca de reinicio, perfil, propuestas de cash flow con presupuesto, lockout reusado, borradores Twilio sin envío, alerta temprana. Cara, holograma, CarPlay, Ojo de Dios y mini Jarvises siguen en 4.3+ (`CAMBIOS_4_2_0.md`).
