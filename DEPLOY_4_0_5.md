# Jarvis 4.0.5 — revisión para despliegue

Fecha: 6 de octubre de 2026 (Puerto Rico).

## Estado de entrega

Revisión técnica aprobada. El dueño autorizó explícitamente publicar el código en
el repositorio público y desplegar en Render el 6 de octubre de 2026.
Verificar el estado del deployment y `/health` después de publicar.

## Decisión

Se elige el ZIP 4.0.5 de Claude como base. `main(2).py` es idéntico a su `main.py`.
`main(3).py` es idéntico al `main.py` del ZIP 4.2 de Grok. No se mezclan ambos núcleos.

| Área | 4.0.5 seleccionada | 4.2 recibida |
|---|---|---|
| Extensiones de negocio | Notas, facturas, cotizaciones, informes, recibos, dictado y acciones con aprobación | Extensiones reducidas a un registro de comandos y respuestas incompletas para recibos/voz |
| Crecimiento | Cálculos de producto, Amazon/YouTube opcionales, evaluación de práctica | `jarvis_growth.py` no instala funciones de negocio |
| Reinicios y datos | Cola Telegram durable, protección contra escrituras de instancias antiguas, restauración validada | Faltan estas funciones del núcleo 4.0.5 |
| Dinero | Selector práctica/real, bloqueo de práctica, doble confirmación y límites | No conserva el selector ni el bloqueo `CRYPTO_PRACTICE_ONLY` de esta base |
| Escritorio | Adaptador autenticado de solo lectura y acompañante local con dos pantallas | Página de transcripción mínima; no equivale al acompañante |
| Costos de IA | Comandos sin IA; conversación usa Claude cuando está configurado | El modo `free` puede llamar al Claude de pago para mensajes de acción |
| Controles 4.2 anunciados | No se anuncian como implementados | `ai_allow`, `ai_record_usage` y `check_red_allowed` se definen, pero no se invocan en el flujo de ejecución recibido |

## Ajustes de esta revisión

- Se añade `GET /health` como alias de `GET /`, tal como indicaba la documentación.
- Se fija Python 3.12.14 mediante `.python-version`, la versión usada para verificar.
- Se agregan dos pruebas HTTP con arranque/cierre real, escritorio encendido/apagado,
  autenticación, backup y funcionamiento sin clave de IA. Sin llamadas de pago.
- Se preservan los módulos y nombres de claves de datos existentes. No se migra ni restaura la base.

## Verificación local

376 pruebas aprobadas, 0 fallos, 0 omitidas, en 36.783 segundos.
FastAPI, Anthropic, httpx, Pydantic y las demás dependencias de `requirements.txt`
se instalaron realmente. `pip check` no encontró incompatibilidades.
Los tres tests de Lua usan un servidor Redis real local suministrado por redislite;
redislite es exclusivamente una herramienta de pruebas y no se añade al servidor.
Las integraciones externas de las pruebas usan dobles controlados: no se ejecutaron
órdenes, envíos a clientes ni llamadas de IA de pago.

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Para ejecutar también los tres tests Redis, `redis-server` debe estar en PATH.
Registro de la ejecución revisada: `docs/PRUEBAS_4_0_5.txt`.

## Servicio existente

- GitHub: `yullianvazquez1020-arch/Jarvis-agents`, rama `main`.
- Render: `Jarvis-agents`, `srv-db0hp2mgekts739p1pu0`.
- URL: https://jarvis-agents.onrender.com
- Build: `pip install -r requirements.txt`.
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1`.
- Una instancia; conservar plan, variables y Upstash existentes.
- No crear un segundo servicio ni reemplazar las variables por `.env.example`.
- `CRYPTO_PRACTICE_ONLY=true` y `COINBASE_TRADING_ENABLED=false`.
- El archivo `.python-version` se aplica salvo que Render tenga `PYTHON_VERSION`,
  que tiene prioridad. Revisar la versión efectiva en el log del build.

## Comprobación posterior

1. Confirmar el commit publicado y deployment `live` en Render.
2. `GET /health` debe responder HTTP 200, versión 4.0.5, almacenamiento Upstash,
   protección de escritura activa, trading real apagado y límites 100/300.
3. Revisar los logs de la nueva instancia por fallos de inicio o del scheduler.
4. Desde el chat privado del dueño: `/diagnostico`, `/cripto modo`, `/hoy`.
   El indicador `telegram_ready` solo comprueba configuración; no certifica por sí
   mismo la entrega de un mensaje real del bot.

## Alcance y pendientes

El despliegue del servidor no instala el acompañante en la Mac ni habilita motores
de voz. `DESKTOP_API_ENABLED` permanece opcional y apagado por defecto.
Micrófono, voces, Safari y monitores reales requieren la instalación local descrita
en `docs/VOICE_DESKTOP.md`. No se incluye el router OpenAI/local de la 4.2 ni se
presenta esta versión como una IA local gratuita ya instalada.

## Retorno a la versión previa

La versión previa verificada era 4.0.3, commit
`3fc1e617d95f6eb4e34d16e92ad0286fdf36ee02`.
Usar el rollback de Render a ese deployment si fuera necesario; no restaurar una
copia antigua de los datos sobre movimientos nuevos. El núcleo conserva las claves
anteriores; las claves del escritorio son adicionales.

Referencias oficiales de configuración:
https://render.com/docs/deploy-fastapi
https://render.com/docs/python-version
