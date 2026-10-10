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


## Cámara Brio y aislamiento del detector

La selección automática exige una cámara identificada como Brio; el selector permite elegir otra explícitamente. La vista previa indica la cámara usada. No se sustituye silenciosamente por FaceTime.

Tras reportarse un bloqueo al activar la mano en Safari del Mac del dueño, se separaron tanto la carga de MediaPipe como `detectForVideo` en `hand-worker.js`. No hay fallback de inferencia en el hilo del avatar. Se captura a resolución solicitada de 320×240, se reduce cada cuadro a ese tamaño y se analizan como máximo cinco cuadros por segundo. Solo puede haber un cuadro pendiente. Arranque: 40 segundos de límite; captura/inferencia: 2,5 segundos. El límite se comprueba desde el hilo del panel, que termina el worker y libera la cámara. Escape, cancelar, cambiar cámara o salir de la página también terminan el worker. Los resultados con más de 350 ms se descartan.

`node scripts/check_hands_camera.cjs` prueba con dobles la selección, los permisos sin etiquetas, la cancelación, los tiempos de espera, la ausencia de cola de cuadros y la liberación de imágenes. No equivale a ejecutar MediaPipe real ni Safari: la compatibilidad del worker/OffscreenCanvas, la Brio física y el rendimiento en el Mac siguen pendientes de comprobación. Si el navegador no admite el detector aislado, debe mostrar el error y detenerse, sin ejecutar el detector en el hilo del avatar.

Los cuadros solo pasan al worker del mismo navegador, no a Jarvis/Render ni a una API de IA. La descarga inicial del modelo y de MediaPipe sigue necesitando red. Este control permanece dentro del panel: no equivale a conectar el seguimiento con el mouse de macOS.

## Observatorio por especialidades

La vista de torre reserva 100 niveles en cinco sectores de 20: servicio local, producto digital, contenido educativo, tienda por validar y afiliados. El directorio conserva las cinco propuestas originales, con costos estimados y autorizaciones; no representa 100 negocios ni empleados activos.

Composición ultrawide: izquierda percepción, membrana y campo neuronal; centro ciudad orbital procedural con portales y dragones/jinetes originales; derecha amplitud de voz, sectores y estado no verificado de agentes/equipo. Cerebro y membrana son decorativos. Voz y detección se leen del estado local real; no hay porcentajes de inteligencia, penetración ni latencias ficticias.

Modo ligero predeterminado: hasta 15 FPS; detalle: hasta 24 FPS. Pausa explícita y respeto inicial de movimiento reducido. No se dibuja si la escena queda fuera de pantalla o la pestaña se oculta. Canvas 2D procedural, no un motor 3D ni una reproducción fotorrealista de la referencia. Sin activos de franquicias ni nuevos modelos descargados.

Validación: scripts/check_atlas_observatory.cjs ejercita vistas, sectores, pausa, estados reales y ocultación. Con ATLAS_NATIVE_CANVAS permite renderizar el lienzo en /tmp, no la página completa. Falta verificar layout Firefox y rendimiento Mac real.
