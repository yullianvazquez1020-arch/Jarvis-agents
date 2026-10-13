# Reconectar el canal de YouTube a Jarvis

Jarvis ya tiene el código para subir (`jarvis_growth.py`: `upload_youtube` / `publish_youtube`).
Solo falta una autorización OAuth válida. Nada se publica sin ti:

1. `/subiryoutube ID` (solo en tu chat privado de Telegram) sube el video como **PRIVADO**.
2. Lo revisas en YouTube Studio.
3. `/publicaryoutube ID` (también en tu chat privado) lo hace público. Jarvis no lo hace solo,
   y el modelo no puede ejecutar esos comandos.

## Por qué dejó de funcionar (lo más probable)
- Si el proyecto de Google Cloud está en modo **Testing**, el refresh token caduca a los **7 días**.
  Por eso funcionó una vez y luego falló (`invalid_grant`).
- El token también se invalida si cambias la contraseña de Google, si revocas el acceso o si pasan 6 meses sin usarlo.
- Una guía vieja pedía el alcance `youtube.upload`. Con ese alcance se puede subir, pero `/publicaryoutube` falla.
  Hace falta `https://www.googleapis.com/auth/youtube`.
- En Render tienen que estar las 4 variables. Antes, `.env.example` no traía `YOUTUBE_CLIENT_ID` ni `YOUTUBE_CHANNEL_ID`.

## Pasos (unos 15 minutos, en tu Mac)
1. Ve a https://console.cloud.google.com, entrando con la cuenta dueña del canal. Usa el proyecto de antes o crea uno, por ejemplo "Jarvis YouTube".
2. En **APIs y servicios > Biblioteca**, busca **YouTube Data API v3** y dale **Habilitar**.
3. En **Pantalla de consentimiento OAuth** (Google Auth Platform):
   - Tipo: **Externo**. Pon el nombre de la app y tu email.
   - En **Público / Audience**, dale **Publicar app** (pasa a *En producción*). Así el token no caduca a los 7 días.
     Google te mostrará que la app no está verificada; para tu propio uso basta con aceptar "Avanzado > Ir a…".
   - Si prefieres dejarla en Testing, agrégate como **usuario de prueba**. Pero tendrás que repetir el paso 6 cada 7 días.
4. En **Credenciales > Crear credenciales > ID de cliente OAuth**, escoge el tipo **App de escritorio**.
   Descarga el JSON (`client_secret_....json`) a Descargas. **No lo subas a git.**
5. En la Terminal:
   ```
   cd ~/yullianvazquez1020-arch-Jarvis-agents
   git checkout feat/youtube-reconexion
   python3 scripts/youtube_refresh_token.py --client-secret ~/Downloads/client_secret_*.json
   ```
6. Se abre el navegador. Escoge la cuenta y el **canal** correctos y acepta.
   La Terminal imprime el nombre del canal y 4 líneas:
   `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`, `YOUTUBE_CHANNEL_ID`.
7. Ve a Render, entra al servicio de Jarvis y abre **Environment**. Pega las 4 variables y dale **Save** (se redeploya solo).
8. En tu chat privado de Jarvis, escribe `/verificarconexion youtube_upload`. Debe confirmar el canal.
9. Para publicar: `/videos`, luego `/subiryoutube ID` (queda privado), revisas el video y después `/publicaryoutube ID`.

Notas: el script no guarda nada en disco. Si Google no devuelve refresh_token, quita el acceso de la app en
https://myaccount.google.com/permissions y repite el paso 5. Las apps sin verificar pueden tener los videos subidos
bloqueados como privados hasta que pasen la auditoría de la API de YouTube. Si `/publicaryoutube` dice que siguen privados,
esa es la causa: hay que pedir la auditoría (formulario "YouTube API Services - Audit and Quota Extension").
