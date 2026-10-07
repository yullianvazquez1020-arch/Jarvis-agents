# Jarvis 4.0.5: correcciones, seguridad y displays

Rama local `feature/voice-desktop`, sobre la 4.0.4 (`76df67f`), que a su vez sale del 4.0.3 desplegado (`3fc1e61`).
**No se publicó, no se hizo merge a `main` y no se desplegó. El trading real sigue apagado.**

Cada punto tiene su propio commit y su parche en la carpeta `parches/`, con el mismo número que la lista de instrucciones.

## Parte 1. Correcciones

| # | Qué corrige | Cómo |
|---|---|---|
| 1.1 | Un `main.py` sin `jarvis_desktop_api.py` al lado no arrancaba, aunque el escritorio estuviera apagado | El módulo solo se carga con `DESKTOP_API_ENABLED=true`. Si falta o falla al instalarse, se usa un stub que no hace nada. `/health` y `/diagnostico` dicen «apagado», «módulo ausente» o el error; el servidor nunca se cae por esto. |
| 1.2 | El canal de solo lectura dependía de lo que ve el modelo | Lista única `READ_ONLY_TOOLS` (27 herramientas). `run_tool` rechaza cualquier otra **antes del handler**, aunque se pase por error. `_WRITE_BLOCK` sigue como segunda cerradura. *Nota:* en la 4.0.4, `run()` ya rechazaba antes del handler lo que no estaba en la lista; esta es la cerradura adicional que pediste. |
| 1.3 | Pocas frases de acción se rechazaban | La Mac y el servidor rechazan igual: confirmar, aprobar, rechazar, modo real, enviar, anotar/apuntar, ejecutar, restaurar, borrar/eliminar, transferir/retirar, compra/vende/paga, `/comandos` y códigos de 6 dígitos. No salen del equipo. El API no tiene rutas de acción y `delegate` no está en la lista de lectura. |
| 1.4 | Al pasar de 3,000 movimientos se borraban los viejos casi en silencio | Cada recorte se registra y se avisa en la importación, en `/banco` (30 días) y en el brief (7 días), con la sugerencia de `/exportar movimientos`. Desde el 90 % se avisa **antes** de perder datos. El tope no se subió: `/diagnostico` mide cuántos KB ocupa el banco. |
| 1.5 | Nadie decía que el historial de charla vive en memoria | `/diagnostico` lo dice: «no sobrevive un deploy; tus datos sí». No se persiste la conversación, porque puede tener texto sensible. |
| 1.6 | `/confirmar` en línea sin documentar; una orden en «enviándose» se quedaba así para siempre | El trade-off queda explicado en el código del webhook. Al arrancar, y otra vez pasados 5 minutos, una orden real que quedó a medias pasa a «sin confirmar». Te llega un aviso: «revisa Coinbase antes de repetirla; no la repetí». Nunca se reenvía y el límite del día sigue contado. Una de práctica pasa a «fallida», sin efectos. |
| 1.7 | Sin Redis, los ids vistos de Telegram se borraban todos al pasar de 2,000 | Se expulsa solo el más viejo y la lista se guarda en un archivo local, así sobrevive un reinicio. |
| 1.8 | `SET` seguido de una comprobación aparte para tomar el liderazgo | Un solo script atómico (`_TAKE_LEADER`). No se usa NX porque un deploy nuevo debe desplazar al proceso viejo. El último en tomarlo escribe; el anterior recibe `StaleInstance`. Comprobado contra Redis real. |

## Parte 2. Seguridad

| # | Qué agrega |
|---|---|
| 2.1 | Máximo de 30 mensajes por minuto por clave en `/chat` y por chat en el webhook (`RATE_LIMIT_PER_MIN`, entre 1 y 120). Responde 429 antes de encolar nada; Telegram reintenta y no se pierde el mensaje. |
| 2.2 | El token de dispositivo vence a los 90 días y solo se renueva con `/emparejar` en tu chat privado; eso revoca el token anterior del mismo equipo. `/dispositivos` muestra alta, último uso, vencimiento y estado. En Upstash solo queda el hash. Si Jarvis responde 401, la Mac olvida el token y ofrece emparejar. |
| 2.3 | Auditoría del panel en `jarvis:desktop:audit` (últimas 500 entradas): equipo, hora, endpoint, resultado y tipo de turno. Sin preguntas, respuestas, montos ni tokens. Visible en `/dispositivos`. |
| 2.4 | Delegaciones: máximo 3 a la vez. Tras 3 fallos seguidos, el agente queda marcado caído 30 minutos, sin reintentar en cada mensaje. `/diagnostico` lo muestra. |

## Parte 3. Displays estilo Jarvis (Mac)

Mismo estilo en todo: azul casi negro, cian, tipografía mono y bordes finos.

- **Pantalla 1**
  - Barra superior con hora de Puerto Rico, versión, datos, IA, modo PRACTICE o REAL, Coinbase y trading real.
  - Punto cian si el servidor responde, ámbar si va lento o hace rato que no responde, rojo si no hay red.
  - En el centro, la última respuesta en texto grande. Abajo, Hablar (atajo Espacio), el indicador de micrófono y el modo discreto.
  - En modo discreto, montos, balances y códigos se enmascaran en pantalla hasta pulsar **Mostrar**, y no se leen en voz alta.
- **Pantalla 2 (`/hud`, solo lectura)**
  - Tarjetas: cobros, trabajos vencidos, agenda de hoy y mañana, balances con la fecha del dato, stock bajo, mensajes esperando `/enviar` y práctica simulada.
  - Si el dato del banco tiene más de 3 días, la tarjeta lo dice.
  - Tocar una tarjeta abre el detalle en la ventana principal, sin escribir nada.
- **Alertas** en una franja lateral: recordatorio, cuenta, evento o stock bajo.
  - Cada una sale **una vez**, también después de reiniciar, con botones Silencio y Repetir. Sin ventanas emergentes.
  - Llegan por un latido cada 3 minutos (estado y alertas en una sola solicitud), de solo lectura. No tocan el estado de avisos de Telegram.
- **Órdenes locales nuevas:** «enciende el micrófono» y «modo discreto» (activar y desactivar). «¿Cómo estás?» responde con la salud local (servidor, voz, micrófono y ventanas) y nunca da saldos.
- **DEMO:** estado, tarjetas y alertas rotulados DEMO, sin llamar a Render.
- **`python3 app.py --check`:** informa macOS, Python, el comando `say`, voces en español, micrófono y monitores (vía `system_profiler`), además de los motores de voz.

## Parte 4. Funciones

| # | Qué agrega |
|---|---|
| 4.1 | `/exportar movimientos`, `/exportar libros` o `/exportar trabajos`: CSV por Telegram, solo en tu chat privado. Cuentas solo con los últimos 4 dígitos, secretos filtrados y celdas neutralizadas para que una hoja de cálculo no ejecute fórmulas. |
| 4.2 | Descripción del banco normalizada al importar. La búsqueda encuentra «Home-Depot», «homedepot» o «panaderia espanola». Lo importado antes se normaliza al vuelo. |
| 4.3 | Moneda opcional en ingresos y gastos (USD por defecto; solo se guarda si es otra). Los totales, la ganancia y el estimado de impuestos son solo USD; las otras monedas van aparte. Jarvis nunca convierte. |

No se añadieron geocercas ni compras por voz.

## Extra: error encontrado al probar

Al correr la suite apareció una condición de carrera real, que ya existía en la 4.0.4. Mientras la Mac guardaba el token tras emparejarse, otro hilo podía leer el archivo vacío, creer que el token había sido revocado y borrarlo. Quedó corregido así:

- la escritura del archivo es atómica (archivo temporal más renombrado);
- un solo hilo reclama el emparejamiento;
- «sin token» ya no se confunde con «revocado».

Tiene 2 pruebas propias, y la suite pasó estable en 3 corridas seguidas.

## No se tocó

- Los límites de $100 por operación y $300 por día.
- El flujo `/aprobar` y `/confirmar`.
- Restaurar siempre deja PRACTICE.
- La cola durable y el fencing: solo se volvió atómica la toma de liderazgo.
- El enmascarado de secretos.
- Amazon y Coinbase nunca se delegan.
- Un solo worker.

Las pruebas de la 4.0.3 y la 4.0.4 que cubren todo esto siguen pasando.

## Variables nuevas

| Dónde | Variable | Valor |
|---|---|---|
| Render | `RATE_LIMIT_PER_MIN` | `30` (opcional) |
| Render | `DESKTOP_API_ENABLED` | `false` (sin cambio; ahora además decide si el módulo se carga) |

## Pruebas

**374 pruebas, 374 OK, 0 omitidas** (las 317 de la 4.0.4 más 57 nuevas).

Además hubo una prueba de punta a punta, con 13 comprobaciones OK: el acompañante real habló por HTTP con el `main.py` real más el adaptador, con la IA simulada. Cubrió emparejar, el estado de la barra, las tarjetas del HUD, abrir el detalle, la auditoría sin contenido y un equipo revocado. También se arrancó el proceso real del acompañante en DEMO y se comprobaron todas sus páginas.

La comprobación Lua corrió contra Redis 7 real local, con 15 chequeos OK, incluida la toma de liderazgo atómica.

**Cómo se corrió:** aquí no hay acceso a PyPI. Se usaron imitaciones mínimas de FastAPI, del SDK de Anthropic, de python-dotenv y de imageio-ffmpeg, solo para probar; no están en el ZIP. Fueron reales: Starlette, Pydantic, httpx 0.28.1, Redis 7 y Node 22.

## Lo que no se pudo ejecutar ni verificar

No ejecuté nada en Render, en Upstash, en Coinbase ni en Telegram real, ni en tu Mac. Por tanto quedan sin verificar:

- el arranque de la 4.0.5 en Render;
- los scripts Lua y el límite 429 contra Upstash y Telegram reales;
- el vencimiento de tokens y la auditoría con un dispositivo real;
- el envío del CSV por Telegram;
- el micrófono, la reproducción, las dos ventanas, el HUD en un segundo monitor y la apariencia real en Safari (no hay navegador aquí, así que la interfaz solo se probó por su HTTP y su JavaScript, no visualmente);
- el informe de micrófono y monitores de `--check`, que depende de `system_profiler` en macOS;
- whisper.cpp, `say` y Piper reales.

Repite la suite con las dependencias reales antes de publicar.
