# Plan del canal de YouTube: meta de 2,000 suscriptores (BORRADOR)
Preparado el 13 oct 2026. Nada se ha publicado. Jarvis nunca hace público un video sin tu `/publicaryoutube`.

## A. Checklist de Google Cloud (lo haces tú, ~15 min). Detalles en `docs/YOUTUBE_RECONEXION.md`
- [ ] Entrar a console.cloud.google.com con la cuenta **dueña del canal**.
- [ ] Biblioteca → **YouTube Data API v3** → Habilitar.
- [ ] Pantalla de consentimiento OAuth → Externo → **Publicar app (En producción)**. Así el token no caduca a los 7 días.
- [ ] Credenciales → ID de cliente OAuth → **App de escritorio** → bajar el JSON a Descargas. **No subirlo a git.**
- [ ] En la Mac: `git checkout feat/youtube-reconexion` y `python3 scripts/youtube_refresh_token.py --client-secret ~/Downloads/client_secret_*.json`
- [ ] Pegar las 4 variables en Render → Environment (`YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`, `YOUTUBE_CHANNEL_ID`).
- [ ] En Telegram privado: `/verificarconexion youtube_upload`.
- [ ] Si los videos se quedan forzados en privado, pedir la auditoría "YouTube API Services – Audit and Quota Extension".
- Nota: la rama `feat/youtube-reconexion` todavía no está en GitHub. Primero hay que aplicar `youtube-reconexion.patch` con tu OK.

## B. Decisión clave: ¿contenido para niños o no?
Te recomiendo que **el canal principal NO sea "para niños"**. Haz animación IA de humor y entretenimiento familiar en español boricua, dirigida a **adolescentes y adultos**.
Por qué:
- Si marcas el contenido como *made for kids* (COPPA), YouTube apaga los **comentarios**, las **notificaciones**, la campanita, las tarjetas y pantallas finales, las membresías y los **anuncios personalizados**. YouTube mismo advierte que eso puede **bajar los ingresos**. Además, sin comentarios ni notificaciones es mucho más difícil llegar a 2,000 suscriptores. Fuentes: https://support.google.com/youtube/answer/9527654 · https://support.google.com/youtube/answer/9632097 · https://support.google.com/youtube/answer/9713557
- **No puedes "esquivar" la etiqueta.** Si el público principal son niños, o el estilo es infantil (canciones de cuna, personajes de juguete, colores tipo preescolar), *tienes* que marcarlo para niños. La FTC puede multar por no hacerlo, y YouTube puede cambiar la etiqueta y penalizar el canal. Un estilo "tipo Cocomelon" casi seguro cae en *made for kids*.
- Si de todas formas quieres una línea infantil, hazla en un **segundo canal** aparte, marcado para niños desde el inicio, y con expectativas bajas de ingresos.

## C. Riesgos legales y de políticas
1. **Copyright y marcas:** no se pueden usar personajes, nombres, canciones, logos ni el estilo distintivo de **Cocomelon** (Moonbug), Bluey, Peppa, etc. Tampoco "JJ" ni la canción de "Bath Song", ni con IA ni "parecidos". Eso trae reclamos de Content ID, strikes de copyright (3 strikes y se cierra el canal) y demandas de marca. Las canciones infantiles de **dominio público** (Los pollitos dicen, Arroz con leche, Pin Pon) sí se pueden usar, con un arreglo y una voz propios. Fuente: https://support.google.com/youtube/answer/2797466
2. **Divulgación de IA:** en la subida tienes que marcar "contenido alterado o sintético" cuando el video *parece real* (personas reales, lugares o eventos realistas). La animación claramente irreal no lo requiere, pero el fotorrealismo y las voces clonadas de personas reales **sí**. Si no lo marcas, te pueden poner la etiqueta a la fuerza, quitar el video o suspenderte del YPP. Fuentes: https://support.google.com/youtube/answer/14328491 · https://blog.youtube/news-and-events/disclosing-ai-generated-content/
3. **"Contenido no auténtico"** (antes "contenido repetitivo", renombrado en julio de 2025): YouTube **no monetiza** canales con videos producidos en masa, con plantilla o intercambiables, como slideshows con voz IA o el mismo formato con otro título. Cada video necesita guion, chiste, historia o valor propio. Fuente: https://support.google.com/youtube/answer/1311392
4. **Personas reales y streamers:** no hagas avatares IA de streamers reales sin permiso. Eso cae en derecho de imagen y en la política de privacidad de YouTube. Mejor crea **tus propios personajes**.
5. **Música:** usa solo la biblioteca de audio de YouTube, música propia, o IA con licencia comercial (por ejemplo, el plan pago de Suno).

## D. Umbrales del YPP (verificados el 13 oct 2026)
| Nivel | Requisito | Qué desbloquea |
|---|---|---|
| Inicial | **500 subs** + 3 subidas públicas en 90 días + (3,000 h de reproducción en 12 meses **o** 3M vistas de Shorts en 90 días) | Membresías, Super Thanks, Shopping. **Sin anuncios.** |
| Completo | **1,000 subs** + (4,000 h en 12 meses **o** 10M vistas de Shorts en 90 días) | Ingresos por anuncios y Premium |
| ⚠️ **Desde el 1 feb 2027** (solo canales nuevos) | 1,000 subs + **8,000 h** o **20M** vistas de Shorts | Anuncios |
Fuentes: https://www.youtube.com/creators/earn/youtube-partner-program/ · https://support.google.com/youtube/answer/72851 · https://blog.youtube/news-and-events/youtube-partner-program-updates-2027-new-opportunities-earn/
**Implicación:** si quieres el umbral viejo de anuncios, hay que solicitarlo **antes del 1 feb 2027**. Eso es muy difícil desde cero en 3.5 meses. La meta realista es **500 subs a fines de enero** y **2,000 a mediados de 2027**.

## E. Nicho y ángulo
**Nicho recomendado:** *"Muñequitos IA boricuas"*, una serie animada corta de personajes propios. Por ejemplo, **"Coquí Bot"**, un coquí robot con Jarvis como asistente, que vive situaciones de PR: el apagón de LUMA, el tapón en la Baldorioty, la abuela y el WhatsApp, el colmado. Tono de humor familiar, **para mayores de 13**.
- **Ángulo en español:** hay poca competencia en animación IA con identidad puertorriqueña. La diáspora en EE.UU. (~6M) comparte mucho este contenido.
- **Formato "streamer con muñequito IA":** Coquí Bot hace "reacciones" a noticias o tendencias **en tono de comedia**, con avatar propio (estilo VTuber). Así los videos no se ven "en masa": cada uno tiene su propio chiste.
- **Línea secundaria (opcional, canal aparte para niños):** canciones de dominio público boricuas animadas.

## F. Ritmo y formato
- **Shorts:** 1 al día (5–7 por semana), de 20–45 s, con un gancho en los primeros 2 s.
- **Videos largos:** 1 por semana, de 4–8 min (compilado nuevo con hilo narrativo, o un episodio). Esto suma horas de reproducción, porque los Shorts no cuentan para las 4,000 h.
- **Comunidad:** contestar comentarios (solo si el canal NO es para niños), encuestas y colaboraciones con creadores boricuas.
- **Supuesto realista:** con 30+ Shorts al mes y 4 videos largos, un canal nuevo bien hecho puede llegar a 100–500 subs en el primer mes. **No está garantizado.** Hay que ajustar según la retención en Analytics.

## G. Calendario de 30 días
| Día | Tarea |
|---|---|
| 1 | [Y] Pasos de Google Cloud (sección A). [J] Biblia de personajes de Coquí Bot (nombre, personalidad, frases, paleta). |
| 2 | [J] 30 ideas de Shorts + 4 ideas de videos largos. [Y] Escoger 15. |
| 3 | [Y] Banner, logo y descripción del canal; audiencia: **"No es para niños"**. |
| 4–5 | [J] Guiones de los Shorts 1–7. [Y/J] Generar los videos y editarlos en CapCut. |
| 6 | [J] `/subiryoutube` de los 7 Shorts (**privados**). [Y] Revisar en Studio, marcar IA si aplica, y `/publicaryoutube` de 1 Short. |
| 7 | [Y] Publicar el Short 2. Revisión: retención y vistas. |
| 8–13 | 1 Short al día. [J] Guion del video largo 1. |
| 14 | Video largo 1 (episodio de 5 min). Revisión de la semana 2: duplicar el formato que funcione mejor. |
| 15–20 | 1 Short al día. Primer "reacción" de Coquí Bot a una tendencia. |
| 21 | Video largo 2 + post de comunidad (encuesta). |
| 22–27 | 1 Short al día. [Y] Contactar a 3 creadores boricuas para colaborar (tú en persona). |
| 28 | Video largo 3. |
| 29 | [J] Informe: subs, vistas, CTR, retención, los 5 mejores. |
| 30 | [Y] Decidir el plan del mes 2. Video largo 4 en la semana 5. |
Meta del mes 1: **150–300 subs**. Mes 3: **500** (YPP inicial). Mes 6–9: **2,000**.

## H. Cómo encaja Jarvis
1. Jarvis hace el guion, las ideas, los títulos, las miniaturas en borrador y la lista de videos (`/videos`).
2. `/subiryoutube ID` (solo en tu chat privado) sube el video como **PRIVADO**.
3. Tú lo revisas en YouTube Studio: audiencia, divulgación de IA, música y título.
4. `/publicaryoutube ID` lo hace público **solo con tu orden**. El modelo no puede ejecutar ese comando.
5. Jarvis nunca contesta comentarios ni manda mensajes por su cuenta (regla de `/enviar`).

## I. Herramientas y costos (verifica precios el día que compres)
| Uso | Herramienta | Costo aprox. |
|---|---|---|
| Guiones | Jarvis (modelos locales) | $0 |
| Imagen/personajes | Leonardo, Ideogram, Midjourney | $0–$10/mes |
| Animación IA | Kling, Runway, Hailuo, Pika (con créditos) | $10–$35/mes |
| Voz | Tu propia voz, o ElevenLabs Starter (fuera de Jarvis) | $0–$5/mes |
| Música | Biblioteca de audio de YouTube / Suno Pro (licencia comercial) | $0–$10/mes |
| Edición | CapCut / DaVinci Resolve | $0 |
| **Total** | | **≈ $20–$60/mes** |
Precios de referencia: https://elevenlabs.io/pricing · https://runwayml.com/pricing · https://suno.com/pricing (no verificados hoy, confírmalos).
Recuerda: la Mac 2015 no aguanta generar video localmente, así que todo se genera en la nube.
