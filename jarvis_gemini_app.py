"""Optional alias. Production command stays uvicorn main:app --workers 1."""
import main as core
import jarvis_gemini

jarvis_gemini.install(core)
app = core.app
