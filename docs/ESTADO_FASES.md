# Estado de las fases — 11 de octubre de 2026

Este documento distingue implementación, configuración y operación comprobada.
Un conector preparado no equivale a un envío recibido ni a un pago conciliado.

## Estado observado en producción

Consulta de `/health` a las 16:43 PR del 11 de octubre: versión 4.2.4, Upstash
permanente, protección de escrituras activa, scheduler activo y sin último error.
Render confirmó el despliegue `2713a282` (PR71) como `live`.

| Fase | Implementado y comprobado | Requisito que sigue abierto |
|---|---|---|
| 1. Registros personales y libros | Editar/borrar, completar pagos/recordatorios, recurrencias; pruebas locales aprobadas | Validar los datos reales que introduzca el dueño |
| 2. Clientes y trabajos | Precio/costo, pagos parciales, saldo, documentos y borradores con aprobación; pruebas aprobadas | Cliente piloto y oferta vigente; comprobante antes de registrar cobros |
| 2. Mensajes y correo | Borradores y conectores con aprobación; en producción `sms=false`, `email=false` | Proveedor/remitente configurado y entrega de prueba autorizada; no hubo envío real |
| 3. Organización | Calendario local, inventario y alertas de stock; pruebas aprobadas | Calendario externo sin conectar; no confundirlo con la agenda local |
| 4. Avisos proactivos | Scheduler activo; resumen bancario semanal habilitado, lunes 08:00 PR; reglas de caja probadas | Importación bancaria reciente y vencimientos completos; no existe conexión bancaria privada verificada |
| 5. Análisis de mercados | Informe separado de cripto, acciones y negocio; programado cada seis horas | Fuentes disponibles en cada ejecución; noticias/precios privados no garantizados, usar sin dato cuando falten |
| 6. Trading | Plan simulado habilitado, órdenes reales apagadas; evaluación de minuto documentada | Muestra prospectiva y validación histórica suficiente; −2,02% en siete días no acredita rentabilidad |
| Oportunidades de productos | Cálculo de margen con costos explícitos y candidatos documentados | Cotización puesta en PR, calidad, demanda y aprobación de cada compra |
| Voz, display y manos | Cambios en el otro hilo del dueño; voz automática Telegram habilitada según salud | `device_delivery_verified=false`; prueba en la Mac y recepción de voz aún no certificadas aquí |

## Verificación de esta entrega

255 pruebas locales aprobadas: registros, flujos del negocio, extensiones, fase A,
brief, operaciones, aprendizaje, alcance del mercado, plan de práctica y evaluación.
Incluyen siete pruebas nuevas de continuidad de velas, precios válidos, archivos
dañados, calentamiento de indicadores y ausencia de uso del cierre de la hora actual.
Proveedores y datos de negocio de prueba simulados: no son ventas, cobros ni mensajes reales.

La suite completa local se interrumpió con `Bus error` al cargar dependencias nativas
de voz. No se presenta como aprobada ni se eliminaron esas pruebas: GitHub Actions
es la puerta de integración completa, con dependencias reales y Redis sin omisiones.

El parche de evaluación valida también las cachés, carga sus propias horas previas
si faltan y registra hashes de ambas fuentes. No modifica las reglas del plan,
el capital simulado, VERSION ni la producción de trading. No recalcula ni sustituye
las cifras históricas publicadas.

## Para cerrar la operación real

Ver `PENDIENTES_OPERATIVOS.md`: cuentas/remitentes, oferta y cliente piloto, datos de
cobro, cotizaciones y evidencia de entrega. Las claves se ponen en el proveedor,
nunca en Git ni en el chat. El envío exacto conserva aprobación del dueño.

Los límites siguen en $100 por operación y $300 por día. Comprar, pagar, publicar
o activar dinero real no se autoriza por completar estas fases. IA local 24/7
requiere hardware accesible y mediciones; no se declara instalada por tener código.
