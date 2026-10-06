# Jarvis 4.0.3: modo cripto PRÁCTICA o REAL desde Telegram

Base: 4.0.2 con la cola de Telegram sin `cjson` (`Jarvis-4.0.2-sin-cjson.zip`). Todo lo de 4.0.2 se conserva: no se borró ninguna función ni clave de datos, y la corrección de `cjson` sigue igual.

**Estado:** el código está listo y probado con servicios simulados. **No se publicó, no se desplegó y no se activó trading real.** La conexión real con Coinbase **no está verificada**.

---

## 1. Qué cambia

| | Antes (4.0.2) | Ahora (4.0.3) |
|---|---|---|
| Elegir el modo | Solo con variables de Render | `/cripto modo`, `/cripto modo practica` y `/cripto modo real`, desde tu chat privado |
| Modo por defecto | Práctica | Práctica (igual) |
| Entrar a REAL | No existía como paso aparte | `/cripto modo real` te da un código de 6 dígitos (vence en 5 min, un solo uso), y luego `/confirmar modo CÓDIGO` |
| Volver a práctica | — | `/cripto modo practica`, inmediato y sin código |
| Órdenes en práctica | No se podían preparar con `CRYPTO_PRACTICE_ONLY=true` | Se preparan y ejecutan en una **cuenta simulada aparte**, con el mismo `/aprobar` + `/confirmar` |
| Órdenes reales | `/aprobar` + `/confirmar` si las variables lo permitían | Igual, **y además** el modo REAL seleccionado por ti, comprobado otra vez justo antes del envío |

### Las capas de seguridad (cada una sola puede impedir una orden real)

1. **`CRYPTO_PRACTICE_ONLY=true`** es el bloqueo superior. Ningún comando lo salta; solo se cambia en Render.
2. Además hacen falta las credenciales de Coinbase y `COINBASE_TRADING_ENABLED=true`. **Poner estas variables NO selecciona el modo real.** Si Jarvis arranca y estas variables ya no permiten real, el modo guardado vuelve a práctica. Así, volver a habilitarlas después no reactiva real sin un código nuevo.
3. **Tú eliges REAL** con código de un solo uso, solo desde tu usuario y tu chat privado. Un usuario extraño se ignora; desde un grupo se rechaza y queda en la auditoría.
4. **El modo REAL no autoriza nada.** Cada orden sigue necesitando `/aprobar N` y `/confirmar N CÓDIGO`, con $100 por operación y $300 por día. La IA puede *preparar* una orden, pero no tiene herramienta para aprobar, enviar ni cambiar el modo.
5. **Estado dudoso = real bloqueado.** Si el modo guardado falta, está dañado o Upstash no responde, Jarvis muestra práctica y bloquea las órdenes reales.
6. **Último control.** Justo antes de enviar a Coinbase se vuelven a comprobar el modo, la "época" del modo, las variables y el almacenamiento. Además, el código que habla con Coinbase rechaza cualquier envío de orden que no venga de ese paso final, para esa orden exacta.

### Separación de cuentas

| Registro | Clave en Upstash | Qué guarda |
|---|---|---|
| Cuenta de **práctica manual** (nueva) | `jarvis:crypto:practice` | Efectivo simulado (empieza con `PAPER_START_USD`), posiciones, órdenes simuladas y su propio gasto del día |
| **Real** | `jarvis:crypto` (ya existía) | Propuestas, órdenes enviadas y movimientos de Coinbase |
| Simulador automático **`/practica`** | `jarvis:paper` (ya existía) | No cambia y no se mezcla con lo anterior |
| **Modo** (nueva) | `jarvis:crypto:mode` | Modo seleccionado, época e historial de cambios |
| Límites y auditoría | `jarvis:gate` (ya existía) | El gasto **real** del día; la práctica no lo consume |

- Las órdenes de práctica usan solo el precio **público** de Coinbase. Nunca llaman a la API privada.
- Cada propuesta queda marcada con su modo y su época. Al cambiar de modo, las propuestas pendientes y sus códigos se anulan, y los registros no se borran.
- Las órdenes reales ya enviadas, "enviándose" o "sin confirmar" **se siguen rastreando** y no se tocan.

### Protección contra duplicados y resultados inciertos (se conserva)

- La orden pasa a "enviándose" y se guarda **antes** de ejecutarse, así que un segundo `/confirmar` no la repite.
- Coinbase recibe el mismo `client_order_id` de siempre.
- Si no se sabe si Coinbase recibió la orden, queda "sin confirmar". Nunca se reenvía sola y el límite del día no se devuelve.
- Si el modo cambia entre tu `/confirmar` y el envío, la orden se cancela antes de salir y el límite se devuelve.

### Restaurar copias

`/restore` deja siempre el modo en **PRÁCTICA**. El modo nunca se restaura desde una copia. La cuenta de práctica sí se incluye en `/backup`.

---

## 2. Comandos (sin gastar tokens)

| Comando | Qué hace |
|---|---|
| `/cripto` | Cuenta del modo activo: práctica (simulada) o Coinbase real (solo lectura) |
| `/cripto practica` · `/cripto real` | Ver una cuenta en particular sin cambiar el modo |
| `/cripto movimientos` | Historial del modo activo |
| `/cripto modo` | Modo activo, si real está disponible y qué falta |
| `/cripto modo practica` | Vuelve a práctica **al instante** |
| `/cripto modo real` | Pide un código para activar real (no compra nada) |
| `/confirmar modo CÓDIGO` | Activa real si todo se cumple otra vez |
| `/aprobar N` → `/confirmar N CÓDIGO` | Ejecuta una orden preparada, en el modo en que se preparó |
| `/rechazar N` | Descarta una propuesta |
| `/seguridad` · `/diagnostico` | Muestran el modo, los límites y los intentos |

Las propuestas, las aprobaciones, las confirmaciones y los resultados llevan la etiqueta **[🧪 PRÁCTICA]** o **[💵 REAL]**.

---

## 3. Variables exactas en Render

### Configuración recomendada hoy (solo práctica)

| Variable | Valor |
|---|---|
| `CRYPTO_PRACTICE_ONLY` | `true` |
| `COINBASE_TRADING_ENABLED` | `false` |
| `COINBASE_API_KEY_NAME` | vacía o sin definir |
| `COINBASE_API_PRIVATE_KEY` | vacía o sin definir |
| `MONEY_MAX_ORDER_USD` | `100` (solo puede bajar el máximo, nunca subirlo) |
| `MONEY_MAX_DAY_USD` | `300` (igual) |
| `PAPER_START_USD` | `1000`, saldo inicial de las cuentas simuladas |
| `TELEGRAM_OWNER_ID` / `TELEGRAM_OWNER_USER_ID` | Tus IDs (sin cambios) |

Con esto, `/cripto modo real` responde "⛔ No puedo activar el modo REAL" y explica por qué.

### Para que el modo REAL quede *disponible* (cuando decidas, no ahora)

Las cuatro condiciones a la vez:

| Variable | Valor |
|---|---|
| `CRYPTO_PRACTICE_ONLY` | `false` |
| `COINBASE_TRADING_ENABLED` | `true` |
| `COINBASE_API_KEY_NAME` | Nombre de tu llave de Coinbase (CDP, ES256), por ejemplo `organizations/.../apiKeys/...` |
| `COINBASE_API_PRIVATE_KEY` | La llave privada `-----BEGIN EC PRIVATE KEY-----...` |

Y `TELEGRAM_OWNER_USER_ID` configurado.

Aun con todo esto, **Jarvis sigue en PRÁCTICA** hasta que escribas `/cripto modo real` y confirmes el código.

Recomendación para la llave de Coinbase: crea una llave nueva solo con permisos de **ver** y **operar (trade)**, **sin permiso de transferir o retirar**. Jarvis no tiene código de retiros ni transferencias, y la llave tampoco debería permitirlo. Revisa los permisos exactos en la consola de Coinbase al crearla; no se verificaron en esta revisión.

---

## 4. Qué se probó y qué falta

### Probado en esta revisión

- **263 pruebas, todas OK, 0 omitidas.** Son las 232 anteriores más 31 nuevas en `tests/test_crypto_mode.py`. Las 3 de Redis corrieron contra un `redis-server` 7.0.15 real local.
- Las 31 nuevas cubren:
  - **Autorización:** un extraño se ignora, un grupo se rechaza, `/confirmar modo` desde un grupo se ignora y el código nunca entra a la cola. Además se comprueba que la IA no tiene herramientas para cambiar el modo, aprobar ni enviar.
  - **Variables:** el bloqueo de `CRYPTO_PRACTICE_ONLY`, las credenciales que faltan y el `COINBASE_TRADING_ENABLED` apagado. También que habilitar las variables no selecciona real, que el arranque baja real a práctica y que la conexión de Telegram al arrancar no activa real.
  - **Cambios de modo:**
    - Códigos: incorrecto, vencido, reutilizado, y variables que cambian después del código.
    - Al cambiar de modo: la época sube, se anulan las propuestas y los códigos, y se conservan las órdenes ya enviadas.
    - Fallos: si falla el almacenamiento al volver a práctica, igual se frena el real.
  - **Estado dañado o ilegible:** real bloqueado en todos los casos.
  - **Separación:** la práctica no llama nunca a la API privada y no toca el registro real, el gasto real ni `/practica`. Lo real no toca la cuenta simulada. Una cuenta de práctica dañada no se sobrescribe. El envío de órdenes se bloquea fuera del paso final. Restaurar deja práctica.
  - **Límites:** $100 por operación en ambos modos y $300 por día, contados por separado.
  - **Duplicados:** dos `/confirmar` envían una sola orden. Un resultado incierto no se reenvía. Un cambio de modo justo antes del envío lo cancela. Una propuesta de una época vieja no se ejecuta.
- **Integración con Redis real local:** el flujo completo (práctica, activar real, orden real simulada, volver a práctica, valor dañado, instancia vieja) guardando en un Redis de verdad.
- **Ninguna prueba movió dinero:** Coinbase siempre fue simulado, y el cliente de red se reemplazó por uno que hace fallar la prueba si alguien intenta conectarse.

**Cómo se corrieron:** este entorno no puede instalar paquetes desde PyPI. Se usaron las versiones reales de Starlette, Pydantic, httpx 0.28.1, cryptography, reportlab y Pillow. **FastAPI, el SDK de Anthropic, python-dotenv e imageio-ffmpeg se reemplazaron por imitaciones mínimas solo para las pruebas.** No están en el ZIP. Por eso conviene que repitas la suite con `pip install -r requirements.txt` como hiciste antes.

### Pendiente (no se pudo verificar aquí)

- **Upstash:** los scripts Lua y las claves nuevas en tu base real. Corre `scripts/check_redis_lua.py` (paso 0 de `CONFIGURACION_4_0_2.md`).
- **Coinbase real, nada verificado:**
  - que tu llave autentique (ES256);
  - que la vista previa y el envío de órdenes respondan como espera el código;
  - los permisos de la llave;
  - los nombres de productos;
  - el formato de las respuestas de error.
- **Precios públicos de Coinbase** desde Render, para la cuenta de práctica.
- **El arranque en Render, el webhook y los comandos** por Telegram de punta a punta.

### Riesgos que quedan

- Si cambias a práctica en el mismo instante en que una orden ya pasó el último control, esa orden sí sale: el cambio aplica a las siguientes. El margen es de milisegundos.
- El modo real seleccionado sobrevive reinicios mientras las variables lo sigan permitiendo. Si prefieres que cada deploy vuelva a práctica, es un cambio pequeño.
- La cuenta de práctica usa el precio público con comisión y deslizamiento simulados (`PAPER_FEE_PCT`, 0.1%). El resultado real en Coinbase será distinto.
- Si una orden real queda "enviándose" porque falló el almacenamiento justo después del envío, revísala en la app de Coinbase **antes** de repetirla.

---

## 5. Pasos sugeridos (no ejecutados)

1. Corre las pruebas con las dependencias reales: `pip install -r requirements.txt` y luego `python -m unittest discover -s tests`.
2. Corre `scripts/check_redis_lua.py` contra Upstash.
3. Despliega con la **configuración recomendada hoy (solo práctica)**.
4. Prueba por Telegram:
   - `/cripto modo`: debe decir que real no está disponible.
   - Pide preparar una compra de $10 de BTC, luego `/aprobar N` y `/confirmar N CÓDIGO`: debe ejecutarse en la cuenta **simulada**.
   - `/cripto`, `/seguridad` y `/diagnostico`.
5. Solo cuando lo decidas, en otra sesión: crea la llave de Coinbase, configura las variables de real, despliega y usa `/cripto modo real`. Empieza con una orden pequeña y comprueba el resultado en la app de Coinbase.

## Volver atrás

En Render, Deploys, elige el deploy anterior y haz "Rollback".

Las claves nuevas (`jarvis:crypto:mode`, `jarvis:crypto:practice`) las ignora 4.0.2. Las propuestas con los campos `mode` y `epoch` no le estorban.

Al volver a 4.0.2, el comportamiento real lo deciden otra vez solo las variables. Por eso **no vuelvas atrás con las variables de real activadas**.
