# Cifrado del historial y del perfil (4.2)

Sobre el commit `961047a`. Reutiliza `jarvis_seal.py` (AES-256-GCM, formato `sealed:v1:` sin cambios).
**Este parche no genera, no guarda y no activa ninguna clave.** Mientras `DATA_ENCRYPTION_KEY` esté vacía en Render, todo sigue igual que hoy: historial y perfil en claro.

## Qué se cifra y qué no

| Se cifra (si hay clave) | No se cifra, para que siga operable |
|---|---|
| `jarvis:history`, `jarvis:profile`, `jarvis:bio`, `jarvis:diary` | Gate de dinero, cola de Telegram, líder, libros, clientes, banco, cripto y demás |

- Es cifrado en reposo: Upstash ve texto cifrado, salvo los respaldos en claro, que duran 72 h y `/cifrado limpiar` borra antes.
- Quien tenga acceso a las variables de Render tiene la clave; eso no cambia con este parche.
- La copia diaria (`daily_backup`) no incluye estas cuatro llaves; ya era así antes.

## Lo que corrige este parche

1. **Pérdida de datos con una clave equivocada (comprobada en `961047a`):**
   - Si la clave de Render cambiaba por error, el siguiente turno reemplazaba el historial cifrado con la clave buena, y ese historial se perdía.
   - Ahora un dato que la clave actual no abre (otra clave o dato dañado) nunca se pisa.
   - El chat sigue funcionando y avisa una vez: «No guardé esta conversación en el historial…».
2. **Migración explícita y verificable** de lo que ya está en claro.
3. **Respaldo, recuperación y reversión** con comandos del dueño.
4. **Diagnóstico** que separa tres cosas: si el código está disponible, si la clave está configurada (con su huella) y si los datos están cifrados de verdad.

## Comandos (solo en tu chat privado con Jarvis, sin tokens)

| Comando | Qué hace |
|---|---|
| `/cifrado` | Estado: código, clave (huella) y estado de cada dato. Nunca muestra contenido ni la clave. |
| `/cifrado revisar` | Simulación: dice qué se cifraría. No cambia nada. |
| `/cifrado migrar` | Cifra lo que está en claro, verificando cada paso. Se niega si hay datos que esta clave no abre o si los datos se cifraron con otra clave. |
| `/cifrado restaurar` | Devuelve el respaldo previo a cifrar (72 h). Solo sobre datos que no abren y cuya clave registrada coincide; en otro caso pide `forzar`. |
| `/cifrado recuperar` | Trae de vuelta la copia guardada más nueva que abre con la clave actual y es distinta de lo que hay. Sobre datos legibles pide `forzar`. |
| `/cifrado descartar` | Si hay datos ilegibles, los guarda aparte (30 días) y deja el historial vacío para que vuelva a guardarse. Registra la clave actual como la buena; la anterior queda anotada. |
| `/cifrado revertir` | Descifra a claro y deja de cifrar hasta reiniciar. Después quitas la clave en Render. |
| `/cifrado limpiar` | Borra antes de tiempo las copias en claro (respaldos de migración y copias sin clave). |

`/diagnostico` muestra la misma línea `Cifrado: …`.

## Procedimiento de la clave (lo hace el dueño, no Jarvis)

**No la pegues en Telegram, en un chat con una IA ni en un correo.**

1. **Genérala en tu computadora**, no en Render ni en un chat:
   ```
   python3 -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
   ```
2. **Guárdala en dos sitios tuyos:** tu gestor de contraseñas y una copia fuera de línea (papel en un lugar seguro, o una memoria cifrada). Si la pierdes, lo cifrado no se puede abrir; nadie puede recuperarla.
3. **Calcula su huella** en tu computadora. `getpass` no la muestra ni la deja en el historial del terminal:
   ```
   python3 -c "import base64,hmac,hashlib,getpass; k=base64.b64decode(getpass.getpass('Clave: '),validate=True); print(hmac.new(k,b'jarvis-seal-fingerprint-v1',hashlib.sha256).hexdigest()[:8])"
   ```
   Anota esos 8 caracteres junto a la clave. La huella no revela la clave.
4. **Ponla en Render** (Environment → `DATA_ENCRYPTION_KEY`) y deja que reinicie.
5. **En Telegram, escribe `/cifrado`.** La huella que muestra debe ser la tuya. Si no coincide, no sigas: corrige la variable.
6. **Escribe `/cifrado revisar`, y luego `/cifrado migrar`.** Debe decir «✅ Migración verificada».
7. **Cuando confirmes que la clave está guardada en los dos sitios, escribe `/cifrado limpiar`.** Si no lo haces, el respaldo en claro se borra solo a las 72 h.

Con la clave puesta, un turno normal también cifra lo que esté en claro, con el mismo respaldo de 72 h. Por eso conviene correr `/cifrado migrar` justo después del paso 5.

## Recuperación

| Situación | Qué hacer |
|---|---|
| `/cifrado` muestra otra huella o «Los datos se cifraron con otra clave» | Pon en Render la clave correcta (la de tu respaldo). No se perdió nada: no se sobrescribió. |
| Perdiste la clave, dentro de las 72 h de la migración | Pon una clave nueva (pasos 1–5), luego `/cifrado restaurar forzar`. Lo cifrado con la clave perdida queda guardado aparte 30 días por si la encuentras. |
| Perdiste la clave, después de las 72 h | Lo cifrado no se puede abrir. Pon una clave nueva y escribe `/cifrado descartar`: guarda lo viejo aparte 30 días y el historial vuelve a guardarse. Si encuentras la clave vieja dentro de esos 30 días: ponla y escribe `/cifrado recuperar`. Lo que hablaste con la clave nueva queda guardado aparte; si vuelves a la nueva, `/cifrado recuperar` lo trae. |
| Dato dañado, con la clave correcta | Si hay respaldo vigente: `/cifrado restaurar`. Si no: `/cifrado descartar`. |
| Reinicio o deploy | Nada que hacer: el historial cifrado se lee con la misma clave (probado). |

Las copias guardadas aparte:
- Son como máximo 5 por dato. Al pasar de 5 se borra la más vieja que la clave actual abre; una copia que la clave actual no abre nunca se borra por el tope (vence a los 30 días).
- Si había clave al guardarlas, quedan cifradas.
- Una copia en claro (sin clave) dura solo 72 h.

## Reversión

- **Código (rollback en Render al deploy anterior):**
  - Es seguro si dejas la misma clave.
  - `961047a` lee el mismo formato `sealed:v1:` e ignora las llaves nuevas `jarvis:seal:*`.
  - Volver más atrás que la Fase A (antes del PR #7) no lee el historial cifrado.
- **Datos a claro:**
  1. `/cifrado revertir`: descifra, verifica y deja de cifrar.
  2. Quita `DATA_ENCRYPTION_KEY` en Render.
  - Si se reinicia con la clave puesta, vuelve a cifrar al guardar; los datos siguen legibles.

## Garantías de la migración (y cómo se prueban)

- **Respaldo antes de escribir.** En `/cifrado migrar`, si el respaldo falla, no se escribe nada. En un turno normal, si el respaldo falla, el turno se guarda igual (cifrado) y queda anotado en el log, para no perder la conversación.
- **Prueba de ida y vuelta.** Cifra y descifra en memoria, y compara con el original.
- **Escritura condicional.** Solo escribe si el dato sigue igual que cuando lo leyó; si entró un turno mientras tanto, no escribe y no se pierde nada.
  - En Upstash va en un solo script Lua con la misma protección de líder que el resto de las escrituras.
- **Verificación al final.** Relee lo guardado y lo descifra.
- **No toca lo que no debe.** Lo ilegible o ya cifrado nunca se toca, y el canal de solo lectura no puede migrar.
- **Turnos completos.** Se mantiene el guardado atómico de turnos de `remember_turn`.

## Pruebas

- **Archivo:** `tests/test_seal_migration.py`, con 50 pruebas.
- **Qué cubren:**
  - Migración: revisión y aplicación.
  - Clave incorrecta y dato dañado.
  - Fallo de almacenamiento, del respaldo y de la escritura.
  - Turno guardado durante la migración.
  - Reinicio, con la clave correcta y con la equivocada.
  - Restaurar, recuperar, descartar y revertir.
  - Vencimiento y tope de copias, y los pasos de «clave perdida» de este documento, de punta a punta.
  - Diagnóstico de tres partes, sin el módulo y con un módulo antiguo.
  - Que los límites de $100/$300 no cambian.
- **Dónde corren:**
  - Todas sobre archivos locales.
  - 5 de ellas también contra un `redis-server` real 7.0, con el mismo camino de código de Upstash: `EVAL` con protección de líder y `SET EX`.

## Pendiente de comprobar (no se pudo aquí)

- Upstash real: la respuesta de `EVAL` y `SET … EX` vía REST. El código usa los mismos comandos que `daily_backup` y `_redis_write`.
- `pip install -r requirements.txt` con PyPI. Este entorno no tiene acceso; ver la nota de entrega.
- La migración con los datos reales de producción. Hazla con `/cifrado revisar` primero.

## Revisión de integración de Codex

Se vuelve a comprobar el valor almacenado antes de cada escritura sensible, incluso si una lectura anterior fue válida. Una clave configurada pero inválida bloquea también la restauración: nunca se interpreta como permiso para guardar en claro. Si un comando falla después de algunos pasos, el aviso pide revisar el estado y no afirma que no hubo cambios. Dos pruebas de regresión adicionales cubren estos casos.
