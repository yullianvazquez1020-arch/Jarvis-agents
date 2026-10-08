# Integración de entregas de Claude y Grok

Base de trabajo: main después del PR12, commit 961047a2a4921fcd3b3238a66cbc58544c0fc59d.
El usuario envió las tareas a ambas herramientas; sus entregas aún no se recibieron en este repositorio.

## Responsabilidades

- Claude: parche de cifrado/migración, recuperación y pruebas. No activar la clave de producción.
- Grok: requisitos, fuentes y casos ficticios para flujo de caja, YouTube y Amazon. Su texto no es prueba de código implementado ni autorización para ejecutar acciones.
- Codex: revisar parches contra la base correcta, integrar, ejecutar regresiones y comprobar el despliegue autorizado.

## Validación reproducible

Python 3.12, dependencias de requirements.txt y redis-server en PATH:

```bash
python -m pip install -r requirements.txt
python -m pip check
sha256sum -c SHA256SUMS.txt
python scripts/validate_suite.py
```

El validador requiere faster-whisper 1.2.1, onnxruntime 1.30.0 y PyAV 16.1.0 importables.
Corre la misma suite de unittest discover y falla si hay errores, fallos, omisiones o menos de las 579 pruebas base.
Imprime los identificadores de pruebas fallidas y omitidas. No requiere credenciales de producción ni activa proveedores.
El workflow de GitHub valida cada PR con permisos de lectura y acciones fijadas por SHA; no fusiona ni despliega.
No ejecutar parches ni pruebas de terceros con claves reales del servidor.

## Condiciones para integrar

1. Confirmar commit base y archivos modificados; conservar trabajo concurrente.
2. Revisar lógica, especialmente recuperación de datos, errores y rutas de escritura.
3. Mantener topes $100/$300, aprobaciones y /confirmar fuera de la cola.
4. Mantener OpenAI/TTS externo/trading real apagados; voz local automática activa con WHISPER_BEAM=1.
5. Actualizar manifest SHA256SUMS.txt con cambios verificados.
6. Exigir la suite completa verde; las pruebas simuladas no sustituyen una prueba de la integración real.
7. Para cifrado, exigir respaldo y recuperación de la clave antes de cambiar producción.
8. En un despliegue autorizado, verificar SHA live, /health, Telegram y registros. No declarar conexiones externas probadas sin acceso real.

Las recomendaciones de Grok se convierten en tareas delimitadas y comprobables antes de escribir código.
No existe comunicación automática entre las sesiones personales de Claude/Grok y este repositorio.
