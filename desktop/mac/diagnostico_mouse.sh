#!/bin/bash
# Diagnóstico del mouse de Jarvis en la Mac. Solo lee estado y hace UN movimiento de prueba en Notes.
#   bash desktop/mac/diagnostico_mouse.sh
LABEL="com.jarvis.mouse-autonomo"; CTL="${JARVIS_CONTROL_DIR:-$HOME/.jarvis-control}"
PY="${JARVIS_PYTHON:-$HOME/.jarvis-control-venv/bin/python}"; LOGS="$HOME/Library/Logs/Jarvis"
echo "== 1. LaunchAgent"; launchctl print "gui/$(id -u)/$LABEL" 2>&1 | grep -E "state|pid|last exit|program|Could not find" || echo "NO CARGADO -> bash desktop/mac/instalar_mouse_autonomo.sh instalar"
echo "== 2. Python del agente (ESTE es el que necesita Accesibilidad, no Terminal)"
[ -x "$PY" ] && echo "$("$PY" -c 'import sys,os;print(os.path.realpath(sys.executable))')" || echo "FALTA $PY -> python3 scripts/mac_setup.py --install"
echo "== 3. Dependencias"; "$PY" -c 'import pyautogui, Quartz; print("pyautogui + Quartz OK")' 2>&1 | tail -1
echo "== 4. STOP / latido"; [ -e "$CTL/STOP" ] && echo "STOP ACTIVO (rm $CTL/STOP)" || echo "sin STOP"; cat "$CTL/autonomo.json" 2>/dev/null; echo
echo "== 5. Logs"; tail -n 15 "$LOGS/mouse-autonomo-error.log" "$LOGS/mouse-autonomo.log" 2>/dev/null
echo "== 6. Prueba verificada en la pantalla de Notes"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
"$PY" - "$ROOT" "$PY" <<'PYTHON'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "scripts"))
from mac_setup import mouse_report
print(mouse_report(Path(sys.argv[2]), probar=True))
PYTHON
