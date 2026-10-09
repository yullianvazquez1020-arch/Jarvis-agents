#!/usr/bin/env python3
"""WhatsApp solo hacia el número del dueño. No escribe a clientes.

No crea cuentas. El token se lee de WA_TOKEN y no se guarda ni se imprime.
Por defecto no hay red: hace falta --enviar, y esta prueba no lo usa.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import urllib.request

NUMBER = re.compile(r"\d{8,15}")
VERSION = re.compile(r"v\d+\.\d+")


def owner() -> str:
    number = os.environ.get("WA_OWNER_NUMBER", "").strip()
    if not NUMBER.fullmatch(number):
        raise ValueError("WA_OWNER_NUMBER")
    return number


def decide(to: str) -> str:
    try:
        mine = owner()
    except ValueError:
        return "config"
    if to != mine:
        return "clientes"
    return "dueno"


def payload(to: str, text: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text[:1000]},
    }


def audit(to: str, text: str, verdict: str) -> None:
    row = {
        "verdict": verdict,
        "to_hash": hashlib.sha256(to.encode()).hexdigest()[:12],
        "text_len": len(text),
        "text_hash": hashlib.sha256(text.encode()).hexdigest()[:12] if text else "",
    }
    print(json.dumps(row, ensure_ascii=False))


def uso_wa(to: str, text: str) -> bool:
    from agent_executor import control_dir

    key = hashlib.sha256(f"{to}\n{hashlib.sha256(text.encode()).hexdigest()}".encode()).hexdigest()[:16]
    path = control_dir() / "usos-wa.json"
    used: list[str] = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                used = [str(item) for item in loaded]
        except (OSError, ValueError):
            used = []
    if key in used:
        return False
    used.append(key)
    path.write_text(json.dumps(used), encoding="utf-8")
    return True


def enviar(to: str, text: str, *, confirmed: bool, dry: bool, sender=None) -> str:
    if decide(to) != "dueno":
        audit(to, text, "BLOQUEADO")
        return "BLOQUEADO"
    if not confirmed:
        audit(to, text, "CANCELADO")
        return "CANCELADO"
    body = payload(to, text)
    if dry:
        if sender is not None:
            sender(body)
        audit(to, text, "SECO")
        return "SECO"
    token = os.environ.get("WA_TOKEN", "")
    phone_id = os.environ.get("WA_PHONE_NUMBER_ID", "")
    version = os.environ.get("WA_GRAPH_VERSION", "v23.0")
    if not token or not NUMBER.fullmatch(phone_id) or not VERSION.fullmatch(version):
        audit(to, text, "FALTA")
        return "FALTA"
    if not uso_wa(to, text):
        audit(to, text, "BLOQUEADO")
        return "BLOQUEADO"
    url = f"https://graph.facebook.com/{version}/{phone_id}/messages"
    data = json.dumps(body).encode()
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    if sender is not None:
        sender(request)
    else:
        with urllib.request.urlopen(request, timeout=20) as response:
            response.read()
    audit(to, text, "HECHO")
    return "HECHO"


def firma_ok(body: bytes, header: str, secret: str) -> bool:
    if not header.startswith("sha256=") or not secret:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


def desafio(params: dict, token: str) -> str | None:
    mode = str(params.get("hub.mode") or "")
    verify = str(params.get("hub.verify_token") or "")
    if mode == "subscribe" and token and hmac.compare_digest(verify, token):
        return str(params.get("hub.challenge") or "")
    return None


def entrante(payload_in: dict, seen: set[str]) -> str:
    """No contesta a clientes. Repetir el mismo id no hace nada."""
    try:
        message = payload_in["entry"][0]["changes"][0]["value"]["messages"][0]
        message_id = str(message["id"])
        sender = str(message["from"])
    except (KeyError, IndexError, TypeError):
        return "IGNORADO"
    if message_id in seen:
        return "REPETIDO"
    seen.add(message_id)
    if decide(sender) != "dueno":
        return "CLIENTE"
    return "AVISAR"


def self_test() -> int:
    os.environ["WA_OWNER_NUMBER"] = "17875550199"
    calls = []
    assert decide("17875550100") == "clientes"
    assert enviar("17875550100", "no sales", confirmed=True, dry=True, sender=calls.append) == "BLOQUEADO"
    assert calls == []
    assert enviar("17875550199", "nota ficticia", confirmed=False, dry=True, sender=calls.append) == "CANCELADO"
    assert calls == []
    assert enviar("17875550199", "nota ficticia", confirmed=True, dry=True, sender=calls.append) == "SECO"
    assert calls[0]["to"] == "17875550199"
    assert "token" not in json.dumps(calls)
    secret = "secreto-de-prueba"
    body = b'{"object":"whatsapp_business_account"}'
    good = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert firma_ok(body, good, secret)
    assert not firma_ok(body, good, "otro")
    assert desafio({"hub.mode": "subscribe", "hub.verify_token": "abc", "hub.challenge": "1"}, "abc") == "1"
    assert desafio({"hub.mode": "subscribe", "hub.verify_token": "no", "hub.challenge": "1"}, "abc") is None
    seen: set[str] = set()
    incoming = {"entry": [{"changes": [{"value": {"messages": [{"id": "m1", "from": "17875550100"}]}}]}]}
    assert entrante(incoming, seen) == "CLIENTE"
    own = {"entry": [{"changes": [{"value": {"messages": [{"id": "m2", "from": "17875550199"}]}}]}]}
    assert entrante(own, seen) == "AVISAR"
    assert entrante(own, seen) == "REPETIDO"
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["JARVIS_CONTROL_DIR"] = tmp
        assert uso_wa("17875550199", "nota ficticia") is True
        assert uso_wa("17875550199", "nota ficticia") is False
        assert "nota ficticia" not in (control_dir_text := open(os.path.join(tmp, "usos-wa.json"), encoding="utf-8").read())
        del control_dir_text
    print("SELFTEST OK")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="WhatsApp solo al dueño. No escribe a clientes.")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--to", default="")
    parser.add_argument("--text", default="")
    parser.add_argument("--enviar", action="store_true")
    parser.add_argument("--confirmar", default="")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.to:
        print("Nada enviado. Hace falta --to y, para salir a la red, --enviar.")
        return 2
    confirmed = args.confirmar == "si"
    try:
        result = enviar(args.to, args.text, confirmed=confirmed, dry=not args.enviar)
    except ValueError:
        print("Falta WA_OWNER_NUMBER")
        return 2
    return 0 if result in {"SECO", "HECHO"} else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
