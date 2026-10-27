# Jarvis sin Upstash: despliegue seguro (propuesta; NO activar sin respaldo)

## Diagnóstico confirmado
El código main.py acepta almacenamiento JSON local si **ambas** variables
UPSTASH_REDIS_REST_URL y UPSTASH_REDIS_REST_TOKEN están ausentes. Si solo
una existe, falla. Al usar Redis, el arranque exige EVAL para liderazgo.
Sin Redis, main.py usa DATA_DIR y el disco original puede ser efímero.

## Requisitos previos
1. Exportar y verificar un respaldo de los datos actualmente guardados en
   Upstash; no quitar variables ni redesplegar hasta verificar una migración.
   Este PR **no migra** datos de Redis.
2. Provisionar almacenamiento **realmente persistente** (VPS con volumen
   durable / disco montado). No sirve una carpeta efímera de Render.
3. Asegurar que un solo servidor/proceso escribe a ese volumen. No usar
   múltiples réplicas ni dos servidores que comparten el mismo estado.
4. Restaurar los archivos JSON originales a DATA_DIR, incluidas las claves
   y metadatos cifrados; conservar la clave de cifrado necesaria.
   Validar restauración sin imprimir credenciales.
5. Comprobar que estado de Telegram pendiente, deduplicación y operaciones
   transaccionales no se duplican al cambiar proveedor; ejecutar pruebas
   de recuperación y flujos de aprobación antes de habilitar tráfico.

## Variables para el nuevo despliegue Linux
- DATA_DIR=/ruta/absoluta/al/volumen/persistente
- JARVIS_PERSISTENT_STORAGE_CONFIRMED=YES
- PORT=8000 (o asignado por proveedor)
- Remover COMPLETAMENTE UPSTASH_REDIS_REST_URL y UPSTASH_REDIS_REST_TOKEN.
- JARVIS_ALLOW_EMPTY_STORE=YES **solo** si el dueño autoriza iniciar sin
  ninguna memoria antigua; nunca hacerlo para resolver apresuradamente
  una migración fallida.

Comando: `python3 scripts/start_without_upstash.py`

La comprobación del script impide arranque sin disco declarado persistente,
sin datos previos (salvo autorización explícita) o con otro proceso que
mantenga el bloqueo del mismo volumen. El bloqueo es local (flock en Linux)
y **no protege entre máquinas distintas**. No certifica persistencia
automáticamente: esa condición depende del proveedor y de su configuración.

## Condiciones de aceptación ANTES de conmutar Telegram/producción
- Respaldo restaurable y comparación de datos protegidos por cifrado.
- Prueba reinicio/despliegue que conserva memoria y cola.
- Webhook configurado para una sola instancia y sin mensajes duplicados.
- Aprobaciones de cobros, envíos y operaciones reales siguen requiriendo
  autorización del dueño, con topes preexistentes.
- Pruebas de voz/Telegram, health, diagnóstico, backups y recuperación.
- Reversión documentada; **no** ejecutar dos versiones productivas activas.

Nota: esta es una ruta de arranque y runbook, NO un cambio automático
de infraestructura ni la confirmación de que Jarvis está funcionando.
