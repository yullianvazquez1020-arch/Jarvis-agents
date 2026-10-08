# Entrega Grok: cotejo e integración

`main(4).py` y el `main.py` del ZIP son idénticos al commit `b67a629`. Reemplazar main quitaría cifrado/recuperación del PR #14, caja/fichas del PR #15 y la conciliación explícita de ingresos. `desktop-app.py` es idéntico al escritorio existente. Se conservan los archivos actuales.

La aportación nueva es el avatar de canvas y una aproximación de movimientos de boca. El original no genera audio, muestra «en línea» sin verificarlo, consulta un puerto local absoluto y no muestra el resultado; su generador Python elimina vocales acentuadas en vez de normalizarlas. No se instala ese generador redundante: la vista usa la normalización Unicode del navegador.

Se incorpora la animación en `/avatar` del escritorio local, enlazada desde el panel. Usa la misma cookie de sesión, lista permitida de archivos, comprobación de Host y CSP existente. CSS y JavaScript se separan para respetar esa CSP. La consulta de estado es del mismo origen; no se abre CORS, se envían tokens a otro puerto ni se publica en Render.

«Animar frase» solo mueve la boca: no sintetiza voz, escucha el micrófono ni ejecuta órdenes. Se limita a mil caracteres y un clic nuevo cancela la animación anterior. La vista indica conexión comprobada/DEMO o desconexión; no afirma sincronización real con audio. La conversación real sigue en el panel de escritorio existente.

Para usarla hay que iniciar el escritorio en la Mac con su procedimiento de sesión existente y abrir «Avatar local». El despliegue de Render no instala programas en la Mac. No se activan proveedores, cuentas ni gasto adicional.
