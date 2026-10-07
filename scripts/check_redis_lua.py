"""Run Jarvis's real Lua scripts (taken from main.py) against a real Redis, without touching Jarvis data.

Why: the Telegram queue and write protection depend on Redis EVAL. Unit tests use a simulated Redis; this
script proves the exact scripts work on the real server before (or right after) a deploy.

Upstash (from your Mac, nothing installed; Python 3 standard library only):
    export UPSTASH_REDIS_REST_URL='https://....upstash.io'
    export UPSTASH_REDIS_REST_TOKEN='...'          # paste it; it is never printed
    python3 scripts/check_redis_lua.py

It only uses temporary keys "jarvis:selftest:<random>:*" (expire in 5 minutes, deleted at the end).
It never reads or writes jarvis:leader, the real queue or any business data. It costs ~25 Upstash commands.
"""
import ast
import json
import os
import sys
import urllib.request
import uuid
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "main.py"
NAMES = ("_ENQUEUE", "_CLAIM_JOB", "_FENCED_SET", "_TG_QUEUED_PREFIX", "_TAKE_LEADER")


def load_scripts(main_path=MAIN):
    """Read the script strings and _tg_job_json from main.py without importing it (no dependencies needed)."""
    tree = ast.parse(Path(main_path).read_text(encoding="utf-8"))
    found, ns = {}, {"json": json}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in NAMES and isinstance(node.value, ast.Constant):
                found[name] = node.value.value
        if isinstance(node, ast.FunctionDef) and node.name == "_tg_job_json":
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(main_path), "exec"), ns)
    missing = [n for n in NAMES if n not in found] + ([] if "_tg_job_json" in ns else ["_tg_job_json"])
    if missing:
        raise RuntimeError("main.py is missing " + ", ".join(missing))
    found["_tg_job_json"] = ns["_tg_job_json"]
    return found


TRICKY = ('cobré $200 a "Ana" ñ 😀 \\ backslash\nnueva línea y texto falso {"state": "queued", '
          '"started": "x"}')


def run_checks(call, s=None):
    """call(cmd_list) -> Redis reply. Returns [(check, ok, detail)]. Uses only temporary keys."""
    s = s or load_scripts()
    ns = f"jarvis:selftest:{uuid.uuid4().hex[:12]}:"
    leader, upd, job, other_job, data = ns + "leader", ns + "upd:1", ns + "job:1", ns + "job:2", ns + "data"
    me, intruder = "instance-new", "instance-old"
    out = []

    def check(name, cond, detail=""):
        out.append((name, bool(cond), detail))

    try:
        check("no Lua script uses optional libraries (cjson, cmsgpack, struct, bit)",
              not any(lib + "." in s[n] for lib in ("cjson", "cmsgpack", "struct", "bit")
                       for n in ("_ENQUEUE", "_CLAIM_JOB", "_FENCED_SET", "_TAKE_LEADER")))
        call(["SET", leader, me, "EX", "300"])
        msg = {"chat": {"id": 1, "type": "private"}, "from": {"id": 1}, "text": TRICKY}
        raw = s["_tg_job_json"]({"id": 1, "msg": msg, "state": "queued", "at": "2026-10-06T18:00:00-04:00"})
        check("queued job starts with the expected prefix", raw.startswith(s["_TG_QUEUED_PREFIX"]))

        r = call(["EVAL", s["_ENQUEUE"], "3", upd, job, leader, raw, "300", "1", intruder])
        check("old instance cannot enqueue (FENCED)", r == "FENCED" and call(["GET", job]) is None, repr(r))
        r1 = call(["EVAL", s["_ENQUEUE"], "3", upd, job, leader, raw, "300", "1", me])
        r2 = call(["EVAL", s["_ENQUEUE"], "3", upd, job, leader, raw, "300", "1", me])
        check("first delivery is queued (NEW)", r1 == "NEW", repr(r1))
        check("Telegram retry of the same update is ignored (DUP)", r2 == "DUP", repr(r2))
        check("the stored job is byte-identical", call(["GET", job]) == raw)

        claim = ["EVAL", s["_CLAIM_JOB"], "2", leader, job]
        r = call(claim + [intruder, "2026-10-06T18:00:05-04:00", "300", s["_TG_QUEUED_PREFIX"]])
        check("old instance cannot claim (FENCED) and the job stays queued",
              r == "FENCED" and call(["GET", job]) == raw, repr(r))

        r = call(claim + [me, "2026-10-06T18:00:05-04:00", "300", s["_TG_QUEUED_PREFIX"]])
        try:
            claimed = json.loads(r)
        except Exception:
            claimed = None
        check("claim returns valid JSON in state running", claimed and claimed.get("state") == "running"
              and claimed.get("started") == "2026-10-06T18:00:05-04:00", repr(r)[:120])
        check("message text survives the claim unchanged (quotes, ñ, emoji, \\n, fake prefix)",
              claimed and claimed.get("msg") == msg and claimed.get("id") == 1)
        check("claimed job is saved as running", json.loads(call(["GET", job]) or "{}").get("state") == "running")
        ttl = call(["TTL", job])
        check("claimed job keeps an expiry", isinstance(ttl, int) and 0 < ttl <= 300, repr(ttl))

        r = call(claim + [me, "2026-10-06T18:00:09-04:00", "300", s["_TG_QUEUED_PREFIX"]])
        check("a second claim gets nothing (never runs twice)", r in ("", None), repr(r))

        legacy = json.dumps({"id": 2, "msg": msg, "state": "queued", "at": "x"}, ensure_ascii=False)
        call(["SET", other_job, legacy, "EX", "300"])
        r = call(["EVAL", s["_CLAIM_JOB"], "2", leader, other_job, me, "2026-10-06T18:00:10-04:00", "300",
                  s["_TG_QUEUED_PREFIX"]])
        check("unknown job format is refused (BADFORMAT) and left untouched",
              r == "BADFORMAT" and call(["GET", other_job]) == legacy, repr(r))

        # 4.0.5 (1.8): two processes take over; only the LAST one can write afterwards
        a = call(["EVAL", s["_TAKE_LEADER"], "1", leader, "boot-a"])
        b = call(["EVAL", s["_TAKE_LEADER"], "1", leader, "boot-b"])
        wa = call(["EVAL", s["_FENCED_SET"], "1", leader, "boot-a", data, '{"by": "a"}'])
        wb = call(["EVAL", s["_FENCED_SET"], "1", leader, "boot-b", data, '{"by": "b"}'])
        check("atomic take-over: last leader writes, the previous one is fenced",
              a == "OK" and b == "OK" and wa == "FENCED" and wb == "OK" and call(["GET", data]) == '{"by": "b"}',
              f"{a!r} {b!r} {wa!r} {wb!r}")
        call(["SET", leader, me, "EX", "300"])
        w = call(["EVAL", s["_FENCED_SET"], "1", leader, me, data, '{"ok": 1}'])
        f = call(["EVAL", s["_FENCED_SET"], "1", leader, intruder, data, '{"ok": 0}'])
        check("fenced write: active instance writes, old one is refused",
              w == "OK" and f == "FENCED" and call(["GET", data]) == '{"ok": 1}', f"{w!r} {f!r}")
    except Exception as exc:
        check("Redis accepted every command", False, f"{type(exc).__name__}: {str(exc)[:160]}")
    finally:
        for k in (leader, upd, job, other_job, data):
            try:
                call(["DEL", k])
            except Exception:
                pass
    return out


def upstash_call():
    url = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
    if not url.startswith("https://") or not token:
        raise SystemExit("Define UPSTASH_REDIS_REST_URL (https://...) and UPSTASH_REDIS_REST_TOKEN first.")

    def call(cmd):
        req = urllib.request.Request(url, data=json.dumps(cmd).encode(), method="POST",
                                     headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read())
        except urllib.error.HTTPError as e:   # never echo the token or the request
            body = json.loads(e.read() or b"{}")
        if "error" in body:
            raise RuntimeError(str(body["error"])[:160])
        return body.get("result")
    return call


def main():
    results = run_checks(upstash_call())
    for name, ok, detail in results:
        print(("✅ " if ok else "❌ ") + name + (f"  [{detail}]" if detail and not ok else ""))
    bad = [r for r in results if not r[1]]
    print("\nTODO BIEN: Upstash ejecuta los scripts de Jarvis." if not bad else
          f"\n{len(bad)} comprobación(es) fallaron. NO despliegues 4.0.2 todavía.")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
