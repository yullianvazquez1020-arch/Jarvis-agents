"""Local, deterministic voice intents (no network, no tokens). Python 3.8+.

Interface orders ("silencio", "repite", "más despacio", "abre práctica") are resolved here. Anything that looks like
an approval, a code or a command is refused here too, so it never reaches Jarvis or any parser."""
import re
import unicodedata
try:
    from .account_navigation import parse_account, parse_application
except ImportError:
    from account_navigation import parse_account, parse_application

PANELS = ("estado", "agenda", "cobros", "practica", "brief", "caja")


def norm(text):
    t = unicodedata.normalize("NFKD", str(text or "").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[¿?¡!.,;:\"']", " ", t)
    t = re.sub(r"^\s*(oye\s+)?jarvis\b", " ", t)          # "Jarvis, ..." is just how he talks to it
    return re.sub(r"\s+", " ", t).strip()


# 4.0.5 (1.3): these never leave the Mac. Same list on the server (jarvis_desktop_api._REFUSE).
ACTION_MSG = ("Eso no se hace por voz ni desde el panel. Confirmar, aprobar, rechazar, enviar, anotar, ejecutar, "
              "restaurar, borrar o mover dinero se hace solo en tu chat privado de Telegram.")
_REFUSE = (
    (re.compile(r"\b(?:approve|authorize|transfer money|delete|restore|execute|send payment)\b|^(?:buy|sell|pay|send)\b"), ACTION_MSG),
    (re.compile(r"^\s*/"), "Por voz no ejecuto comandos. Escríbelo en tu chat privado de Telegram."),
    (re.compile(r"\d{6}|\d{3}\s\d{3}"),
     "Una transcripción no te identifica ni confirma nada. Los códigos solo valen en tu chat privado de Telegram."),
    (re.compile(r"\b(confirm\w*|aprob\w*|aprueb\w*|rechaz\w*|modo real|activa real|envi\w*|anot\w*|apunt\w*|"
                r"ejecut\w*|restaur\w*|borr\w*|elimin\w*|autoriz\w*|transfier\w*|transferenc\w*|retir\w*)\b"),
     ACTION_MSG),
    (re.compile(r"^(compra|comprame|compre|vende|vendeme|venda|paga|pagale|manda|mandale)\b"), ACTION_MSG),
)

_LOCAL_EN = (
    ("stop_mouse", re.compile(r"^(?:please )?(?:stop|pause) (?:the )?(?:mouse|pointer)(?: please)?$")),
    ("stop_audio", re.compile(r"^(?:please )?(?:stop talking|stop speaking|be quiet|silence)(?: please)?$")),
    ("mic_off", re.compile(r"^(?:please )?(?:turn off|disable|mute) (?:the )?(?:microphone|mic)$")),
    ("mic_on", re.compile(r"^(?:please )?(?:turn on|enable|unmute) (?:the )?(?:microphone|mic)$")),
    ("slower", re.compile(r"\b(?:speak slower|talk slower|slow down|speak more slowly)\b")),
    ("faster", re.compile(r"\b(?:speak faster|talk faster|speed up)\b")),
    ("repeat", re.compile(r"^(?:please )?(?:repeat|repeat that|say that again|what did you say)(?: please)?$")),
    ("health", re.compile(r"^(?:system status|jarvis status|diagnostics)$")),
)

_LOCAL = (
    ("stop_mouse", re.compile(r"\b(para|deten|detener|apaga|stop|frena)( el)? (mouse|raton|puntero)\b|^stop mouse$")),
    ("stop_audio", re.compile(r"^(silencio|callate|calla|para|deten(te)?|stop|basta|ya)( por favor)?$")),
    ("mic_off", re.compile(r"\b(apaga|desactiva|cierra|silencia) (el )?microfono\b")),
    ("mic_on", re.compile(r"\b(enciende|prende|activa|abre) (el )?microfono\b")),            # 4.0.5 (3.4)
    ("discreet_off", re.compile(r"\b(desactiva|apaga|quita|sal del?) (el )?modo discreto\b")),
    ("discreet_on", re.compile(r"\b(modo discreto)\b")),
    ("health", re.compile(r"^(estado del sistema|estado de jarvis|diagnostico)$")),
    ("business", re.compile(r"\b(negocios? externos?|proveedores externos?|enfoque de negocio)\b")),
    ("repeat", re.compile(r"^(repite|repitelo|repitemelo|otra vez|que dijiste|puedes repetir)( eso| por favor)?$")),
    ("slower", re.compile(r"\b(mas despacio|mas lento|habla (mas )?despacio|baja la velocidad)\b")),
    ("faster", re.compile(r"\b(mas rapido|habla (mas )?rapido|sube la velocidad)\b")),
)

_MOUSE = (
    ("mouse", re.compile(r"\b(open|abre|abrir) (safari)\b"), {"action": "open_app", "app": "Safari"}),
    ("mouse", re.compile(r"\b(open|abre|abrir) (notes|notas)\b"), {"action": "open_app", "app": "Notes"}),
    ("mouse", re.compile(r"\b(scroll|baja|desliza) (down|abajo)\b|^scroll down$"), {"action": "scroll", "dy": -5}),
    ("mouse", re.compile(r"\b(scroll|sube|desliza) (up|arriba)\b|^scroll up$"), {"action": "scroll", "dy": 5}),
    ("mouse", re.compile(r"\b(take a screenshot|captura (de )?pantalla)\b"), {"action": "screenshot"}),
)

_PANEL = (
    ("brief", re.compile(r"\b(brief|resumen comercial|informe comercial)\b")),
    ("caja", re.compile(r"\b(caja|flujo de efectivo)\b")),
    ("cobros", re.compile(r"\b(cobros?|por cobrar|me deben)\b")),
    ("agenda", re.compile(r"\b(agenda|calendario|que tengo hoy|mis citas)\b")),
    ("practica", re.compile(r"\b(practica|simulador|simulado)\b")),
    ("estado", re.compile(r"\b(panel de estado|estado del servidor)\b")),
)
_NAV = re.compile(r"\b(dame|abre|abrir|muestrame|muestra|ensename|ensena|ver|pon|lee|leeme|panel|como estas|que tengo)\b")


def parse(text):
    """-> (kind, arg). kind: refuse | stop_mouse | stop_audio | mic_off | repeat | slower | faster | panel | server | empty."""
    n = norm(text)
    if not n:
        return "empty", None
    for rx, reply in _REFUSE:
        if rx.search(n):
            return "refuse", reply
    account = parse_account(n)
    if account:
        return "account", account
    application = parse_application(n)
    if application:
        return "application", application
    for kind, rx in _LOCAL_EN + _LOCAL:
        if rx.search(n):
            # A request for faster replies is not a request to speed up speech.
            # Keep the existing short commands, but let conversation reach the model.
            if kind in ("slower", "faster") and not re.fullmatch(
                    r"(?:please )?(?:mas despacio|mas lento|mas rapido|habla (?:mas )?(?:despacio|rapido)|"
                    r"baja la velocidad|sube la velocidad|speak slower|talk slower|slow down|"
                    r"speak more slowly|speak faster|talk faster|speed up)(?: por favor| please)?", n):
                continue
            if kind == "business" and n not in ("negocios externos", "negocio externo", "proveedores externos", "enfoque de negocio"):
                continue
            return kind, None
    for kind, rx, arg in _MOUSE:                     # voz -> orden al mouse (el ejecutor revalida y pide /confirmar)
        if rx.search(n):
            return kind, arg
    if len(n.split()) <= 8 and _NAV.search(n):
        for name, rx in _PANEL:
            if rx.search(n):
                return "panel", name
    return "server", None
