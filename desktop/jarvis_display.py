#!/usr/bin/env python3
"""Display de terminal estilo JARVIS (solo lectura). Python 3.9+, requiere `rich`.

Lee cada 10 s:
  - GET {JARVIS_URL}/health                      -> estado, versión, IA, almacenamiento, topes de dinero, AINCRAD
  - main.py de Jarvis-agents (HELP_TEXT)          -> panel "Poderes" (comandos reales, no inventados)
  - BRAIN.md de jarvis-ai-automation              -> tareas del ciclo
No envía comandos ni escribe nada. Uso:  python3 desktop/jarvis_display.py  [--once] [--url URL]
"""
import argparse
import json
import re
import time
import urllib.request

from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

URL = "https://jarvis-agents.onrender.com"
BRAIN_URL = "https://raw.githubusercontent.com/yullianvazquez1020-arch/jarvis-ai-automation/main/BRAIN.md"
MAIN_URL = "https://raw.githubusercontent.com/yullianvazquez1020-arch/Jarvis-agents/main/main.py"
AVATAR = r"""
      .-=====-.
    .'  .---.  '.
   /   / ◉ ◉ \   \
  |   |   ▽   |   |
   \   \_____/   /
    '.  J.A.R.V.I.S
      '-=====-'
"""


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "jarvis-display/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # solo GET
        return r.read().decode("utf-8", "replace")


def parse_brain(md):
    """Tareas numeradas de BRAIN.md: [(n, texto)]."""
    return [(int(n), t.strip()) for n, t in re.findall(r"^\s*(\d{1,2})\.\s+(.+)$", md, re.M)]


def parse_powers(main_py):
    """Comandos de HELP_TEXT en main.py: [(comando, descripción)]."""
    m = re.search(r"HELP_TEXT\s*=\s*\((.*?)\)\n", main_py, re.S)
    if not m:
        return []
    text = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))).replace("\\n", "\n")
    out = []
    for line in text.split("\n"):
        cmds = re.findall(r"/[a-zñ]+", line)
        if cmds:
            desc = line.split("—", 1)[1].strip() if "—" in line else ""
            out.append((" ".join(dict.fromkeys(cmds)), desc))
    return out


def status_rows(h):
    ai = h.get("ai") or {}
    gate = h.get("money_gate") or {}
    q = h.get("telegram_queue") or {}
    sch = h.get("scheduler") or {}
    return [
        ("Jarvis", str(h.get("jarvis", "?")), h.get("jarvis") == "online"),
        ("Versión", str(h.get("version", "?")), True),
        ("Telegram", "listo" if h.get("telegram_ready") else "NO listo", bool(h.get("telegram_ready"))),
        ("Cola Telegram", "interrumpidos: %s · atascados: %s" % (q.get("interrupted", 0), q.get("stale", 0)),
         not q.get("interrupted") and not q.get("stale")),
        ("IA", "%s%s" % (ai.get("model", "?"), "" if ai.get("configured") else " (sin configurar)"), bool(ai.get("configured"))),
        ("Almacenamiento", str(h.get("storage", "?")), True),
        ("Tope por operación", "$%.0f" % gate.get("max_order_usd", 0), gate.get("max_order_usd") == 100.0),
        ("Tope diario", "$%.0f" % gate.get("max_day_usd", 0), gate.get("max_day_usd") == 300.0),
        ("Programador", "error: %s" % sch["last_error"] if sch.get("last_error") else "ok", not sch.get("last_error")),
    ]


def render(health, powers, brain, err=None):
    lay = Layout()
    lay.split_column(Layout(name="top", size=11), Layout(name="mid"), Layout(name="bot", size=8))
    lay["top"].split_row(Layout(name="avatar", size=30), Layout(name="status"))
    lay["mid"].split_row(Layout(name="powers"), Layout(name="brain"))
    alert = bool(err) or not health or health.get("jarvis") != "online"
    color = "orange1" if alert else "cyan"
    lay["avatar"].update(Panel(Align.center(Text(AVATAR, style="bold " + color)), border_style=color))
    t = Table.grid(padding=(0, 2))
    for k, v, ok in status_rows(health or {}):
        t.add_row(Text(k, style="dim"), Text(v, style="green" if ok else "orange1"))
    title = "ESTADO · /health · %s" % time.strftime("%H:%M:%S")
    lay["status"].update(Panel(Text("Sin conexión: %s" % err, style="orange1") if err else t, title=title, border_style=color))
    pt = Table(show_header=False, box=None, expand=True)
    for c, d in powers:
        pt.add_row(Text(c, style="bold cyan"), Text(d, style="white"))
    for b in (health or {}).get("builtin", []):
        pt.add_row(Text("• " + b, style="cyan"), Text("módulo activo (/health)", style="dim"))
    lay["powers"].update(Panel(pt, title="PODERES · HELP_TEXT de main.py + builtin", border_style="cyan"))
    bt = Table(show_header=False, box=None, expand=True)
    for n, txt in brain:
        bt.add_row(Text("%2d" % n, style="bold cyan"), Text(txt))
    lay["brain"].update(Panel(bt or Text("BRAIN.md no disponible"), title="BRAIN · tareas del ciclo", border_style="cyan"))
    h = health or {}
    keys = ("aincrad", "funnel", "evolve", "ops", "learn", "brief")
    at = Table.grid(padding=(0, 3))
    at.add_row(*[Text("%s: %s" % (k, (h.get(k) or {}).get("status", "—")), style="cyan") for k in keys])
    note = Text("Landing: %s" %
                (h.get("aincrad") or {}).get("landing", "—"), style="dim")
    lay["bot"].update(Panel(Group(at, note), title="NÚCLEO · módulos", border_style="cyan"))
    return lay


def load(url):
    health, err = None, None
    try:
        health = json.loads(fetch(url.rstrip("/") + "/health"))
    except Exception as e:  # el display nunca se cae
        err = type(e).__name__
    try:
        powers = parse_powers(fetch(MAIN_URL))
    except Exception:
        powers = []
    try:
        brain = parse_brain(fetch(BRAIN_URL))
    except Exception:
        brain = []
    return health, powers, brain, err


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=URL)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--every", type=int, default=10)
    a = ap.parse_args(argv)
    con = Console()
    if a.once:
        con.print(render(*load(a.url)))
        return 0
    with Live(render(*load(a.url)), console=con, screen=True, refresh_per_second=1) as live:
        while True:
            time.sleep(a.every)
            live.update(render(*load(a.url)))


if __name__ == "__main__":
    raise SystemExit(main())
