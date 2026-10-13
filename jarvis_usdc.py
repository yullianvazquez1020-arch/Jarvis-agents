"""Jarvis: verificación SOLO LECTURA de pagos USDC y créditos de uso prepagados (BORRADOR).

Reglas fijas: este módulo nunca envía, cobra, reembolsa ni mueve dinero. Solo verifica firmas
de webhooks entrantes (Coinbase Commerce / Stripe) y registra créditos de uso consumibles.
Los cobros siguen bajo los topes $100/op y $300/día con /aprobar + /confirmar (fuera de aquí).
Secretos solo por variables de entorno; nunca se registran en logs.
Variables: USDC_PROVIDER (coinbase|stripe), COINBASE_COMMERCE_WEBHOOK_SECRET,
STRIPE_WEBHOOK_SECRET, USDC_WEBHOOK_TOLERANCE_S (300), CREDITS_EXPIRY_DAYS (365).
"""
import datetime as dt
import hashlib
import hmac
import json
import os
import time

CREDIT_TERMS = ("Los créditos Jarvis son de uso exclusivo para servicios de Jarvis/ISLAFIX, "
                "no son inversión, no generan ganancia, no son transferibles ni revendibles, "
                "no se canjean por dinero y vencen a los {days} días.")
CONFIRMED = {"coinbase": {"charge:confirmed", "charge:resolved"},
             "stripe": {"payment_intent.succeeded", "checkout.session.completed"}}


class VerificationError(Exception):
    pass


def _secret(name):
    value = os.environ.get(name, "")
    if not value:
        raise VerificationError(f"falta {name}")
    return value.encode()


def verify_coinbase(raw_body: bytes, signature: str) -> dict:
    expected = hmac.new(_secret("COINBASE_COMMERCE_WEBHOOK_SECRET"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, (signature or "").strip()):
        raise VerificationError("firma inválida")
    return json.loads(raw_body)


def verify_stripe(raw_body: bytes, header: str, now=None) -> dict:
    parts = dict(p.split("=", 1) for p in (header or "").split(",") if "=" in p)
    ts, sig = parts.get("t", ""), parts.get("v1", "")
    if not ts.isdigit():
        raise VerificationError("cabecera inválida")
    tol = int(os.environ.get("USDC_WEBHOOK_TOLERANCE_S", "300"))
    if abs((now or time.time()) - int(ts)) > tol:
        raise VerificationError("evento vencido")
    expected = hmac.new(_secret("STRIPE_WEBHOOK_SECRET"), ts.encode() + b"." + raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise VerificationError("firma inválida")
    return json.loads(raw_body)


def payment_summary(provider: str, event: dict) -> dict:
    """Resumen de solo lectura para avisar a Yullian. No ejecuta nada."""
    etype = event.get("type") or event.get("event", {}).get("type", "")
    return {"provider": provider, "event_id": event.get("id") or event.get("event", {}).get("id"),
            "type": etype, "confirmed": etype in CONFIRMED.get(provider, set()), "action": "solo_aviso"}


class CreditLedger:
    """Créditos consumibles en memoria/dict. No hay retiro, transferencia ni reembolso en dinero."""

    def __init__(self, store=None, expiry_days=None):
        self.store = store if store is not None else {}
        self.expiry_days = expiry_days or int(os.environ.get("CREDITS_EXPIRY_DAYS", "365"))
        self.seen = set()

    def grant(self, customer, credits, event_id, today=None):
        if event_id in self.seen:
            return False                    # idempotente: webhook repetido no duplica
        if credits <= 0:
            raise ValueError("créditos deben ser positivos")
        self.seen.add(event_id)
        exp = (today or dt.date.today()) + dt.timedelta(days=self.expiry_days)
        self.store.setdefault(customer, []).append({"credits": credits, "expires": exp.isoformat()})
        return True

    def balance(self, customer, today=None):
        today = (today or dt.date.today()).isoformat()
        return sum(l["credits"] for l in self.store.get(customer, []) if l["expires"] >= today)

    def consume(self, customer, credits, today=None):
        if credits > self.balance(customer, today):
            raise ValueError("créditos insuficientes")
        t = (today or dt.date.today()).isoformat()
        for lot in sorted(self.store.get(customer, []), key=lambda l: l["expires"]):
            if lot["expires"] < t or credits == 0:
                continue
            used = min(lot["credits"], credits)
            lot["credits"] -= used
            credits -= used
        return self.balance(customer, today)

    def transfer(self, *_a, **_k):
        raise PermissionError("los créditos no son transferibles")

    def cash_out(self, *_a, **_k):
        raise PermissionError("los créditos no se canjean por dinero")
