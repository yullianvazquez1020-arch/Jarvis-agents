"""Mount the text-only Gemini reviewer on the already running app.

Imported by jarvis_extensions.install. A failure here must not stop Jarvis.
Production command stays uvicorn main:app.
"""

def mount(core):
    core.GEMINI_STATUS = "no cargado"
    try:
        import jarvis_gemini
        jarvis_gemini.install(core)
        core.GEMINI_STATUS = "rutas listas; apagado hasta GEMINI_ENABLED=true"
    except Exception as exc:
        core.GEMINI_STATUS = f"apagado ({type(exc).__name__})"
        logger = getattr(core, "logger", None)
        if logger is not None:
            logger.warning("gemini off: %s", type(exc).__name__)
