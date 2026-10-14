# HUD v2 · reactor mecánico

Abre HUD desde la ventana principal del escritorio. El diseño usa un reactor dibujado en Canvas, paneles laterales, una silueta del asistente y cuatro medidores. El reactor y la silueta son elementos visuales; no representan sensores, actividad neuronal ni un análisis del cuerpo.

- Trabajos: hasta 20 abiertos, ordenados por vencimiento, y el total real. Las cinco posiciones son etapas registradas (cotización, confirmado, en proceso, entregado, facturado), no porcentajes de progreso. Pagados y cancelados quedan fuera.
- Línea de tiempo: fecha de registro y vencimiento. Solo dibuja un intervalo cuando ambas fechas son válidas y el vencimiento no precede al registro.
- Medidores: trabajos abiertos, latencia del servidor, ventanas locales y antigüedad del estado. Sin una medición aparece «sin dato»; cero sigue siendo cero.
- Seguridad: emparejamiento, almacenamiento y operaciones reales según las respuestas existentes. El HUD consulta; no aprueba ni ejecuta operaciones.
- Las tarjetas conservan sus detalles y el control Mostrar montos. Avatar y conversación abren sus vistas existentes.
- Voz continua: el cliente de la Mac avisa a `http://127.0.0.1:8765/api/voz`. El HUD muestra escucha, pensamiento, habla, el idioma (ES/EN) y el texto. La silueta mueve la boca mientras Jarvis habla. Si el HUD está cerrado, la voz sigue por los altavoces. Desde aquí no se aprueba ni se envía nada.

El servidor añade `jobs`, `jobs_count` y `as_of` al HUD autenticado. La consulta de trabajos usa el bloqueo de escritura existente y una lista explícita de campos. Un servidor antiguo puede seguir dando tarjetas: los trabajos aparecerán como «sin dato».

La animación está limitada a 24 FPS; la geometría se dibuja una vez y se reutiliza. Se detiene al ocultar la página, respeta movimiento reducido y tiene un botón de pausa. El lienzo limita resolución a 1.25× y 1400 píxeles por eje. Estos límites no sustituyen una medición en el Mac del usuario.

## Actualización del Mac

Desplegar el servidor no reemplaza los archivos del escritorio local. Actualiza la carpeta `desktop` completa desde esta versión, conserva tu configuración y reinicia el compañero. Abre HUD desde su ventana principal para conservar la sesión local; no es una página pública de `/telegram`.

## Verificación

Las pruebas del compañero cubren los campos nuevos, compatibilidad con un servidor anterior y protección de los recursos por sesión. `node scripts/check_hud.cjs` comprueba etapas, fechas inválidas, datos ausentes, privacidad y desconexión. Las pruebas del servidor comprueban autenticación, proyección limitada y ausencia de cambios en los libros. La compatibilidad y la fluidez en Safari del Mac físico requieren comprobarse allí.
