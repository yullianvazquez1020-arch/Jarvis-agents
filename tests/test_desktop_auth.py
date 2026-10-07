"""Desktop adapter: off by default, pairing approved only in the owner's private Telegram chat, hashed tokens,
revocation and capabilities."""
import json
import unittest
from unittest.mock import patch

from desktop_helpers import DesktopBase, D, j


class Disabled(DesktopBase):
    def test_everything_404_when_disabled(self):
        with patch.object(D, "ENABLED", False):
            self.assertEqual(self.client.post("/desktop/v1/pair/start", json={}).status_code, 404)
            self.assertEqual(self.client.post("/desktop/v1/pair/claim", json={}).status_code, 404)
            self.assertEqual(self.client.get("/desktop/v1/status").status_code, 404)
            self.assertEqual(self.client.post("/desktop/v1/turns", json={}).status_code, 404)
            self.assertEqual(self.client.post("/desktop/v1/panel", json={"name": "cobros"}).status_code, 404)

    def test_default_is_off_and_telegram_unaffected(self):
        self.assertFalse(j.os.getenv("DESKTOP_API_ENABLED"))
        with patch.object(D, "ENABLED", False):
            self.assertIn("desktop_api", self.client.get("/").json())
            self.assertFalse(self.client.get("/").json()["desktop_api"]["enabled"])


class ConditionalImport(DesktopBase):
    """4.0.5 (1.1): a missing or broken jarvis_desktop_api.py never stops Jarvis from starting."""
    def test_variable_off_uses_stub_without_importing(self):
        with patch("builtins.__import__", side_effect=AssertionError("must not import")):
            mod, status = j._desktop_load("false")
        self.assertTrue(mod.STUB); self.assertFalse(mod.ENABLED); self.assertEqual(status, "apagado")
        mod.install(j)                                            # no-op

    def test_missing_module_uses_stub(self):
        import builtins
        real = builtins.__import__
        def fake(name, *a, **k):
            if name == "jarvis_desktop_api":
                raise ImportError("no module")
            return real(name, *a, **k)
        with patch("builtins.__import__", side_effect=fake):
            mod, status = j._desktop_load("true")
        self.assertTrue(mod.STUB); self.assertIn("módulo ausente", status)

    def test_broken_install_uses_stub(self):
        with patch.object(D, "install", side_effect=RuntimeError("boom")):
            mod, status = j._desktop_load("true")
        self.assertTrue(mod.STUB); self.assertIn("RuntimeError", status)

    def test_health_and_diagnostics_report_status(self):
        with patch.object(j, "DESKTOP_STATUS", "módulo ausente (falta jarvis_desktop_api.py)"), \
             patch.object(j, "_desktop", j._desktop_stub()):
            h = self.client.get("/").json()["desktop_api"]
            self.assertEqual((h["enabled"], h["status"][:14]), (False, "módulo ausente"))
            self.assertIn("módulo ausente", j.asyncio.run(j.diagnostics_text()))


class Pairing(DesktopBase):
    def test_full_pairing_token_shown_once(self):
        r = self.client.post("/desktop/v1/pair/start", json={"device_name": "Mac <b>1</b>"}).json()
        claim = {"pairing_id": r["pairing_id"], "claim_secret": r["claim_secret"]}
        self.assertEqual(self.client.post("/desktop/v1/pair/claim", json=claim).json()["status"], "pending")
        self.assertIn("No aprobé", D.pairing_approve("000000" if r["code"] != "000000" else "111111"))
        self.assertEqual(self.client.post("/desktop/v1/pair/claim", json=claim).json()["status"], "pending")
        D.pairing_approve(r["code"])
        c = self.client.post("/desktop/v1/pair/claim", json=claim).json()
        self.assertTrue(c["token"].startswith("jd1."))
        self.assertEqual(self.client.post("/desktop/v1/pair/claim", json=claim).status_code, 404)   # only once
        stored = json.dumps(j.kv_get(D.KEY, {}))
        self.assertNotIn(c["token"].split(".")[2], stored)            # only the hash is stored
        self.assertEqual(self.client.get("/desktop/v1/status", headers=self.hdr(c["token"])).status_code, 200)

    def test_wrong_claim_secret_and_expired(self):
        r = self.client.post("/desktop/v1/pair/start", json={}).json()
        D.pairing_approve(r["code"])
        bad = self.client.post("/desktop/v1/pair/claim", json={"pairing_id": r["pairing_id"], "claim_secret": "x" * 32})
        self.assertEqual(bad.status_code, 404)
        with j._data_lock:
            d = D.load(); d["pairings"][r["pairing_id"]]["created"] = "2000-01-01T00:00:00-04:00"; D.save(d)
        ok = self.client.post("/desktop/v1/pair/claim", json={"pairing_id": r["pairing_id"],
                                                              "claim_secret": r["claim_secret"]})
        self.assertEqual(ok.status_code, 404)

    def test_pending_limit_and_wrong_code_lockout(self):
        for _ in range(3):
            self.assertEqual(self.client.post("/desktop/v1/pair/start", json={}).status_code, 200)
        self.assertEqual(self.client.post("/desktop/v1/pair/start", json={}).status_code, 429)
        for _ in range(5):
            D.pairing_approve("999999")
        self.assertEqual(D.load()["pairings"], {})                   # cleared after 5 wrong codes
        self.assertIn("Demasiados", D.pairing_approve("123456"))

    def test_emparejar_only_in_owner_private_chat(self):
        r = self.client.post("/desktop/v1/pair/start", json={}).json()
        j.TG_SECRET = "sec"; h = {"x-telegram-bot-api-secret-token": "sec"}
        def tg(text, uid, chat_type="private", user=123):
            return {"update_id": uid, "message": {"chat": {"id": 123, "type": chat_type}, "from": {"id": user}, "text": text}}
        self.client.post("/telegram", headers=h, json=tg(f"/emparejar {r['code']}", 701, user=999))   # stranger
        self.client.post("/telegram", headers=h, json=tg(f"/emparejar {r['code']}", 702, chat_type="group"))
        self.assertEqual(D.load()["pairings"][r["pairing_id"]]["status"], "pending")
        self.client.post("/telegram", headers=h, json=tg(f"/emparejar {r['code']}", 703))
        self.assertEqual(D.load()["pairings"][r["pairing_id"]]["status"], "approved")
        self.assertTrue(any("Aprobé" in s for s in self.sent))


class Tokens(DesktopBase):
    def test_bad_tokens_and_master_key_rejected(self):
        token, dev = self.pair()
        for bad in (None, "", "Bearer", "Bearer " + j.API_KEY, "Bearer jd1.1.short", f"Bearer jd1.{dev}." + "A" * 43,
                    f"Bearer jd1.99.{token.split('.')[2]}"):
            hdr = {} if bad is None else {"Authorization": bad}
            self.assertEqual(self.client.get("/desktop/v1/status", headers=hdr).status_code, 401, bad)

    def test_revoked_device_stops_working(self):
        token, dev = self.pair()
        self.assertIn("Revoqué", D.devices_text(f"revocar {dev}"))
        self.assertEqual(self.client.get("/desktop/v1/status", headers=self.hdr(token)).status_code, 401)
        self.assertIn("revocado", D.devices_text())

    def test_capabilities_enforced(self):
        token, dev = self.pair()
        with j._data_lock:
            d = D.load(); d["devices"][dev]["caps"] = ["read"]; D.save(d)
        self.assertEqual(self.turn(token, "hola").status_code, 403)
        self.assertEqual(self.client.post("/desktop/v1/panel", headers=self.hdr(token),
                                          json={"name": "agenda"}).status_code, 200)

    def test_status_never_leaks_secrets(self):
        token, _ = self.pair()
        body = self.client.get("/desktop/v1/status", headers=self.hdr(token)).text
        for secret in (j.API_KEY, token):
            self.assertNotIn(secret, body)


class Expiry(DesktopBase):
    """4.0.5 (2.2): tokens expire after 90 days; renewing = pairing again in the private chat."""
    def age(self, dev, days):
        with j._data_lock:
            d = D.load(); x = d["devices"][dev]
            x["created"] = (j._now() - j.datetime.timedelta(days=days)).isoformat(timespec="seconds")
            x["expires"] = (j._now() - j.datetime.timedelta(days=days - D.TOKEN_DAYS)).isoformat(timespec="seconds")
            D.save(d)

    def test_expired_token_refused_and_listed(self):
        token, dev = self.pair()
        self.assertEqual(self.client.get("/desktop/v1/status", headers=self.hdr(token)).status_code, 200)
        self.age(dev, 91)
        r = self.client.get("/desktop/v1/status", headers=self.hdr(token))
        self.assertEqual(r.status_code, 401); self.assertIn("venció", r.json()["detail"])
        listing = D.devices_text()
        for word in ("VENCIDO", "alta", "último uso", "vence"):
            self.assertIn(word, listing)

    def test_new_token_lasts_90_days(self):
        _, dev = self.pair()
        exp = j.datetime.datetime.fromisoformat(D.load()["devices"][dev]["expires"])
        self.assertAlmostEqual((exp - j._now()).days, 89, delta=1)

    def test_pairing_again_renews_and_kills_old_token(self):
        old, dev1 = self.pair("Mac oficina")
        new, dev2 = self.pair("Mac oficina")
        self.assertEqual(self.client.get("/desktop/v1/status", headers=self.hdr(old)).status_code, 401)
        self.assertEqual(self.client.get("/desktop/v1/status", headers=self.hdr(new)).status_code, 200)
        self.assertEqual(D.load()["devices"][dev1]["replaced_by"], dev2)

    def test_legacy_device_without_expiry_uses_creation_date(self):
        token, dev = self.pair()
        with j._data_lock:
            d = D.load(); x = d["devices"][dev]; x.pop("expires")
            x["created"] = (j._now() - j.datetime.timedelta(days=100)).isoformat(timespec="seconds"); D.save(d)
        self.assertEqual(self.client.get("/desktop/v1/status", headers=self.hdr(token)).status_code, 401)


class Audit(DesktopBase):
    """4.0.5 (2.3): every request leaves device, time, endpoint and result; never text or amounts."""
    def test_audit_without_content(self):
        token, dev = self.pair()
        self.ai()
        j.add_client("Ana")
        self.turn(token, "muéstrame los cobros")
        self.turn(token, "confirma 123456", rid="req-00000002")
        self.client.get("/desktop/v1/status", headers={"Authorization": "Bearer jd1.99." + "x" * 43})
        a = j.kv_get(D.AUDIT_KEY, [])
        self.assertTrue({"pair/start", "pair/claim", "turns"} <= {x["endpoint"] for x in a})
        self.assertIn({"device": dev, "endpoint": "turns", "result": 200, "kind": "panel"},
                      [{k: x[k] for k in ("device", "endpoint", "result", "kind")} for x in a])
        self.assertIn(401, [x["result"] for x in a if x["device"] == "99"])
        raw = json.dumps(a, ensure_ascii=False)
        for secret in ("123456", "cobros", "Ana", token):
            self.assertNotIn(secret, raw)
        self.assertIn("Últimos accesos", D.devices_text())

    def test_audit_is_bounded(self):
        with patch.object(D, "AUDIT_KEEP", 3):
            for i in range(5):
                D.audit("1", f"e{i}", 200)
        self.assertEqual([x["endpoint"] for x in j.kv_get(D.AUDIT_KEY, [])], ["e2", "e3", "e4"])


if __name__ == "__main__":
    unittest.main()
