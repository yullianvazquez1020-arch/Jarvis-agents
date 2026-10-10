# Prueba local: mano → puntero de macOS

Control manual del dueño, sin modelo de lenguaje ni API de pago. No es acceso remoto de Codex, Claude, Grok o MyClaw. No altera el ejecutor de agentes, sus turnos ni sus permisos. Tampoco cambia Render, el comando de producción, los límites financieros ni los gates.

## Alcance de este corte

- El modo original solo mueve el puntero de la pantalla principal medida por PyAutoGUI. El modo nuevo de clic requiere el botón separado «Mover + clic con pinza · 60 s» y una confirmación explícita. Solo permite un clic izquierdo; no scroll, teclas, clic derecho, doble clic, arrastres ni capturas. No recibe comandos libres.
- Apagado por defecto. Requiere iniciar la app local con `--hand-mouse` y pulsar el botón físico del panel «Mover mouse de Mac · prueba 60 s». La navegación por permanencia de Atlas no puede seleccionar ese botón y se suspende mientras el modo de macOS está activo.
- Cada activación vence a los 60 segundos, sin renovación automática. La concesión se guarda solo en memoria y se vincula a la sesión local y a un token aleatorio. Se rechazan otras sesiones, tokens falsos, cuadros repetidos, no finitos o vencidos.
- La cámara se analiza en el worker existente. El puente recibe coordenadas normalizadas y tiempo de captura; en modo clic añade la distancia pulgar–índice dividida por el ancho de palma. Nunca recibe imágenes. Un único destino sustituye al anterior, sin cola. Pasados 400 ms desde la captura deja de mover. El movimiento se suaviza y cada paso tiene un límite aproximado de 60 píxeles.
- Escape se consulta localmente en macOS además del evento de Firefox. Llevar el puntero al borde o fuera de la pantalla principal también apaga la concesión. PyAutoGUI conserva FAILSAFE. No lee ni guarda texto del teclado.
- Ocultar la pestaña, apagar la cámara o cerrar el panel detiene el puente. Si el navegador deja de enviar datos, caducan primero las coordenadas y después la concesión. Los errores nativos apagan el modo.
- El acceso HTTP requiere cookie de sesión, `X-Jarvis-UI: 1`, Host válido y Origin local explícito. No se habilita en LAN ni DEMO. No se escriben permisos reutilizables en disco.

## Arranque en el Mac del dueño

Conservar la instalación ya existente de PyAutoGUI y PyObjC en `~/.jarvis-control-venv`; no instalar dependencias en Render.

```bash
cd "$HOME/Jarvis-agents"
BROWSER='open -a Firefox %s' "$HOME/.jarvis-control-venv/bin/python" desktop/app.py --hand-mouse
```

Abrir el enlace de acceso en Firefox. En Avatar local, activar Logitech BRIO y verificar puntos reales de los dedos. Pulsar «Mover mouse de Mac · prueba 60 s», mantener el índice visible y moverlo lentamente. Para probar clic, detener primero el modo de movimiento y seleccionar el botón nuevo. Confirmar solo sobre una zona de prueba vacía, lejos de acciones de envío o compra. Escape cancela; una nueva activación requiere volver a pulsar el botón con el mouse físico.

La pantalla principal del dueño fue medida previamente en 3840×1080. Esto no es control coordinado de varios monitores. El dueño confirmó movimiento real con Brio durante la prueba de 60 segundos y parada con Escape. Esto no verifica todavía el nuevo clic por pinza.

## Verificación y límites

`tests/test_hand_mouse.py` prueba sin hardware la caducidad, la frescura, la vinculación a sesión/token, Escape, límites, errores, ausencia de clics y cierre. Las pruebas HTTP del panel cubren denegación sin sesión/origen y apagado por defecto. Los dobles de prueba no certifican precisión, latencia ni permiso de Accesibilidad en macOS.

Pendiente en la Mac: movimiento con la Brio, latencia, pérdida de mano, Escape fuera de Firefox, parada al borde y vencimiento real de 60 segundos. No fusionar ni desplegar este corte sin revisión y autorización del dueño. Un programa malicioso ejecutándose bajo el mismo usuario del sistema queda fuera de esta frontera de seguridad.

## Clic por pinza: contrato y verificación pendiente

Modo apagado por defecto. `arm` conserva `SOLO_MOVER_60S`; el botón nuevo pide `MOVER_Y_CLIC_60S`. Solo en este modo, cada `frame` añade `pinch_ratio`, calculado con los puntos 4, 8, 5 y 17. `null` significa pérdida de detección y borra el gesto inmediatamente. La concesión sigue ligada al dueño, al token aleatorio y al límite de 60 segundos.

Primero se observa una apertura (ratio ≥ 0.6). Al acercar los dedos se congela el puntero para apuntar sin arrastrarlo; un cierre ≤ 0.3 durante al menos 350 ms y tres capturas distintas permite un único clic izquierdo. Mantener la pinza nunca repite el clic. Hay que volver a abrir después del segundo de espera antes de un gesto nuevo; abrir durante ese segundo no deja un clic pendiente. Capturas inválidas, repetidas, antiguas o pérdida de mano borran el gesto y exigen abrir otra vez.

Solo el ciclo nativo ejecuta el clic, después de comprobar Escape, borde, caducidad y captura reciente. No hay cola de clics. La navegación por permanencia de Atlas permanece suspendida mientras el puente está activo. La confirmación de macOS no convierte a ninguna IA en operador remoto.

La precisión de pinza y el clic físico con Brio/Firefox siguen pendientes de prueba en la Mac. La medida es una heurística de distancia, no certifica intención ni identifica al dueño de la mano. La primera prueba debe hacerse únicamente sobre «Probar clic · 0»: incrementa un contador local sin llamadas, mensajes ni escrituras. Apuntar allí con los dedos abiertos, cerrar la pinza medio segundo y volver a abrir. Nunca probar sobre enviar, pagar o borrar. Este código se prepara para revisión; no implica autorización de fusión o despliegue.
