# Informe automático: mercados y negocio

El informe existente ahora separa cripto (BTC/ETH/SOL), bolsa estadounidense y
materiales/economía de Puerto Rico. Solo consulta datos públicos: no incorpora
clientes, libros, saldos, historial de operaciones ni cartera del dueño.

Configuración: MARKET_ANALYSIS_ENABLED=true, MARKET_ANALYSIS_HOURS=6 y
WEB_SEARCH_ENABLED=true. Usa el cliente Anthropic existente y consume tokens y
búsquedas según su cuenta. No usa Venice ni añade proveedores de voz.

El scheduler intenta una vez por bloque de seis horas y envía al dueño por
Telegram si existe respuesta con búsqueda web. Sin búsqueda no inventa informe;
registra error y espera el siguiente bloque. La exclusión entre instancias evita
repeticiones. No garantiza entrega exactamente cada seis horas ante caída del
servicio o errores del proveedor. /mercado muestra el último informe y su edad.

Se piden fuentes, fechas y distinción de mercado cerrado/cotizaciones atrasadas.
El modelo no es un verificador financiero determinista. Los enlaces y datos deben
revisarse antes de decisiones. El informe no ejecuta órdenes ni activa dinero real.
Mantiene separado el rendimiento del trading y los ingresos de ISLAFIX PRO.
