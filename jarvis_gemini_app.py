"""Optional ASGI entry point: uvicorn jarvis_gemini_app:app (one worker)."""
import main as core
import jarvis_gemini

jarvis_gemini.install(core)
app = core.app
