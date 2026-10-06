# Jarvis 3.9 — instalación y funciones

Archivos necesarios: main.py, jarvis_extensions.py, requirements.txt. Mantener una sola réplica/worker. Conservar todas las variables y datos anteriores. La clave de almacenamiento nueva es jarvis:extensions y queda incluida en /backup.

## Lo implementado

- /configuracion: muestra capacidades y conexiones reales, sin claves.
- Facturas y cotizaciones PDF: pedir en el chat «prepara la factura del trabajo N»; luego /factura ID_DOCUMENTO. Para cotizaciones, /cotizacion ID_DOCUMENTO. No se envían automáticamente al cliente ni registran ingresos.
- IVU: el dueño indica la tasa y cuáles documentos son tributables. No se asume una tasa legal. El CPA valida. El IVU del documento no modifica el precio/saldo del trabajo; mantener esa distinción al registrar cobros.
- /reporte YYYY-MM [ID_CLIENTE]: PDF con gráfica. El reporte de cliente usa ingresos vinculados a sus trabajos; los gastos generales no se atribuyen automáticamente.
- Notas permanentes: pedir «guarda una nota titulada ...»; /notas y /nota ID. Hasta 100,000 caracteres por nota. Incluidas en respaldos.
- Facturación recurrente: pedir un borrador recurrente para un trabajo, fecha inicial y frecuencia. Genera facturas para revisar; NO carga una tarjeta ni debita una cuenta. Para pausar, pedirlo en el chat y confirmar la acción.
- Recibos: enviar foto JPEG/PNG por chat privado. Se propone monto/comercio/fecha/categoría; /registrar ID aprueba el gasto y /descartarrecibo ID descarta. Si la fecha es ilegible, registrar manualmente con la fecha correcta. Fotos usan Claude y consumen tokens. El mismo archivo no debe registrarse dos veces; imágenes distintas del mismo recibo requieren revisión humana.
- Cambios y borrados: el chat prepara una acción. /acciones ID muestra los datos; /ejecutar ID confirma. Se registra su estado y no se reintenta automáticamente si la ejecución queda incierta.
- Coinbase mantiene sus funciones originales y /aprobar + /confirmar con los límites existentes. La práctica usa dinero simulado. Esta actualización no activa operaciones reales ni modifica las credenciales.
- Investigación periódica de proveedores: pedir expresamente el tema e intervalo (6–168 horas). Consume tokens Claude. No compra. Si no hay resultados web verificados, se indica.
- Acciones de agentes externos: borrador y /ejecutar ID. Cada servicio externo debe imponer permisos limitados; el orquestador no puede garantizar permisos internos de un servicio ajeno. Amazon se investiga, sin compras. Coinbase usa su módulo propio.

## Variables opcionales nuevas

No añadirlas vacías para intentar activar servicios. Las URLs deben ser servicios reales compatibles.

| Variable | Uso |
|---|---|
| STT_AGENT_URL | Servicio HTTPS de voz a texto. POST /transcribe, multipart file, respuesta JSON {"text":"..."}. Puede ser un servicio local expuesto de manera segura. |
| STT_AGENT_API_KEY | Clave del servicio STT; enviada solo a ese servicio como x-api-key. |
| TTS_AGENT_URL | Servicio HTTPS de voz. POST /synthesize con {"text":"..."}; respuesta binaria audio/mpeg, audio/ogg o audio/wav. |
| TTS_AGENT_API_KEY | Clave del servicio TTS; enviada solo a ese servicio como x-api-key. |
| INCOMING_AGENT_API_KEY | Secreto separado para agentes de llamadas/mensajes/correo que envían eventos al endpoint /integrations/incoming. No usar el secreto del webhook Telegram. |

Notas de voz: se transcriben y se muestran; /dictado ID confirma su procesamiento. No ejecutan comandos de aprobación de Coinbase por voz. /audio TEXTO genera respuesta audible si TTS está conectado.

Eventos entrantes: POST /integrations/incoming con cabecera x-api-key y JSON {"kind":"call|message|email","sender":"...","text":"...","event_id":"ID único"}. El evento se guarda y se notifica por Telegram. Su texto nunca es una orden del dueño. Este endpoint no contesta llamadas por sí mismo; necesita un agente telefónico real.

## Servicios y datos pendientes

- SMS/WhatsApp: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM. WhatsApp requiere remitente aprobado y reglas del proveedor.
- Email: RESEND_API_KEY, EMAIL_FROM; EMAIL_REPLY_TO opcional. Remitente/dominio verificado.
- Llamadas: número, proveedor, agente de llamadas y CALL_AGENT_URL; contrato previo /ask con x-api-key. El agente atiende y recoge nombre/motivo sin dar precios ni aceptar trabajos. Configuración y pruebas reales pendientes.
- Apps específicas y permisos: falta lista del dueño y proveedores. No se conectan por inventar sus URLs.
- Banco directo: no implementado; requiere banco/proveedor compatible y autorización. Continúa CSV/OFX/QFX, con alertas sobre datos importados, no balances en vivo.
- Clientes, trabajos, inventario, cuentas, calendarios y 33 movimientos sin categoría: los suministra el dueño. No se inventaron registros ni categorías definitivas.
- Tasa de reserva, IVU y umbrales de alerta: solicitar y guardar lo que indique el dueño.
- Render: Auto Deploy debe estar habilitado o hacer Manual Deploy > Deploy latest commit. El acceso al panel fue denegado; el despliegue real no ha sido verificado.

## Validación

Pruebas locales con credenciales ficticias y proveedores simulados. No se usaron dinero real, mensajes reales a clientes ni datos bancarios reales. Verificar /ayuda, /configuracion y /practica después del despliegue. Una prueba local aprobada no demuestra que las credenciales o servicios externos estén conectados.
