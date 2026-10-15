"""Open fixed account landing pages locally; never inspect credentials or transact."""
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys

SITES = {
    "coinbase": "https://www.coinbase.com/",
    "chatgpt": "https://chatgpt.com/",
    "claude": "https://claude.ai/",
    "gemini": "https://gemini.google.com/",
    "grok": "https://grok.com/",
    "venice": "https://venice.ai/",
    "perplexity": "https://www.perplexity.ai/",
    "gmail": "https://mail.google.com/",
    "outlook": "https://outlook.live.com/mail/",
    "youtube": "https://www.youtube.com/",
    "youtube studio": "https://studio.youtube.com/",
    "facebook": "https://www.facebook.com/",
    "instagram": "https://www.instagram.com/",
    "meta business": "https://business.facebook.com/",
    "tiktok": "https://www.tiktok.com/",
    "linkedin": "https://www.linkedin.com/",
    "x": "https://x.com/",
    "whatsapp": "https://web.whatsapp.com/",
    "telegram": "https://web.telegram.org/",
    "gumroad": "https://gumroad.com/",
    "fiverr": "https://www.fiverr.com/",
    "amazon seller": "https://sellercentral.amazon.com/",
    "canva": "https://www.canva.com/",
    "github": "https://github.com/",
    "capcut web": "https://www.capcut.com/",
    "render": "https://dashboard.render.com/",
}
ALIASES = {"chat gpt": "chatgpt", "you tube": "youtube", "studio de youtube": "youtube studio",
           "correo": "gmail", "email": "gmail", "mi correo": "gmail", "mi email": "gmail",
           "twitter": "x", "facebook business": "meta business", "amazon seller central": "amazon seller"}


def parse_account(normalized):
    # Full match: a compound financial/send/delete instruction must never become a navigation command.
    match = re.fullmatch(r"(?:por favor |please )?(?:abre|abrir|abreme|entra a|entra en|ve a|navega a|open|go to)(?: la cuenta de| mi cuenta de| mi| my)? (.+?)(?: por favor| please)?", normalized)
    if not match:
        return None
    site = ALIASES.get(match[1], match[1])
    return site if site in SITES else None


def open_account(site):
    if site not in SITES:
        return {"ok": False, "message": "Ese sitio no está configurado."}
    root = Path(os.environ.get("JARVIS_CONTROL_DIR") or Path.home() / ".jarvis-control")
    if (root / "STOP").exists():
        return {"ok": False, "message": "STOP está activo; no abrí la página."}
    if sys.platform != "darwin":
        return {"ok": False, "message": "La apertura de cuentas requiere la Mac."}
    try:
        # Only fixed HTTPS landing pages. No model-supplied URL, script, field, click or key.
        result = subprocess.run(["/usr/bin/open", "-a", "Safari", SITES[site]],
                                capture_output=True, timeout=10)
        ok = result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    try:
        root.mkdir(parents=True, exist_ok=True)
        with (root / "account-navigation.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                 "site": site, "result": "open_requested" if ok else "failed"}) + "\n")
    except OSError:
        pass
    message = ("Solicité abrir " + site + " en Safari. No he comprobado la sesión ni realizado acciones dentro de la cuenta."
               if ok else "No pude abrir " + site + " en Safari.")
    if ok and site == "coinbase":
        message += " Esta orden solo abre Coinbase; no compra, vende ni transfiere dinero."
    return {"ok": ok, "message": message}


APPS = {"mail": "Mail", "calendario": "Calendar", "recordatorios": "Reminders",
        "fotos": "Photos", "finder": "Finder", "vista previa": "Preview",
        "calculadora": "Calculator", "contactos": "Contacts", "musica": "Music",
        "pages": "Pages", "numbers": "Numbers", "keynote": "Keynote",
        "imovie": "iMovie", "capcut": "CapCut"}
APP_ALIASES = {"calendar": "calendario", "reminders": "recordatorios", "photos": "fotos",
               "preview": "vista previa", "calculator": "calculadora", "contacts": "contactos",
               "music": "musica", "cap cut": "capcut", "apple mail": "mail"}


def parse_application(normalized):
    match = re.fullmatch(r"(?:por favor |please )?(?:abre|abrir|abreme|open) (?:la app |la aplicacion )?(.+?)(?: por favor| please)?", normalized)
    if not match:
        return None
    app = APP_ALIASES.get(match[1], match[1])
    return app if app in APPS else None


def open_application(app):
    if app not in APPS:
        return {"ok": False, "message": "Esa aplicación no está configurada."}
    root = Path(os.environ.get("JARVIS_CONTROL_DIR") or Path.home() / ".jarvis-control")
    if (root / "STOP").exists():
        return {"ok": False, "message": "STOP está activo; no abrí la aplicación."}
    if sys.platform != "darwin":
        return {"ok": False, "message": "Esta apertura requiere la Mac."}
    try:
        result = subprocess.run(["/usr/bin/open", "-a", APPS[app]], capture_output=True, timeout=10)
        ok = result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    return {"ok": ok, "message": ("Solicité abrir " + APPS[app] + ". No he realizado acciones dentro de la aplicación."
            if ok else "No pude abrir " + APPS[app] + ". Comprueba que esté instalada en esta Mac.")}
