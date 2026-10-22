# Jarvis Business OS — tema visual preliminar

## Estado
Propuesta visual aislada para revisión; NO fusionar ni desplegar automáticamente.

## Previsualización
Abrir la interfaz existente con `?business_os=1` al final de la URL.
Quitar el parámetro para recuperar el aspecto actual.

## Alcance técnico
- Cambios únicamente de CSS y una clase visual de activación.
- Mantiene los IDs DOM, controladores, voz, mouse, estado, alertas y prácticas de trading.
- No implementa todavía las tarjetas de métricas, CRM, call center ni módulos de la imagen conceptual.
- No presenta cifras simuladas como datos reales.

## Pruebas obligatorias antes del merge
1. Verificar el diseño en escritorio, móvil y doble monitor.
2. Probar micrófono, voz, enviar, cancelar, alertas, emparejamiento y mouse.
3. Ejecutar suite UI existente y pruebas de regresión.
4. Verificar que sin el parámetro no cambió el diseño.
5. Comparar captura del tema contra la referencia aprobada por el propietario.
