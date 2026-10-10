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
