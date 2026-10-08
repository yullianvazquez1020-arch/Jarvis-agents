# Jarvis 4.2.0 — notas de cambio

Parche aditivo sobre `main.py` 4.1.0. No reescribe el orquestador. Un solo worker. No sube `$100` por orden ni `$300` por día. No autoenvía mensajes ni órdenes. No hay acciones reales de Twilio, Amazon ni Coinbase. Coinbase y Amazon no se delegan. `EXTERNAL_AGENT_KEY` sigue distinta de `AGENT_API_KEY`. La cola durable de Telegram y el fencing `jarvis:leader` no se tocan. `/confirmar` sigue fuera de la cola. El Mac 2015 no es el servidor de clientes.

El dueño controla el deploy. Esta versión no promete dejar de actualizar.

## Correcciones de revisión

- El marcador de reinicio se guarda durante el arranque después de obtener liderazgo Redis, no durante la importación. `/health` informa si el módulo está activo; el ciclo nuevo también exige liderazgo.

- Los canales con herramientas restringidas o de solo lectura conservan las comprobaciones del orquestador original; no pueden activar el bloqueo financiero ni guardar historial mediante los atajos de esta versión. Los atajos del dueño verifican liderazgo antes de escribir.
- El flujo separa ingresos y gastos registrados hasta hoy de gastos futuros a siete días. Un gasto se descuenta una sola vez y los ingresos futuros no se presentan como dinero disponible. Es una estimación de los libros, no un saldo bancario verificado.
- Pruebas de regresión cubren canales públicos, voz, restricciones de herramientas, instancias antiguas y límites de fechas del flujo.

## Qué entra

1. Agente local sin tokens para el día a día (`jarvis_v420.local_answer` y los atajos ya existentes). El chat libre que ninguna regla cubre usa el modelo corto (`JARVIS_SHORT_MODEL`, por defecto `claude-haiku-4-5`), no el modelo largo.
2. Marcador de reinicio `jarvis:v420:boot`. `/diagnostico` dice si el marcador sobrevivió y si el historial está presente o cifrado. Los secretos se redactan antes de guardar.
3. Perfil de decisión (metas, debilidades, fortalezas, beneficio, techo). Se consulta antes de proponer. El techo solo puede bajar el tope duro. No mueve dinero fuera del gate.
4. Criterio de monetización: propone cash flow con los libros (YouTube, Amazon y cobros como señal, sin ejecutar). Un ciclo del scheduler por día y presupuesto de 8 propuestas. Sin bucle infinito.
5. Autoapagado si el patrón no encaja (gasto raro o delegación de Coinbase/Amazon). Reusa `locked_until` y `gate_audit`.
6. Número Twilio propio como borrador SMS/WhatsApp/llamada. 2FA del canal, distinto del código de dinero. No autoenvío. Telegram sigue en el bot actual. Llamada al dueño solo como borrador si él marcó el evento urgente.
7. Aviso temprano de cash-flow con los libros, antes de que falte para gastos o proveedores a 7 días.
8. `tests/test_v420.py`: regresión de comandos, topes y gate con servicios simulados.
9. Seguridad de este corte: no sube topes, no suelta contraseñas, códigos ni datos financieros aunque la petición parezca del dueño. 2FA en el canal Twilio. El dinero queda fuera del proceso de credenciales. Firewall y VPN sin logs son configuración de Render, no código.
10. Actualización: el dueño controla el deploy.

## Fuera de 4.2.0 (4.3+)

Cara, holograma, Live2D/VRM, Rhubarb, narración visual, MediaPipe, Leap Motion, Ojo de Dios, Ring/Eufy, CarPlay, modo familiar, red de mini Jarvises, pipeline Revit, precios dinámicos de Amazon, reputación, contratos, negociación, legado, salud, viajes.

Anonimato y dark web no entran en ninguna versión de este producto. En 4.2.0 no se redactan contratos.
