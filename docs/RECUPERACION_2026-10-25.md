# Corrección de conversación y voz — 25 de octubre de 2026

## Cambios

- Se transmite el modelo elegido de `run` a `_run_turn`, también durante
  turnos con herramientas. Se corrige el uso de una variable no definida.
- Las llamadas con caché actualizan sus métricas agregadas sin registrar
  contenido de conversación.
- La transcripción respeta el idioma configurado; las consultas inglesas
  usan el mismo flujo restringido de lectura. Los alias de inglés seleccionan
  la voz masculina ya configurada por defecto.
- Detener el audio durante la síntesis descarta el saludo pendiente y termina
  su proceso de reproducción.
- Se evitan consultas y escrituras redundantes de estado. La caché limitada
  de reclamaciones solo rechaza duplicados; cada intento sigue comprobando
  el liderazgo contra el almacén y nunca concede autoridad por sí sola.
- El estilo de la pestaña seleccionada usa el atributo `aria-pressed` que
  actualiza el controlador. Las pruebas verifican la portada y rutas actuales.

Los controles de aprobación y el rechazo de operaciones sin liderazgo
confirmado conservan su comportamiento.

## Validación

`scripts/validate_suite.py` terminó con código 0: **1,625 pruebas Python,
cero fallos, cero errores y cero omisiones**, además de las comprobaciones
JavaScript de gestos, cámara, renderizado, saludo y ciclo de conversación.
Las dependencias de voz coinciden con las versiones exigidas por el proyecto.
El manifiesto de integridad verifica 389 archivos.

Se verificó localmente el recorrido Piper → WAV → FFmpeg/Opus → Whisper tiny
con frases sintéticas en español e inglés. Ambos idiomas produjeron audio y
transcripción; el saludo español tuvo un error de reconocimiento. Estas
pruebas no certifican precisión perfecta ni validan los dispositivos físicos
de otra máquina.

Las pruebas HTTP verifican las ocho vistas del panel y sus recursos, incluidos
contenido, tipo MIME y encabezado `nosniff`.

En un ensayo sintético de 60 ciclos de un minuto, después del trabajo inicial
del día y con Telegram/práctica apagados, las solicitudes al almacén bajaron
de 660 a 420 (36.4 %). El ensayo no representa consumo real de ningún servicio.

Para una validación completa en cada entorno se debe comprobar también el
inicio del proceso, una conversación con seguimiento, reproducción de voz,
entrada por micrófono y cancelación del audio en el dispositivo correspondiente.
