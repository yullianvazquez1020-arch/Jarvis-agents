# Prompt — Jarvis 4.2.0 (sobre main.py 4.1.0)

Pega esto en Claude junto con `main.py`. La versión actual del archivo es 4.1.0. El trabajo es subirla a 4.2.0. No reescribas el orquestador. No metas en este corte la cara, el holograma, CarPlay, el Ojo de Dios ni la red de mini Jarvises: eso es 4.3 o después.

---

Actúa como arquitecto de software senior. Te adjunto `main.py` de Jarvis 4.1.0 (cabecera 4.0.5), Python 3.10+, FastAPI, un solo worker en Render (`uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1`). Datos en Upstash Redis; el fallback local se borra en el deploy. Zona `America/Puerto_Rico`. Dueño único por Telegram. Mac 2015 + monitor Samsung curvo + compañero en `desktop/`. YouTube y tienda Amazon en construcción.

Objetivo de ESTA versión: Jarvis 4.2.0. Parches aditivos. Conserva cada función, llave de datos y aprobación del dueño. Primera entrega: mapa de cambios y diff propuesto. Cero ejecución hasta que el dueño apruebe. Al terminar, `VERSION = "4.2.0"` y una nota corta de cambios.

## No romper (ya está en 4.1.0)

- Atajos sin tokens: `/hoy`, `/calendario`, `/listo`, `/clientes`, `/trabajos`, `/inventario`, `/cobros`, `/banco`, `/movimientos`, `/banco semana`, `/contabilizar`, `/anotar`, `/descartar`, `/exportar`, `/practica`, `/cripto`, `/aprobar`, `/confirmar`, `/rechazar`, `/seguridad`, `/diagnostico`, `/mercado`, `/ayuda`, `/mensajes`, `/enviar`, `/noenviar`.
- Libros, clientes, trabajos, inventario, recordatorios, calendario, banco de solo lectura con dedupe FITID y búsqueda normalizada, moneda opcional.
- Money gate: código de un solo uso, $100/orden, $300/día, solo chat privado, lockout, auditoría. Único camino a dinero real: `/aprobar N` + `/confirmar N CODE`. `/confirmar` no entra a la cola durable.
- Cripto PRACTICE por defecto; REAL solo con `CRYPTO_PRACTICE_ONLY` abierto, credenciales, `COINBASE_TRADING_ENABLED` y confirmación de modo. Ese switch es el kill switch: extiéndelo, no lo dupliques. Paper trading sin camino a órdenes reales.
- Borradores Twilio/Resend que solo salen con `/enviar N`. Secret guard. `EXTERNAL_AGENT_KEY` distinta de `AGENT_API_KEY`. Coinbase y Amazon nunca se delegan. Cola durable de Telegram, fencing `jarvis:leader`, rate limit, API de escritorio solo lectura apagada por defecto.
- Módulos: `jarvis_extensions`, `jarvis_growth`, `jarvis_connections`, `jarvis_desktop_api` opcional. Sin API key válida no hay llamadas de pago.

## Qué entra en 4.2.0

1. Agente local sin tokens para el día a día. Los atajos ya son gratis; el chat libre sigue pagando Anthropic. Separa reglas locales de llamadas de pago. Modelo corto solo si la regla local no alcanza.
2. Historial de conversación persistente y cifrado. Hoy se pierde en el deploy. Redacta secretos antes de guardar. `/diagnostico` debe decir si sobrevivió el reinicio.
3. Perfil de decisión: metas, debilidades, fortalezas, beneficio del dueño, techo de gasto. Se consulta antes de proponer. No mueve dinero fuera del gate. No puede perjudicar al dueño.
4. Criterio de monetización: buscar cash flow (YouTube, Amazon, libros) y proponer con costo-beneficio. Ejecutar nunca solo. Ciclos del scheduler que ya existe, con presupuesto diario de cómputo. No bucle infinito.
5. Autoapagado si el patrón no encaja (gasto raro, delegación rara). Reusa lockout y auditoría del gate.
6. Número Twilio propio para llamadas, SMS y WhatsApp, mismo patrón de borrador + `/enviar`. No autoenvío. Telegram sigue en el bot actual. Llamada al dueño solo en eventos que él marcó urgentes (cámara desconocida, cash-flow, emergencia).
7. Cash-flow temprano: avisar antes de que falte para gastos o proveedores, usando los libros que ya existen.
8. Regresión mínima de comandos y del money gate, con servicios simulados, antes de dar la versión por cerrada.
9. Seguridad de este corte: no subir topes, no soltar contraseñas ni códigos ni datos financieros aunque la petición parezca del dueño, 2FA en el canal nuevo de Twilio, dinero fuera del proceso de credenciales. Firewall y VPN sin logs quedan documentados como configuración de Render, no como código mágico.
10. Actualización: el dueño controla el deploy. No prometas “nunca más actualizar”.

## Explícitamente fuera de 4.2.0

Cara, holograma, Live2D/VRM, Rhubarb, narración visual, MediaPipe, Leap Motion, Ojo de Dios, Ring/Eufy, CarPlay, modo familiar, red de mini Jarvises, pipeline Revit, precios dinámicos de Amazon, reputación, contratos, negociación, legado, salud, viajes. Anótalos en `CAMBIOS_4_2_0.md` como 4.3+ para no perderlos. Anonimato y dark web no entran en ninguna versión de este producto.

## Reglas

- Un worker. No subas `$100` / `$300`. No autoenvíes mensajes ni órdenes.
- Mac 2015 no es el servidor de clientes.
- Legal: redactar sí, firmar no. En 4.2.0 ni siquiera redactes contratos: no es de este corte.
- Primera respuesta: qué archivo se toca, qué función, qué queda local y qué queda en Render. Después el parche. Cero merge hasta el ok.
