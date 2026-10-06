# Jarvis 4.0.2 — revisión del parche de Claude

**Resultado: Listo para GitHub como paquete de código revisado. Todavía no desplegado ni verificado integralmente en producción.**

Base: repositorio `yullianvazquez1020-arch/Jarvis-agents`, commit `ab1830f`, más `jarvis-4.0.1.patch` de Claude y las correcciones descritas abajo. Se conservaron los cuatro módulos principales y sus funciones. No es la versión 4.2 completa: no incluye `jarvis_voice.py` ni `jarvis_ai/`. No promete conversación de voz en Mini App, OpenAI ni IA local que no estén implementados.

## Cambios adicionales a Claude

| Archivo | Problema comprobado | Corrección |
|---|---|---|
| main.py | La cola guardaba el mensaje original, incluidas claves, antes de aplicar el filtro | Redacción de patrones de secretos conocidos antes de persistir texto/caption/estructura. Las confirmaciones se procesan directamente, sin guardar su código en la cola. |
| main.py | Un error de historial después de ejecutar herramientas podía volver a pedir la acción al modelo | Se permite reparación automática solo antes de intentar herramientas en esa petición. |
| main.py | Respuestas vacías o cortadas podían dejar llamadas de herramientas sin resultado en el historial | Se guarda texto válido en las respuestas finales, incluso vacías o truncadas; llamadas incompletas no se ejecutan. |
| main.py | El parche permitía escrituras sin protección si Redis EVAL fallaba | Arranque y escrituras bloqueados si no se puede establecer protección. No hay degradación silenciosa a escrituras desprotegidas. |
| main.py | La toma de trabajo en Redis era una secuencia no atómica; una cancelación borraba el trabajo | Toma atómica con Lua; trabajos cancelados o fallidos quedan marcados para revisión, sin repetición automática. |
| main.py | Una escritura local fallida podía marcar prematuramente una actualización como vista | Se marca después de persistir. |
| main.py | Una bandera heredada podía habilitar la API privada de Coinbase | Nuevo `CRYPTO_PRACTICE_ONLY=true` por defecto: bloquea toda la API privada, aunque `COINBASE_TRADING_ENABLED=true`. Las funciones reales se conservan, desactivadas. |
| main.py | Faltaban correcciones independientes presentes en main(2).py | Coincidencia por palabras de clientes, facturas del mes anterior, exclusión de reembolsos y aislamiento de fallos del resumen/respaldo. |
| jarvis_extensions.py | /audio enviaba texto sin redacción al sintetizador | Redacción antes de enviarlo. |
| tests/ | Dos cargas del mismo módulo cambiaban el core compartido; deduplicación de Telegram sobrevivía entre pruebas | Un core de pruebas y reinicio del estado entre casos. |
| requirements.txt | Pydantic se importaba sin declararse directamente; versiones directas flotantes | Pydantic explícito y versiones directas fijadas a las probadas. |
| .gitignore | Solo excluía `.env` exacto | También excluye variantes `.env.*` salvo plantilla, claves privadas, JSON de datos, entornos y cachés. |

El filtrado de secretos es detección de patrones, no una garantía universal. Imágenes y audio enviados a proveedores de visión/transcripción se procesan allí: el filtro de texto no puede prometer ocultar previamente todo lo visible o hablado. No se detectaron credenciales reales incrustadas en la revisión de archivos actuales; esto no es una auditoría de todo el historial de GitHub. Las cadenas de pruebas son sintéticas.

## Seguridad del dinero

- Máximos en código: $100 por operación y $300 diarios, con fecha de Puerto Rico. Las variables solo permiten reducirlos.
- Códigos de seis dígitos, un solo uso, vencimiento de cinco minutos; se conserva el bloqueo por intentos incorrectos.
- Aprobaciones de operaciones restringidas al ID del dueño, desde su chat privado; no son herramientas de la IA.
- Práctica autónoma con dinero simulado y precios públicos. No requiere credenciales de Coinbase y no llama a su API privada.
- Mantener `CRYPTO_PRACTICE_ONLY=true` y `COINBASE_TRADING_ENABLED=false`. No se activó ni probó trading real. La rama real conservada requiere una revisión separada antes de habilitarla; sus límites usan estimaciones previas a la ejecución.
- Mensajes a clientes siguen necesitando `/enviar`; acciones externas `/ejecutar`. Amazon no compra; las publicaciones existentes requieren aprobación.

## Verificaciones realizadas

- Sintaxis y análisis estático de los cuatro módulos y del script de webhook: sin nombres indefinidos detectados.
- Importación completa y arranque real mediante Uvicorn con entorno aislado, sin credenciales reales.
- 227 ejecuciones de pruebas con servicios simulados, sin fallos. Incluyen pruebas heredadas repetidas por la estructura de clases; no son 227 escenarios únicos.
- 16 regresiones nuevas cubren cola y secretos, cancelación, historial, práctica privada bloqueada, códigos vencidos/reutilizados, dueño y chat privado, webhook, clientes, facturas, reembolsos y tareas.
- Todos los nombres de funciones y clases originales de los cuatro módulos permanecen. Las pruebas respaldan compatibilidad en los escenarios cubiertos; no prueban cada posible integración real.
- `pip check` y dependencias directas instaladas en Python 3.12.14.
- Anthropic, Telegram y Coinbase se simularon en pruebas. Los scripts Lua sí se ejecutaron contra un Redis real local (ver "Revisión: cola sin cjson"); contra Upstash todavía no. El arranque rechaza Upstash sin soporte de EVAL, y esto debe comprobarse antes o durante el despliegue.
- Consulta pública de producción el 6 de octubre de 2026, 18:10 hora PR: versión 4.0.0, Upstash, Telegram declarado configurado, práctica activa, Coinbase desconectado y trading apagado, límites 100/300. No se cambió producción.

## Revisión: cola de Telegram sin `cjson`

**Por qué.** El script Lua que toma cada mensaje de la cola usaba `cjson` (librería JSON dentro de Lua). No estaba confirmado que Upstash la ofrezca. Si faltaba, Jarvis arrancaba normal pero ningún mensaje de Telegram se procesaba.

**Qué cambió (solo `main.py`, función de cola):**
- Cada trabajo se guarda con `"state"` como primera clave (`_tg_job_json`). Un trabajo en cola siempre empieza por `{"state": "queued", `.
- `_CLAIM_JOB` ya no decodifica JSON: compara ese inicio y lo cambia por `{"state": "running", "started": "...", `. Solo usa `GET`, `SET` y la librería de texto estándar de Lua.
- Se conserva todo lo de antes: un mensaje repetido por Telegram se ignora (`_ENQUEUE`, sin cambios), la toma es atómica y sucede una sola vez, y una instancia vieja no puede tomar ni escribir.
- Un trabajo con formato desconocido no se ejecuta a ciegas: se responde `BADFORMAT`, queda intacto y la recuperación lo reporta como vencido a las 6 horas.
- Producción (4.0.0) no tiene cola, así que no hay trabajos viejos que convertir. Las claves de datos no cambian.

**Archivos nuevos:**
- `scripts/check_redis_lua.py`: ejecuta los scripts reales de `main.py` contra Upstash con claves temporales `jarvis:selftest:*`. No toca `jarvis:leader`, la cola ni tus datos, y cuesta unos 25 comandos. Solo usa la librería estándar de Python.
- `tests/test_redis_lua.py`: los mismos chequeos contra un `redis-server` real local. No requiere instalar paquetes; se salta si no hay `redis-server`.
- `tests/test_hardening.py`: el Redis simulado imita el script nuevo, y hay dos pruebas nuevas (texto con comillas, ñ, emoji y un prefijo falso; formato desconocido).

**Qué se probó en esta revisión (Redis 7.0.15 real, local):**
- 14 chequeos de los scripts reales, todos OK. Cubren: sin librerías opcionales, NEW y luego DUP, instancia vieja bloqueada (FENCED) al encolar, tomar y escribir, JSON válido tras la toma, mensaje idéntico, segunda toma vacía, expiración conservada, formato desconocido rechazado y escritura protegida.
- Ocho conexiones distintas intentan tomar el mismo trabajo y solo una lo consigue.
- Prueba de mutación: si se rompe el prefijo, los chequeos fallan, así que la prueba sí detecta errores.
- Integración: el código Python de `main.py` (`fence_take_leadership`, `_tg_enqueue`, `_tg_claim`, `_tg_process`, la recuperación al arrancar, `kv_set` y el rechazo a una instancia vieja) contra ese Redis real. `/ayuda` se procesó una sola vez y la cola quedó vacía. Esto se corrió con dependencias simuladas (FastAPI y Anthropic de mentira), porque el entorno no podía instalar paquetes.

**Qué NO se pudo verificar sin Render/Upstash:**
- Los scripts en **Upstash** de verdad. Upstash es compatible con Redis, pero no es el mismo servidor. Para comprobarlo, corre `scripts/check_redis_lua.py` (paso 0 abajo).
- Las 229 pruebas completas con las librerías reales. En esta revisión no se pudieron instalar (sin acceso a PyPI). La entrega anterior reportó 227 OK; faltan por correr las 2 nuevas junto a ellas.
- El arranque real en Render, el webhook de punta a punta y el acceso de tu cuenta al modelo.

**Riesgos que quedan:**
- Si Upstash rechaza `EVAL`, Jarvis 4.0.2 no arranca. Render mantiene la versión anterior viva, así que no hay caída, pero tampoco hay actualización.
- Cada mensaje y cada paso del programador hacen una lectura extra a Upstash para la protección (unos 3,000 comandos más al día: al menos dos por minuto, más los de avisos y práctica). Revisa el consumo en Upstash la primera semana.
- `/confirmar` se deduplica solo en memoria del proceso. Un reintento de Telegram justo durante un deploy podría llegar dos veces; el código de un solo uso impide que se ejecute dos veces.
- Si algún día otra versión escribe trabajos en la cola con otro orden de claves, esos trabajos no se ejecutan: se reportan como vencidos a las 6 horas.

### Paso 0 antes de desplegar: probar Upstash desde tu Mac

En Terminal, dentro de la carpeta `jarvis-4.0.2`:

```bash
export UPSTASH_REDIS_REST_URL='https://...upstash.io'
export UPSTASH_REDIS_REST_TOKEN='...'
python3 scripts/check_redis_lua.py
```

Copia los valores desde Upstash (botón de copiar, no a mano). El token no se imprime. Si todo sale ✅, Upstash ejecuta los scripts de Jarvis. Si algo sale ❌, no despliegues y comparte el resultado (sin el token).

## Variables que debes configurar o conservar en Render

No borres variables existentes ni pegues claves reales en GitHub. `.env.example` contiene nombres y valores no secretos de referencia.

| Variable | Valor para este despliegue |
|---|---|
| AGENT_API_KEY | Conservar tu clave maestra privada y robusta; obligatoria para arrancar |
| ANTHROPIC_API_KEY | Tu clave válida de Anthropic para conversación/visión; sin ella funcionan comandos deterministas |
| CLAUDE_MODEL | `claude-sonnet-5-5`; identificador verificado en documentación oficial, acceso de tu cuenta pendiente |
| TELEGRAM_BOT_TOKEN | Token de tu bot, conservar el actual |
| TELEGRAM_WEBHOOK_SECRET | Secreto del webhook, 1–256 caracteres A–Z, a–z, 0–9, guion o guion bajo; debe coincidir con setWebhook |
| TELEGRAM_OWNER_ID | ID numérico de tu chat privado con el bot |
| TELEGRAM_OWNER_USER_ID | Tu ID numérico personal; en chat privado normalmente coincide con OWNER_ID |
| UPSTASH_REDIS_REST_URL | URL HTTPS REST de la base existente |
| UPSTASH_REDIS_REST_TOKEN | Token REST de esa misma base; necesita permisos para las operaciones y EVAL usados |
| OWNER_NAME | `Yullian` |
| BUSINESS_NAME | `ISLAFIX PRO LLC` |
| TZ_NAME | `America/Puerto_Rico` |
| CRYPTO_PRACTICE_ONLY | `true` |
| COINBASE_TRADING_ENABLED | `false` |
| MONEY_MAX_ORDER_USD | `100` |
| MONEY_MAX_DAY_USD | `300` |
| PAPER_TRADING_ENABLED | `true` |
| PAPER_START_USD | `1000` simulados; no reinicia el estado existente |
| PAPER_PRODUCTS | `BTC-USD,ETH-USD,SOL-USD` |
| PAPER_EVERY_HOURS | `1` |
| PAPER_REPORT_HOUR | `20` |
| SCHEDULER_ENABLED | `true` |
| SCHEDULER_INTERVAL_SECONDS | `60` |
| DAILY_BRIEF_HOUR | `8` para el resumen de las 8 a. m.; el valor predeterminado del código sigue siendo 7 |
| MARKET_ANALYSIS_ENABLED | `false` para evitar informes de IA programados de pago por esta opción |

`PORT` lo suministra Render. No hace falta escribirlo manualmente. `AGENT_API_KEY` no es una clave de OpenAI ni de Anthropic. Las claves API de esos proveedores son independientes de las suscripciones de chat.

### Opcionales: solo si utilizas la función

| Función | Variables exactas / valores predeterminados |
|---|---|
| Calendario y avisos | `CAL_ALLDAY_HOUR=9`, `BILL_NOTICE_DAYS=2` |
| Banco por archivos | `BANK_DEFAULT_NAME=FirstBank`, `BANK_BIG_AMOUNT=1000`, `BANK_LOW_BALANCE=0`, `BANK_STALE_DAYS=7` |
| Resumen bancario | `BANK_WEEKLY_ENABLED=true`, `BANK_WEEKLY_DAY=0` (lunes), `BANK_WEEKLY_HOUR=8` |
| Avisos de clientes | `CLIENT_NOTICES_ENABLED=true`, `CLIENT_NOTICE_HOUR=9`, `OUTBOX_MAX_PER_DAY=20` |
| SMS/WhatsApp con Twilio | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` |
| Email con Resend | `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_REPLY_TO` (opcional) |
| Agentes externos | `CALL_AGENT_URL`, `SMS_AGENT_URL`, `EMAIL_AGENT_URL`, `CALENDAR_AGENT_URL`; HTTPS de confianza |
| Credencial externa | `EXTERNAL_AGENT_KEY`, diferente de `AGENT_API_KEY`; no hay fallback a la clave maestra |
| Restricción de destinos | `EXTERNAL_AGENT_HOSTS`, dominios separados por comas |
| Eventos entrantes | `INCOMING_AGENT_API_KEY` |
| Transcripción | `STT_AGENT_URL`, `STT_AGENT_API_KEY` |
| Síntesis de audio | `TTS_AGENT_URL`, `TTS_AGENT_API_KEY` |
| Investigación con IA | `WEB_SEARCH_ENABLED=true`, `MARKET_ANALYSIS_HOURS=6`; solo el informe automático se controla con MARKET_ANALYSIS_ENABLED. Las investigaciones pedidas y watches existentes pueden consumir tokens. |
| Parámetros simulados | `PAPER_FEE_PCT=0.6`, `PAPER_SIZE_PCT=25`, `PAPER_STOP_PCT=5`, `PAPER_TAKE_PCT=10`, `PAPER_TRADE_ALERTS=true` |
| Riesgo simulado adicional | `PAPER_DAILY_LOSS_PCT=5`, `PAPER_MAX_DRAWDOWN_PCT=15`, `PAPER_MAX_ENTRIES_PER_DAY=6` |
| Amazon Seller | `AMAZON_CLIENT_ID`, `AMAZON_CLIENT_SECRET`, `AMAZON_REFRESH_TOKEN`, `AMAZON_SELLER_ID`, `AMAZON_MARKETPLACE_ID`, `AMAZON_REGION=na` |
| Investigación de YouTube | `YOUTUBE_API_KEY` |
| Subida/publicación YouTube con aprobación | `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`, `YOUTUBE_CHANNEL_ID` |
| Archivos locales | `DATA_DIR=.`; no sustituye Upstash con persistencia garantizada en este despliegue |

No necesitas `COINBASE_API_KEY_NAME` ni `COINBASE_API_PRIVATE_KEY` para práctica. Si existen, el modo de práctica las deja sin uso. También se conservan los nombres heredados `COINBASE_MAX_ORDER_USD` y `COINBASE_MAX_DAY_USD` como alternativas de límites, subordinadas a MONEY_MAX_* y a los máximos del código. `COINBASE_AGENT_URL` nunca se delega; `AMAZON_AGENT_URL` no habilita compras y no es necesario para la integración Seller directa.

`OPENAI_API_KEY` aparece únicamente en la lista de secretos a ocultar: esta versión no implementa un proveedor OpenAI. `OPENAI_MODEL`, `OPENAI_REVIEW_MODEL`, `OPENAI_REASONING_EFFORT`, `OPENAI_BASE_URL`, `CLAUDE_REVIEW_MODEL`, `AI_ROUTER_MODE`, `LOCAL_LLM_URL` y `LOCAL_LLM_MODEL` no activan un router en esta entrega.

## Instalar, verificar y publicar

1. Guarda un `/backup` autenticado de producción de forma privada antes de desplegar. No lo subas al repositorio.
2. Usa una rama basada en `ab1830f`. El parche acumulado de esta entrega ya incluye el trabajo de Claude: no apliques ambos parches sobre la misma copia. Ejecuta `git apply --check jarvis-4.0.2.patch` antes de aplicarlo. Si el repositorio avanzó, revisa conflictos; no fuerces el reemplazo.
3. En un entorno aislado: `python -m pip install -r requirements.txt`; luego `python -m unittest discover -s tests -q`.
4. Revisa el diff y publica los archivos en el repositorio correcto. La entrega actual no hizo push ni inició un deploy.
5. Render: Web Service Python; un worker y una instancia. Conserva la configuración y base de datos existente. Build: `pip install -r requirements.txt`.
6. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1`. Comprobar `GET /` con versión 4.0.2, almacenamiento Upstash y `coinbase.practice_only=true`, `coinbase.trading=false`.
7. Si el arranque rechaza Redis EVAL, no desactives la protección: confirma permisos y soporte del servicio antes de continuar.
8. Comprobar el webhook usando el script de abajo y enviar `/diagnostico`, `/hoy`, `/clientes`, `/trabajos`, `/inventario`, `/banco`, `/practica`, `/seguridad` desde tu chat privado. Verificar respuesta y logs. No ejecutar órdenes reales como prueba.
9. Probar `/aprobar 0` y el comando `/confirmar 0 CÓDIGO` que devuelva el bot: es una prueba del gate sin movimiento de dinero.

### Webhook

URL esperada: `https://jarvis-agents.onrender.com/telegram`. Se usa POST y el header `X-Telegram-Bot-Api-Secret-Token`. La ruta rechaza solicitudes sin el secreto correcto.

Con variables disponibles en el entorno del servidor, comprobar:

```bash
python scripts/check_telegram.py --url https://jarvis-agents.onrender.com/telegram
```

Solo si hay que registrarlo o actualizarlo:

```bash
python scripts/check_telegram.py --set --url https://jarvis-agents.onrender.com/telegram
```

El script no imprime tokens ni descarta actualizaciones pendientes. `getWebhookInfo` no devuelve el secreto configurado: se valida de extremo a extremo enviando un comando real del dueño y comprobando su respuesta. Esta revisión no tuvo acceso al token, a las variables privadas ni a los logs de Render: el registro efectivo del webhook sigue pendiente de comprobar.

### Reversión

Conserva el commit anterior y el backup privado. Revierte el commit de esta entrega si el despliegue falla. Los campos añadidos son compatibles con la base, pero la versión 4.0.0 no recupera su cola nueva y pierde las protecciones añadidas. No habilites trading al revertir. No restaures datos encima de actividad posterior sin revisar qué se sustituye.

## Fuentes oficiales consultadas

- https://render.com/docs/deploy-fastapi
- https://core.telegram.org/bots/api#setwebhook
- https://core.telegram.org/bots/api#getwebhookinfo
- https://platform.claude.com/docs/en/models/overview

**Listo para GitHub. Pendiente para confirmar producción: `scripts/check_redis_lua.py` contra Upstash, suite completa con dependencias reales, publicación, deploy, variables privadas, acceso al modelo y webhook de extremo a extremo.**
