# Aviso a Grok cuando el monitor termina

Automatización: jarvis-operacion-terminada (webhook). No es el aviso de GitHub Actions.

En Render, copiados de la automatización (el secreto se muestra una sola vez):

```
JARVIS_GROK_WEBHOOK_URL=
JARVIS_WEBHOOK_SECRET=
```

Vacías = no se envía nada. Un POST fallido no tumba el worker. 202 significa que Grok aceptó el aviso, no que la notificación ya llegó.

Después de cerrar un ciclo:

```python
from jarvis_webhook_notify import notify_operation_done
notify_operation_done("paper_cycle", "ciclo de práctica cerrado", status="completed")
```
