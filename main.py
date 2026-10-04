"""Jarvis: the orchestrator. You talk to Jarvis; he routes each task to the
right specialist agent and brings back the answer. Runs on a server; you
control him from your iPhone via Telegram (or the /chat HTTP endpoint).
"""
import os, json, datetime, httpx
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(title="Jarvis Orchestrator")
client = Anthropic()
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
API_KEY = os.getenv("AGENT_API_KEY", "change-me")
OWNER = os.getenv("OWNER_NAME", "the boss")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

AGENTS = {
    "personal": os.getenv("PERSONAL_AGENT_URL", ""),
    "call":     os.getenv("CALL_AGENT_URL", ""),
    "message":  os.getenv("SMS_AGENT_URL", ""),
    "email":    os.getenv("EMAIL_AGENT_URL", ""),
    "calendar": os.getenv("CALENDAR_AGENT_URL", ""),
    "amazon":   os.getenv("AMAZON_AGENT_URL", ""),
    "coinbase": os.getenv("COINBASE_AGENT_URL", ""),
}
# endpoint + payload key for each plain-language agent
AGENT_ENDPOINT = {
    "personal": ("/ask", "message"),
    "calendar": ("/ask", "message"),
    "amazon":   ("/ask", "message"),
    "coinbase": ("/ask", "message"),
    "email":    ("/process-inbox", None),
}

async def delegate(agent: str, instruction: str):
    url = AGENTS.get(agent)
    if not url:
        return {"error": f"Agent '{agent}' not deployed yet. Add its URL to Jarvis's .env."}
    path, key = AGENT_ENDPOINT.get(agent, ("/ask", "message"))
    headers = {"x-api-key": API_KEY}
    async with httpx.AsyncClient(timeout=90) as hc:
        try:
            if key:
                r = await hc.post(url + path, headers=headers, json={key: instruction})
            else:
                r = await hc.post(url + path, headers=headers)
            return r.json()
        except Exception as e:
            return {"error": str(e)}

TOOLS = [
    {"name": "delegate", "description": "Hand a task to a specialist agent and get its result.",
     "input_schema": {"type": "object", "properties": {
         "agent": {"type": "string",
                   "enum": ["personal", "call", "message", "email", "calendar", "amazon", "coinbase"]},
         "instruction": {"type": "string"}},
      "required": ["agent", "instruction"]}},
]

def system_prompt():
    now = datetime.datetime.now().astimezone().isoformat()
    deployed = [a for a, u in AGENTS.items() if u] or ["(none deployed yet)"]
    return (f"You are Jarvis, chief of staff for {OWNER}. Now: {now}.\n"
            f"You command a team of specialist agents. Deployed: {', '.join(deployed)}.\n"
            "Pick the right agent and use the delegate tool. For money matters (coinbase, amazon) you "
            "NEVER authorize a purchase or trade yourself — you bring the boss the info or the prepared "
            "order and he approves it. Be brief, reply in the boss's language (Spanish by default), and "
            "never invent a result. If an agent isn't deployed, say so.")

conversations: dict = {}

async def run(session: str, message: str) -> str:
    history = conversations.setdefault(session, [])
    history.append({"role": "user", "content": message})
    history[:] = history[-30:]
    if history[0]["role"] != "user":
        history.pop(0)
    for _ in range(10):
        r = client.messages.create(model=MODEL, max_tokens=1500,
                                   system=system_prompt(), tools=TOOLS, messages=history)
        if r.stop_reason != "tool_use":
            text = "".join(b.text for b in r.content if b.type == "text")
            history.append({"role": "assistant", "content": r.content})
            return text
        history.append({"role": "assistant", "content": [b for b in r.content if b.type != "thinking"]})
        results = []
        for b in r.content:
            if b.type == "tool_use":
                out = await delegate(**b.input)
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": json.dumps(out, default=str, ensure_ascii=False)[:15000]})
        history.append({"role": "user", "content": results})
    return "Me enrede con demasiados pasos. Repitemelo mas simple?"

class Chat(BaseModel):
    message: str
    session: str = "default"

@app.post("/chat")
async def chat(req: Chat, x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(401, "Bad API key")
    return {"reply": await run(req.session, req.message)}

@app.post("/telegram")
async def telegram(request: Request):
    update = await request.json()
    msg = update.get("message") or update.get("edited_message") or {}
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = msg.get("text", "")
    if not chat_id or not text:
        return {"ok": True}
    owner = os.getenv("TELEGRAM_OWNER_ID", "")
    if owner and chat_id != owner:
        return {"ok": True}
    reply = await run(f"tg:{chat_id}", text)
    async with httpx.AsyncClient(timeout=30) as hc:
        await hc.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      json={"chat_id": chat_id, "text": reply})
    return {"ok": True}

@app.get("/")
async def health():
    return {"jarvis": "online", "agents": {a: bool(u) for a, u in AGENTS.items()}}
