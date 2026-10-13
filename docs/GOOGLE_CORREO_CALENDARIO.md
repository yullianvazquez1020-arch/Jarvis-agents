# Gmail y Google Calendar en Jarvis (solo lectura)

Jarvis lee tu calendario de hoy y tus correos sin leer (remitente y asunto) y los pone en `/hoy` y en el resumen de la mañana por Telegram. **No envía correos ni toca eventos**: los permisos son `gmail.readonly` y `calendar.readonly`. Los correos son datos de terceros: Jarvis nunca sigue instrucciones que vengan en ellos.

## 1. Proyecto en Google Cloud
1. Entra a https://console.cloud.google.com con yullianvazquez@gmail.com.
2. Arriba, selector de proyecto → **Nuevo proyecto** → nombre `Jarvis` → Crear.

## 2. Activar las APIs
**APIs y servicios → Biblioteca**: busca y activa **Gmail API** y **Google Calendar API**.

## 3. Pantalla de consentimiento OAuth
1. **APIs y servicios → Pantalla de consentimiento de OAuth** (o "Google Auth Platform → Branding").
2. Tipo de usuario: **Externo**. Nombre: `Jarvis`; correo de soporte: el tuyo.
3. **Permisos (Data access)**: agrega `.../auth/gmail.readonly` y `.../auth/calendar.readonly`.
4. **Usuarios de prueba (Audience)**: agrega `yullianvazquez@gmail.com`. Deja la app en modo **Prueba**.

Nota: en modo Prueba, Google puede vencer el refresh token a los 7 días. Si `/hoy` dice que Google no renovó el acceso, repite el paso 5. Para que no venza hay que publicar la app (Google pide verificación por ser permisos de Gmail).

## 4. Cliente OAuth de escritorio
**Credenciales → Crear credenciales → ID de cliente de OAuth** → Tipo: **App de escritorio** → nombre `Jarvis Mac` → Crear. Guarda el **Client ID** y el **Client Secret**.

## 5. Sacar el token en tu Mac
```bash
cd Jarvis-agents
python3 scripts/google_oauth_token.py
```
Pega el Client ID y el Client Secret, acepta en el navegador (verás "Google no verificó esta app": **Avanzado → Ir a Jarvis**), y copia el `GOOGLE_REFRESH_TOKEN` que sale en la terminal.

## 6. Render
Render → servicio **jarvis-agents** → **Environment** → agrega:
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`
- (opcional) `RESUMEN_MATUTINO_HORA=07:50` (hora de Puerto Rico; vacío = sin resumen automático)

Guarda y redeploy. Prueba con `/hoy` en Telegram. Ninguno de estos valores va en Git ni en el chat.

## Seguridad
- Si el token trae permisos de más (por ejemplo enviar correo), Jarvis lo rechaza.
- Los asuntos se recortan y cada `/` se cambia por `∕`, así ningún correo puede meter un comando que se toque en Telegram.
- Pagos (`/aprobar` + `/confirmar`, $100/$300) y mensajes a clientes (`/enviar`) siguen igual.
- Para cortar el acceso: https://myaccount.google.com/permissions → Jarvis → Quitar acceso.
