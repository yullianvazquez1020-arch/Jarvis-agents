# Jarvis — handoff para Claude

Fecha de lo verificado: 2026-10-13, servicio en vivo.
Repo: https://github.com/yullianvazquez1020-arch/Jarvis-agents
Servicio: https://jarvis-agents.onrender.com
No vuelvas a construir el hub, el kit, el botón ni el webhook. Ya están en `main`.

## Qué ya responde

- Landing: https://jarvis-agents.onrender.com/kit
- PDF: https://jarvis-agents.onrender.com/kit/archivo.pdf
- Plantillas: https://jarvis-agents.onrender.com/kit/plantillas.md
- Hub: https://jarvis-agents.onrender.com/hub
- El hub ya tiene el botón WhatsApp a https://wa.me/17874465095
- Hay un botón verde fijo en `/kit` y en `/hub`. Abre `/hub/go/whatsapp`.
- Salud: `funnel`, `aincrad` y `evolve` en activo. Telegram conectado.
- WhatsApp automático y correo siguen apagados. En `/health`, `client_messages.sms` y `email` están en false.

## Qué no hacer

- No pongas el SID ni el token en git. `.env.example` se commitea.
- No quites la doble aprobación de Coinbase.
- No conectes historial crediticio, ni scrapers de LinkedIn, ni búsqueda de teléfonos.
- No cambies `PUBLIC_HOST` a otra cosa. Si va, es exactamente `jarvis-agents.onrender.com`, sin `https://` y sin barra.
- El botón verde no es el bot. Abre el celular `787 446 5095`. El bot solo contesta si Twilio llama a `/ventas/whatsapp`.

## Pegar en Render, Environment, y redeploy

Rellena los vacíos. No inventes valores.

```
PUBLIC_HOST=jarvis-agents.onrender.com
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM=whatsapp:+14155238886
RESEND_API_KEY=
EMAIL_FROM=AINCRAD <avisos@tu-dominio.com>
GUMROAD_PING_SECRET=
GUMROAD_SELLER_ID=
```

Cuando el sender propio esté Active:

```
TWILIO_FROM=whatsapp:+17874465095
```

SID y token: página de inicio de https://console.twilio.com
Clave de Resend: Resend, API Keys. El dominio de `EMAIL_FROM` tiene que estar verificado.

## Pegar en Twilio

When a message comes in, método POST, sin barra final:

```
https://jarvis-agents.onrender.com/ventas/whatsapp
```

Prueba de hoy: sandbox https://www.twilio.com/console/sms/whatsapp/sandbox
Número de prueba: +1 415 523 8886
Desde el celular, manda la frase `join` que muestra esa pantalla. Después manda `precio`.
Tiene que contestar con el kit a $9 y el hub.
Un 404 es variables ausentes. Un 403 es `PUBLIC_HOST` o la URL distinta.
La segunda escritura del mismo número en menos de 10 minutos no se contesta.

Sender propio: https://1console.twilio.com/us1/develop/sms/senders/whatsapp-senders
Ahí, Edit Sender, la misma URL.

## Pegar en Gumroad

Settings, Advanced, Ping endpoint. La frase es la misma de `GUMROAD_PING_SECRET`.

```
https://jarvis-agents.onrender.com/public/gumroad-sale?token=LA-FRASE-DEL-SECRETO
```

Un ping de prueba no anota dinero. Una venta real sí, y mete el email en la secuencia de 5 correos.
`GUMROAD_SELLER_ID` puede ir vacío la primera vez. El id viene dentro del ping.

## Pegar en Telegram, chat con Jarvis

```
/hub set Kit https://tu-usuario.gumroad.com/l/el-producto
```

## Pegar en las bios

```
https://jarvis-agents.onrender.com/hub
```

## Dónde está el código

- `jarvis_funnel.py` — `/hub`, `/hub/go/{slug}`, pixel y GA4 solo si hay id válido, link de WhatsApp.
- `jarvis_aincrad.py` — `/kit`, secuencia de 5 correos, `/ventas/whatsapp`, afiliados, borradores de TikTok, Reddit, Medium y Quora.
- `jarvis_evolve.py` — ping de Gumroad, PDF, `/precio`, `/redes` para X, Pinterest y TikTok.
- `jarvis_video.py` — cada video deja un `.srt`.
- `main.py` — instala funnel, aincrad y evolve. `/confirmarredes` no pasa por la cola.
- Publicar en X, Pinterest o TikTok exige `*_POST_ENABLED=true`, el token, y `/confirmarredes ID CODIGO`. TikTok sale como privado de la cuenta.

## Sigue sin estar

- El producto de Gumroad no está enlazado en el hub.
- Resend no está configurado, así que los correos no salen.
- Twilio no está configurado, así que el bot no contesta.
- Pixel, GA4, X, Pinterest y TikTok esperan sus tokens. No hacen falta para la primera venta.

## Tu trabajo: comprobar que no hay errores

No reescribas el proyecto. Lee el diff de `jarvis_funnel.py`, `jarvis_aincrad.py`, `jarvis_evolve.py`, `jarvis_video.py` y el bloque nuevo de `main.py`. Corre esto y pega el resultado:

```
python3 -m unittest tests.test_funnel tests.test_aincrad tests.test_evolve -v
```

El 2026-10-13 esos 12 tests pasaron. Si uno falla, arréglalo. Si pasan, no los cambies para hacerlos verdes.

Revisa estos puntos y di sí o no, con el archivo y la línea:

1. `/ventas/whatsapp` guarda el número antes de que Twilio acepte el envío. Si Twilio responde 400, ese número queda mudo 10 minutos. Confírmalo y, si es así, guarda la hora solo después de un envío aceptado.
2. La firma usa `https://{PUBLIC_HOST}/ventas/whatsapp`. Un host con `https://`, mayúsculas o una barra hace 403. No lo "arregles" aceptando cualquier host.
3. `TWILIO_FROM` tiene que empezar por `whatsapp:`. `_send_sms` vuelve a poner `whatsapp:` al destino. Confirma que no queda `whatsapp:whatsapp:+`.
4. Gumroad manda `price` en centavos. `900` tiene que anotarse como 9.00 dólares. Un ping con `test=true` no puede llamar a `add_income`.
5. El mismo `sale_id` no puede crear dos ingresos.
6. `/hub/go/whatsapp` tiene que redirigir a `https://wa.me/17874465095`.
7. El botón verde de `/kit` y `/hub` tiene que apuntar a `/hub/go/whatsapp`, no a un número escrito en el HTML.
8. `/confirmarredes` no puede quedar guardado en la cola de Telegram. Tiene que salir por el mismo camino que `/confirmarred`.
9. X, Pinterest y TikTok no publican sin código del dueño ni con `*_POST_ENABLED` apagado.
10. No hay SID, token, ni secreto de Gumroad dentro del repo.

Entrega solo esto: tests, los 10 puntos, y el parche si el punto 1 es cierto. Nada más.

