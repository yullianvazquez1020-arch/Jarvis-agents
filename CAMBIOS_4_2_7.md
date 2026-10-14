# Jarvis 4.2.7 — BRAIN: ciclo autónomo continuo

- `jarvis_brain.py`: descarga BRAIN.md (`BRAIN_URL`) al arrancar y cada 6 h, con copia en caché (Upstash/local).
- Ciclo cada `BRAIN_INTERVAL_MIN` (60): BRAIN + "ejecuta el siguiente ciclo" entra por el mismo camino que un texto libre del dueño (`_handle_tg` → `run`).
- Se borran las líneas de BRAIN que empiezan por `/`, así que no puede lanzar comandos. `/confirmar`, los topes de $100/$300 y `/enviar` no cambian.
- Tope diario `BRAIN_MAX_CYCLES_DAY` (24). Interruptor: `BRAIN_ENABLED` (apagado por defecto) y `/brain on|off|estado` (solo en el chat privado).
- Nunca se detiene: si un ciclo falla, reintenta con espera exponencial (60 s → 1 h) y reporta el error en el siguiente ciclo.
- `AI_MAX_TOKENS` (1500 por defecto, igual que antes) para evitar "Respuesta interrumpida" si el dueño decide subirlo; BRAIN se limita a 4000 caracteres por ciclo.
- `/health` añade `brain {enabled, loaded, last_cycle, last_error}`. También incluye `POST /api/encargo` (parche anterior).
