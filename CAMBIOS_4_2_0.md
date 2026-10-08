# Cambios 4.2.0

Corte aditivo sobre `main.py` 4.1.0. No reescribe el orquestador. Un worker. Topes $100 por orden y $300 por día sin cambios. Sin autoenvío, sin órdenes reales, sin Twilio real, sin Amazon ni Coinbase delegados. `/confirmar` sigue fuera de la cola durable. `EXTERNAL_AGENT_KEY` sigue distinta de `AGENT_API_KEY`.

El dueño controla el deploy. Esta nota no promete dejar de actualizar.

## Qué entró

1. Agente local sin tokens para el día a día: atajos previos intactos; `/perfil`, `/flujo`, `/monetizar`, `/canal` y `/urgente` no llaman al modelo. El chat libre que no cubre una regla sigue el camino actual. `JARVIS_SHORT_MODEL` vacío no cambia el modelo; si se pone, solo se usa después de fallar la regla local.
2. Historial persistente: se sigue guardando en `jarvis:history` con redacción de secretos antes de escribir. El sellado AES-256-GCM existente (`DATA_ENCRYPTION_KEY`, `jarvis_seal`) lo cifra si la clave está puesta. `/diagnostico` dice si sobrevivió el reinicio (marca de arranque anterior y mensajes guardados).
3. Perfil de decisión (`jarvis:profile`): metas, debilidades, fortalezas, beneficio del dueño y techo. Se consulta antes de proponer. El techo no puede pasar $100. No mueve dinero fuera del gate.
4. Monetización: propuestas de cash flow (YouTube, Amazon, libros) con costo-beneficio. No ejecuta ni publica ni compra. El scheduler corre un ciclo acotado (`JARVIS_COMPUTE_BUDGET`, default 6/día) y se detiene. No hay bucle infinito.
5. Autoapagado: gasto raro o delegación rara (incluye Coinbase/Amazon) reusa lockout y auditoría del money gate. No sube topes.
6. Número Twilio propio: borrador SMS, WhatsApp o llamada y `/enviar cN`. No marca ni envía en este corte (`TWILIO_SEND_ENABLED` no abre envío real). Telegram sigue en el bot actual. Llamada solo si el dueño marcó urgente (`/urgente cash-flow|camara|emergencia`).
7. Cash-flow temprano: compara el neto de los libros con gastos del mes aún no pagados y avisa antes de proponer gasto. No paga.
8. Regresión: `tests/test_v420.py` con almacén simulado. Cubre reglas locales, historial, perfil, presupuesto, lockout, 2FA de canal y topes $100/$300.
9. Seguridad del corte: no se sueltan contraseñas, códigos ni datos financieros aunque la petición parezca del dueño. 2FA de un solo uso en el canal Twilio. Dinero fuera del proceso de credenciales. Firewall y VPN sin logs quedan como configuración de Render, no como código.
10. Actualización: el dueño despliega. No hay promesa de “nunca más actualizar”.

## Fuera de 4.2.0 (4.3+)

Cara, holograma, Live2D/VRM, Rhubarb, narración visual, MediaPipe, Leap Motion, Ojo de Dios, Ring/Eufy, CarPlay, modo familiar, red de mini Jarvises, pipeline Revit, precios dinámicos de Amazon, reputación, contratos, negociación, legado, salud, viajes.

Anonimato y dark web no entran en ninguna versión de este producto.

Legal: redactar sí, firmar no. En 4.2.0 no se redactan contratos.

Mac 2015 no es el servidor de clientes.
