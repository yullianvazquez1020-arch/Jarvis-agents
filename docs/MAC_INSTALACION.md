# Instalación local y alcance del control

Desde la carpeta del repositorio en macOS:

```bash
python3 scripts/mac_setup.py --install --launch
```

El instalador usa un entorno virtual local, instala PyAutoGUI y Quartz y comprueba Accesibilidad sin mover el puntero. Muestra la resolución y la voz española instalada que seleccionó. Prioriza es_PR y después español latino; favorece voces femeninas conocidas dentro de cada idioma. No descarga modelos de voz ni promete un acento que no esté instalado. Si falta Accesibilidad, informa dónde concederla y termina; el dueño vuelve a ejecutar el comando después de concederla.

La apertura del panel no activa el mouse: la activación y parada siguen siendo controles visibles del panel. Escape, pérdida de mano y caducidad de la sesión conservan su función. El controlador actual es para gestos del dueño; no da acceso remoto a este chat ni a otros agentes.

## Criterio incorporado de la revisión de Claude

El control autónomo necesita un ejecutor instalado en la Mac y un canal autenticado de acciones. La conexión de lectura y conversación no otorga ese permiso. No se deben eludir las autorizaciones del sistema operativo.

Antes de integrar el ejecutor revisado se debe verificar:

- Bloqueo de bancos y pagos por subcadena y dominio, incluyendo nombres pegados.
- Atajos peligrosos bloqueados también con modificadores adicionales y orden de teclas correcto.
- Permisos no falsificables, de un uso y con vencimiento corto.
- Límite de ritmo persistente entre ejecuciones.
- Turnos por agente: con turno ajeno, ninguna llamada al puntero incluso en la ruta de ejecución real.
- Confirmación, parada local, Accesibilidad y FAILSAFE con hardware real.
- Parche mínimo separado de envíos, crédito y otros módulos.

Las pruebas con un puntero simulado no verifican movimiento físico. Tener el programa en el repositorio tampoco instala ni enlaza una Mac.

## Pruebas físicas pendientes

Comprobar selección de Brio, clic, arrastre, dos dedos y parada en Firefox; escuchar la voz elegida y comparar boca con audio; medir fluidez y memoria del display con voz y gestos activos. Los paneles deben conservar la distinción entre datos reales, propuestas y desconexión. Estas comprobaciones requieren acceso al equipo y no se declaran realizadas desde un contenedor.
