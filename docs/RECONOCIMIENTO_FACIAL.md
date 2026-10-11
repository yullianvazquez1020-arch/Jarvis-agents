# Reconocimiento facial local con Logitech Brio

Fase siguiente al control por mano: presencia y reconocimiento del dueño en el escritorio local.

## Qué hace
- Detecta rostros con MediaPipe Face Landmarker en el navegador (worker aislado).
- Prefiere automáticamente la cámara Logitech Brio.
- Enrolamiento simple del dueño: guarda una firma local (distancias entre puntos clave) en localStorage.
- Reporta `presente`, `reconocido`, confianza y landmarks en `window.JarvisFace` y evento `jarvis-face-frame`.
- Todo el procesamiento es local. Ningún cuadro ni embedding sale de la página ni va a Render.

## Uso
1. Abre `/avatar` en el acompañante local.
2. Pulsa **Activar rostro**.
3. Con tu cara visible, pulsa **Enrolar dueño** una vez.
4. El estado indica si el dueño está presente y reconocido.

## Integración
- Disponible en la página Avatar.
- Otros paneles pueden escuchar el evento o consultar `JarvisFace`.
- Compatible con el canal de cámara compartido para no pelearse con la mano.

## Límites
- Firma geométrica simple (no embedding profundo). Buena para presencia del dueño en condiciones similares de luz/pose; no es seguridad biométrica fuerte.
- Requiere permisos de cámara en Safari/Chrome.
- No modifica límites de dinero, aprobaciones ni envíos.

No despliega nada en Render. Solo archivos del escritorio local.
