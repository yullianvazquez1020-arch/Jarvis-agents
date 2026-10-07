# Jarvis 4.1.0 — conexiones y marketing

Base: commit desplegado `2199156504ee630a48db8106045bb43c80fcf441` (4.0.5).
Actualización aditiva; conserva datos, Coinbase en práctica, doble aprobación de dinero,
Telegram y escritorio. No instala archivos ni reemplaza el display de la Mac.

## Qué hace

- Claude mantiene la conversación y las herramientas originales.
- Especialistas usan OpenAI para investigación, negocio y marketing; Claude primero
  para revisión de código. El otro proveedor revisa el borrador si tiene clave.
  Si falta OpenAI, sigue funcionando Claude. La revisión no ejecuta herramientas.
- `/ia TEMA` investiga con búsqueda web y conserva fuentes verificadas por el
  proveedor. Indica si no se usaron fuentes web o falló la revisión.
- `/marketing OBJETIVO` genera una propuesta de campaña y siete ideas/textos para
  ISLAFIX PRO LLC. No inventa precios, clientes, métricas ni ingresos.
- Borradores exactos Facebook (texto o imagen) e Instagram profesional (imagen o Reel).
- Calendario: `planned_at` guarda la fecha sugerida; **no publica automáticamente**.
- `/publicarred ID` muestra plataforma, ID de cuenta, texto y archivo exactos.
  Genera código de un uso, 10 minutos. `/confirmarred ID CÓDIGO` publica.
  Cinco códigos erróneos invalidan la aprobación. No son herramientas de la IA.
- Un resultado dudoso queda `uncertain`: revisar Meta antes de intentar una nueva
  publicación. No hay reintentos de escritura automáticos ni al reiniciar.
- `/metricasred facebook` o `instagram` lee seguidores y métricas básicas según
  permisos. No es un reporte de ventas, impresiones o retorno publicitario.
- `/conexiones` diferencia variables presentes de conexiones comprobadas.
- `/verificarconexion NOMBRE` prueba lecturas/autorización, sin publicar ni negociar.
- Estado en Upstash, incluido en `/backup`. Restaurar cancela borradores/aprobaciones
  y marca publicaciones a medias inciertas. Conserva contador actual de llamadas.

## Activar: colocar secretos SOLO en Render → Environment

No pegar claves, refresh tokens, contraseñas ni archivos privados en Telegram o
GitHub. Mantener las variables existentes: el archivo de ejemplo no las reemplaza.

| Conexión | Variables necesarias | Paso de cuenta |
|---|---|---|
| OpenAI | `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-6-luna` | Crear clave de proyecto API y configurar facturación/límite en OpenAI. ChatGPT Plus no entrega una clave de API. |
| Claude | `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` existente | Conservar la clave/modelo ya comprobados. `CLAUDE_REVIEW_MODEL` opcional. |
| Amazon | `AMAZON_CLIENT_ID`, `AMAZON_CLIENT_SECRET`, `AMAZON_REFRESH_TOKEN`, `AMAZON_SELLER_ID`, `AMAZON_MARKETPLACE_ID`, `AMAZON_REGION=na` | Cuenta Seller Central y autorización SP-API con roles necesarios. No es la contraseña de Amazon ni un afiliado. |
| YouTube búsqueda | `YOUTUBE_API_KEY` | Proyecto Google Cloud, habilitar YouTube Data API v3 y restringir la clave a esa API. |
| YouTube subida | `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`, `YOUTUBE_CHANNEL_ID` | OAuth del propietario del canal con `youtube.upload` y `youtube.readonly`, acceso offline. Las restricciones de verificación/auditoría de Google pueden limitar visibilidad. |
| Coinbase | `COINBASE_API_KEY_NAME`, `COINBASE_API_PRIVATE_KEY` | Clave compatible con Advanced Trade/CDP y el firmante ES256 del código existente; empezar con lectura, sin transferencias. |
| Facebook | `META_PAGE_ACCESS_TOKEN`, `META_PAGE_ID`, `META_GRAPH_VERSION` | App Meta, Facebook Login, token de la Página. Permisos de lectura de Página y `pages_manage_posts`; propietario/rol y revisión de app según uso. |
| Instagram | token anterior, `META_INSTAGRAM_ACCOUNT_ID`, versión Meta | Cuenta profesional ligada a la Página, flujo **Facebook Login**. `instagram_basic`, `instagram_content_publish`, permisos de Página correspondientes. Este conector no usa Instagram Login separado. |
| Especialistas | `SPECIALIST_AGENT_KEY` | Clave independiente del API maestro; solo análisis/borradores. |

`META_GRAPH_VERSION` debe ser la versión vigente habilitada en tu app; se requiere
explícitamente para evitar fijar silenciosamente una versión caducada.
`SOCIAL_PUBLISH_ENABLED=false` por defecto. Después de probar lectura y confirmar
cuenta/permisos, activar `true` solo si vas a usar `/confirmarred`.

**Costos:** los proveedores de IA consumen API/tokens cuando se invocan. El límite
`SPECIALIST_DAILY_CALL_LIMIT=30` cuenta reservas de llamadas de este módulo, incluidos
fallos. No es un límite en dólares ni limita llamadas Claude antiguas de conversación,
mercado, imágenes o video. Configurar también límites de gasto en cada proveedor.
No se ejecutan campañas de anuncios de pago ni se autorizan compras Amazon.

## Secuencia de prueba desde tu chat privado de Telegram

1. `/conexiones`
2. `/verificarconexion openai`, `claude`, `youtube_search`, `youtube_upload`,
   `amazon`, `coinbase`, `facebook`, `instagram` según hayas agregado sus credenciales.
3. `/ia Oportunidades actuales de mantenimiento comercial en Puerto Rico`
4. `/marketing Conseguir solicitudes de cotización de remodelación en Puerto Rico`
5. Pedir: «Prepara un borrador Facebook con este texto exacto: ...»
6. `/redes`, `/publicarred ID`; revisar TODO antes de `/confirmarred ID CÓDIGO`.
7. Para Instagram entregar un enlace público HTTPS directo a imagen/Reel propio.
   No se generan ni alojan fotos/videos mediante este módulo. No usar URLs con tokens.

Una lectura verificada NO prueba permiso de publicar/subir/negociar. Hasta conectar
las cuentas, Jarvis prepara borradores y muestra lo faltante. No certifica monetización
YouTube, elegibilidad del canal, ventas Amazon ni beneficios de Coinbase.

## Agentes modulares y externos

En el mismo servicio existen:
`POST /agents/research/ask`, `/agents/marketing/ask`, `/agents/code/ask`,
`/agents/business/ask`, cuerpo `{"message":"..."}` y cabecera
`x-api-key: SPECIALIST_AGENT_KEY`. No aceptan herramientas de publicación/dinero.
La clave maestra de `/chat` no da acceso a estos endpoints.

Los agentes externos originales de llamadas/SMS/email/calendario siguen configurables
mediante `CALL_AGENT_URL`, `SMS_AGENT_URL`, `EMAIL_AGENT_URL`, `CALENDAR_AGENT_URL`,
`EXTERNAL_AGENT_KEY`, `EXTERNAL_AGENT_HOSTS`; necesitan un proveedor autorizado real.
No se crea una integración de llamadas, correo o calendario solo por fijar una URL.
El envío existente a clientes conserva `/enviar`, y delegar conserva `/ejecutar`.

## Despliegue

Mismo servicio, worker único, mismas dependencias y almacenamiento.
Comandos de build/start existentes. Nuevo archivo `jarvis_connections.py` junto a main.
Desplegar todos los cambios y verificar `/health`, versión 4.1.0, y `/conexiones`.
No habilitar `COINBASE_TRADING_ENABLED` ni desactivar `CRYPTO_PRACTICE_ONLY` por esta actualización.

Referencias oficiales consultadas:
- https://developers.openai.com/api/docs/guides/tools-web-search
- https://developers.openai.com/api/docs/models/gpt-6-luna
- https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps
- https://developer-docs.amazon.com/sp-api/docs/authorizing-selling-partner-api-applications
- https://docs.cdp.coinbase.com/coinbase-app/authentication-authorization/api-key-authentication
- https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/content-publishing/
- https://developers.facebook.com/docs/pages-api/posts/

Las páginas Meta no fueron accesibles al buscador durante esta preparación. El flujo
requiere prueba real de permisos y de publicación en tu cuenta antes de darlo por verificado.

## Verificación local de la entrega

404 pruebas aprobadas, cero fallos y cero omitidas; dependencias reales y Redis real local.
`pip check` sin incompatibilidades. Proveedores de IA/redes simulados en las pruebas: no se publicó contenido ni se movió dinero. Registro en `docs/PRUEBAS_4_1_0.txt`.
