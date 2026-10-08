# Requisitos para Codex — cash flow, YouTube, Amazon
Consulta: 7 de octubre de 2026. Commit leído: 961047a2a4921fcd3b3238a66cbc58544c0fc59d.
Archivos leídos: docs/ESTADO_FASES.md (fecha interna 8 de octubre de 2026), docs/backlog/prompt-jarvis-4.2.0.md, CONEXIONES_MONETIZACION.md.
No se ejecutó la suite. El dueño informó 579 pruebas; este revisor no las volvió a correr.
No se afirma que Claude o Codex hayan recibido este texto.

## Comprobado en documentos
- Voz Telegram local activa: Whisper tiny CPU/int8 y Piper, sin fallback de pago. Preguntas de voz en solo lectura; acciones con /dictado ID.
- Libros, clientes, trabajos, inventario, cobros, importación bancaria y práctica cripto existen. No son una predicción financiera validada.
- Límites $100/$300, aprobación del dueño y /confirmar fuera de la cola.
- Alertas de flujo de caja: fase pendiente. Requisito: libros y vencimientos completos, reglas y periodo de prueba.
- Amazon y YouTube: variables y borradores no equivalen a cuenta conectada ni a ventas o monetización.
- OpenAI, TTS externo y trading real permanecen apagados por estas fases.

## Estimado
- Un aviso diario local cabe en el worker. Una investigación de YouTube o Amazon no: tope de 1 ciclo al día y máximo 10 fichas.
- Puerto Rico en envío de vendedor: USPS suele ser la vía viable; UPS/FedEx a menudo lo tratan como internacional. Eso no está en el fee schedule oficial leído hoy. Queda pendiente de plantilla del vendedor.

## Pendiente de acceso
- Saldo bancario observado solo si hay importación con fecha. Sin FITID reciente, no hay saldo.
- Retención de YouTube: solo Analytics del canal propio, OAuth yt-analytics.readonly. No está en el Data API público.
- Comisiones Amazon reales: SP-API Product Fees o Seller Central. Precio público no es demanda.

## 1. Flujo de caja
Tres capas, nunca mezcladas en el texto del aviso:
- Observado: último saldo importado y su fecha. Si tiene más de BANK_STALE_DAYS, el aviso dice “saldo viejo”.
- Registrado: ingresos y gastos ya contabilizados. No es caja.
- Proyección: cobros con vencimiento más gastos recurrentes futuros. Es una resta, no un hecho.

Regla local, sin tokens: en el brief diario, si proyección a 7 días es menor que los pagos de esos 7 días, un aviso. Umbral fijo $50 por debajo, no configurable por el modelo. Máximo un aviso por día y por regla. Clave de dedupe: fecha + regla + id de cobro o gasto. No llama, no paga, no usa el money gate.

Falta si no hay vencimientos o el banco no se importó: decir qué falta y no estimar un faltante.

## 2. YouTube infantil educativo
Entrada: tema del dueño, no un video ajeno para copiar. Salida: hasta 10 videos públicos con título, canal, fecha, viewCount, likeCount, commentCount y duración. Esos conteos son observados. Retención, RPM e ingresos no se estiman. Si no hay Analytics del canal propio, el campo queda “no disponible”.

Calidad: duración corta, idioma español, tema educativo, sin personaje reconocible de terceros. Originalidad: historia nueva de Jarvis, revisión humana antes de /producirvideo. No prometer monetización. Cuota: una búsqueda al día. Data API público no exige OAuth para videos públicos; Analytics sí.

## 3. Amazon
Comparar solo con costo total escrito por el dueño: producto, envío a Puerto Rico, comisión de categoría, empaque. Margen = precio publicado − esa suma. Precio publicado no es venta ni demanda. Restricciones y fee real requieren Seller Central y, si se autoriza lectura, getMyFeesEstimateForSKU. Sin esa cuenta, el resultado dice “comisión de tabla, no comprobada”. No comprar. No publicar ficha.

## Orden
1. Aviso de caja local y dedupe.
2. Investigación YouTube de solo lectura, con tope.
3. Ficha Amazon con costos del dueño. Fees API después, si hay rol de lectura.

## Casos ficticios
- Caja: saldo importado $400 el día 1, cobro $150 vence en 5 días, gasto fijo $380 en 6 días. Esperado: aviso “proyección corta $130; saldo observado $400 con fecha”. No decir que el banco tiene $400 hoy si la importación es vieja.
- Caja vacía: sin cobros y sin banco. Esperado: “faltan vencimientos e importación”. Cero aviso de faltante.
- YouTube: 10 resultados con viewCount. Esperado: vistas observadas; retención “no disponible”. Ningún personaje de terceros en el plan.
- Amazon: precio $25, envío PR $8, comisión tabla 15% = $3.75, costo $10. Esperado: margen estimado $3.25, marcado estimado. Sin unidades vendidas.

## Checklist Codex
- No subir $100/$300. /confirmar sigue fuera de la cola.
- Aviso de caja sin red y sin Claude.
- Dedupe sobrevive reinicio (Upstash).
- YouTube no copia título ni guion. No publica.
- Amazon no llama a Orders ni a listings sin rol y sin /publicarproducto ya existente.
- OpenAI, TTS externo y trading real siguen apagados.
- WHISPER_BEAM=1 no se toca en este corte.
- Ningún comando oculta un ingreso ni lo saca de los libros.

## 4. Caja diaria de ISLAFIX
Jarvis no crea un ingreso diario. El flujo usa cobros y trabajos ya registrados.
- Mañana, en el brief: cobros que vencen en 7 días, trabajos sin cobrar, y un borrador de seguimiento si el cliente ya existe.
- El borrador no se envía. Sale solo con /enviar.
- Un cobro anotado no es dinero recibido. Hace falta el pago registrado o el banco importado.
- Meta de “un contacto al día” es un recordatorio, no una venta. Si no hay cliente pendiente, el aviso dice “nada que cobrar hoy”.

## 5. Monetización infantil, sin prometer ingreso
Opciones permitidas en requisitos, todas fuera de YouTube Ads personalizados:
- Anuncios contextuales solo si el Programa de Socios acepta el canal. Campo de ingreso: no disponible hasta Analytics monetario del dueño.
- Paquete para adultos: PDF o licencia de aula, cobrado fuera del video. Jarvis guarda el precio que el dueño escribió. No lo inventa.
- El video no lleva donación, membresía ni Super Chat si está marcado hecho para niños.
- Prohibido: copiar personajes, pedir datos del niño, o tratar una vista como venta.

## 6. Lo que no entra
- Evasión o libros que omitan un cobro. Todo ingreso anotado permanece en los libros.
- Trading real, compras Amazon y publicación automática.
- EIN, cuenta bancaria y contraseñas no se piden ni se guardan en el repo.
- Un ingreso diario fijo no es un requisito. El requisito es el aviso de lo ya vencido.

## Casos añadidos
- Cobro $200 vence mañana y no hay pago. Esperado: aviso de seguimiento en borrador. Estado del cobro sigue pendiente.
- Tema “Peppa”. Esperado: rechazo antes de buscar. Cero plan.
- Precio de paquete en blanco. Esperado: “falta precio del dueño”. No se publica un monto.
- Pedido de ocultar un ingreso. Esperado: rechazo. El libro no cambia.

## 7. Sitio web por negocio
Jarvis propone una ficha solo si en libros o clientes ya están nombre, oficio y zona. ISLAFIX PRO LLC es la primera. YouTube, Amazon y la cripto en práctica no generan página.
Comando local, sin tokens: `/pagina NOMBRE`. Si faltan datos, dice cuáles y no escribe archivos. Si están, deja HTML estático para revisión del dueño. No lo sube, no compra dominio y no avisa al cliente.
Sin APIs de pago, sin pasarela y sin guardar EIN, banco ni tarjeta. La solicitud dice “recibido, sin precio”. Un envío por teléfono cada 10 minutos.
Detalle en `requisitos-pagina-islafix.md`.

## 8. Aplicaciones conectadas, sin costo nuevo
Jarvis puede proponer una conexión solo si no añade una cuota. Lo que ya existe y no se paga por uso: Telegram, libros locales, importación bancaria que el dueño exporta, voz Whisper/Piper, y la ficha HTML estática.
Puede listar, sin activar, lo que falta y cuesta: Twilio, Resend, Amazon Seller, YouTube Analytics, dominio propio. La lista dice “no conectado, tiene costo” y no pide la clave por chat.
No se encienden OpenAI, TTS externo ni trading real. No se compra una app ni se abre una cuenta desde el comando. `/conexiones` sigue distinguiendo variable presente de conexión comprobada.

## 9. Teléfono y bot
La conexión gratis al teléfono es el bot de Telegram del servicio `jarvis-agents.onrender.com`. No es un bot de Grok. El @ vive en BotFather y no se copia al repo. Una nota de voz entra por ese bot. Un enlace wa.me abre WhatsApp y no es una API. Llamadas y SMS no se activan.

## 10. Lo que Jarvis no crea aunque crea que falta
No crea otro negocio, otra página ni otra app si no hay nombre, oficio y zona en los libros. No pide el EIN ni lo guarda. No oculta ingresos. No promete caja diaria. Si falta un dato, el comando dice cuál y se detiene.

## 11. Negocios, LLC y crédito que Jarvis sí lleva
Negocios actuales: ISLAFIX PRO LLC es el único con nombre, oficio y zona en los documentos leídos. Los demás entran cuando el dueño anote nombre, oficio y zona. Un plan de YouTube, una ficha de Amazon o la cripto en práctica no son un negocio con página.

Jarvis puede, sin costo y sin entrar a cuentas ajenas:
- Separar en los libros el gasto anotado de ISLAFIX del gasto personal, si el dueño lo marca.
- Avisar un vencimiento de pago que el dueño escribió. No paga y no entra al banco.
- Listar qué falta para un negocio nuevo: nombre, oficio, zona. No crea la LLC ni pide el EIN.
- Decir que una LLC no sube el puntaje personal. Solo una cuenta que el dueño garantizó con su firma puede aparecer en su reporte.

No puede: entrar a Credit Karma, disputar un buró, pedir una tarjeta, usar el EIN como ingreso, ni ver o manejar el crédito de otra persona o de su empresa. Una solicitud de tarjeta la hace el dueño en el banco. Jarvis no la envía.

Aplicaciones por negocio, solo si ya existe en los libros: ficha HTML de cotización, aviso de cobro en borrador, y Telegram. Amazon Seller y YouTube Analytics se listan como no conectados. No se activan solos.

## 12. Checklist de Codex para negocios y avisos de pago
- Un negocio nuevo sin nombre, oficio o zona no genera página ni app.
- ISLAFIX puede tener ficha. YouTube, Amazon y cripto en práctica no.
- Un vencimiento anotado por el dueño produce un aviso. No paga, no abre el banco y no entra a Credit Karma.
- Un pedido de tarjeta, de disputa al buró o de crédito de un tercero se rechaza y no cambia los libros.
- El EIN no se pide, no se guarda y no se usa como ingreso.
- /confirmar sigue fuera de la cola. Los topes de $100 y $300 no se tocan.

Casos:
- “Crea la página del canal”. Esperado: rechazo. No es un negocio con oficio y zona.
- “Avísame el día 20 el pago de la tarjeta, $40”. Esperado: un aviso ese día. Cero pago.
- “Pide la tarjeta con el EIN”. Esperado: rechazo. El libro no cambia.

## Fuentes oficiales
- YouTube Data API, statistics.viewCount: https://developers.google.com/youtube/v3/docs/videos/batchGetStats (consulta 7 oct 2026).
- YouTube Analytics, averageViewPercentage, OAuth obligatorio: https://developers.google.com/youtube/analytics/content_owner_reports (consulta 7 oct 2026).
- Amazon fees 2026: https://sellingpartners.aboutamazon.com/update-to-u-s-referral-and-fulfillment-by-amazon-fees-for-2026 (publicado 15 oct 2025; consulta 7 oct 2026).
- SP-API getMyFeesEstimateForSKU: https://developer-docs.amazon.com/sp-api/reference/getmyfeesestimateforsku (consulta 7 oct 2026).
- Autorización SP-API ya citada en CONEXIONES_MONETIZACION.md: https://developer-docs.amazon.com/sp-api/docs/authorizing-selling-partner-api-applications
