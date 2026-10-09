# Jarvis 4.2.1 — brief comercial ISLAFIX

Parche aditivo sobre 4.2.0. No reescribe el orquestador.

**Lo que no cambia:**
- Un worker: `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1`.
- Topes de $100 por orden y $300 por día.
- `/confirmar` sigue fuera de la cola.
- Sin autoenvío y sin publicación.
- `BUSINESS_REQUESTS_ENABLED=false`, Cripto en PRACTICE, `GEMINI_ENABLED=false`.

## Qué entra

`/brief` (también con las frases «brief», «brief de hoy» o «caja y cobros» como mensaje completo, escritas o por voz).
- Funciona solo en el chat privado del dueño.
- No gasta tokens y no llama a ningún modelo.
- Corre con el bloqueo de escritura del almacenamiento (`_WRITE_BLOCK`): no puede guardar nada.

**Comprobación previa:** si `BUSINESS_NAME` no es `ISLAFIX PRO LLC`, lo dice y se detiene.

**Secciones, en orden:**
1. **Caja:**
   - Reutiliza `cash_flow_report` (el mismo cálculo de `/caja`).
   - Muestra el saldo observado con su fecha, o «sin saldo observado».
   - Muestra los libros hasta hoy, sin presentarlos como saldo bancario.
   - Proyección condicional a 7 días. Si la importación está vieja, tiene fecha futura o falta un dato, la proyección queda bloqueada y no estima.
   - Los cobros y pagos futuros se listan aparte.
2. **Solicitudes y seguimientos vencidos, con sus ids:**
   - Solicitudes pendientes de ISLAFIX.
   - Trabajos vencidos (tienen que tener fecha).
   - Cotizaciones viejas (de `/seguimientos`).
   - Si no hay, «ninguna».
3. **Borradores:** uno por ítem, marcado `BORRADOR — no enviado`.
   - Plantilla fija, sin modelo.
   - Solo usa un precio si ya está guardado en el trabajo.
   - No se guardan ni se envían.
4. **Red social:** un borrador marcado `BORRADOR — no publicado`.
   - Sin precio, métricas, teléfono, fecha programada ni código.
5. **Por cobrar:**
   - Cuántos trabajos tienen saldo y el importe ya guardado.
   - Qué le falta al siguiente trabajo (precio, fecha, cliente o aprobación), o «no hay trabajo abierto».

**Marcador final:** `Cobrado esta semana: $X de $Y`.
- `$X`: ingresos USD registrados de lunes a hoy, hora de Puerto Rico. No cuenta futuros, ingresos sin fecha ni otras monedas.
- `$Y`: solo la meta numérica `meta_semanal_usd` del perfil. Si no existe, «sin meta». Nunca 167000 ni 1000000 por defecto.

## Corrección incluida

`/caja` marcaba como «vencido» un trabajo sin fecha de vencimiento. Ya no lo hace: `jarvis_business_workflows.cash_flow_report`, `overdue_jobs`.

## Archivos

| Archivo | Cambio |
|---|---|
| `jarvis_brief.py` | Nuevo: el brief, las frases, la voz y `/dictado`. |
| `main.py` | `VERSION`; carga protegida de `jarvis_brief` y `BRIEF_STATUS`; `brief` en `/health`. |
| `jarvis_v420.py` | `VERSION`. |
| `jarvis_business_workflows.py` | Corrección de `overdue_jobs`. |
| `.env.example` | Nota sobre `BUSINESS_NAME`. |
| `tests/test_brief.py` | Pruebas nuevas. |
| `tests/test_deployment_http.py` | Versión y estado del brief. |

**En Render:** poner `BUSINESS_NAME=ISLAFIX PRO LLC`. No hay variables nuevas.

**Si el módulo falla al cargar:** Jarvis arranca igual y `/health` muestra `brief: apagado (...)`.
