"""Jarvis v3.1: orchestrator + built-in specialists + permanent memory.

Built-in: personal (reminders, shopping list, bills) and accountant
(income, expenses, net profit, tax estimates). Data is saved in Upstash
Redis (free) so it survives every deploy. If the Upstash variables are
not set yet, it falls back to local files (those get wiped on deploy).
One Render service, one bill.

v3.1 fixes: Telegram secret + owner required, no duplicate entries on
Telegram retries, Puerto Rico time zone, history safe on errors, async
Claude calls, long/empty replies handled, input validation.
"""
import os, json, datetime, asyncio, httpx
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Header, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(title="Jarvis Orchestrator")
client = AsyncAnthropic()
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
API_KEY = os.getenv("AGENT_API_KEY", "").strip()
OWNER = os.getenv("OWNER_NAME", "the boss")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
TG_OWNER = os.getenv("TELEGRAM_OWNER_ID", "").strip()
TZ = ZoneInfo(os.getenv("TZ_NAME", "America/Puerto_Rico"))

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

def add_reminder(text, when=""):
    d=_pload(); e={"id":_next_id(d["reminders"]),"text":text,"when":when,"done":False}
    d["reminders"].append(e); _psave(d); return e
def complete_reminder(id):
    d=_pload()
    for x in d["reminders"]:
        if x["id"]==int(id):
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
# EDIT / DELETE for any list.
# ---------------------------------------------------------------------------
KINDS = {"reminder":(_pload,_psave,"reminders"), "bill":(_pload,_psave,"bills"),
         "income":(_bload,_bsave,"income"), "expense":(_bload,_bsave,"expenses")}
EDITABLE = {"reminder":["text","when","done"], "bill":["name","day","amount"],
            "income":["amount","source","date"], "expense":["amount","category","note","date"]}

def delete_entry(kind, id):
    if kind not in KINDS: return {"error":f"unknown kind {kind}"}
    load, save, field = KINDS[kind]; d=load()
    keep=[x for x in d[field] if x["id"]!=int(id)]
    if len(keep)==len(d[field]): return {"error":f"{kind} {id} not found"}
    d[field]=keep; save(d); return {"deleted":kind,"id":int(id)}

def edit_entry(kind, id, changes):
    if kind not in KINDS: return {"error":f"unknown kind {kind}"}
    load, save, field = KINDS[kind]; d=load()
    for x in d[field]:
        if x["id"]==int(id):
            for k,v in (changes or {}).items():
                if k not in EDITABLE[kind]: continue
                if k=="amount" and kind in ("income","expense"): v=float(v)
                if k=="day": v=_valid_day(v)
                if k=="done": v=_to_bool(v)
                if k=="category" and v not in EXPENSE_CATEGORIES: v="other"
                x[k]=v
            save(d); return x
    return {"error":f"{kind} {id} not found"}

HANDLERS = {"add_reminder":add_reminder,"complete_reminder":complete_reminder,
            "add_shopping":add_shopping,"remove_shopping":remove_shopping,"clear_shopping":clear_shopping,
            "add_bill":add_bill,"mark_bill_paid":mark_bill_paid,"overview":overview,
            "add_income":add_income,"add_expense":add_expense,"list_books":list_books,
            "finances_summary":finances_summary,"tax_estimate":tax_estimate,
            "delete_entry":delete_entry,"edit_entry":edit_entry}

def _t(name, desc, props=None, req=None):
    return {"name":name,"description":desc,
            "input_schema":{"type":"object","properties":props or {},"required":req or []}}
S={"type":"string"}; N={"type":"number"}; I={"type":"integer"}
KIND={"type":"string","enum":["reminder","bill","income","expense"]}

TOOLS = [
    _t("add_reminder","Add a reminder.",{"text":S,"when":S},["text"]),
    _t("complete_reminder","Mark a reminder as done by id.",{"id":I},["id"]),
    _t("add_shopping","Add one item to the shopping list.",{"item":S},["item"]),
    _t("remove_shopping","Remove one item from the shopping list by name.",{"item":S},["item"]),
    _t("clear_shopping","Empty the shopping list."),
    _t("add_bill","Track a recurring bill by day of month (1-31).",{"name":S,"day":I,"amount":S},["name","day"]),
    _t("mark_bill_paid","Mark a bill paid for a month (YYYY-MM, default this month).",{"id":I,"month":S},["id"]),
    _t("overview","All reminders, shopping list and bills, with ids."),
    _t("add_income","Log business income. date is YYYY-MM-DD, default today.",{"amount":N,"source":S,"date":S},["amount"]),
    _t("add_expense","Log a business expense. date is YYYY-MM-DD, default today. category: "
       +", ".join(EXPENSE_CATEGORIES)+".",
       {"amount":N,"category":S,"note":S,"date":S},["amount"]),
    _t("list_books","All income and expense entries, with ids."),
    _t("finances_summary","Totals: income, expenses, net profit, expenses by category."),
    _t("tax_estimate","Tax set-aside estimate on net profit; ask the boss for rate_percent.",{"rate_percent":N},["rate_percent"]),
    _t("delete_entry","Delete a reminder, bill, income or expense by id. Look up the id first.",{"kind":KIND,"id":I},["kind","id"]),
    _t("edit_entry","Edit fields of a reminder, bill, income or expense by id. Look up the id first.",
       {"kind":KIND,"id":I,"changes":{"type":"object"}},["kind","id","changes"]),
    _t("delegate","Hand a task to an EXTERNAL specialist agent.",
       {"agent":{"type":"string","enum":list(AGENTS)},"instruction":S},["agent","instruction"]),
]

async def run_tool(name, args):
    try:
        if name == "delegate":
            return await delegate(**args)
        if name not in HANDLERS:
            return {"error": f"unknown tool {name}"}
        # storage calls are blocking; run them off the event loop
        return await asyncio.to_thread(HANDLERS[name], **args)
    except Exception as e:
        return {"error": str(e)}

def system_prompt():
    now = _now().strftime("%A %Y-%m-%d %H:%M (%Z)")
    deployed = [a for a, u in AGENTS.items() if u]
    ext = ", ".join(deployed) if deployed else "(none deployed yet)"
    return (f"You are Jarvis, chief of staff for {OWNER}. Now in Puerto Rico: {now}.\n"
            "Built-in tools: reminders, shopping list, bills, accounting (income, expenses, "
            "net profit, tax estimates), and editing/deleting any of those entries.\n"
            f"Storage: {storage_mode()}.\n"
            f"External agents deployed: {ext}. Use delegate for those.\n"
            "Before editing or deleting, look up the entry id; confirm with the boss before deleting. "
            "As accountant you ORIENT only — a licensed CPA files official returns. For money "
            "matters (coinbase, amazon) you NEVER authorize a purchase or trade — the boss approves. "
            "Be brief, reply in Spanish by default, never invent a result, and say so if an agent "
            "isn't deployed.")

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
    # Answer Telegram right away; do the work in the background.
    background.add_task(_handle_tg, chat_id, text)
    return {"ok": True}

@app.get("/")
async def health():
    return {"jarvis": "online", "version": "3.1", "storage": storage_mode(),
            "time": _now().isoformat(),
            "telegram_ready": bool(TG_TOKEN and TG_SECRET and TG_OWNER),
            "builtin": ["personal", "accountant", "edit/delete"],
            "external_agents": {a: bool(u) for a, u in AGENTS.items()}}
