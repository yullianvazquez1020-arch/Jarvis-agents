"""Shared setup for the desktop adapter tests. No network, no real AI, no real money."""
import json
import re
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import test_jarvis as base
j = base.j
if getattr(j._desktop, "STUB", False):          # 4.0.5: main loads the module only when enabled; load it once here
    j._desktop, j.DESKTOP_STATUS = j._desktop_load("true")
D = j._desktop


class NoNetwork:
    def __init__(self, *a, **k):
        raise AssertionError("a test tried to open a network connection")


def ai_text(text):
    return MagicMock(content=[MagicMock(type="text", text=text)], stop_reason="end_turn")


def ai_tool(name, args, tid="t1"):
    block = MagicMock(type="tool_use", input=args, id=tid)
    block.name = name   # MagicMock(name=...) would name the mock itself
    return MagicMock(content=[block], stop_reason="tool_use")


class DesktopBase(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = Path(tempfile.mkdtemp()); j.USE_REDIS = False
        j._fence.update(mode="off", leader=True); j._seen_updates.clear(); j._rate_hits.clear(); j.conversations.clear()
        D._rate.clear(); D._running.clear()
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(j.httpx, "AsyncClient", NoNetwork))
        self.stack.enter_context(patch.object(D, "ENABLED", True))
        self.sent = []
        async def tg_send(chat_id, text):
            self.sent.append(str(text))
        self.stack.enter_context(patch.object(j, "_tg_send", new=tg_send))
        from fastapi.testclient import TestClient
        self.client = TestClient(j.app)

    # --- helpers ---------------------------------------------------------------
    def pair(self, name="MacBook 2015"):
        r = self.client.post("/desktop/v1/pair/start", json={"device_name": name}).json()
        msg = D.pairing_approve(r["code"]); self.assertIn("Aprobé", msg)
        c = self.client.post("/desktop/v1/pair/claim", json={"pairing_id": r["pairing_id"],
                                                             "claim_secret": r["claim_secret"]}).json()
        self.assertEqual(c["status"], "approved")
        return c["token"], c["device_id"]

    def hdr(self, token):
        return {"Authorization": f"Bearer {token}"}

    def turn(self, token, text, rid="req-00000001"):
        return self.client.post("/desktop/v1/turns", headers=self.hdr(token), json={"request_id": rid, "text": text})

    def ai(self, *responses):
        """Patch the scoped model call; returns the list of calls (history, tools)."""
        calls = []; seq = list(responses)
        async def fake(history, tools, extra_system):
            calls.append({"history": json.loads(json.dumps(history, default=str)), "tools": [t["name"] for t in tools],
                          "system": extra_system})
            return seq.pop(0) if seq else ai_text("listo")
        self.stack.enter_context(patch.object(j, "AI_READY", True))
        self.stack.enter_context(patch.object(j, "_ai_call_scoped", new=fake))
        self.stack.enter_context(patch.object(j, "_ai_call", new=AsyncMock(side_effect=AssertionError("unscoped call"))))
        return calls
