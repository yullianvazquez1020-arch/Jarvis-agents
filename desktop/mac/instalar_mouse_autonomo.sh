#!/bin/bash
# Instala o quita el modo mouse autónomo (LaunchAgent del usuario, sin sudo).
#   bash desktop/mac/instalar_mouse_autonomo.sh instalar
#   bash desktop/mac/instalar_mouse_autonomo.sh quitar
set -euo pipefail
LABEL="com.jarvis.mouse-autonomo"
AQUI="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="${JARVIS_PYTHON:-$HOME/.jarvis-control-venv/bin/python}"
case "${1:-}" in
  instalar)
    [ "$(uname)" = "Darwin" ] || { echo "Solo en macOS."; exit 2; }
    [ -x "$PY" ] || { echo "No encuentro $PY (usa JARVIS_PYTHON=...)."; exit 2; }
    mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/Jarvis"
    sed -e "s#__PYTHON__#$PY#" -e "s#__EXECUTOR__#$AQUI/agent_executor.py#" -e "s#__HOME__#$HOME#g" \
      "$AQUI/$LABEL.plist" > "$DEST"
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$DEST"
    echo "Instalado. Para pararlo: touch ~/.jarvis-control/STOP  (o di «para el mouse»)."
    ;;
  quitar)
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$DEST"
    echo "Quitado. El mouse autónomo ya no arranca solo."
    ;;
  *) echo "Uso: $0 instalar|quitar"; exit 2;;
esac
