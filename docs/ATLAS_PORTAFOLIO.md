# Atlas local del portafolio — prototipo en revisión

Tres vistas Canvas 2D (torre, galaxia y membrana) en /avatar. La torre usa un piso por propuesta. No es un modelo arquitectónico 3D ni una reproducción exacta de las referencias. No hay empleados, agentes ni ingresos conectados en estas vistas.

Cinco propuestas iniciales: servicio local ISLAFIX, producto digital, contenido educativo, tienda por validar y afiliados. Todas incluyen costo estimado, objetivo de 30 días, métricas y aprobación necesaria. Seleccionar un piso no inicia un negocio ni autoriza una operación. No hay tareas programadas, publicación, mensajería o llamadas a modelos en atlas.js. El reporte diario y el paquete semanal aún necesitan integración con datos reales y el flujo de aprobaciones.

## Mano

Activar mano requiere permiso de cámara en el navegador y red para obtener MediaPipe. Navegar con la mano habilita un cursor virtual solo para las tres pestañas y cinco propuestas. Índice sobre el control durante 1,2 segundos selecciona. Escape detiene la cámara y la navegación. Pérdida de señal mayor de 350 ms cancela la selección. No puede confirmar operaciones ni mover el puntero de macOS.

El seguimiento corre a un máximo de 15 detecciones por segundo; el atlas dibuja a 24 cuadros por segundo como máximo y se pausa fuera de pantalla o en una pestaña oculta. Movimiento reducido detiene la evolución de la escena. No se ha medido la memoria ni el rendimiento en el Mac 2015.

## Validación de este corte

- 42 pruebas de desktop_companion: pasan.
- Comprobación sintáctica de atlas.js y hands.js: pasa.
- Tres rutas de dibujo, cinco propuestas, selección y corte de cursor ante señal obsoleta: comprobadas en Node con DOM simulado y Canvas real.
- No es una prueba de navegador, MediaPipe real, Safari ni cámara.
- scripts/validate_suite.py se detiene: falta redis-server. No se declara suite completa verde.

No cambia main:app, Render, los límites monetarios ni GEMINI_ENABLED. No requiere servicios de pago. El consumo existente del resto de Jarvis no se vuelve gratuito por este cambio.
