# Gestos visuales y fluidez

En /avatar, activa la cámara y después «Navegar con la mano».

- Índice: señala una vista o piso y espera 1,2 segundos.
- Pulgar e índice juntos en ambas manos: separa las manos para acercar y júntalas para alejar. Abre la pinza para fijar el zoom, entre 65 % y 250 %.
- V con índice y medio: mantén 0,9 segundos para cambiar a la siguiente vista.
- Puño: mantén 0,9 segundos para pausar el universo.
- Palma abierta: mantén 0,9 segundos para reanudarlo.
- Escape: apaga la navegación. «Restablecer zoom» vuelve a 100 %.

Un gesto sostenido ejecuta su comando una vez. Suelta o cambia de gesto para repetir. La pérdida de mano, pestaña oculta y control del mouse de Mac suspenden los comandos visuales. Estos gestos no aprueban órdenes ni escriben al sistema.

La Torre limita el canvas a 24 FPS, no dibuja con la pestaña oculta y congela el canvas en pausa. El suavizado de navegación y zoom se calcula según el tiempo entre cuadros.

Comprobado con landmarks y navegador simulados; falta medir la precisión y el rendimiento con la cámara en Safari de la Mac 2015. Las mejoras del escritorio necesitan actualizar los archivos locales y reiniciar app.py; Render sirve el agente remoto.
