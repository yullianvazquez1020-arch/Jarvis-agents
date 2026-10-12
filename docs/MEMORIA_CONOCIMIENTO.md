# Memoria de conocimiento local (RAG)

Jarvis busca en una biblioteca local antes de contestar y le pasa al modelo hasta 4 fragmentos con su
fuente citada (`[tema] título — archivo`). Todo corre en la Mac: SQLite FTS5 (BM25), solo librería
estándar, sin dependencias nuevas. **Solo añade texto de contexto**: no ejecuta acciones ni cambia dinero,
topes, aprobaciones, `/confirmar`, cifrado ni mensajes.

## Interruptores (solo nombres)
| Variable | Por defecto | Qué hace |
|---|---|---|
| `JARVIS_KNOWLEDGE_ENABLED` | `0` | Con `1` el router añade contexto. Apagado = Jarvis igual que antes. |
| `JARVIS_KNOWLEDGE_EMBED` | `0` | Con `1` reordena con embeddings de Ollama local. Si Ollama falla, sigue con BM25. |
| `JARVIS_KNOWLEDGE_DB` | vacío | Vacío = `data/knowledge.sqlite3` del repo (`data/` está en `.gitignore`). |
| `JARVIS_EMBED_MODEL` | `nomic-embed-text` | Modelo de embeddings en Ollama (`/api/embed`). |

La URL de Ollama sale de `JARVIS_OLLAMA_URL` o, si no está, de `OLLAMA_URL` (la misma del router). Solo se
acepta loopback (`127.0.0.1`, `localhost`, `::1`), sin proxy y sin redirecciones.

## Reglas de privacidad
- La ingesta salta `.env*`, `data/`, `venv/`, `.venv/`, `.git/`, `node_modules/`, enlaces simbólicos y
  archivos de más de 5 MB. Tapa valores de `KEY/TOKEN/SECRET/PASSWORD`, cabeceras `Bearer`, claves PEM,
  formas típicas de tokens y cualquier valor de secreto presente en el entorno.
- Temas públicos: `python`, `redes`, `seguridad`. **Cualquier otro tema** (incluido `jarvis`, el código
  propio) vuelve el mensaje sensible: va **solo** al modelo local y, si Ollama no responde, error. Nunca a la nube.
- `/venice` no recibe contexto de la memoria.
- Las rutas guardadas son relativas a la carpeta indexada (no llevan tu carpeta de usuario).

## Uso en la Mac (Python 3.9+, Ollama v0.12.3)
```bash
cd "$HOME/Jarvis-agents"
bash scripts/descargar_conocimiento.sh          # baja fuentes libres e indexa (incluye el repo como "jarvis")
python3 jarvis_knowledge.py search "como validar entradas" -k 3
python3 jarvis_knowledge.py stats
# Opcional, embeddings:
ollama pull nomic-embed-text
# Activar solo cuando el dueño lo autorice (entorno local):
export JARVIS_KNOWLEDGE_ENABLED=1
```
Volver a correr `ingest` es incremental: salta archivos sin cambios y borra los que ya no existen.

## Fuentes
Python docs (PSF), RFCs de rfc-editor.org (IETF Trust), OWASP Cheat Sheet Series y Top 10 (CC BY-SA 4.0).
Todo es material defensivo.
