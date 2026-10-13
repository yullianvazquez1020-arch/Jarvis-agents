# API de encargos: POST /api/encargo

Le manda una tarea a Jarvis como si Yullian se la escribiera en Telegram (texto libre del dueño).
URL: `https://jarvis-agents.onrender.com/api/encargo`

## Configuración (Render → servicio Jarvis → Environment)
- `JARVIS_ENCARGO_SECRET`: valor aleatorio de **24 caracteres o más**, por ejemplo `python3 -c "import secrets;print(secrets.token_urlsafe(48))"`. Si está vacío o es más corto, el endpoint queda cerrado (401) y se avisa en el log al arrancar.
- `TELEGRAM_OWNER_ID`: sin él responde 503.
Nunca pongas el secreto en Git ni en el chat.

## Uso
```bash
curl -sS -X POST "https://jarvis-agents.onrender.com/api/encargo" \
  -H "Content-Type: application/json" -H "X-Jarvis-Secret: $JARVIS_ENCARGO_SECRET" \
  -d '{"texto":"Prueba de encargo: responde solo OK."}'
```
Respuesta: `{"ok":true,"queued":true}`. Te llega a Telegram un aviso (con vista previa recortada) y luego la respuesta.

## Respuestas
| Código | Motivo |
|---|---|
| 200 | Encargo en cola |
| 401 | Secreto incorrecto, vacío o corto |
| 422 | Texto vacío, de más de 4000 caracteres, o que empieza con `/` |
| 429 | Más de RATE_LIMIT_PER_MIN encargos por minuto, o demasiados secretos incorrectos (cubeta aparte: los intentos fallidos no gastan tu cupo) |
| 503 | Falta TELEGRAM_OWNER_ID |

## Reglas que no cambian
- Ningún comando entra por aquí: un texto que empieza con `/` se rechaza, y el resto se envía con el prefijo `[Encargo recibido por la API del dueño]`, así que un `/confirmar` en la 2ª línea es solo texto.
- Pagos: solo `/aprobar` + `/confirmar` escritos en el chat privado, con tope de $100 por operación y $300 al día.
- Mensajes a clientes: solo salen con `/enviar`.
- El log guarda solo cuántos caracteres llegaron; nunca el secreto ni el texto.
