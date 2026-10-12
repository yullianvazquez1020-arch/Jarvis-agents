#!/usr/bin/env bash
# Descarga fuentes libres (solo lectura pública, HTTPS) y las indexa en la memoria local de Jarvis.
# Compatible con bash 3.2 (macOS Monterey). No toca .env, no envía datos, no ejecuta nada descargado.
# Variables (solo nombres): JARVIS_KNOWLEDGE_SRC, JARVIS_REPO, JARVIS_KNOWLEDGE_DB.
set -euo pipefail

DEST="${JARVIS_KNOWLEDGE_SRC:-$HOME/Jarvis-conocimiento}"
REPO="${JARVIS_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
PY="${PYTHON:-python3}"
dl() { curl --proto '=https' --proto-redir '=https' -fsSL --retry 2 "$@"; }
kb() { "$PY" "$REPO/jarvis_knowledge.py" "$@"; }

"$PY" -c 'import sys; assert sys.version_info >= (3, 9), "Hace falta Python 3.9+"'
"$PY" -c 'import sqlite3; sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(x)")' \
  || { echo "Este Python no trae SQLite con FTS5. Usa Python de python.org o Homebrew." >&2; exit 1; }

mkdir -p "$DEST/python" "$DEST/redes" "$DEST/seguridad"
cd "$DEST"

# 1) Python: documentación oficial en texto (licencia PSF). Toma el nombre actual de la página de descargas.
ZIP=$(dl https://docs.python.org/3/download.html | grep -oE 'archives/python-[0-9.]+-docs-text\.zip' | head -1 || true)
if [ -n "$ZIP" ]; then
  dl -o python/docs.zip "https://docs.python.org/3/$ZIP"
  (cd python && unzip -qo docs.zip)
else
  echo "Aviso: no encontré el ZIP de texto de docs.python.org; sigo sin él." >&2
fi

# 2) Redes y seguridad: RFCs (IETF Trust permite copiar y distribuir el texto completo).
for n in 791 792 768 9293 1918 1035 4033 8484 2979 4301 8446 9110 6749 7519 8017 5280; do
  dl -o "redes/rfc$n.txt" "https://www.rfc-editor.org/rfc/rfc$n.txt" || echo "Aviso: rfc$n no se descargó" >&2
  sleep 1
done

# 3) Seguridad defensiva: OWASP Cheat Sheet Series (CC BY-SA 4.0) y OWASP Top 10.
if dl -o seguridad/cheatsheets.zip https://github.com/OWASP/CheatSheetSeries/archive/refs/heads/master.zip; then
  (cd seguridad && unzip -qo cheatsheets.zip 'CheatSheetSeries-master/cheatsheets/*')
fi
if dl -o seguridad/top10.zip https://github.com/OWASP/Top10/archive/refs/heads/master.zip; then
  (cd seguridad && unzip -qo top10.zip 'Top10-master/2021/docs/en/*' || echo "Aviso: Top 10 sin carpeta 2021/docs/en" >&2)
fi

# 4) Indexar. La base va a JARVIS_KNOWLEDGE_DB o a data/knowledge.sqlite3 del repo (data/ está en .gitignore).
kb ingest "$DEST/python"    --topic python
kb ingest "$DEST/redes"     --topic redes
kb ingest "$DEST/seguridad" --topic seguridad
# Código propio: se saltan .env*, data/, venv/, .git y enlaces; los valores de secretos se tapan.
# El tema "jarvis" es privado: lo que lo use va solo al modelo local.
kb ingest "$REPO" --topic jarvis
kb stats
