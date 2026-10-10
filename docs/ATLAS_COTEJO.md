# Órbita: cotejo y límites de la entrega

Referencia: image(5).png suministrada por el dueño. La referencia es una fotografía de una escena renderizada; esta implementación es Canvas 2D con proyección y sombreado procedural. No es una copia idéntica ni un modelo 3D fotorealista.

| Elemento | Referencia | Implementación |
|---|---|---|
| Ciudadela | Arquitectura dorada detallada | Terrazas sombreadas, ventanas, torres laterales y base invertida; menor detalle |
| Esfera | Nodos y conexiones cian | Retícula esférica y nodos animados |
| Mundo | Paisaje volumétrico | Montañas en capas; no terreno 3D |
| Viaje | Pedido adicional del dueño | Ciclo mundo verde, nebulosa, galaxia; estelas al salir, sin rutas comerciales reales |
| Dragones | Pedido artístico previo | Siluetas originales articuladas; 3 en ligero, 6 en detalle |
| Cuerpo | Identidad bioluminiscente | Malla vascular, columna, dedos articulados, boca RMS y sonrisa conservadas |
| Cerebro y membrana | Módulos científicos | Lóbulos y pliegues, membrana bilaminar; representaciones artísticas |
| Datos | Etiquetas de la referencia | Sin métricas ficticias: estado, agenda y cobros solo tras consulta explícita al servidor emparejado |

## Voz local

`VOICE_TTS_BACKEND=macos_say` y `VOICE_TTS_VOICE=auto-latino` seleccionan una voz española instalada, priorizando es_PR, es_MX, es_CO, es_AR, es_CL y después es_ES. No descargan voces. Una selección explícita se conserva. La selección no garantiza un acento puertorriqueño cuando no existe una voz es_PR. La velocidad sigue ajustándose desde el control existente del panel. No se clona la voz de un actor.

## Verificación

- 36 pruebas de gestos: aprobadas con puntero simulado; cubren arrastre, soltado, expiración, Escape, pérdidas de cuadros y calibración.
- 46 pruebas desktop_companion: aprobadas; incluyen preferencia de voz local, caché y ausencia de voces españolas.
- Cuatro comprobaciones JavaScript aprobadas: atlas, avatar, puente de mano y cámara.
- Consulta de datos: DEMO no muestra cifras como reales; únicamente tres GET de paneles conocidos tras verificar emparejamiento.
- Render de Canvas inspeccionado, no captura de navegador completo.
- Sin pruebas físicas nuevas en Mac, altavoz, Quartz o Brio; no se afirma latencia, FPS sostenidos ni desfase acústico medido.
- Conectar empleados y cuatro negocios adicionales requiere que existan sus registros y fuentes. No se inventa esa integración.
