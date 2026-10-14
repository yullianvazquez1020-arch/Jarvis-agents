# Tres frentes de dinero + tokens (técnico)

Todo es **borrador/propuesta**. Jarvis no cobra, no envía mensajes a clientes y no publica nada por su cuenta.
Comando del dueño en Telegram: `/frentes`, `/frentes planes`, `/frentes contenido DIA`, `/frentes pendientes`.
Reutiliza: `kv_get/kv_set`, bus de negocios (`jarvis_bus`, PR #120: negocios `contesta-ya` y `youtube`)
y la regla de topes del money gate (`_limits_problem`: $100/operación, $300/día).

## 1. Venta de acceso — `jarvis_frentes_acceso.py`
Planes de Contesta Ya (**PENDIENTE_APROBACION**, igual que la garantía borrador):

| Plan | Setup | Mensual | Notas |
|---|---|---|---|
| Fundador | $750 | $397 | primeros 3 clientes, precio por 6 meses |
| Básico | $1,250 | $497 | |
| Pro | $2,500 | $997 | |

Minuto extra $0.35 · mínimo 3 meses · IVU configurable (`FRENTES_IVU_TASA`, por defecto 0.115) — **confirmar con CPA**.
Incluye: lista de clientes, asignación/cambio de plan, medición de minutos por mes, factura borrador.
Pagos: `proponer_pago` solo crea una propuesta que requiere `/aprobar N` + `/confirmar N CODIGO`; montos
sobre $100 o que pasen $300/día quedan **bloqueados** (un setup de $750 no puede pasar por Jarvis).
Minutos incluidos por plan (500/500/1500) son supuestos de borrador.

## 2. Automatizar negocio — `jarvis_frentes_playbooks.py`
Plantillas `lead`, `recordatorio`, `seguimiento`. Cada ejecución crea tareas y borradores en una cola y publica
un evento en el bus. Un borrador solo pasa a `aprobado` con aprobación explícita del dueño; el módulo nunca envía.

## 3. Contenido a volumen — `jarvis_frentes_contenido.py`
Lee el calendario de 30 días de `docs/youtube/PLAN-CONTENIDO-2000-SUBS.md` (meta 2,000 suscriptores) y genera
título, guion y descripción por pieza, más borradores de productos digitales. Todo queda `en_revision`;
publicar sigue siendo `/publicaryoutube` del dueño.

## 4. Tokens — `tokens/`
ERC-20 mínimo de prueba (Foundry), solo testnet; el constructor revierte en mainnet y el script de despliegue
tiene `MAINNET_ENABLED = false`. Sin llaves, sin fondos, **no se desplegó nada**.
**Lo legal/regulatorio es responsabilidad de Yullian; esto no es asesoría legal.**

## Decisiones del dueño
1. Aprobar precios, cupo Fundador y garantía. 2. Tasa de IVU con el CPA. 3. Minutos incluidos por plan.
4. Cómo cobrar setups > $100 (fuera de Jarvis). 5. Qué día empieza el calendario de 30 días.
6. Si el token pasa de testnet: decisión legal y un PR aparte aprobado por el dueño.
