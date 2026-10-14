# Ejecutor del mouse en la Mac

Los agentes proponen órdenes en un archivo `.jsonl`. El dueño las aprueba **una sola vez**, antes de irse, y después el puntero corre solo, pero solo esas órdenes, solo con el turno de cada agente y solo hasta que venza el permiso.

## Antes de irte (una vez)

```
cd desktop/mac
python3 agent_executor.py --dry-run --file ordenes_confirmadas.jsonl       # revisa en seco; no mueve nada
python3 agent_executor.py --otorgar --file ordenes_confirmadas.jsonl --horas 8
```

`--otorgar` muestra cada orden completa antes de pedirte nada: coordenadas, desplazamiento, segundos, el texto que se escribirá, la URL, la app o las teclas. Después te muestra un código. Si escribes el código, cada orden recibe un permiso firmado que sirve una vez y vence en 8 horas (máximo 24). Sin el código, o si no lo corres desde tu terminal, no se otorga nada.

## Mientras no estás

Cada agente toma su turno y corre su orden:

```
python3 agent_executor.py --take-lock grok --minutes 5
python3 agent_executor.py --file ordenes_confirmadas.jsonl
```

- Una orden con permiso y con el turno de su agente se ejecuta. El permiso se gasta en ese momento y se gasta una sola vez, aunque dos ejecutores lo intenten al mismo tiempo.
- Solo corre un ejecutor real a la vez. Si ya hay uno corriendo, el segundo responde `OCUPADO` y no hace nada.
- Justo antes de mover el puntero se revisa todo otra vez: tu código, la parada (`STOP`), la denylist, que la sesión siga vigente y que el turno siga siendo de ese agente.
- Una orden sin permiso queda en `ESPERA` y no se ejecuta.
- Si estás frente a la terminal, solo confirma el código de un uso que sale en tu pantalla. Ese código no se guarda en ningún archivo. Una «s» suelta no confirma, y un gesto ✊ (o cualquier archivo `decision.json`) solo puede **cancelar**.
- Una orden que no tiene el turno de su agente queda `RECHAZADO turno` y no se ejecuta.
- **Para pararlo todo:** crea el archivo `~/.jarvis-control/STOP`. También puedes llevar el mouse a la esquina superior izquierda.

## Lo que nunca pasa, aunque lo apruebes

- **Banco, pagos y finanzas.** Bancos (incluido FirstBank, aunque esté pegado a otras palabras como en `1firstbank.com`), pagos, Coinbase, PayPal, Venmo, ATH Móvil, tarjetas y burós de crédito quedan **BLOQUEADO**.
- **Comandos de terminal:** `sudo`, `rm -` y `curl` quedan bloqueados.
- **Atajos peligrosos:** salir, cerrar sesión, forzar salida, borrar y Spotlight quedan bloqueados, también si se les suma otra tecla.
- **Apps:** Terminal, Finder, Ajustes, Llavero, Mail, Mensajes, WhatsApp y Telegram no se abren.
- **Ritmo y sesión:** el tope de ritmo (20 por minuto) se mantiene entre corridas, y una sesión vencida sigue bloqueando.
- **Auditoría:** `~/.jarvis-control/audit.jsonl` guarda solo el largo y un hash corto del texto, nunca el texto.

## Dónde se guarda cada cosa

- **`~/.jarvis-owner/`:** la llave que firma los permisos y los permisos ya gastados. Es una carpeta aparte de la de los agentes, con permisos `700`. Un permiso escrito a mano, alargado o reusado no vale.
- **Límite:** el turno (`lock.json`) y la sesión (`session.json`) siguen en la carpeta de control, donde escriben los agentes. Un agente podría tomarse un turno o reabrir la sesión escribiendo esos archivos. Aun así, sin un permiso firmado por ti no mueve nada. Moverlos a `~/.jarvis-owner` queda como siguiente paso.
- **Límite:** cualquier programa que corra con tu mismo usuario de macOS puede leer esa carpeta. Para separarla del todo habría que guardar la llave en el Llavero o correr los agentes con otro usuario.

## Mouse automático: ejecutar el lote sin cambiar turnos a mano

Con el display actualizado y el permiso de Accesibilidad concedido, desde la carpeta del proyecto:

```bash
"$HOME/.jarvis-control-venv/bin/python" desktop/mac/agent_executor.py --otorgar --file desktop/mac/ordenes_confirmadas.jsonl
"$HOME/.jarvis-control-venv/bin/python" desktop/mac/agent_executor.py --automatic --file desktop/mac/ordenes_confirmadas.jsonl
```

El primer comando muestra el texto completo (escapando caracteres de control) y el orden exacto de las teclas. El segundo ejecuta una sola vez el lote aprobado, coordinando y liberando los turnos. No pide códigos, no se concede permisos y no repite órdenes gastadas. Un turno ocupado queda `OCUPADO`, sin quitárselo a otro agente. Una orden nueva o sin permiso queda en `ESPERA`. La lista incluida es una prueba: mover, capturar, desplazar y esperar; no completa tareas generales por sí sola.

El movimiento aprobado tiene una transición de 160 ms y no añade la pausa global de PyAutoGUI. Es suavizado intencional, no una garantía de cero latencia. La sesión dura **10 minutos** desde su inicio; el permiso puede vencer más tarde, pero no prolonga una sesión vencida. STOP y la esquina superior izquierda siguen deteniendo el control. Si falla el puntero, se crea STOP y las órdenes siguientes no se ejecutan. El mouse por gestos mantiene su permiso independiente de 60 segundos y Escape.

Los permisos anteriores de atajos quedan invalidados al cambiar la representación de sus teclas; vuelve a aprobarlos. Con el mismo usuario de macOS, los agentes y el dueño no están aislados por sistema operativo: el candado y la firma no sustituyen ese aislamiento.

### Recuperar una sesión vencida

`python desktop/mac/agent_executor.py --status` consulta STOP, sesión y turno. No mueve el puntero.
`python desktop/mac/agent_executor.py --start-session` pide un código en la Terminal del dueño y abre
10 minutos nuevos. No elimina STOP, no toma turnos ocupados ni concede o prolonga permisos de órdenes.
Después se usa `--otorgar --file ARCHIVO` y `--automatic --file ARCHIVO` como antes.
Los bloqueos automáticos muestran su motivo y quedan en el registro de auditoría.

### Panel en segundo plano (macOS)

Desde el repositorio actualizado: `python3 scripts/mac_service.py start`.
Si el panel ya está abierto en Terminal, primero ciérralo con Ctrl+C en esa pestaña.
El instalador verifica el entorno y Accesibilidad; instala un LaunchAgent del usuario, sin sudo.
El panel abre el navegador, continúa después de cerrar Terminal y vuelve a arrancar tras un fallo
 o al iniciar sesión en macOS. La Mac tiene que estar encendida y despierta.

Estado: `python3 scripts/mac_service.py status`.
Detener y desactivar el inicio al iniciar sesión: `python3 scripts/mac_service.py stop`.
Registros locales: `~/Library/Logs/Jarvis/panel.log` y `panel-error.log` (acceso solo del dueño).
El registro de salida puede incluir enlaces de acceso locales de corta duración: no se debe publicar.
macOS puede pedir Accesibilidad de nuevo al cambiar de Terminal al servicio; verificar en la Mac.

Este servicio mantiene el panel y sus consultas de estado. No genera tareas, no inicia un agente de IA
continuo y no vuelve a ejecutar `ordenes_confirmadas.jsonl`. El mouse sigue necesitando órdenes concretas,
permisos de un uso y sesión vigente. Los recordatorios y la práctica programada del servidor dependen
de su propia configuración y no necesitan el mouse local.


### Comparar la fluidez de manos

En Avatar, «Aceleración automática» intenta GPU y vuelve a CPU si falla; «CPU · comparar»
permite medir el mismo recorrido sin GPU. No se elige el motor por una estimación de velocidad:
el indicador muestra cuál está funcionando realmente. «Una mano · menor carga» limita el detector
a una mano y desactiva de hecho el zoom con ambas; «Dos manos · zoom» conserva el seguimiento doble.
Cambiar una opción detiene la cámara y el modo de mouse; después pulsa Activar mano.

Muestra la palma durante al menos 10 segundos por configuración y compara «ms/cuadro» y
«detecciones/s» junto a los botones. El detalle debajo del video separa el tiempo interno del
motor («detector») del tiempo de captura, preparación, detección y entrega («análisis»).
Ninguno mide la latencia física completa desde el movimiento hasta la pantalla. La tasa se
calcula con los últimos 30 resultados y se reinicia al apagar. No son números simulados.

La escena decorativa baja a 8 FPS con cámara (4 si está pausada); las manos conservan su
redibujado independiente con cada resultado. Audio activo mantiene su actualización anterior.
No se promete 30 FPS ni latencia cero: hay que medir cada navegador y equipo físico.

## Modo autónomo (`autonomo.py`)

Un agente mueve el mouse, hace clic y decide el próximo clic por su cuenta, **solo** dentro de la lista permitida y **solo** después de que tú abras la sesión en tu Terminal.

### Preparar la Mac (una vez)
1. `python3 -m pip install --user pyautogui pillow`
2. Ajustes del Sistema → Privacidad y seguridad → **Accesibilidad** → activa Terminal (o la app desde la que lo corres).
3. Ajustes del Sistema → Privacidad y seguridad → **Grabación de pantalla** → activa la misma app (para `pantalla.png`).
4. Cierra y vuelve a abrir Terminal.

### Usar
```
cd Jarvis-agents/desktop/mac
python3 autonomo.py --start claude --minutes 15 --run   # te pide un código; escríbelo
```
- El agente lee `~/.jarvis-control/autonomo/pantalla.png` y `estado.json` (tamaño, cursor, app al frente, resultado de la última orden).
- Deja su orden en `~/.jarvis-control/autonomo/siguiente.json`, por ejemplo `{"agent":"claude","action":"click","x":700,"y":400}`.
- Permitido: move, click, double_click, scroll, screenshot, wait, type (≤200 caracteres, sin Enter ni secretos), open_url (hosts permitidos), open_app (Notes, Safari).
- Siempre bloqueado: atajos de teclado, bancos/pagos, mensajes/correo, Terminal, Finder, Ajustes, borrar, comandos y contraseñas. Tampoco hay clic ni texto si la app al frente es una de esas.
- La sesión vive en `~/.jarvis-owner/autonomo.json`, fuera del alcance de los agentes. Tope: 30 min, 20 acciones/min, 300 pasos.
- Parada: mouse a la esquina superior izquierda, Ctrl+C, `python3 autonomo.py --stop` o `touch ~/.jarvis-control/STOP`.
- La bitácora `audit.jsonl` guarda tipo y veredicto, nunca el texto escrito (solo su largo y hash).
