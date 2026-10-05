"""Jarvis v3.2: orchestrator + built-in specialists + permanent memory.

Built-in: personal (reminders, shopping list, bills) and accountant
(income, expenses, net profit, tax estimates). Data is saved in Upstash
Redis (free) so it survives every deploy. If the Upstash variables are
not set yet, it falls back to local files (those get wiped on deploy).
One Render service, one bill.

v3.1 fixes: Telegram secret + owner required, no duplicate entries on
Telegram retries, Puerto Rico time zone, history safe on errors, async
Claude calls, long/empty replies handled, input validation.

v3.2 (Phase 1, additive): proactive engine. A background loop inside the
same service sends Telegram alerts on its own: reminders with a real
date/time (optionally repeating daily/weekly/monthly), bills coming due,
and a short morning brief. Alerts use ZERO Claude tokens. Daily backup of
the data inside Redis + /backup endpoint. /hoy command in Telegram (no
tokens). Every v3.1 function is kept as it was.

v3.3 (Phase 3, step 1, additive): built-in CALENDAR agent for deliveries,
appointments, dates to pay and dates to collect. Events can repeat and get
ONE Telegram alert before they start (zero tokens, never re-sent). Today's
and tomorrow's events appear in the morning brief and /hoy; /calendario
lists the next days without tokens. Exact upcoming dates go in the system
prompt so "el jueves" lands on the right day. Every v3.2 function is kept.
"""
import os, json, datetime, asyncio, calendar, threading, contextlib, httpx
import re   # v3.3
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Header, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()

@contextlib.asynccontextmanager
async def _lifespan(app):
    # start the proactive engine when the server boots, stop it on shutdown
    task = asyncio.create_task(_scheduler_loop())
    yield
    task.cancel()

app = FastAPI(title="Jarvis Orchestrator", lifespan=_lifespan)
client = AsyncAnthropic()
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
API_KEY = os.getenv("AGENT_API_KEY", "").strip()
OWNER = os.getenv("OWNER_NAME", "the boss")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
TG_OWNER = os.getenv("TELEGRAM_OWNER_ID", "").strip()
TZ = ZoneInfo(os.getenv("TZ_NAME", "America/Puerto_Rico"))
# Proactive engine settings (all optional; defaults work as-is)
SCHED_ON = os.getenv("SCHEDULER_ENABLED", "true").strip().lower() not in ("false", "0", "no")
SCHED_EVERY = max(30, int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "60") or 60))
BILL_NOTICE_DAYS = int(os.getenv("BILL_NOTICE_DAYS", "2") or 2)
BRIEF_HOUR = os.getenv("DAILY_BRIEF_HOUR", "7").strip()   # 0-23 PR time; blank = off

if not API_KEY or API_KEY == "change-me":
    raise RuntimeError("Set AGENT_API_KEY in Render before starting Jarvis.")

def _now():   return datetime.datetime.now(TZ)
def _today(): return _now().date()

# ---------------------------------------------------------------------------
# Permanent storage: Upstash Redis over HTTPS, fallback to local JSON files.
# ---------------------------------------------------------------------------
UP_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
UP_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
USE_REDIS = bool(UP_URL and UP_TOKEN)

def _redis(cmd):
    r = httpx.post(UP_URL, headers={"Authorization": f"Bearer {UP_TOKEN}"},
                   json=cmd, timeout=15)
    r.raise_for_status()
    return r.json().get("result")

def kv_get(key, default):
    if USE_REDIS:
        v = _redis(["GET", key])
        return json.loads(v) if v else default
    path = key.replace(":", "_") + ".json"
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)

def kv_set(key, value):
    data = json.dumps(value, ensure_ascii=False)
    if USE_REDIS:
        _redis(["SET", key, data])
        return
    with open(key.replace(":", "_") + ".json", "w") as f:
        f.write(data)

def storage_mode():
    return "upstash (permanent)" if USE_REDIS else "local files (erased on deploy)"

def _with_ids(items):
    """Give every entry a numeric id so it can be edited or deleted."""
    nxt = max([x.get("id", 0) for x in items if isinstance(x, dict)] + [0]) + 1
    for x in items:
        if isinstance(x, dict) and "id" not in x:
            x["id"] = nxt; nxt += 1
    return items

def _next_id(items):
    return max([x.get("id", 0) for x in items] + [0]) + 1

def _to_bool(v):
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "si", "sí")
    return bool(v)

def _valid_day(day):
    day = int(day)
    if not 1 <= day <= 31:
        raise ValueError("day must be between 1 and 31")
    return day

# One lock for every read-modify-save, so the chat and the proactive engine
# never overwrite each other's changes.
_data_lock = threading.RLock()

REPEATS = ["", "daily", "weekly", "monthly"]

def _parse_due(due):
    """'YYYY-MM-DD HH:MM' (PR time) -> normalized string. Blank stays blank."""
    due = (due or "").strip().replace("T", " ")
    if not due:
        return ""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.datetime.strptime(due, fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=9)   # date only -> 9:00 AM
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
    raise ValueError("due must be 'YYYY-MM-DD HH:MM' (Puerto Rico time)")

def _due_dt(due):
    return datetime.datetime.strptime(due, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)

def _valid_repeat(repeat):
    repeat = (repeat or "").strip().lower()
    if repeat in ("none", "no", "nunca"):
        repeat = ""
    if repeat not in REPEATS:
        raise ValueError("repeat must be daily, weekly, monthly or blank")
    return repeat

def _roll(due, repeat):
    """Next occurrence of a repeating reminder, always in the future."""
    dt = _due_dt(due); now = _now()
    while dt <= now:
        if repeat == "daily":
            dt += datetime.timedelta(days=1)
        elif repeat == "weekly":
            dt += datetime.timedelta(weeks=1)
        else:  # monthly, same day (clamped to month length)
            y, m = (dt.year + 1, 1) if dt.month == 12 else (dt.year, dt.month + 1)
            dt = dt.replace(year=y, month=m, day=min(dt.day, calendar.monthrange(y, m)[1]))
    return dt.strftime("%Y-%m-%d %H:%M")

# ---------------------------------------------------------------------------
# External specialist agents (optional). Leave URLs blank until deployed.
# ---------------------------------------------------------------------------
AGENTS = {
    "call":     os.getenv("CALL_AGENT_URL", ""),
    "message":  os.getenv("SMS_AGENT_URL", ""),
    "email":    os.getenv("EMAIL_AGENT_URL", ""),
    "calendar": os.getenv("CALENDAR_AGENT_URL", ""),
    "amazon":   os.getenv("AMAZON_AGENT_URL", ""),
    "coinbase": os.getenv("COINBASE_AGENT_URL", ""),
}
AGENT_ENDPOINT = {
    "calendar": ("/ask", "message"),
    "amazon":   ("/ask", "message"),
    "coinbase": ("/ask", "message"),
    "email":    ("/process-inbox", None),   # email agent only processes the inbox
}

async def delegate(agent: str, instruction: str):
    url = AGENTS.get(agent)
    if not url:
        return {"error": f"Agent '{agent}' not deployed yet."}
    path, key = AGENT_ENDPOINT.get(agent, ("/ask", "message"))
    async with httpx.AsyncClient(timeout=90) as hc:
        try:
            if key:
                r = await hc.post(url + path, headers={"x-api-key": API_KEY}, json={key: instruction})
            else:
                r = await hc.post(url + path, headers={"x-api-key": API_KEY})
            return r.json()
        except Exception as e:
            return {"error": str(e)}

# ---------------------------------------------------------------------------
# PERSONAL: reminders, shopping list, bills.
# ---------------------------------------------------------------------------
P_KEY = "jarvis:personal"
def _pload():
    d = kv_get(P_KEY, {"reminders": [], "shopping": [], "bills": []})
    for k in ("reminders", "shopping", "bills"):
        d.setdefault(k, [])
    _with_ids(d["reminders"]); _with_ids(d["bills"])
    return d
def _psave(d): kv_set(P_KEY, d)

def add_reminder(text, when="", due="", repeat=""):
    due=_parse_due(due); repeat=_valid_repeat(repeat)
    if repeat and not due:
        raise ValueError("a repeating reminder needs a due date/time")
    d=_pload(); e={"id":_next_id(d["reminders"]),"text":text,"when":when,"done":False}
    if due: e["due"]=due; e["notified"]=False
    if repeat: e["repeat"]=repeat
    d["reminders"].append(e); _psave(d); return e
def complete_reminder(id):
    d=_pload()
    for x in d["reminders"]:
        if x["id"]==int(id):
            if x.get("repeat") and x.get("due"):
                # repeating: keep it alive; the engine already moved it to the next date
                return {**x, "note": f"Recurrente ({x['repeat']}); sigue activo, próximo aviso {x['due']}. "
                                     "Para detenerlo: quitar la repetición o borrarlo."}
            x["done"]=True; _psave(d); return x
    return {"error":f"reminder {id} not found"}
def add_shopping(item):
    d=_pload(); d["shopping"].append(item); _psave(d); return {"shopping":d["shopping"]}
def remove_shopping(item):
    d=_pload(); before=len(d["shopping"])
    d["shopping"]=[x for x in d["shopping"] if x.lower()!=item.lower()]
    _psave(d); return {"removed":before-len(d["shopping"]),"shopping":d["shopping"]}
def clear_shopping():
    d=_pload(); d["shopping"]=[]; _psave(d); return {"shopping":[]}
def add_bill(name, day, amount=""):
    d=_pload(); e={"id":_next_id(d["bills"]),"name":name,"day":_valid_day(day),"amount":amount,"paid":[]}
    d["bills"].append(e); _psave(d); return e
def mark_bill_paid(id, month=""):
    month = month or _today().strftime("%Y-%m")
    d=_pload()
    for x in d["bills"]:
        if x["id"]==int(id):
            x.setdefault("paid",[])
            if month not in x["paid"]: x["paid"].append(month)
            _psave(d); return x
    return {"error":f"bill {id} not found"}
def overview(): return _pload()

# ---------------------------------------------------------------------------
# ACCOUNTANT: income, expenses, tax estimate. Orientation only.
# ---------------------------------------------------------------------------
B_KEY = "jarvis:books"
EXPENSE_CATEGORIES = ["operational","materials","equipment","labor",
                      "vehicle","rent","utilities","professional","other"]
def _bload():
    d = kv_get(B_KEY, {"income": [], "expenses": []})
    d.setdefault("income", []); d.setdefault("expenses", [])
    _with_ids(d["income"]); _with_ids(d["expenses"])
    return d
def _bsave(d): kv_set(B_KEY, d)

def add_income(amount, source="", date=""):
    d=_bload(); e={"id":_next_id(d["income"]),"amount":float(amount),"source":source,
                   "date":date or _today().isoformat()}
    d["income"].append(e); _bsave(d); return e
def add_expense(amount, category="other", note="", date=""):
    d=_bload(); category = category if category in EXPENSE_CATEGORIES else "other"
    e={"id":_next_id(d["expenses"]),"amount":float(amount),"category":category,"note":note,
       "date":date or _today().isoformat()}
    d["expenses"].append(e); _bsave(d); return e
def list_books(): return _bload()
def finances_summary():
    d=_bload()
    inc=sum(x["amount"] for x in d["income"]); exp=sum(x["amount"] for x in d["expenses"])
    by_cat={}
    for x in d["expenses"]:
        by_cat[x["category"]]=by_cat.get(x["category"],0)+x["amount"]
    return {"total_income":round(inc,2),"total_expenses":round(exp,2),"net_profit":round(inc-exp,2),
            "expenses_by_category":{k:round(v,2) for k,v in by_cat.items()},
            "entries":{"income":len(d["income"]),"expenses":len(d["expenses"])}}
def tax_estimate(rate_percent=0):
    s=finances_summary(); net=s["net_profit"]
    return {"net_profit":net,"rate_percent":float(rate_percent),
            "suggested_tax_reserve":round(max(0.0,net)*float(rate_percent)/100.0,2),
            "note":"Estimate only. Confirm the rate and final filing with your CPA."}

# ---------------------------------------------------------------------------
# CALENDAR (v3.3, Phase 3): deliveries, appointments, payment and collection
# dates. Each event can repeat (daily/weekly/monthly) and gets ONE Telegram
# alert before it starts (zero tokens). No nagging: nothing is re-sent.
# ---------------------------------------------------------------------------
E_KEY = "jarvis:calendar"
EVENT_TYPES = ["delivery", "appointment", "payment", "collection", "other"]
EVENT_ES = {"delivery": "📦 Entrega", "appointment": "📅 Cita", "payment": "💸 Pago",
            "collection": "💰 Cobro", "other": "🗓️ Evento"}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
CAL_ALLDAY_HOUR = int(os.getenv("CAL_ALLDAY_HOUR", "9") or 9)   # all-day events count as starting at this hour

def _eload():
    d = kv_get(E_KEY, {"events": []})
    d.setdefault("events", [])
    _with_ids(d["events"])
    return d
def _esave(d): kv_set(E_KEY, d)

def _valid_type(t):
    t = (t or "other").strip().lower()
    alias = {"entrega": "delivery", "cita": "appointment", "pago": "payment", "cobro": "collection",
             "otro": "other", "meeting": "appointment", "reunion": "appointment", "reunión": "appointment"}
    t = alias.get(t, t)
    if t not in EVENT_TYPES:
        raise ValueError("type must be one of " + ", ".join(EVENT_TYPES))
    return t

def _valid_date(v):
    v = (v or "").strip()[:10]
    if not v:
        raise ValueError("date is required as YYYY-MM-DD")
    return datetime.date.fromisoformat(v).isoformat()

def _valid_time(v):
    """'HH:MM' 24h or blank (= all day)."""
    v = (v or "").strip().lower().replace(".", "")
    if v in ("", "all day", "todo el dia", "todo el día"):
        return ""
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%I %p", "%I%p"):
        try:
            return datetime.datetime.strptime(v, fmt).strftime("%H:%M")
        except ValueError:
            pass
    raise ValueError("time must be 'HH:MM' (24h, Puerto Rico time) or blank for all day")

def _int_or_none(v):
    if v in (None, ""):
        return None
    return int(float(v))

def _default_remind(e):
    # timed event: 1 hour before; all-day event: the day before
    return 60 if e.get("time") else 1440

def _remind_of(e):
    r = e.get("remind_min")
    return _default_remind(e) if r is None else int(r)

def _add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year; m += 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))

def _occurrences(e, start, end):
    """Dates (datetime.date) of an event between start and end, inclusive."""
    d0 = datetime.date.fromisoformat(e["date"]); rep = e.get("repeat", "")
    skip = set(e.get("skip_dates", []))
    if not rep:
        return [d0] if start <= d0 <= end and d0.isoformat() not in skip else []
    out = []
    if rep in ("daily", "weekly"):
        step = 1 if rep == "daily" else 7
        n = max(0, (start - d0).days // step)
        for _ in range(400):
            occ = d0 + datetime.timedelta(days=step * n); n += 1
            if occ > end: break
            if occ >= start and occ.isoformat() not in skip: out.append(occ)
    else:  # monthly
        n = max(0, (start.year - d0.year) * 12 + start.month - d0.month - 1)
        for _ in range(400):
            occ = _add_months(d0, n); n += 1
            if occ > end: break
            if occ >= start and occ.isoformat() not in skip: out.append(occ)
    return out

def _occ_start(e, occ):
    """Start datetime of one occurrence (all-day -> CAL_ALLDAY_HOUR)."""
    if e.get("time"):
        h, m = map(int, e["time"].split(":"))
    else:
        h, m = CAL_ALLDAY_HOUR, 0
    return datetime.datetime(occ.year, occ.month, occ.day, h, m, tzinfo=TZ)

def _occ_done(e, occ):
    return e.get("status") == "done" or occ.isoformat() in e.get("done_dates", [])

def _day_label(occ, today=None):
    today = today or _today(); diff = (occ - today).days
    rel = {0: "hoy", 1: "mañana", -1: "ayer"}.get(diff, "")
    base = f"{DIAS[occ.weekday()]} {occ.isoformat()}"
    return f"{rel} ({base})" if rel else base

def _ev_view(e, occ):
    return {"id": e["id"], "title": e["title"], "type": e["type"], "date": occ.isoformat(),
            "weekday": DIAS[occ.weekday()], "time": e.get("time", ""),
            "duration_min": e.get("duration_min"), "location": e.get("location", ""),
            "who": e.get("who", ""), "amount": e.get("amount", ""), "notes": e.get("notes", ""),
            "repeat": e.get("repeat", ""), "done": _occ_done(e, occ),
            "status": "done" if _occ_done(e, occ) else e.get("status", "scheduled"),
            "remind_min": _remind_of(e)}

def _ev_line(v, today=None, with_date=True):
    when = (_day_label(datetime.date.fromisoformat(v["date"]), today) + " ") if with_date else ""
    when += v["time"] if v["time"] else "todo el día"
    extra = "".join(x for x in (
        f" · 📍{v['location']}" if v.get("location") else "",
        f" · 👤{v['who']}" if v.get("who") else "",
        f" · ${v['amount']}" if str(v.get("amount") or "").strip() else "",
        " · 🔁" if v.get("repeat") else "",
        " · ✅" if v.get("done") else ""))
    return f"Ev#{v['id']} {EVENT_ES[v['type']]}: {v['title']} — {when}{extra}"

def _interval(e, occ):
    s = _occ_start(e, occ)
    return s, s + datetime.timedelta(minutes=int(e.get("duration_min") or 60))

def _conflicts(d, e):
    """Other timed events that overlap this one in the next 60 days (first 5)."""
    if not e.get("time"):
        return []
    today = _today(); end = today + datetime.timedelta(days=60); out = []
    mine = _occurrences(e, today, end)
    for o in d["events"]:
        if o["id"] == e["id"] or not o.get("time") or o.get("status") == "cancelled":
            continue
        for occ in mine:
            if occ in _occurrences(o, occ, occ) and not _occ_done(o, occ):
                a1, a2 = _interval(e, occ); b1, b2 = _interval(o, occ)
                if a1 < b2 and b1 < a2:
                    out.append(_ev_line(_ev_view(o, occ), today))
                    break
        if len(out) >= 5:
            break
    return out

LATE_ALERT_MIN = 15   # created too late for the normal alert -> alert this many minutes before

def _premark_past_alerts(e):
    """Event created/moved after its normal alert moment (e.g. 'cita en 40 minutos' with a 60-min
    reminder, or an all-day delivery for tomorrow saved after 9 AM): instead of an instant ping
    (the boss just typed it) or no alert at all, it alerts LATE_ALERT_MIN minutes before it starts.
    Only if it starts in LATE_ALERT_MIN minutes or less is the alert skipped."""
    e.setdefault("notices", []); e.setdefault("late", [])
    if e.get("status") == "cancelled" or _remind_of(e) < 0:
        return
    now = _now(); today = now.date()
    for occ in _occurrences(e, today - datetime.timedelta(days=1), today + datetime.timedelta(days=60)):
        start = _occ_start(e, occ); key = occ.isoformat()
        if start - datetime.timedelta(minutes=_remind_of(e)) > now:
            break
        if start - datetime.timedelta(minutes=LATE_ALERT_MIN) <= now:
            if key not in e["notices"]: e["notices"].append(key)
        elif key not in e["late"]:
            e["late"].append(key)
    e["late"] = e["late"][-20:]

def add_event(title, date, type="other", time="", duration_min=None, location="", who="",
              amount="", notes="", remind_min=None, repeat=""):
    title = (title or "").strip()
    if not title:
        raise ValueError("title is required")
    e = {"title": title, "type": _valid_type(type), "date": _valid_date(date), "time": _valid_time(time),
         "duration_min": _int_or_none(duration_min), "location": location, "who": who,
         "amount": str(amount or "").strip(), "notes": notes, "remind_min": _int_or_none(remind_min),
         "repeat": _valid_repeat(repeat), "status": "scheduled", "done_dates": [], "skip_dates": [],
         "notices": [], "late": [], "created": _now().isoformat(timespec="minutes")}
    if e["time"] and e["duration_min"] is None:
        e["duration_min"] = 60
    d = _eload(); e["id"] = _next_id(d["events"])
    _premark_past_alerts(e)
    d["events"].append(e); _esave(d)
    out = {**_ev_view(e, datetime.date.fromisoformat(e["date"]))}
    clash = _conflicts(d, e)
    if clash:
        out["warning_conflicts"] = clash
    if not e["repeat"] and _occ_start(e, datetime.date.fromisoformat(e["date"])) < _now() - datetime.timedelta(hours=1):
        out["warning"] = "Esa fecha ya pasó. ¿Seguro que es esa fecha?"
    r = _remind_of(e)
    out["alert"] = "sin aviso" if r < 0 else (
        f"aviso {r} min antes" if e["time"] else f"aviso {'el día antes' if r == 1440 else f'{r} min antes'} "
        f"(día completo cuenta como {CAL_ALLDAY_HOUR}:00)")
    return out

def list_events(start="", days=14, type="", include_done=True):
    s = datetime.date.fromisoformat(start[:10]) if (start or "").strip() else _today()
    days = max(0, min(int(days), 366)); end = s + datetime.timedelta(days=days)
    t = _valid_type(type) if (type or "").strip() else ""
    rows = []
    for e in _eload()["events"]:
        if e.get("status") == "cancelled" or (t and e["type"] != t):
            continue
        for occ in _occurrences(e, s, end):
            v = _ev_view(e, occ)
            if v["done"] and not _to_bool(include_done):
                continue
            rows.append(v)
    rows.sort(key=lambda v: (v["date"], v["time"] or "00:00", v["id"]))
    return {"from": s.isoformat(), "to": end.isoformat(), "events": rows[:200], "count": len(rows)}

def find_events(query="", include_past=False):
    q = (query or "").strip().lower(); out = []
    for e in _eload()["events"]:
        hay = " ".join(str(e.get(k, "")) for k in ("title", "who", "location", "notes")).lower()
        if q and q not in hay:
            continue
        if not _to_bool(include_past) and not e.get("repeat") and e["date"] < (_today() - datetime.timedelta(days=7)).isoformat():
            continue
        out.append({k: e.get(k) for k in ("id", "title", "type", "date", "time", "repeat", "status", "who",
                                          "location", "amount", "remind_min", "done_dates", "skip_dates")})
    return {"events": out[:50], "count": len(out)}

def _pick_occurrence(e, date=""):
    if date:
        occ = datetime.date.fromisoformat(date[:10])
        if not _occurrences(e, occ, occ):
            raise ValueError(f"el evento #{e['id']} no ocurre el {occ.isoformat()}")
        return occ
    today = _today()
    # the open date closest to today (today first; on a tie the past one), never an old forgotten one
    opens = [o for o in _occurrences(e, today - datetime.timedelta(days=60), today + datetime.timedelta(days=400))
             if not _occ_done(e, o)]
    if not opens:
        raise ValueError("no encontré una fecha abierta para ese evento")
    return min(opens, key=lambda o: (abs((o - today).days), o > today))

def complete_event(id, date=""):
    """Mark done. Repeating events: only that date (default: the open date closest to today)."""
    d = _eload(); e = next((x for x in d["events"] if x["id"] == int(id)), None)
    if not e: return {"error": f"event {id} not found"}
    if not e.get("repeat"):
        e["status"] = "done"; _esave(d)
        return {**_ev_view(e, datetime.date.fromisoformat(e["date"])), "note": "Marcado como hecho."}
    occ = _pick_occurrence(e, date)
    if occ.isoformat() not in e["done_dates"]:
        e["done_dates"] = (e["done_dates"] + [occ.isoformat()])[-60:]
    _esave(d)
    return {**_ev_view(e, occ), "note": f"Hecho el {occ.isoformat()}; el evento se sigue repitiendo ({e['repeat']})."}

def cancel_event(id, date=""):
    """Cancel an event. For a repeating one, pass date to skip only that day; no date = cancel the whole series."""
    d = _eload(); e = next((x for x in d["events"] if x["id"] == int(id)), None)
    if not e: return {"error": f"event {id} not found"}
    if e.get("repeat") and date:
        occ = _pick_occurrence(e, date)
        if occ.isoformat() not in e["skip_dates"]:
            e["skip_dates"] = (e["skip_dates"] + [occ.isoformat()])[-60:]
        _esave(d)
        return {"cancelled_date": occ.isoformat(), "id": e["id"], "title": e["title"],
                "note": "Solo ese día; la serie sigue."}
    e["status"] = "cancelled"; _esave(d)
    return {"cancelled": e["id"], "title": e["title"]}

EVENT_EDITABLE = ["title", "type", "date", "time", "duration_min", "location", "who", "amount", "notes",
                  "remind_min", "repeat", "status"]

def edit_event(id, changes):
    d = _eload(); e = next((x for x in d["events"] if x["id"] == int(id)), None)
    if not e: return {"error": f"event {id} not found"}
    moved = False
    for k, v in (changes or {}).items():
        if k not in EVENT_EDITABLE: continue
        if k == "type": v = _valid_type(v)
        if k == "date": v = _valid_date(v); moved = True
        if k == "time": v = _valid_time(v); moved = True
        if k in ("duration_min", "remind_min"): v = _int_or_none(v); moved = moved or k == "remind_min"
        if k == "repeat": v = _valid_repeat(v); moved = True
        if k == "amount": v = str(v or "").strip()
        if k == "status":
            v = (v or "").strip().lower()
            if v not in ("scheduled", "done", "cancelled"):
                raise ValueError("status must be scheduled, done or cancelled")
        if k == "title" and not str(v).strip(): raise ValueError("title can't be blank")
        e[k] = v
    if e.get("time") and not e.get("duration_min"):
        e["duration_min"] = 60
    if moved:
        # new date/time -> the alert can fire again for the new moment
        e["notices"] = []; e["late"] = []; _premark_past_alerts(e)
    _esave(d)
    out = {k: e.get(k) for k in ("id", "title", "type", "date", "time", "duration_min", "location", "who",
                                 "amount", "notes", "remind_min", "repeat", "status")}
    clash = _conflicts(d, e)
    if clash: out["warning_conflicts"] = clash
    return out

def collect_event_alerts():
    """One alert per occurrence, remind_min before it starts. Read-only."""
    alerts = []; now = _now(); today = now.date()
    for e in _eload()["events"]:
        if e.get("status") in ("cancelled", "done"):
            continue
        r = _remind_of(e)
        if r < 0:
            continue
        horizon = today + datetime.timedelta(days=r // 1440 + 2)
        for occ in _occurrences(e, today - datetime.timedelta(days=1), horizon):
            key = occ.isoformat()
            if key in e.get("notices", []) or _occ_done(e, occ):
                continue
            start = _occ_start(e, occ)
            rr = min(r, LATE_ALERT_MIN) if key in e.get("late", []) else r
            if not (start - datetime.timedelta(minutes=rr) <= now):
                continue
            # too late to be useful? timed: 30 min after start; all-day: end of that day
            limit = start + datetime.timedelta(minutes=30) if e.get("time") else \
                datetime.datetime(occ.year, occ.month, occ.day, 23, 59, tzinfo=TZ)
            if now > limit:
                continue
            mins = int((start - now).total_seconds() // 60)
            if e.get("time"):
                if mins <= 0: when = "AHORA"
                elif mins < 120: when = f"en {mins} min (a las {e['time']})"
                elif (occ - today).days == 0: when = f"hoy a las {e['time']}"
                else: when = f"{_day_label(occ, today)} a las {e['time']}"
            else:
                when = {0: "HOY", 1: "MAÑANA"}.get((occ - today).days, _day_label(occ, today))
            v = _ev_view(e, occ)
            extra = "".join(x for x in (
                f"\n📍 {v['location']}" if v["location"] else "",
                f"\n👤 {v['who']}" if v["who"] else "",
                f"\n💵 ${v['amount']}" if v["amount"] else "",
                f"\n📝 {v['notes'][:200]}" if v["notes"] else ""))
            alerts.append({"kind": "event", "id": e["id"], "key": key,
                           "text": f"{EVENT_ES[e['type']]} {when}: {e['title']}{extra}\n"
                                   f"(Evento #{e['id']}. Cuando esté hecho: /listo {e['id']})"})
    return alerts

def mark_event_alert(alert):
    d = _eload()
    for e in d["events"]:
        if e["id"] == alert["id"]:
            e.setdefault("notices", [])
            if alert["key"] not in e["notices"]:
                e["notices"].append(alert["key"])
            e["notices"] = e["notices"][-40:]
    _esave(d)

def calendar_brief_lines():
    """Morning brief: today's and tomorrow's events + overdue deliveries/payments (no pings)."""
    today = _today(); lines = []
    rows = list_events(today.isoformat(), 1, include_done=False)["events"]
    tod = [v for v in rows if v["date"] == today.isoformat()]
    tmw = [v for v in rows if v["date"] != today.isoformat()]
    if tod:
        lines.append("\n🗓️ Calendario de hoy:")
        lines += ["• " + _ev_line(v, today, with_date=False) for v in tod]
    if tmw:
        lines.append("\n🗓️ Mañana:")
        lines += ["• " + _ev_line(v, today, with_date=False) for v in tmw]
    late = [v for v in list_events((today - datetime.timedelta(days=7)).isoformat(), 6, include_done=False)["events"]
            if v["type"] in ("delivery", "payment", "collection") and v["date"] < today.isoformat()]
    if late:
        lines.append("\n⚠️ Sin marcar como hecho:")
        lines += ["• " + _ev_line(v, today) for v in late[:8]]
    return lines

def calendar_text(days=14):
    days = max(1, min(int(days), 90)); today = _today()
    r = list_events(today.isoformat(), days)
    if not r["events"]:
        return f"🗓️ Nada en el calendario en los próximos {days} días."
    lines = [f"🗓️ Próximos {days} días:"]; cur = None
    for v in r["events"]:
        if v["date"] != cur:
            cur = v["date"]
            lines.append(f"\n{_day_label(datetime.date.fromisoformat(cur), today).capitalize()}")
        lines.append("• " + _ev_line(v, today, with_date=False))
    lines.append("\n✅ Para marcar hecho: /listo N (N = número del evento)")
    return "\n".join(lines)

def done_text(arg):
    """v3.3: /listo N [YYYY-MM-DD] — mark a CALENDAR event done without Claude (zero tokens)."""
    nums = re.findall(r"\d{4}-\d{2}-\d{2}|\d+", arg or "")
    ids = [n for n in nums if "-" not in n]; dates = [n for n in nums if "-" in n]
    if not ids:
        return "Usa /listo N con el número del evento (míralo en /calendario)."
    r = complete_event(int(ids[0]), dates[0] if dates else "")
    if r.get("error"):
        return f"⚠️ No encontré el evento #{ids[0]} (/calendario para ver los números)."
    rep_note = " (la serie sigue)" if r.get("repeat") else ""
    return f"✅ Evento #{r['id']} hecho: {EVENT_ES[r['type']]} {r['title']} — {r['date']}{rep_note}"

def _date_helper():
    """Exact dates for the next days, so 'el jueves' / 'pasado mañana' never get miscounted."""
    today = _today()
    return ", ".join(f"{DIAS[(today + datetime.timedelta(days=i)).weekday()]} "
                     f"{(today + datetime.timedelta(days=i)).isoformat()}"
                     + (" (hoy)" if i == 0 else " (mañana)" if i == 1 else "")
                     for i in range(0, 8))

# ---------------------------------------------------------------------------
# EDIT / DELETE for any list.
# ---------------------------------------------------------------------------
KINDS = {"reminder":(_pload,_psave,"reminders"), "bill":(_pload,_psave,"bills"),
         "income":(_bload,_bsave,"income"), "expense":(_bload,_bsave,"expenses"),
         "event":(_eload,_esave,"events")}
EDITABLE = {"reminder":["text","when","done","due","repeat"], "bill":["name","day","amount"],
            "income":["amount","source","date"], "expense":["amount","category","note","date"],
            "event":EVENT_EDITABLE}

def delete_entry(kind, id):
    if kind not in KINDS: return {"error":f"unknown kind {kind}"}
    load, save, field = KINDS[kind]; d=load()
    keep=[x for x in d[field] if x["id"]!=int(id)]
    if len(keep)==len(d[field]): return {"error":f"{kind} {id} not found"}
    d[field]=keep; save(d); return {"deleted":kind,"id":int(id)}

def edit_entry(kind, id, changes):
    if kind not in KINDS: return {"error":f"unknown kind {kind}"}
    if kind=="event": return edit_event(id, changes)   # v3.3: calendar has its own rules
    load, save, field = KINDS[kind]; d=load()
    for x in d[field]:
        if x["id"]==int(id):
            for k,v in (changes or {}).items():
                if k not in EDITABLE[kind]: continue
                if k=="amount" and kind in ("income","expense"): v=float(v)
                if k=="day": v=_valid_day(v)
                if k=="done": v=_to_bool(v)
                if k=="category" and v not in EXPENSE_CATEGORIES: v="other"
                if k=="due":
                    v=_parse_due(v); x["notified"]=False   # new time -> alert again
                if k=="repeat": v=_valid_repeat(v)
                x[k]=v
            if kind=="reminder" and x.get("repeat") and not x.get("due"):
                raise ValueError("a repeating reminder needs a due date/time")
            save(d); return x
    return {"error":f"{kind} {id} not found"}

# ---------------------------------------------------------------------------
# PROACTIVE ENGINE (v3.2). Plain Python, no Claude calls -> zero tokens.
# ---------------------------------------------------------------------------
_local_claims: dict = {}
_sched_state = {"last_tick": None, "last_error": None, "alerts_sent": 0}

def _claim(key, ttl):
    """True only once per key while it lives (safe if two servers overlap on deploy)."""
    if USE_REDIS:
        try:
            return _redis(["SET", key, "1", "NX", "EX", str(int(ttl))]) is not None
        except Exception:
            pass
    now = _now().timestamp()
    for k in [k for k, exp in _local_claims.items() if exp < now]:
        _local_claims.pop(k, None)
    if key in _local_claims:
        return False
    _local_claims[key] = now + ttl
    return True

def _bill_due_dates(bill, today):
    """This month's and next month's due date for a bill: [(YYYY-MM, date)]."""
    out = []
    y, m = today.year, today.month
    for _ in range(2):
        day = min(int(bill["day"]), calendar.monthrange(y, m)[1])
        out.append((f"{y:04d}-{m:02d}", datetime.date(y, m, day)))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out

def _fmt_amount(a):
    return f" (${a})" if str(a).strip() else ""

def collect_alerts():
    """Everything that should be sent right now. Does not change any data."""
    alerts = []; now = _now(); today = now.date()
    d = _pload()
    for r in d["reminders"]:
        if r.get("done") or not r.get("due") or r.get("notified"):
            continue
        try:
            due = _due_dt(r["due"])
        except Exception:
            continue
        if due <= now:
            late = " (atrasado)" if (now - due).total_seconds() > 3600 else ""
            rep = f"\n🔁 Se repite: {r['repeat']}" if r.get("repeat") else ""
            alerts.append({"kind": "reminder", "id": r["id"],
                           "text": f"⏰ Recordatorio #{r['id']}{late}: {r['text']}\n🕒 {r['due']}{rep}"})
    for b in d["bills"]:
        paid = b.get("paid", []); sent = b.get("notices", [])
        for month, due in _bill_due_dates(b, today):
            if month in paid:
                continue
            left = (due - today).days
            if left == 0:
                stage, msg = "today", f"💳 HOY vence: {b['name']}{_fmt_amount(b.get('amount',''))}"
            elif 0 < left <= BILL_NOTICE_DAYS:
                stage, msg = "soon", f"💳 En {left} día(s) vence: {b['name']}{_fmt_amount(b.get('amount',''))} — {due.isoformat()}"
            elif -3 <= left < 0 and any(n.startswith(month + ":") for n in sent):
                # only if we already warned about it (avoids false alarms on new bills)
                stage, msg = "late", f"⚠️ Vencida sin marcar pagada: {b['name']}{_fmt_amount(b.get('amount',''))} — {due.isoformat()}"
            else:
                continue
            key = f"{month}:{stage}"
            if key not in sent:
                alerts.append({"kind": "bill", "id": b["id"], "key": key,
                               "text": msg + f"\n(Cuenta #{b['id']}. Dime \"pagué {b['name']}\" para marcarla.)"})
    try:
        alerts += collect_event_alerts()   # v3.3 calendar
    except Exception as e:
        _sched_state["last_error"] = f"calendar: {type(e).__name__}: {e}"
    return alerts

def mark_alert_sent(alert):
    """Record a sent alert so it is never repeated (repeating reminders move to the next date)."""
    with _data_lock:
        if alert["kind"] == "event":   # v3.3 calendar lives in its own key
            mark_event_alert(alert)
            return
        d = _pload()
        if alert["kind"] == "reminder":
            for r in d["reminders"]:
                if r["id"] == alert["id"]:
                    if r.get("repeat"):
                        r["due"] = _roll(r["due"], r["repeat"]); r["notified"] = False
                    else:
                        r["notified"] = True
        elif alert["kind"] == "bill":
            for b in d["bills"]:
                if b["id"] == alert["id"]:
                    b.setdefault("notices", [])
                    if alert["key"] not in b["notices"]:
                        b["notices"].append(alert["key"])
                    b["notices"] = b["notices"][-24:]   # keep it small
        _psave(d)

def upcoming(days=7):
    """Reminders with a date and unpaid bills in the next N days."""
    days = max(0, min(int(days), 60)); now = _now(); today = now.date()
    end = today + datetime.timedelta(days=days)
    d = _pload(); rem = []; bills = []
    for r in d["reminders"]:
        if r.get("done") or not r.get("due"):
            continue
        try:
            if _due_dt(r["due"]).date() <= end:
                rem.append(r)
        except Exception:
            pass
    for b in d["bills"]:
        for month, due in _bill_due_dates(b, today):
            if month not in b.get("paid", []) and today - datetime.timedelta(days=3) <= due <= end:
                bills.append({"id": b["id"], "name": b["name"], "amount": b.get("amount", ""),
                              "due": due.isoformat(), "month": month, "overdue": due < today})
    rem.sort(key=lambda r: r["due"]); bills.sort(key=lambda b: b["due"])
    open_no_date = [r for r in d["reminders"] if not r.get("done") and not r.get("due")]
    try:   # v3.3: calendar events in the same window
        events = list_events(today.isoformat(), days, include_done=False)["events"]
    except Exception:
        events = []
    return {"reminders": rem, "bills": bills, "events": events,
            "open_reminders_without_date": len(open_no_date),
            "shopping_items": len(d["shopping"])}

def brief_text():
    """Short morning summary built without Claude."""
    u = upcoming(0); today = _today().isoformat()
    lines = [f"☀️ Buenos días, {OWNER}. Resumen de hoy {today}:"]
    todays = [r for r in u["reminders"]]
    if todays:
        lines.append("\n⏰ Recordatorios:")
        lines += [f"• #{r['id']} " + (r['due'][11:] if r['due'][:10] == today else f"{r['due']} ⚠️ atrasado")
                  + f" — {r['text']}" for r in todays]
    week = upcoming(BILL_NOTICE_DAYS + 5)["bills"]
    if week:
        lines.append("\n💳 Cuentas próximas:")
        lines += [f"• {b['name']}{_fmt_amount(b['amount'])} — {b['due']}" + (" ⚠️ vencida" if b["overdue"] else "")
                  for b in week]
    try:
        lines += calendar_brief_lines()   # v3.3: today's/tomorrow's events
    except Exception:
        pass
    if u["open_reminders_without_date"]:
        lines.append(f"\n📝 Pendientes sin fecha: {u['open_reminders_without_date']}")
    if u["shopping_items"]:
        lines.append(f"🛒 Lista de compras: {u['shopping_items']} artículo(s)")
    if len(lines) == 1:
        lines.append("Nada programado. Día libre para avanzar los negocios. 💪")
    return "\n".join(lines)

def snapshot():
    return {"taken_at": _now().isoformat(), "personal": _pload(), "books": _bload(),
            "calendar": _eload()}

def daily_backup():
    """One copy of all data per day, kept 30 days inside Redis."""
    if not USE_REDIS:
        return False
    key = f"jarvis:backup:{_today().isoformat()}"
    _redis(["SET", key, json.dumps(snapshot(), ensure_ascii=False), "EX", str(30 * 86400)])
    return True

async def _tick():
    now = _now()
    if not await asyncio.to_thread(_claim, f"jarvis:tick:{now:%Y%m%d%H%M}", 300):
        return   # another copy of the server already handled this minute
    can_send = bool(TG_TOKEN and TG_OWNER)
    if can_send:
        alerts = await asyncio.to_thread(collect_alerts)
        for a in alerts:
            try:
                await _tg_send(TG_OWNER, a["text"])
            except Exception as e:
                _sched_state["last_error"] = f"send: {e}"
                continue   # not marked -> retried next tick
            await asyncio.to_thread(mark_alert_sent, a)
            _sched_state["alerts_sent"] += 1
        if BRIEF_HOUR.isdigit() and now.hour == int(BRIEF_HOUR):
            if await asyncio.to_thread(_claim, f"jarvis:brief:{now.date().isoformat()}", 2 * 86400):
                await _tg_send(TG_OWNER, await asyncio.to_thread(brief_text))
    if await asyncio.to_thread(_claim, f"jarvis:backupclaim:{now.date().isoformat()}", 2 * 86400):
        await asyncio.to_thread(daily_backup)
    _sched_state["last_tick"] = now.isoformat()

async def _scheduler_loop():
    if not SCHED_ON:
        return
    await asyncio.sleep(10)   # let the server finish booting
    while True:
        try:
            await _tick()
        except Exception as e:
            _sched_state["last_error"] = f"{type(e).__name__}: {e}"
        await asyncio.sleep(SCHED_EVERY)

HANDLERS = {"add_reminder":add_reminder,"complete_reminder":complete_reminder,
            "add_shopping":add_shopping,"remove_shopping":remove_shopping,"clear_shopping":clear_shopping,
            "add_bill":add_bill,"mark_bill_paid":mark_bill_paid,"overview":overview,
            "add_income":add_income,"add_expense":add_expense,"list_books":list_books,
            "finances_summary":finances_summary,"tax_estimate":tax_estimate,
            "delete_entry":delete_entry,"edit_entry":edit_entry,"upcoming":upcoming}
# v3.3 calendar
HANDLERS.update({"add_event":add_event,"list_events":list_events,"find_events":find_events,
                 "complete_event":complete_event,"cancel_event":cancel_event})

def _t(name, desc, props=None, req=None):
    return {"name":name,"description":desc,
            "input_schema":{"type":"object","properties":props or {},"required":req or []}}
S={"type":"string"}; N={"type":"number"}; I={"type":"integer"}
KIND={"type":"string","enum":["reminder","bill","income","expense","event"]}

TOOLS = [
    _t("add_reminder","Add a reminder. To get an automatic Telegram alert, set due as "
       "'YYYY-MM-DD HH:MM' in Puerto Rico time (convert 'mañana a las 9' yourself using the current "
       "date). repeat: daily, weekly, monthly or blank (needs due). when is free text.",
       {"text":S,"when":S,"due":S,"repeat":{"type":"string","enum":REPEATS}},["text"]),
    _t("complete_reminder","Mark a reminder as done by id.",{"id":I},["id"]),
    _t("add_shopping","Add one item to the shopping list.",{"item":S},["item"]),
    _t("remove_shopping","Remove one item from the shopping list by name.",{"item":S},["item"]),
    _t("clear_shopping","Empty the shopping list."),
    _t("add_bill","Track a recurring bill by day of month (1-31).",{"name":S,"day":I,"amount":S},["name","day"]),
    _t("mark_bill_paid","Mark a bill paid for a month (YYYY-MM, default this month). If the boss pays "
       "early for next month's due date, pass that month (see upcoming).",{"id":I,"month":S},["id"]),
    _t("upcoming","Agenda: dated reminders and unpaid bills in the next N days (default 7).",{"days":I}),
    _t("overview","All reminders, shopping list and bills, with ids."),
    _t("add_income","Log business income. date is YYYY-MM-DD, default today.",{"amount":N,"source":S,"date":S},["amount"]),
    _t("add_expense","Log a business expense. date is YYYY-MM-DD, default today. category: "
       +", ".join(EXPENSE_CATEGORIES)+".",
       {"amount":N,"category":S,"note":S,"date":S},["amount"]),
    _t("list_books","All income and expense entries, with ids."),
    _t("finances_summary","Totals: income, expenses, net profit, expenses by category."),
    _t("tax_estimate","Tax set-aside estimate on net profit; ask the boss for rate_percent.",{"rate_percent":N},["rate_percent"]),
    _t("delete_entry","Delete a reminder, bill, income, expense or calendar event by id. Look up the id first. "
       "For an event the boss just wants to call off, prefer cancel_event.",{"kind":KIND,"id":I},["kind","id"]),
    _t("edit_entry","Edit fields of a reminder, bill, income, expense or calendar event by id. Look up the id "
       "first. Event fields: "+", ".join(EVENT_EDITABLE)+" (same formats as add_event).",
       {"kind":KIND,"id":I,"changes":{"type":"object"}},["kind","id","changes"]),
    _t("delegate","Hand a task to an EXTERNAL specialist agent.",
       {"agent":{"type":"string","enum":list(AGENTS)},"instruction":S},["agent","instruction"]),
    # --- v3.3: calendar ---
    _t("add_event","Put a dated item on the calendar: delivery (entrega), appointment (cita), payment (a date "
       "the boss must PAY someone), collection (a date a client must PAY the boss), other. date YYYY-MM-DD and "
       "time HH:MM 24h in Puerto Rico time — convert 'el jueves a las 3' yourself using the date list in the "
       "system prompt. time blank = all day. duration_min default 60. remind_min: minutes before to send ONE "
       "Telegram alert (default 60 for timed, 1440 = day before for all-day; -1 = no alert). repeat: daily, "
       "weekly, monthly or blank. amount as text, no $. Reports overlapping events in warning_conflicts.",
       {"title":S,"date":S,"type":{"type":"string","enum":EVENT_TYPES},"time":S,"duration_min":I,"location":S,
        "who":S,"amount":S,"notes":S,"remind_min":I,"repeat":{"type":"string","enum":REPEATS}},["title","date"]),
    _t("list_events","Calendar from start (YYYY-MM-DD, default today) for N days (default 14), each repeat "
       "expanded to its dates. type filters (delivery, appointment, payment, collection, other).",
       {"start":S,"days":I,"type":{"type":"string","enum":EVENT_TYPES},"include_done":{"type":"boolean"}}),
    _t("find_events","Search calendar events by text (title, who, location, notes) to get their id.",
       {"query":S,"include_past":{"type":"boolean"}}),
    _t("complete_event","Mark an event done (delivered, paid, collected, attended). For a repeating event only "
       "that date is marked (date YYYY-MM-DD; default the oldest open one).",{"id":I,"date":S},["id"]),
    _t("cancel_event","Cancel an event. For a repeating event, pass date to skip only that day; without date "
       "the whole series is cancelled.",{"id":I,"date":S},["id"]),
]

async def run_tool(name, args):
    try:
        if name == "delegate":
            return await delegate(**args)
        if name not in HANDLERS:
            return {"error": f"unknown tool {name}"}
        # storage calls are blocking; run them off the event loop
        def _locked():
            with _data_lock:
                return HANDLERS[name](**args)
        return await asyncio.to_thread(_locked)
    except Exception as e:
        return {"error": str(e)}

def system_prompt():
    now = _now().strftime("%A %Y-%m-%d %H:%M (%Z)")
    deployed = [a for a, u in AGENTS.items() if u]
    ext = ", ".join(deployed) if deployed else "(none deployed yet)"
    return (f"You are Jarvis, chief of staff for {OWNER}. Now in Puerto Rico: {now}.\n"
            "Built-in tools: reminders, shopping list, bills, accounting (income, expenses, "
            "net profit, tax estimates), and editing/deleting any of those entries.\n"
            "Proactive engine: reminders with a due date/time are sent to Telegram automatically "
            "(also daily/weekly/monthly repeats), bills get alerts before they are due, and a morning "
            "brief goes out. When the boss asks to be reminded at a time, ALWAYS set due.\n"
            f"Storage: {storage_mode()}.\n"
            f"External agents deployed: {ext}. Use delegate for those.\n"
            "Before editing or deleting, look up the entry id; confirm with the boss before deleting. "
            "As accountant you ORIENT only — a licensed CPA files official returns. For money "
            "matters (coinbase, amazon) you NEVER authorize a purchase or trade — the boss approves. "
            "Be brief, reply in Spanish by default, never invent a result, and say so if an agent "
            "isn't deployed.\n"
            f"Exact dates (use these, never count weekdays yourself): {_date_helper()}.\n"
            "v3.3 CALENDAR is built-in (do NOT delegate('calendar')): deliveries, appointments, dates to "
            "pay (payment) and dates to collect (collection) go to add_event. A plain to-do or 'avísame a "
            "las X' stays a reminder; a fixed monthly household bill stays add_bill. If an appointment has "
            "no time, ask for it. After saving, confirm in one line with weekday, date and time, and mention "
            "any warning_conflicts or warning. 'Qué tengo esta semana' -> list_events. The boss can also "
            "type /calendario for a zero-token list and /listo N to mark event N done.\n"
            "IDs: reminders and calendar events are numbered SEPARATELY (reminder #2 and event #2 can both "
            "exist). Calendar alerts and lists show events as 'Evento #N' / 'Ev#N'. If the boss says 'listo N' "
            "or 'borra el N' without saying evento or recordatorio, check whether both exist; if both do, ask "
            "which one before changing anything.")

# ---------------------------------------------------------------------------
# Conversation loop. Works on a copy of the history and only saves it when
# the turn finishes cleanly, so an error never leaves a broken history.
# ---------------------------------------------------------------------------
conversations: dict = {}
_locks: dict = {}

def _trim(history):
    history = history[-30:]
    while history and not (history[0]["role"] == "user" and isinstance(history[0]["content"], str)):
        history.pop(0)
    return history

async def run(session: str, message: str) -> str:
    lock = _locks.setdefault(session, asyncio.Lock())
    async with lock:   # one message at a time per session
        history = list(conversations.get(session, []))
        history.append({"role": "user", "content": message})
        history = _trim(history)
        for _ in range(10):
            r = await client.messages.create(model=MODEL, max_tokens=1500,
                                              system=system_prompt(), tools=TOOLS, messages=history)
            content = [b for b in r.content if b.type != "thinking"]
            history.append({"role": "assistant", "content": content})
            if r.stop_reason != "tool_use":
                conversations[session] = history
                return "".join(b.text for b in r.content if b.type == "text")
            results = []
            for b in r.content:
                if b.type == "tool_use":
                    out = await run_tool(b.name, b.input)
                    results.append({"type": "tool_result", "tool_use_id": b.id,
                                    "content": json.dumps(out, default=str, ensure_ascii=False)[:15000]})
            history.append({"role": "user", "content": results})
        conversations[session] = history
        return "Me enredé con demasiados pasos. ¿Me lo repites más simple?"

# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------
class Chat(BaseModel):
    message: str
    session: str = "default"

@app.post("/chat")
async def chat(req: Chat, x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(401, "Bad API key")
    try:
        reply = await run(req.session, req.message)
    except Exception as e:
        conversations.pop(req.session, None)
        reply = f"Tuve un error y reinicié la conversación. Repíteme, por favor. ({type(e).__name__})"
    return {"reply": reply}

_seen_updates: set = set()

def _first_time(update_id) -> bool:
    """True only the first time we see a Telegram update (Telegram retries)."""
    if update_id is None:
        return True
    if USE_REDIS:
        try:
            return _redis(["SET", f"jarvis:tg:upd:{update_id}", "1", "NX", "EX", "86400"]) is not None
        except Exception:
            pass
    if update_id in _seen_updates:
        return False
    _seen_updates.add(update_id)
    if len(_seen_updates) > 1000:
        _seen_updates.clear(); _seen_updates.add(update_id)
    return True

async def _tg_send(chat_id, text):
    text = text.strip() or "(sin respuesta)"
    async with httpx.AsyncClient(timeout=30) as hc:
        for i in range(0, len(text), 4000):   # Telegram limit is 4096 chars
            await hc.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                          json={"chat_id": chat_id, "text": text[i:i+4000]})

async def _handle_tg(chat_id, text):
    session = f"tg:{chat_id}"
    try:
        reply = await run(session, text)
    except Exception as e:
        conversations.pop(session, None)
        reply = f"Tuve un error y reinicié la conversación. Repíteme, por favor. ({type(e).__name__})"
    try:
        await _tg_send(chat_id, reply)
    except Exception:
        pass

async def _tg_brief(chat_id):
    try:
        await _tg_send(chat_id, await asyncio.to_thread(brief_text))
    except Exception:
        pass

async def _tg_done(chat_id, arg):
    """v3.3: /listo N — mark calendar event N done (zero tokens)."""
    def _txt():
        with _data_lock:
            return done_text(arg)
    try:
        await _tg_send(chat_id, await asyncio.to_thread(_txt))
    except Exception as e:
        try:
            await _tg_send(chat_id, f"⚠️ No pude marcarlo ({type(e).__name__}: {e}).")
        except Exception:
            pass

async def _tg_calendar(chat_id, days):
    """v3.3: /calendario [días] — calendar list without Claude (zero tokens)."""
    def _txt():
        with _data_lock:
            return calendar_text(days)
    try:
        await _tg_send(chat_id, await asyncio.to_thread(_txt))
    except Exception as e:
        try:
            await _tg_send(chat_id, f"⚠️ No pude leer el calendario ({type(e).__name__}).")
        except Exception:
            pass

@app.post("/telegram")
async def telegram(request: Request, background: BackgroundTasks,
                   x_telegram_bot_api_secret_token: str = Header(None)):
    # Only Telegram knows the secret; only the owner gets answers.
    if not TG_SECRET or x_telegram_bot_api_secret_token != TG_SECRET:
        raise HTTPException(401, "Bad secret")
    update = await request.json()
    msg = update.get("message") or {}   # edited messages ignored to avoid double entries
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = msg.get("text", "")
    if not chat_id or not text or not TG_OWNER or chat_id != TG_OWNER:
        return {"ok": True}
    if not await asyncio.to_thread(_first_time, update.get("update_id")):
        return {"ok": True}
    if text.strip().lower().split("@")[0] in ("/hoy", "/agenda"):
        # instant summary without Claude (zero tokens)
        background.add_task(_tg_brief, chat_id)
        return {"ok": True}
    cmd, _, arg = text.strip().partition(" ")
    cmd = cmd.lower().split("@")[0]
    if cmd in ("/calendario", "/cal", "/semana"):
        # v3.3: calendar list without Claude (zero tokens). /calendario 30 = next 30 days
        n = int(arg.strip()) if arg.strip().isdigit() else (7 if cmd == "/semana" else 14)
        background.add_task(_tg_calendar, chat_id, n)
        return {"ok": True}
    if cmd in ("/listo", "/hecho"):
        # v3.3: /listo N [YYYY-MM-DD] marks calendar event N done (zero tokens)
        background.add_task(_tg_done, chat_id, arg)
        return {"ok": True}
    # Answer Telegram right away; do the work in the background.
    background.add_task(_handle_tg, chat_id, text)
    return {"ok": True}

@app.get("/backup")
async def backup(x_api_key: str = Header(...)):
    """Full copy of all data (personal + books + calendar). Save it somewhere safe."""
    if x_api_key != API_KEY:
        raise HTTPException(401, "Bad API key")
    def _snap():
        with _data_lock:
            return snapshot()
    return await asyncio.to_thread(_snap)

@app.get("/")
async def health():
    return {"jarvis": "online", "version": "3.3", "storage": storage_mode(),
            "time": _now().isoformat(),
            "telegram_ready": bool(TG_TOKEN and TG_SECRET and TG_OWNER),
            "builtin": ["personal", "accountant", "edit/delete", "proactive", "calendar"],
            "scheduler": {"enabled": SCHED_ON, "every_seconds": SCHED_EVERY,
                          "brief_hour": BRIEF_HOUR or "off", "bill_notice_days": BILL_NOTICE_DAYS,
                          **_sched_state},
            "external_agents": {a: bool(u) for a, u in AGENTS.items()}}
