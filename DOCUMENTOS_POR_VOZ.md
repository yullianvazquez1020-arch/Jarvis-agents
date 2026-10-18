# Documentos por voz

Una petición explícita como «Jarvis, hazme una monografía sobre energía solar» genera un borrador y guarda DOCX y Markdown en `~/.jarvis-desktop/documentos`. En macOS se intenta abrir el DOCX con la aplicación predeterminada. La confirmación hablada es breve; no recita el documento completo ni una ruta de archivo.

Comandos:

- «Amplía la introducción del documento»: usa el último borrador y guarda otra versión.
- «Abre el último documento».
- «Recuerda para mis documentos: usa párrafos cortos»: conserva hasta cinco preferencias explícitas de redacción. No entrena el modelo ni cambia su código.
- «Recupera el documento pendiente»: consulta el resultado del turno original sin otra llamada al modelo.
- «Descarta el documento pendiente»: borra solo la referencia local pendiente, sin borrar los documentos guardados. Una petición nueva posterior sí consume otra generación.

También reconoce instrucciones en inglés, como “Write an essay about solar energy” y “Expand the introduction”. El modelo recibe la instrucción de redactar en el idioma solicitado. La voz del panel sigue usando su configuración existente.

## Instalación compatible con panel-unico

El instalador `scripts/install_voice_documents.py` acepta `--repo`, `--commit` (SHA completo ya descargado mediante git fetch) y `--check`. Obtiene únicamente `desktop/documentos.py` de ese commit. Comprueba la huella exacta del panel revisado antes de añadir dos líneas; rechaza versiones desconocidas. Hace respaldo en `~/.jarvis-desktop/update-backups`, instala el módulo antes del enlace y revierte los archivos escritos si falla. No reemplaza el display, audio, configuración ni rama del usuario. Reiniciar el servicio después de instalar.

## Límites y recuperación

Los endpoints requieren emparejamiento y permiso converse. No proporcionan herramientas al modelo ni ejecutan comandos generados. El nombre de archivo se deriva del ID del turno, no del texto generado. Las respuestas incompletas no producen archivos. Las revisiones preservan versiones anteriores.

El servidor conserva ocho resultados terminados recientes y los pendientes para recuperación; la idempotencia del mismo ID está limitada a ese registro. El cliente guarda el ID antes de enviar y no reintenta automáticamente una generación incierta. Los resultados usan el cifrado en reposo existente cuando está configurado. El contenido y las preferencias deben revisarse antes de compartirlos; las referencias no verificadas se presentan como sugerencias, no como investigación realizada.

La aplicación predeterminada puede rechazar la apertura aunque macOS acepte el comando; el archivo guardado es la evidencia verificable. La validación de escritorio completa requiere una prueba real en la Mac del usuario.
