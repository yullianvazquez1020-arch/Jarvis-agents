# Plan de trading y distribución — experimento simulado

Prioridad solicitada por el dueño el 11 de octubre de 2026. No reemplaza ni reinicia
`jarvis:paper`: usa `jarvis:paper_plan_v1`, $1.000 iniciales simulados, con respaldo.
`/plantrading` muestra el estado en el Telegram privado del dueño.

## Reglas implementadas

- Spot exclusivamente; BTC-USD, ETH-USD, SOL-USD. No apalancamiento ni crédito.
- Entrada: señal existente de tendencia alcista y RSI 45–70 con precios públicos recientes.
- Riesgo previsto por operación: máximo 2% del patrimonio disponible para operar, incluyendo
  comisión de entrada, comisión de salida y deslizamiento simulado.
- Máximo $100 por entrada y $300 de entradas al día, incluso en este experimento. Las salidas
  de riesgo no se bloquean por estos topes simulados. El sistema real conserva sus aprobaciones.
- Stop guardado desde la entrada; primer objetivo NETO a 2R vende 50% de la cantidad inicial;
  segundo objetivo NETO a 3R vende el resto. No se prometen esos múltiplos realizados si hay gaps.
- Rebalance cada 7 días: recorta posiciones sobre el 25% del capital de trading; no fuerza compras
  sin señal. El cálculo usa el precio observado y las comisiones pueden dejar una desviación pequeña.
- Caída del patrimonio total del 20% desde su máximo: pausa persistente de entradas y cierra
  posiciones con precio fresco disponible. Una recuperación no quita la pausa automáticamente.
- El scheduler intenta revisar cada minuto, no hay un stop real alojado en Coinbase. Datos atrasados,
  reinicios, latencia y saltos de precio pueden producir pérdidas mayores a 2% y caída mayor a 20%.
  No se debe presentar el simulador como protección garantizada ni como ejecución en tiempo real.

## Ganancias y cuatro fondos

P&L realizado = producto neto de venta menos costo proporcional de compra, con comisiones y
deslizamiento ya incluidos. Se recuperan las pérdidas realizadas previas antes de distribuir.
Se limita además a ganancias totales marcadas sobre los $1.000 iniciales y a efectivo disponible:
no se reparte principal ni ganancias solamente abiertas.

Distribución acumulada en centavos: reserva fiscal 35%, operación 15%, suscripciones 10%, personal
40%. Redondeo determinista, centavos residuales al fondo personal. Repetir un paso no vuelve a
repartir. Se resta del efectivo de trading y se suma a fondos separados: el patrimonio total y el
drawdown incluyen ambos. Tras pérdidas posteriores, se exige superar lo ya distribuido antes de
repartir de nuevo. No se registran pagos ni gastos reales por separar estos fondos.

Los costos externos de internet, software y plataformas no están integrados: el 15% es una
asignación, no evidencia de facturas pagadas. $20 + $70 mensuales mencionados para suscripciones
son un presupuesto del dueño, no precios verificados ni una autorización de cobro automático.
El 35% es reserva provisional del dueño, no tasa fiscal ni cálculo de obligación ante Hacienda/IRS.

## Evaluación

Meta >55% de aciertos, rentabilidad neta positiva y RR previsto mínimo 1:2. Los aciertos se cuentan
por posición totalmente cerrada, sumando sus salidas parciales, no como dos trades ganadores.
La rentabilidad y el objetivo de aciertos todavía NO están demostrados. Se requiere evaluación
histórica fuera de muestra y seguimiento prospectivo con comisiones y slippage; 30 cierres no
garantizan suficiencia estadística. No se habilitará dinero real por alcanzar un porcentaje.
Escalar a $5.000 requerirá evaluación separada y seguirá sujeto a límites y autorizaciones.

## Operación y reversión

`PAPER_PLAN_ENABLED=true` habilita el experimento. Apagarlo detiene sus pasos automáticos, incluidas
sus salidas simuladas; no borra historial. El simulador anterior continúa como referencia separada.
No existe función de retiro real en este módulo, ni conexión a claves privadas de Coinbase.
El contenido incompleto después de «retirar a billetera personal» no se interpreta como instrucciones
adicionales de reparto o transferencia.

## Referencias verificadas

- Coinbase migró MATIC a POL; no se asume que MATIC-USD siga siendo negociable. POL no se añade
  silenciosamente al universo: https://help.coinbase.com/en/coinbase/trading-and-funding/sending-or-receiving-cryptocurrency/polygon-migration
- El tratamiento fiscal exige registros de ganancias/pérdidas; no se deduce una tasa universal del
  35%: https://www.irs.gov/filing/digital-assets

Pruebas automáticas usan precios sintéticos y no validan rentabilidad ni envían órdenes reales.
