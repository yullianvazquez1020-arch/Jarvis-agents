"""Local, deterministic voice intents (no network, no tokens). Python 3.8+.

Interface orders ("silencio", "repite", "más despacio", "abre práctica") are resolved here. Anything that looks like
an approval, a code or a command is refused here too, so it never reaches Jarvis or any parser."""
import re
import unicodedata

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
    ("health", re.compile(r"^(?:how are you|system status|jarvis status|diagnostics)$")),
)

_LOCAL = (
    ("stop_mouse", re.compile(r"\b(para|deten|detener|apaga|stop|frena)( el)? (mouse|raton|puntero)\b|^stop mouse$")),
    ("stop_audio", re.compile(r"^(silencio|callate|calla|para|deten(te)?|stop|basta|ya)( por favor)?$")),
    ("mic_off", re.compile(r"\b(apaga|desactiva|cierra|silencia) (el )?microfono\b")),
    ("mic_on", re.compile(r"\b(enciende|prende|activa|abre) (el )?microfono\b")),            # 4.0.5 (3.4)
    ("discreet_off", re.compile(r"\b(desactiva|apaga|quita|sal del?) (el )?modo discreto\b")),
    ("discreet_on", re.compile(r"\b(modo discreto)\b")),
    ("health", re.compile(r"^(como estas|como andas|estado del sistema|estado de jarvis|diagnostico)$")),
    ("business", re.compile(r"\b(negocios? externos?|proveedores externos?|enfoque de negocio)\b")),
    ("repeat", re.compile(r"^(repite|repitelo|repitemelo|otra vez|que dijiste|puedes repetir)( eso| por favor)?$")),
    ("slower", re.compile(r"\b(mas despacio|mas lento|habla (mas )?despacio|baja la velocidad)\b")),
    ("faster", re.compile(r"\b(mas rapido|habla (mas )?rapido|sube la velocidad)\b")),
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

# Órdenes de pantalla por voz. Solo las que el ejecutor de la Mac (desktop/mac/agent_executor.py) ya acepta sin
# adivinar nada: abrir una app o una web de SU lista, desplazar, mirar la pantalla y esperar.
# A propósito NO se producen aquí "click", "double_click", "move" ni "type": todas necesitan coordenadas o texto
# que por voz habría que inventar, y una coordenada inventada hace clic en el sitio equivocado. El clic llegará
# cuando Jarvis lea la pantalla y sepa dónde está el elemento; hasta entonces no se promete.
# Quien reciba esto (desktop/mouse_autonomo.py) y el ejecutor vuelven a validar STOP, denylist, app al frente,
# ritmo y turno. Esta tabla no afloja ninguna de esas reglas: solo traduce la frase.
MOUSE_APPS = {"safari": "Safari", "notas": "Notes", "notes": "Notes",
              "outlook": "Microsoft Outlook", "slack": "Slack"}
MOUSE_WEBS = {"github": "https://github.com", "git hub": "https://github.com"}
MOUSE_SCROLL = 320
MOUSE_WAIT_MAX = 10                                   # el ejecutor ya recorta a 10 s; aquí se recorta igual

_ABRIR = r"(?:abre|abreme|abrir|abri|lanza|arranca|ve a|entra a|entra en)"
_ALT = lambda d: "|".join(sorted((re.escape(k) for k in d), key=len, reverse=True))   # noqa: E731
_MOUSE = (
    (re.compile(_ABRIR + r"\s+(?:la\s+)?(?:pagina\s+(?:de\s+)?|web\s+(?:de\s+)?)?(" + _ALT(MOUSE_WEBS) + r")\b"),
     lambda m: {"action": "open_url", "url": MOUSE_WEBS[m.group(1)]}),
    (re.compile(_ABRIR + r"\s+(?:la\s+|el\s+)?(?:app\s+|aplicacion\s+|programa\s+)?(" + _ALT(MOUSE_APPS) + r")\b"),
     lambda m: {"action": "open_app", "app": MOUSE_APPS[m.group(1)]}),
    (re.compile(r"\b(?:baja|bajale|desplaza(?:te)?\s+(?:hacia\s+)?abajo|sigue\s+bajando)\b"),
     lambda m: {"action": "scroll", "dy": -MOUSE_SCROLL}),
    (re.compile(r"\b(?:sube|subele|desplaza(?:te)?\s+(?:hacia\s+)?arriba|sigue\s+subiendo)\b"),
     lambda m: {"action": "scroll", "dy": MOUSE_SCROLL}),
    (re.compile(r"\b(?:toma|tomame|hazme|haz|saca|sacame|dame)\s+(?:una\s+|un\s+)?(?:captura|pantallazo)"
                r"(?:\s+de\s+(?:la\s+)?pantalla)?\b|\b(?:mira|revisa)\s+(?:la\s+)?pantalla\b|"
                r"\bque\s+(?:hay|se\s+ve)\s+en\s+(?:la\s+)?pantalla\b"),
     lambda m: {"action": "screenshot"}),
    (re.compile(r"\bespera\s+(\d{1,3})\s+segundos?\b"),
     lambda m: {"action": "wait", "seconds": min(MOUSE_WAIT_MAX, max(1, int(m.group(1))))}),
)


def parse(text):
    """-> (kind, arg). kind: refuse | stop_mouse | stop_audio | mic_off | repeat | slower | faster | panel |
    mouse (arg = la orden para el ejecutor) | server | empty."""
    n = norm(text)
    if not n:
        return "empty", None
    for rx, reply in _REFUSE:
        if rx.search(n):
            return "refuse", reply
    for kind, rx in _LOCAL_EN + _LOCAL:
        if rx.search(n):
            return kind, None
    if len(n.split()) <= 8 and _NAV.search(n):
        for name, rx in _PANEL:
            if rx.search(n):
                return "panel", name
    command = re.sub(r"^(?:por favor|please)\s+|\s+(?:por favor|please)$", "", n).strip()
    for rx, orden in _MOUSE:                      # solo órdenes completas, no menciones dentro de conversación
        m = rx.fullmatch(command)
        if m:
            return "mouse", orden(m)
    return "server", None
