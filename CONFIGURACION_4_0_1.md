> Documento histórico de Claude. Para el paquete corregido utiliza CONFIGURACION_4_0_2.md: sustituye las instrucciones de seguridad, pruebas y despliegue de este documento.

# Jarvis 4.0.1: corrección de seguridad y confiabilidad

Base: 4.0.0 (commit `ab1830f`, la versión publicada en Render el 6 oct 2026).
Esta versión no trae las mejoras de 4.2.0. Esas se integran cuando estén disponibles `main(2).py`, `jarvis_voice.py` y `jarvis_ai/`.

## Qué cambia

| | Problema confirmado en 4.0.0 | Corrección |
|---|---|---|
| A | `delegate()` del núcleo podía llamar agentes externos con solo invocarla. El borrador lo imponía `jarvis_extensions`, no el núcleo. | `delegate()` exige el ID de una acción aprobada con `/ejecutar`. Coinbase y Amazon nunca se delegan, ni siquiera con aprobación. Si una acción falla, queda como `failed` y ya no se queda en `sending`. |
| B | Se enviaba `AGENT_API_KEY` (la clave maestra de `/chat` y `/backup`) a los agentes externos. Con esa clave, un agente externo podía usar `/chat` con todas las herramientas. | Se usa una clave separada, `EXTERNAL_AGENT_KEY`, obligatoria, distinta de la maestra y sin alternativa. El destino debe ser HTTPS, con dominio público, sin credenciales y sin redirecciones. Se puede limitar con la lista `EXTERNAL_AGENT_HOSTS`. |
| C | No había protección de secretos. | Se ocultan claves, tokens, claves privadas, contraseñas y tarjetas (con validación Luhn) antes de llegar a la IA, al historial, a las notas, a los dictados, a los eventos entrantes, a los resultados de herramientas, a los mensajes de Telegram y a los logs. |
| D | Sin clave de Anthropic, cada mensaje fallaba con un error genérico. | Si la clave falta o es ficticia, no se hace ninguna llamada de pago y Jarvis lo dice. Los comandos deterministas siguen funcionando. |
| E | Un historial dañado dejaba a Jarvis fallando en cada mensaje. | Solo los errores de historial lo reinician, una sola vez. Los errores de modelo o de parámetros conservan el historial y muestran la causa. |
| F | La importación bancaria perdía movimientos reales: un movimiento con la misma fecha y monto que otro ya guardado se descartaba aunque fuera de otro comercio. | La deduplicación usa FITID, saldo corrido y palabras del comercio. Reimportar el mismo archivo, o el mismo movimiento en CSV y luego en QFX, sigue marcándose como duplicado. |
| G | `/backup` solo guardaba la auditoría del gate, no el gasto diario ni los bloqueos. No había restauración. | `/backup` incluye el gate completo, sin los códigos de un solo uso. `POST /restore` hace una simulación por defecto. Al restaurar conserva el gasto más alto de cada día y el bloqueo más reciente, une la auditoría, anula los códigos, vence las órdenes de Coinbase y las acciones externas pendientes, y guarda antes una copia del estado actual. |
| H | `_first_time()` marcaba el update antes de hacer el trabajo: si el proceso caía, el mensaje se perdía y el reintento quedaba bloqueado. Durante un deploy, dos procesos podían pisarse los datos. | Cada update se guarda en una cola persistente antes de responder 200. Al arrancar, lo que quedó en cola se ejecuta una sola vez. Lo que se interrumpió a medias no se repite: se te avisa para que lo revises. Las escrituras en Upstash llevan una protección contra instancias viejas, sin comandos extra. |
| I | Comentarios falsos ("no existe ninguna función que mueva dinero"), versiones mezcladas (3.9.0 y 4.0.0) y contradicciones en el prompt. | Hay una sola `VERSION`. La ayuda y la salud reflejan lo que está realmente configurado. Nuevo comando `/diagnostico`. |

Sin cambios: los límites de $100 por operación y $300 por día, la doble confirmación, la aprobación de mensajes a clientes con `/enviar`, la zona horaria America/Puerto_Rico y las claves de datos existentes.

## Variables en Render

Las variables existentes no cambian. Hay una nueva, que solo se necesita si conectas agentes externos.

| Variable | Obligatoria | Nota |
|---|---|---|
| `AGENT_API_KEY` | Sí | Clave maestra para `/chat`, `/backup` y `/restore`. Nunca se envía a terceros. |
| `ANTHROPIC_API_KEY` | Para la IA | Sin ella, los comandos funcionan y la IA dice que no está configurada. |
| `CLAUDE_MODEL` | No | Por defecto `claude-sonnet-5-5`. `/diagnostico` confirma si tu cuenta tiene acceso. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_OWNER_ID` | Sí | Sin cambios. |
| `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | Sí | Sin cambios. |
| `EXTERNAL_AGENT_KEY` | Solo con agentes externos | Nueva. Debe ser distinta de `AGENT_API_KEY`. Si no está, los agentes externos quedan bloqueados. |
| `EXTERNAL_AGENT_HOSTS` | No | Lista de dominios permitidos, separados por comas. |
| `COINBASE_TRADING_ENABLED` | No | Déjala en `false` para seguir en práctica. |

Comando de inicio: `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1`. Usa una sola instancia.

## Pruebas locales

```
python tests/test_jarvis.py      # 28
python tests/test_extensions.py  # 58
python tests/test_growth.py      # 77
python tests/test_hardening.py   # 48, nuevas de 4.0.1
```

Todas usan servicios simulados: sin dinero, mensajes, tokens ni Upstash reales.

## Restaurar una copia

1. Obtén la copia: `GET /backup` con el header `x-api-key`.
2. Simula: `POST /restore` con `{"backup": <copia>}`. No cambia nada; te dice qué haría.
3. Aplica: `POST /restore` con `{"backup": <copia>, "confirm": "RESTAURAR"}`. Antes guarda el estado actual en `jarvis:backup:prerestore:<fecha>` durante 30 días.

## Volver a 4.0.0

En Render, ve a Deploys, busca el deploy del commit `ab1830f` y elige "Rollback".
En GitHub, la alternativa es `git revert <commit 4.0.1>` en `main`.
Los datos son compatibles en ambos sentidos: 4.0.1 solo añade campos (`bal` y `src` en el banco; `gate` en la copia de seguridad) y las claves `jarvis:tg:job:*`, que 4.0.0 ignora.
