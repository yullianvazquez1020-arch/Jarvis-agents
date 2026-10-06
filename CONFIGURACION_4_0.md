# Jarvis 4.0 — negocios, contenido original y práctica

Mantener main.py, jarvis_extensions.py, jarvis_growth.py, jarvis_video.py y requirements.txt juntos. Python 3.10 o posterior. Una sola réplica y un solo worker. Conservar variables y datos anteriores. Instalar con `pip install -r requirements.txt`. Mantener el comando de inicio actual de Render. Nuevas dependencias: Pillow e imageio-ffmpeg; el render usa FFmpeg del sistema o el binario de imageio-ffmpeg.

## Qué se agregó

- `/negocios`: capacidades y presencia de configuración, sin mostrar claves. Configurado no significa conexión comprobada.
- `/alibaba PRODUCTO`: investigación con el buscador ya existente y enlaces a Alibaba/Amazon. Página oficial: https://www.alibaba.com/. No compra inventario ni maneja pagos.
- Cálculo y almacenamiento de candidatos con costo unitario, cantidad, transporte, aranceles, otros costos, precio, comisión, fulfillment, publicidad, reserva de devoluciones y costo mensual. Todos los costos deben suministrarse; no se inventan tarifas ni ventas.
- `/productos`: candidatos guardados. `/margen ID_TRABAJO`: margen registrado y precio mínimo si el dueño fija margen objetivo.
- `/seguimientos`: cotizaciones antiguas, trabajos sin adelanto, márgenes bajos, clientes inactivos y reseñas. Resumen diario al dueño después de las 9 cuando hay oportunidades y Telegram está disponible. Pide por chat preparar seguimiento; continúa enviándose únicamente mediante `/enviar ID`.
- Enlace de pago y reseñas configurables por chat con las URLs del dueño. El enlace de pago se incluye en el borrador de adelanto; no procesa ni concilia pagos.

## Coinbase: práctica mejor evaluada

Conserva saldo, operaciones y configuración existentes. Nuevos controles solo simulados: máximo de entradas diarias, pausa de compras por pérdida diaria o caída acumulada; las salidas siguen permitidas. No se modifica la aprobación doble del trading real ni sus límites.

- `/evaluarpractica`: días, cierres, comisiones, caída observada, datos antiguos y advertencia de muestra insuficiente.
- `/backtest BTC-USD`: velas horarias públicas cerradas, señales de cierres anteriores, ejecución en apertura siguiente, comisiones y deslizamiento; comparación con mantener el activo. Es una evaluación corta de la regla base, sin optimización ni simulación intrahora, y no replica todos los controles de la práctica en vivo.
- Opcionales: `PAPER_DAILY_LOSS_PCT` (5), `PAPER_MAX_DRAWDOWN_PCT` (15), `PAPER_MAX_ENTRIES_PER_DAY` (6). Un límite de caída acumulada puede mantener las compras pausadas; revisa el informe antes de cambiarlo. Ningún resultado asegura rentabilidad.

## Amazon: cuenta del vendedor necesaria

Variables nuevas: `AMAZON_CLIENT_ID`, `AMAZON_CLIENT_SECRET`, `AMAZON_REFRESH_TOKEN`, `AMAZON_SELLER_ID`, `AMAZON_MARKETPLACE_ID`; `AMAZON_REGION` opcional `na`/`eu`/`fe` (na por defecto). Usar aplicación SP-API autorizada por la cuenta vendedora y roles necesarios.

`/amazon` consulta hasta 20 órdenes recientes sin datos personales. Para publicar, preparar por chat SKU y payload completo de Product Type Definitions, solicitar validación de ficha y revisar `/amazon ficha ID`. La validación usa VALIDATION_PREVIEW. `/publicarproducto ID` envía el contenido previamente validado, con cuenta/mercado iguales y validación de menos de una hora. Una respuesta ACCEPTED no demuestra que el anuncio esté visible. Un envío incierto no se repite automáticamente: revisar Seller Central.

Pendiente para comercio completo: elegir producto, presupuesto, cotización/muestra, cuenta vendedora, restricciones/certificaciones, logística, inventario, devoluciones y operación FBA/FBM. Esta versión no compra automáticamente en Alibaba, no sincroniza existencias y no despacha pedidos. No existe aún una tienda web propia; se usan Alibaba y Seller Central.

## YouTube: investigación y producción de borradores originales

`YOUTUBE_API_KEY` habilita `/youtube TEMA`: títulos, vistas acumuladas, fecha, duración y promedio histórico de vistas por día de hasta 10 resultados. No observa el metraje, no mide retención ni descubre el algoritmo.

Pedir: «Crea un plan de video infantil original en español para contar del uno al tres». Utiliza Claude y sus tokens. `/videos` lista planes; `/video ID` muestra el guion; `/producirvideo ID` crea un MP4 y envía la vista previa al dueño en Telegram. El estilo inicial es una animática educativa de figuras geométricas originales, 960×540 a 12 fps, hasta 4 minutos. No equivale a una producción animada completa. Revisa que narración, cantidades y gráficos coincidan y que exista valor educativo.

La narración usa el servicio TTS compatible de 3.9, mediante `TTS_AGENT_URL` y `TTS_AGENT_API_KEY`. Sin ese servicio, el MP4 es silencioso. Voz femenina depende de la configuración del proveedor TTS. No se han conectado voces nuevas ni cuentas por inventar credenciales.

Para subir: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` y `YOUTUBE_CHANNEL_ID`. Autorizar OAuth con alcance para subir, leer el canal propio y actualizar videos; por ejemplo `https://www.googleapis.com/auth/youtube`. Se verifica que el canal autorizado coincida con el configurado.

`/subiryoutube ID` sube la vista previa a privado y la declara contenido para niños. Después de revisarla, `/publicaryoutube ID` solicita publicación pública. Proyectos API sin verificación pueden permanecer restringidos a privado. Si hay resultado incierto, revisar YouTube Studio para evitar duplicados. No publica videos automáticamente por horario ni copia personajes, música o metraje ajenos. Originalidad y calidad requieren revisión; vistas y monetización no están garantizadas.

## Datos, pruebas y despliegue

`jarvis:growth` guarda productos, investigación, guiones, estados y ajustes. Se incluye en `/backup`. MP4 en `DATA_DIR/jarvis_videos`; los archivos binarios no se incluyen en el respaldo JSON. Usar disco persistente para conservarlos; sin él pueden perderse al reiniciar/desplegar. No regenerar/subir un video con resultado incierto sin revisar el canal.

Pruebas desde la raíz del repositorio: `python tests/test_growth.py` (77 pruebas, incluye regresiones). Utilizan credenciales ficticias y proveedores simulados, no dinero ni mensajes reales. También se comprobó sintaxis Python 3.10 y se codificó un MP4 local de 12 segundos. No se han comprobado credenciales reales de Amazon, YouTube o voz.

En Render: Auto Deploy habilitado para main, o Manual Deploy > Deploy latest commit. Verificar versión 4.0.0 y `/configuracion`, `/negocios`, `/evaluarpractica`. El acceso previo al panel fue denegado; el despliegue real no ha sido verificado desde aquí.

Referencias oficiales: https://developer-docs.amazon.com/sp-api/docs/connecting-to-the-selling-partner-api ; https://developers.google.com/youtube/v3/docs/videos/insert ; https://support.google.com/youtube/answer/1311392 ; https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles
