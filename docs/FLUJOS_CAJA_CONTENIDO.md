# Caja, YouTube, Amazon y fichas de negocio — integración revisada

Requisitos originales: `docs/REQUISITOS_GROK_ORIGINAL.md`. Esta implementación se basa en el árbol del PR #14 (Claude + correcciones de Codex), sin fusionar ni activar cuentas. Se conservaron $100/$300, aprobaciones, `/confirmar` fuera de la cola, voz local y WHISPER_BEAM=1. No cambia variables de producción ni activa OpenAI, TTS externo, trading o recursos.

## Correcciones a los requisitos

- $400 observados + $150 por cobrar − $380 por pagar = **$170**, condicionado a recibir el cobro; sin cobrar quedarían $20. No existe el faltante de $130 descrito en el ejemplo.
- La alerta compara el saldo final proyectado con **−$50**. Compararlo otra vez con los pagos descontaría los mismos pagos dos veces. El umbral vive en código; no lo modifica el modelo.
- FITID identifica un movimiento; no acredita el saldo. El importador existente acepta saldo fechado de OFX o de una columna de balance CSV aunque no haya FITID. Nunca convierte ingresos de los libros en saldo bancario.
- Una importación de más de tres días se rotula «saldo viejo» y bloquea el cálculo de caja. Fecha futura, cuenta de crédito, cuenta no elegida entre varias o datos incompletos también bloquean la proyección.
- No se suman automáticamente cobros/pagos del calendario además de trabajos/cuentas: podrían ser el mismo vencimiento. Se pide conciliación antes de estimar.
- YouTube Analytics requiere OAuth del propietario; no implica por sí solo una cuota mensual. Las métricas monetarias requieren otro scope y elegibilidad del canal. No se afirma que dominio, email o vendedor estén conectados ni que todos tengan el mismo costo.
- La ficha HTML no puede confirmar recepción por sí sola. Solo el receptor opcional, después de guardar, responde «Recibido, sin precio». No se entrega ni publica una página automáticamente.

## Funciones y comandos

| Comando | Comportamiento |
|---|---|
| `/caja [clave de cuenta]` | Observado con fecha, registrado en USD y proyección condicional de trabajos y cuentas de los próximos siete días. No escribe ingresos, no paga y no llama a IA. |
| `/youtube TEMA` | Tema original; una consulta pública al día, máximo diez resultados únicos. Idioma relevante español, duración corta, categoría educativa, safeSearch estricto. Muestra conteos observados o campo ausente, nunca retención, RPM o ingresos inventados. |
| `/alibaba TEMA` | Enlaces de búsqueda gratuitos; no llama a Claude/OpenAI ni afirma haber investigado precios/proveedores. |
| `/fichaamazon JSON` | Margen con precio, producto, flete PR, empaque y porcentaje de comisión suministrados por el dueño. No entra a Orders, Fees o Listings. No compra. |
| `/negocio JSON` | Nombre ya existente en clientes o BUSINESS_NAME, oficio y zona explícitos. Opcional teléfono internacional. No crea una LLC ni inventa contactos. |
| `/pagina NOMBRE` | Genera HTML estático y lo entrega al dueño para revisión, sin alojamiento, dominio ni publicación. Escapa contenido externo. |
| `/paquete JSON` | Borrador para adultos con título y precio del dueño, sin cobro ni publicación. No genera todavía el contenido del PDF/licencia. |
| `/capacidades` | Disponibilidad real de flujos locales y conexiones pendientes; no activa cuentas. |
| `/solicitudes [cerrar ID]` | Consultas recibidas para revisión del dueño. Cerrar no implica precio, pago, envío ni registro de ingreso. |

Ejemplos de datos explícitos:

```
/fichaamazon {"sale_price":25,"unit_cost":10,"shipping_pr":8,"packaging":0,"referral_percent":15}
/negocio {"name":"ISLAFIX PRO LLC","trade":"Construcción y mantenimiento","zone":"Puerto Rico","phone":"17875271440"}
/pagina ISLAFIX PRO LLC
/paquete {"title":"Material educativo para familias","price":5}
```

Son ejemplos: no registran ni confirman por sí solos los datos del negocio. El nombre debe coincidir con el negocio configurado/registrado. Un cero para empaque u otro costo es una decisión explícita del dueño, no una omisión automática.

## Avisos y aprobaciones

- El brief conserva las secciones originales y agrega el reporte de caja. Las alertas automáticas necesitan el programador, Telegram y una hora de brief ya configurados.
- Máximo un intento de alerta de caja por regla y fecha PR. La deduplicación usa las reclamaciones persistentes existentes (Redis SET NX EX o almacenamiento local); sobrevive reinicio y no se restablece al restaurar un backup de libros.
- Envío incierto: no reintenta automáticamente ese día; privilegia el límite de una alerta frente a una posible repetición.
- Los trabajos con saldo y vencimiento generan borradores de seguimiento cuando los avisos existentes están habilitados. Un borrador pendiente/en envío/incierto evita otro por el mismo trabajo. Nunca se envía a un cliente: requiere `/enviar`, con el proveedor configurado o copia manual.
- El pago recibido de un trabajo ya no permite `add_to_books=false` sin identificar un ingreso existente. Se rechaza antes de modificar nada. Para conciliar, `existing_income_id` debe corresponder al ingreso indicado por el dueño, con importe, fecha y USD idénticos y nunca usado en otro pago. Se vinculan trabajo e ingreso en un solo guardado; no se duplica ni se omite el ingreso. Los adelantos históricos del alta de trabajo siguen siendo saldos previos, no dinero nuevo recibido; esa función existente no crea ingresos retroactivos automáticamente.
- Solicitudes explícitas de ocultar ingresos o tramitar tarjetas/crédito tienen respuestas locales antes de llamar al modelo. La regla reconoce expresiones concretas; no es un clasificador universal de intención. Las correcciones normales de contabilidad conservan las aprobaciones existentes.

## YouTube y límites

La cuota se reserva antes de la red, de modo que llamadas concurrentes o reinicios no producen ciclos repetidos. Un error de red también consume el intento diario. La misma consulta completada se devuelve desde su resultado guardado. No se busca automáticamente: la solicitud debe venir del dueño.

`videos.list` sigue siendo el adaptador de detalle del proyecto. `batchGetStats`, citado por Grok, existe, pero no devuelve por sí solo el título y canal completos requeridos. No era necesario sustituir el adaptador existente.

Una lista acotada bloquea personajes conocidos como Peppa, Mickey o Bluey antes de investigar/generar planes. No demuestra que cualquier nombre desconocido esté libre de derechos: la revisión humana de originalidad sigue siendo obligatoria. El filtro relevanceLanguage tampoco demuestra el idioma hablado de cada resultado. No se copia título ni guion para crear un plan.

## Recepción pública opcional de consultas

`BUSINESS_REQUESTS_ENABLED=false` por defecto. El corte no cambia ese valor en Render. Habilitar y alojar la ficha requiere una revisión del dueño.

- `POST /public/business-requests`, máximo 5 KB, JSON o formulario URL-encoded.
- Negocio registrado, nombre, teléfono internacional, consulta y declaración de adulto. No pide EIN, tarjeta ni banco. Rechaza credenciales/campos sensibles reconocidos y un honeypot.
- Un intento por teléfono normalizado cada diez minutos, límite 100 consultas al día y máximo 100 pendientes. Sin cuentas/pasarela/servicio de pago nuevo.
- Guarda consulta como datos externos; nunca interpreta el texto como una orden, abre cuenta, registra pago ni responde al cliente fuera del acuse HTTP.
- La ficha debe alojarse **en el mismo dominio** del receptor para usar el formulario. El HTML enviado como archivo no es una web publicada. El endpoint devuelve 404 mientras la opción esté apagada.
- `/solicitudes` es exclusivo del chat privado del dueño. Las consultas se incluyen en el backup y su estructura se valida al restaurar. Cerradas: se conservan hasta cien; pendientes nunca se eliminan para hacer espacio.
- El límite de teléfono no equivale a verificación de identidad. No se afirma que este formulario sustituya un servicio antiabuso completo.

## Pendiente de datos o autorización

- Importación bancaria reciente, cuentas, vencimientos completos y conciliación de calendario; periodo de prueba real de caja.
- API key/cuota autorizada para búsqueda pública de YouTube; Analytics propio y permisos monetarios no se activan.
- Cuenta Amazon y permisos de Fees para comprobar comisión real y restricciones. Los costos del dueño no predicen demanda.
- Datos confirmados del negocio para la ficha, revisión y alojamiento explícito antes de habilitar solicitudes. No se compró dominio.
- Contenido final de los paquetes educativos/licencias para adultos, aportado y revisado por el dueño.
- Conectores SMS/email/calendario y hardware para IA libre local 24/7: no se instalan inventando cuentas o recursos.

Fuentes oficiales consultadas el 8 de octubre de 2026:
- https://developers.google.com/youtube/v3/docs/search/list
- https://developers.google.com/youtube/v3/docs/videos/list
- https://developers.google.com/youtube/v3/docs/videos/batchGetStats
- https://developers.google.com/youtube/analytics/channel_reports
- https://developer-docs.amazon.com/sp-api/reference/getmyfeesestimateforsku

Pruebas: casos locales y proveedores simulados; Redis real para las pruebas existentes de reclamaciones, fencing y Lua. No se investigó con una cuenta real, no se envió mensaje a clientes ni se probaron movimientos monetarios reales.
