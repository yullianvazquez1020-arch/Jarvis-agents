# Diagnóstico seguro del rechazo de arranque

El despliegue de PR176 (`dep-dbd7an142hec73airqo0`, commit `e7755c7`) falló el 22 de octubre de 2026: seis sondas de liderazgo recibieron HTTP 400. Una consulta a `/health` del servicio anterior el 23 de octubre respondió 500. Estos datos no prueban que el servicio esté sano ni que más reintentos resuelvan el problema.

Esta corrección conserva el contrato de `_redis` y los scripts de liderazgo/escritura. Antes se descartaba el error JSON al recibir HTTP 400; ahora se convierte exclusivamente a una etiqueta fija cuando coincide con una categoría conocida: cuota diaria/mensual, tamaño, conexiones, almacenamiento, permisos, solo lectura, autenticación, comando, argumentos o script Lua. Los cuerpos desconocidos, no JSON o demasiado grandes conservan únicamente la categoría HTTP. Nunca se imprimen cuerpos, tokens, URLs, argumentos ni claves Redis. No cambia los reintentos ni permite arrancar o escribir sin confirmar EVAL.

Validación local: 100 pruebas focalizadas pasan (`test_fence_reintentos`, `test_hardening`, `test_bus`, `test_brain`). Las tres pruebas nuevas cubren 14 categorías del proveedor, formatos desconocidos y respuestas de error con HTTP 200. Las pruebas simulan Redis; no se afirma haber solucionado el rechazo real. El entorno no tiene redis-server ni los componentes completos de voz instalados; no se ejecutó la suite integral.

Después del despliegue, revisar la categoría de arranque para corregir la causa en Upstash. Una cuota requiere reducir consumo o gestionar el límite de la cuenta; no se debe activar un plan pago sin aprobación. Un permiso exige revisar el token/ACL; un error de script exige revisar el script. No borrar claves, cambiar cifrado ni desactivar fencing.

Referencias del proveedor consultadas: https://upstash.com/docs/redis/features/restapi, https://upstash.com/docs/redis/troubleshooting/max_daily_request_limit y https://upstash.com/docs/redis/troubleshooting/max_requests_limit.
