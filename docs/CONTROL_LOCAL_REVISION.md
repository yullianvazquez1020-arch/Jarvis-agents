# Ejecutor local: revisión de PR32, pendiente de aceptación

Este corte extrae únicamente el ejecutor del PR32 (9e32bd2), pruebas y este documento. Excluye WhatsApp, crédito, gestos, panel y demás archivos del PR original. No inicia ningún proceso en la Mac ni cambia producción.

## Cambios

- Bloqueo de subcadenas financieras, incluyendo FirstBank, bancopopular, orientalbank, mibanco, Venmo, Zelle y pagos. Conservador: puede bloquear nombres inocuos que contengan esas cadenas.
- Atajos peligrosos se rechazan también con modificadores extra. Orden de modificadores antes de la tecla.
- usos.json deja de ser una autoridad. --otorgar queda retirado. Permisos y recibos aleatorios de un uso viven en memoria del proceso, con caducidad de 60 segundos. finish rechaza incluso la cadena literal «codigo» sin recibo.
- Archivos de decisión y gestos no aprueban ejecución. La confirmación se lee en la terminal local.
- Límite de 20 ejecuciones/minuto persistido con flock. Datos corruptos bloquean. Cambios cooperativos de turno y ejecución usan el mismo bloqueo.
- La ejecución se restringe a move, screenshot, scroll y wait. Clicks, escritura, URLs y aplicaciones no están habilitados en este corte.
- --confirmar-lote permite una confirmación para las cuatro órdenes fijas originales; sin archivo variable, con turno independiente de cada agente y sin tomar un turno ocupado. La captura se guarda solo localmente.

## Alcance de seguridad

No es un aislamiento contra programas maliciosos bajo el mismo usuario de macOS. Esos programas podrían modificar el código, los archivos de turno, reloj/sesión o usar PyAutoGUI directamente. Antes de conceder escritura/ejecución arbitraria a agentes externos se necesita un broker aislado con identidad y permisos del sistema. No se afirma que HMAC en una carpeta del mismo usuario resuelva ese problema.

Los nombres de agentes son etiquetas del lote, no una conexión autenticada a Claude/Grok/ChatGPT. No habilitar como servicio expuesto ni como «control total». Las funciones de compatibilidad para decisiones antiguas no son leídas por el camino de ejecución autorizado.

## Cotejo de 13 puntos

1. Turno obligatorio: prueba dry=False, permiso válido, turno ajeno => cero llamadas.
2. Uso único: consumo en memoria y recibo aleatorio; no se usa la cola de Jarvis.
3. Dry-run: self-test conserva cero llamadas al puntero.
4. Lote: una confirmación, cuatro acciones exactas con puntero simulado; un turno por acción.
5. Sin confirmación: ESPERA; cadenas de aprobación falsificadas bloqueadas.
6. Finanzas/atajos: nombres pegados y modificadores adicionales comprobados; escritura y apertura bloqueadas en ejecución.
7. Jarvis exige confirmación incluso con --libre.
8. Ritmo persistente y sesión revisada antes de ejecutar; aislamiento frente al mismo usuario NO resuelto.
9. Auditoría sin texto escrito ni tokens de autorización; solo longitud y hash del texto.
10. No cambia límites $100/$300.
11. No añade OpenAI, voz pagada, pagos ni mensajes.
12. No cambia cifrado ni secretos.
13. Self-test y 11 regresiones pasan con puntero falso. No es prueba física de Mac.

Pendientes: revisión independiente; CI de este nuevo commit; PyAutoGUI, Accesibilidad, FAILSAFE y captura real en Mac; aislamiento de agentes externos. No fusionar ni desplegar hasta autorización del dueño. No cambiar el comando uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1.
