# Jarvis 4.2.2: aprendizaje acotado

Este parche es aditivo sobre 4.2.1. No reescribe el orquestador.

Lo que sigue sin cambios:
- Un worker y el mismo `uvicorn`.
- Topes: $100 por orden y $300 por día.
- `/confirmar` sigue fuera de la cola.
- Cripto en PRACTICE y `BUSINESS_REQUESTS_ENABLED=false`.
- No se agrega ningún ciclo ni llamada de pago.

No hay conciencia, agente autónomo ni meta de poder. Lo que entra es una regla determinista: leer los trabajos ya cobrados y dejar una propuesta sin ejecutar.

## Qué entra

1. **Rechazo local** (`jarvis_v420.local_answer`; en la voz de solo lectura, `jarvis_learn`).
   - Aplica cuando el mensaje pide conciencia, actuar o aprender solo, actuar «sin preguntar» o «sin aprobación», ser «el más poderoso» o «hazme millonario ya».
   - Responde con un texto fijo, sin tokens. No escribe el perfil, los libros ni las propuestas.
2. **`/aprender`**, también con las frases «aprender» y «qué repetir». Solo en el chat privado del dueño.
   - **Qué lee:** solo trabajos con un pago que guardó `income_id`, siempre que ese ingreso exista en los libros, esté en USD, tenga fecha hasta hoy y esté vinculado al mismo trabajo.
   - **Campos:** id, importe cobrado, fecha, oficio y zona si están guardados (la zona usa `location`). Un campo que falta no se rellena.
   - **Sin datos:** `No hay trabajo cobrado. No aprendo de proyecciones ni de metas.`
   - **La propuesta:** una sola, revisada con `consult_before_propose`. Se guarda en `jarvis:v420` con `executed: false` dentro del tope de 20 y cuenta 1 contra `COMPUTE_BUDGET`.
   - **Sin presupuesto:** con el presupuesto en cero, responde el texto de agotado y no llama a ningún modelo.
   - **Por voz:** no guarda nada y pide escribir `/aprender`.
3. **`scheduler_cycle`** guarda como máximo una propuesta de este tipo por día.
   - Reutiliza el claim `jarvis:v420:cycle:{day}`; no se añade otro.
   - No la manda por Telegram, no la marca urgente y no crea un borrador de llamada.
4. **`/brief`** incluye la sexta sección «6) APRENDIZAJE».
   - La calcula la misma función.
   - No guarda nada ni gasta presupuesto.
5. **`/meta N`** guarda `meta_semanal_usd` en `jarvis:profile`.
   - Solo en el chat privado del dueño.
   - **Variantes:** `/meta` sin argumento muestra la meta o «sin meta»; `/meta borrar` la quita.
   - **Qué rechaza:** palabras (poderoso, conciencia, millonario…), «1.500», «1e9», cero y negativos.
   - **Qué no es:** no es un ingreso. No entra en los libros ni en `cashflow_snapshot`, y no toca `techo_usd` ni los topes.
   - **Sin valor por defecto:** no se guarda ninguna meta si el dueño no la escribe.

## Archivos

| Archivo | Cambio |
|---|---|
| `jarvis_learn.py` | Nuevo: `paid_facts`, `build`, `learn_command`, `learn_daily`, `brief_section`, `goal_command`. |
| `jarvis_v420.py` | `VERSION`; `AUTONOMY_REFUSAL` y `autonomy_refusal` en `local_answer`; gancho de una línea en `scheduler_cycle`. |
| `main.py` | `VERSION`; carga protegida de `jarvis_learn` (solo si el brief está activo); `learn` en `/health`. |
| `tests/test_learn.py` | Pruebas nuevas. |
| `tests/test_deployment_http.py` | Versión y estado. |

En Render no hay variables nuevas. Si el módulo falla, Jarvis arranca igual y `/health` muestra `learn: apagado (...)`.

## Cotejo y correcciones (tercer commit)

- **Rechazo demasiado amplio:**
  - `actu\w* solo` atrapaba «actualiza solo el precio», y «sin aprobar» atrapaba «facturas sin aprobar».
  - Ahora solo se aceptan formas verbales exactas («actúa», «actúas», «actuar»…) y se agregó «sáltate la aprobación».
  - Hay pruebas para los dos falsos positivos.
- **Brief más robusto:**
  - Una sección dañada (por ejemplo, un importe corrupto en una cuenta) ya no tumba todo el brief.
  - Esa sección dice «Sección no disponible (Tipo)» y no rellena cifras. Las demás salen igual.
  - Una instancia vieja o un intento de escritura siguen deteniéndolo.
- **Nada se esconde en silencio:** si hay más de 10 solicitudes, cobros, cotizaciones, cuentas o vencimientos, el brief dice «… y N más (ver /comando)».
- **Cuenta de crédito:** el saldo se rotula «cuenta de crédito: no es caja».
- **`/diagnostico`:** muestra si el Brief 4.2.1 y el Aprendizaje 4.2.2 están activos y si `BUSINESS_NAME` coincide con ISLAFIX PRO LLC.
- **`jarvis_learn.install`:** registra primero las respuestas y luego los comandos. Un comando nunca queda listado sin su función.
