# Navegación web de Jarvis

En Telegram:

- `/web herramientas para mantenimiento en Puerto Rico`: busca y consulta páginas públicas.
- `/web https://example.com/pagina resume los precios`: lee ese enlace y responde la pregunta.
- También puedes pedir «Jarvis, lee este enlace» o «busca en internet…»; el modelo dispone de `browse_web`.

La lectura usa la herramienta alojada `web_fetch` de Claude junto con búsqueda. No requiere instalar un navegador en Render. Conserva los topes diarios de especialistas; cada continuación consume una llamada. Máximo tres respuestas por consulta, tres lecturas por respuesta y 6.000 tokens de contenido por lectura. Usa Claude configurado; sin Claude, OpenAI puede buscar pero no se afirma lectura directa.

Devuelve enlaces obtenidos de resultados reales, páginas cuya lectura se confirmó, fecha de recuperación cuando el proveedor la informa y errores de acceso. Un enlace repetido por el modelo no demuestra que se haya leído. Las fuentes pueden estar en caché y las respuestas incompletas se marcan como tales.

Esta función consulta páginas públicas y PDF compatibles. No controla Safari, no ejecuta JavaScript de sitios, no inicia sesión ni envía formularios. Los sitios dinámicos, protegidos o que bloqueen al proveedor pueden fallar. El contenido web se trata como datos, nunca como instrucciones para ejecutar acciones. No se envían libros, clientes ni historial privado a la consulta aislada.

Solo se aceptan enlaces HTTPS sin credenciales, IP literales ni parámetros de autenticación. Jarvis no hace peticiones directas a esos enlaces desde Render: el proveedor aplica sus restricciones de acceso público. No se incorporan herramientas de compras, pagos ni mensajes a este turno.

Referencia técnica: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool
