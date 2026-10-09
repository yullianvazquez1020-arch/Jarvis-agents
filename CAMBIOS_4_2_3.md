# Jarvis 4.2.3: ruta, huecos y piso

Parche aditivo sobre 4.2.2. No reescribe el orquestador.

Lo que no cambia: un worker, $100 por orden, $300 por día, `/confirmar` fuera de la cola, cripto en PRACTICE, `BUSINESS_REQUESTS_ENABLED=false`, sin autoenvío y sin publicación.

## Qué entra

1. **`/ruta`** (también «ruta» y «ruta de hoy»). Solo el chat privado del dueño. Sin tokens.
   - Muestra lo cobrado esta semana contra `/meta`, si hay meta.
   - Si hay `/piso`, dice cuántos cobros de ese tamaño faltan para la meta de la semana. Redondea hacia arriba.
   - Lista hasta 5 huecos.
   - No visita, no cobra, no publica y no guarda la ruta.
2. **`/huecos`** (también «huecos»). Lista trabajos no cancelados a los que les falta precio, fecha, cliente, aprobación o `/terminado` cuando el saldo ya es cero. Hasta 12, y dice si hay más.
3. **`/piso N`**. Guarda `ticket_min_usd` en el perfil. No es un ingreso, no entra en los libros y no impide anotar un trabajo menor. `/piso` lo muestra. `/piso borrar` lo quita. Rechaza palabras.
4. **`/brief`** gana la sección «7) RUTA», de solo lectura.

## Archivos

| Archivo | Cambio |
|---|---|
| `jarvis_ops.py` | Nuevo. |
| `main.py` | Versión 4.2.3 y carga protegida. `/health` muestra `ops`. |
| `jarvis_v420.py` | Versión 4.2.3. |
| `tests/test_ops.py` | Pruebas nuevas. |
