# Jarvis Business Core — costo adicional $0 (fase inicial)

Modulo `business_core.py`: SQLite de la biblioteca estandar, **sin servicios externos**.
No se importa ni se inicia desde `main.py`; el PR es aditivo y no altera el servicio actual.

## Funciones implementadas
- Contactos CRM segregados por `tenant` (cada negocio).
- Tickets entrantes, con canal, asunto y contacto.
- Cotizaciones en borrador (nunca se envian automaticamente).
- Libro de diario de **partida doble** en centavos, con equilibrio obligatorio y referencia duplicada rechazada.
- Cola de acciones sensibles con aprobacion del propietario y auditoria.
- Resumen de operaciones por negocio.
- Pruebas unitarias `python -m unittest -v test_business_core`.

## No implementado (no declarar que funciona)
- PBX/call center telefonico: faltan proveedor telefonico, numero y webhook.
- Entrada/salida de WhatsApp, email, pagos o bancos: requiere conexion verificada de cada canal.
- Asesoria legal y financiera: requiere fuentes actualizadas y revision por profesionales competentes.
- Autenticacion de clientes, cifrado de datos por tenant, RBAC, copias y retencion: **obligatorios antes de exponer una API**.
- Migracion de la base historica Upstash: no copiar datos sin credenciales administrativas y respaldo verificable.
- Persistencia del SQLite en Render: **no desplegar sobre disco efimero**.

## Integracion y produccion
1. Recuperar Upstash original (cuota mensual excedida) manteniendo EVAL y fencing. No eludir.
2. Configurar un volumen persistente respaldado en VPS para SQLite (no en Render actual).
3. Anadir autenticacion robusta y autorizacion tenant por request; nunca confiar en tenant entregado por el cliente.
4. Integrar todos los canales a la cola de aprobaciones existente `/confirmar`; `review_action` es solo un registro, NO ejecuta.
5. Pruebas de restauracion, cargas, seguridad, permisos y cumplimiento antes de operar con clientes.

**Costos:** modulo de software $0. Telefonia, transcripcion, modelos externos, VPS y almacenamiento persistente pueden tener costos; no contratar sin aprobacion.
