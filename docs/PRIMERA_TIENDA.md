# Primera tienda en Jarvis

El registro vive en el almacenamiento de Jarvis (Upstash en el servidor configurado), no en el navegador. No crea una tienda pública ni conecta cuentas de cobro.

En el chat privado del dueño, sin créditos de IA:

```text
/tienda nombre NOMBRE DE TU TIENDA
/tienda presupuesto 0
/tienda producto Descripción del producto por investigar
/tienda borrador Texto de la ficha por revisar
/tienda tarea Revisar precio y costos
/tienda resultado Resultado declarado por el dueño
/tienda
/tienda ver 1
/tienda listo 3
```

Los IDs son consecutivos entre productos, borradores, tareas y resultados. Solo las tareas admiten `listo`. Repetir exactamente un registro no lo duplica. El presupuesto es planificación (0–300 USD diarios), nunca permiso para gastar. Los resultados son anotaciones no verificadas y no modifican los libros, banco o trading. Renombrar conserva los registros. Máximo 500 registros, 2000 caracteres cada uno; no se eliminan silenciosamente al alcanzar el límite.

El panel emparejado muestra una tarjeta «Primera tienda» y la conversación puede consultar `store_status` para leer el plan. La conversación con IA sigue dependiendo del proveedor; `/tienda` no. La escritura se hace mediante el comando del dueño, no desde la sesión de solo lectura de la Mac. `/backup` incluye `store`; la restauración valida el registro antes de escribirlo.

El formulario externo «MANDO / Guardar en este equipo» no forma parte de este repositorio y no se importa automáticamente. Para conectar ese formulario hace falta su archivo o código. Esta implementación funciona con Telegram y el HUD existente.

Validación pendiente en dispositivo: comprobar la tarjeta y escuchar la lectura con Juan en la Mac del dueño. Las pruebas automatizadas no verifican el altavoz ni Safari del dueño.
