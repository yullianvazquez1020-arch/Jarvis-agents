# Fluidez de la voz local

La respuesta hablada conserva un límite de 200 caracteres para el servicio de 512 MB.
Ahora termina en una oración completa dentro de ese límite. Si ninguna oración cabe,
remite al texto completo en lugar de leer una afirmación cortada. No añade otra llamada
a un modelo ni resume con una API. El mensaje escrito sigue siendo la referencia completa.

Antes de sintetizar se retiran marcas de formato y pictogramas. Tablas, código y URLs
se remiten al texto escrito. Las cifras, signos monetarios y negaciones de la prosa
se conservan. La selección de voz existente se mantiene; la leyenda deja de afirmar
incorrectamente que siempre es femenina.

Piper pasa de length_scale=1.16 a 1.0 (ritmo normal); afecta también la narración local
de video que comparte el sintetizador. La frase de recepción usa una nueva caché para
no reproducir el audio generado con el ritmo anterior. No se descargan nuevas voces.
Actualización (feat/core-display): Alan (en_GB-alan) vuelve a hablar más pausado, length_scale=1.18,
tanto en el escritorio (desktop/audio/engines.py) como en el servidor (jarvis_local_tts.ALAN_LENGTH_SCALE).

Las consultas automáticas por voz reciben una indicación de estilo: español latino
natural, tono cálido y directo, primera frase breve y completa, sin adornos repetitivos
ni promesas inventadas. Los permisos de solo lectura, herramientas, claves, memoria,
topes financieros y confirmaciones siguen iguales.

Verificación: pruebas de preparación de texto, integración del audio con Telegram
simulado, conversación en solo lectura y sintetizador local. Estas pruebas no validan
la percepción humana de naturalidad. Escuchar una nota real tras desplegar y comparar
con la anterior; un modelo local sencillo puede seguir sonando sintético.

Reversión: revertir el commit de este cambio. No limpiar memoria ni cambiar claves.

Referencia de la API de Piper (length_scale mayor de 1 ralentiza):
https://github.com/OHF-Voice/piper1-gpl/blob/main/src/piper/config.py
