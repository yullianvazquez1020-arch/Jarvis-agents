# Prueba local: mano → puntero de macOS

Control manual del dueño, sin modelo de lenguaje ni API de pago. No es acceso remoto de Codex, Claude, Grok o MyClaw. No altera el ejecutor de agentes, sus turnos ni sus permisos. Tampoco cambia Render, el comando de producción, los límites financieros ni los gates.

## Alcance de este corte

- Solo mueve el puntero de la pantalla principal medida por PyAutoGUI. No hace clic, scroll, teclas, arrastres ni capturas. No recibe comandos libres.
- Apagado por defecto. Requiere iniciar la app local con `--hand-mouse` y pulsar el botón físico del panel «Mover mouse de Mac · prueba 60 s». La navegación por permanencia de Atlas no puede seleccionar ese botón y se suspende mientras el modo de macOS está activo.
- Cada activación vence a los 60 segundos, sin renovación automática. La concesión se guarda solo en memoria y se vincula a la sesión local y a un token aleatorio. Se rechazan otras sesiones, tokens falsos, cuadros repetidos, no finitos o vencidos.
- La cámara se analiza en el worker existente. El puente recibe solo coordenadas normalizadas y tiempo de captura; nunca imágenes. Un único destino sustituye al anterior, sin cola. Pasados 400 ms desde la captura deja de mover. El movimiento se suaviza y cada paso tiene un límite aproximado de 60 píxeles.
- Escape se consulta localmente en macOS además del evento de Firefox. Llevar el puntero al borde o fuera de la pantalla principal también apaga la concesión. PyAutoGUI conserva FAILSAFE. No lee ni guarda texto del teclado.
- Ocultar la pestaña, apagar la cámara o cerrar el panel detiene el puente. Si el navegador deja de enviar datos, caducan primero las coordenadas y después la concesión. Los errores nativos apagan el modo.
- El acceso HTTP requiere cookie de sesión, `X-Jarvis-UI: 1`, Host válido y Origin local explícito. No se habilita en LAN ni DEMO. No se escriben permisos reutilizables en disco.

## Arranque en el Mac del dueño

Conservar la instalación ya existente de PyAutoGUI y PyObjC en `~/.jarvis-control-venv`; no instalar dependencias en Render.

```bash
cd "$HOME/Jarvis-agents"
BROWSER='open -a Firefox %s' "$HOME/.jarvis-control-venv/bin/python" desktop/app.py --hand-mouse
```

Abrir el enlace de acceso en Firefox. En Avatar local, activar Logitech BRIO y verificar puntos reales de los dedos. Pulsar «Mover mouse de Mac · prueba 60 s», mantener el índice visible y moverlo lentamente. No hay selección nativa por dedo en este corte. Escape cancela; una nueva activación requiere volver a pulsar el botón con el mouse físico.

La pantalla principal del dueño fue medida previamente en 3840×1080. Esto no es control coordinado de varios monitores. Las pruebas reales previas confirmaron movimiento de PyAutoGUI, detección de dedos en Firefox, selección dentro de Atlas y parada de cámara con Escape; NO prueban aún este nuevo puente.

## Verificación y límites

`tests/test_hand_mouse.py` prueba sin hardware la caducidad, la frescura, la vinculación a sesión/token, Escape, límites, errores, ausencia de clics y cierre. Las pruebas HTTP del panel cubren denegación sin sesión/origen y apagado por defecto. Los dobles de prueba no certifican precisión, latencia ni permiso de Accesibilidad en macOS.

Pendiente en la Mac: movimiento con la Brio, latencia, pérdida de mano, Escape fuera de Firefox, parada al borde y vencimiento real de 60 segundos. No fusionar ni desplegar este corte sin revisión y autorización del dueño. Un programa malicioso ejecutándose bajo el mismo usuario del sistema queda fuera de esta frontera de seguridad.
