"""Jarvis Business Core: offline-first, standard-library operations, no automatic external actions.

DO NOT mount its API publicly without authentication and tenant isolation.
Pass a persistent SQLite path on the future VPS; Render ephemeral storage is not durable.
This module does NOT replace the existing Redis leadership/fencing controls.
"""
from __future__ import annotations
import datetime as dt
import json
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS contacts(
 id INTEGER PRIMARY KEY, tenant TEXT NOT NULL, name TEXT NOT NULL,
 email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tickets(
 id INTEGER PRIMARY KEY, tenant TEXT NOT NULL, contact_id INTEGER,
 channel TEXT NOT NULL, subject TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL,
 FOREIGN KEY(contact_id) REFERENCES contacts(id));
CREATE TABLE IF NOT EXISTS estimates(
 id INTEGER PRIMARY KEY, tenant TEXT NOT NULL, contact_id INTEGER,
 description TEXT NOT NULL, total_cents INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL,
 FOREIGN KEY(contact_id) REFERENCES contacts(id));
CREATE TABLE IF NOT EXISTS journal(
 id INTEGER PRIMARY KEY, tenant TEXT NOT NULL, reference TEXT NOT NULL,
 account TEXT NOT NULL, debit_cents INTEGER NOT NULL DEFAULT 0,
 credit_cents INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS approvals(
 id INTEGER PRIMARY KEY, tenant TEXT NOT NULL, action TEXT NOT NULL,
 payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 created_at TEXT NOT NULL, reviewed_at TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_tickets_tenant ON tickets(tenant,status);
CREATE INDEX IF NOT EXISTS ix_journal_tenant ON journal(tenant,reference);
CREATE INDEX IF NOT EXISTS ix_approvals_tenant ON approvals(tenant,status);
"""
ALLOWED_CHANNELS = frozenset(("phone", "email", "web", "whatsapp", "telegram", "in_person"))
SENSITIVE_ACTIONS = frozenset(("send_message", "place_call", "publish", "purchase", "charge",
                              "transfer", "refund", "sign_contract", "file_taxes",
                              "legal_advice", "financial_advice", "delete_data"))
def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def _cents(value):
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d < 0 or d.as_tuple().exponent < -2:
            raise ValueError("amount must be nonnegative and have at most 2 decimals")
        c = int(d * 100)
        if c > 10**12:
            raise ValueError("amount is too large")
        return c
    except (InvalidOperation, TypeError):
        raise ValueError("invalid monetary amount") from None

def _required(value, label, max_length=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"invalid {label}")
    return value.strip()

class BusinessCore:
    def __init__(self, path):
        path = Path(path)
        if str(path) == ":memory:":
            raise ValueError("persistent path required")
        if not path.parent.is_dir():
            raise ValueError("database directory does not exist")
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    def add_contact(self, tenant, name, email="", phone="", notes=""):
        tenant = _required(tenant, "tenant", 120)
        name = _required(name, "name", 200)
        with self.db:
            cur = self.db.execute(
                "INSERT INTO contacts(tenant,name,email,phone,notes,created_at) VALUES(?,?,?,?,?,?)",
                (tenant,name,email,phone,notes,_now()))
        return cur.lastrowid

    def add_ticket(self, tenant, subject, channel="web", detail="", contact_id=None):
        tenant = _required(tenant, "tenant", 120)
        subject = _required(subject, "subject", 300)
        if channel not in ALLOWED_CHANNELS:
            raise ValueError("unknown channel")
        if contact_id is not None and not self._owned_contact(tenant, contact_id):
            raise ValueError("contact not found in tenant")
        with self.db:
            cur = self.db.execute(
                "INSERT INTO tickets(tenant,contact_id,channel,subject,detail,created_at) VALUES(?,?,?,?,?,?)",
                (tenant,contact_id,channel,subject,detail,_now()))
        return cur.lastrowid

    def draft_estimate(self, tenant, description, total, contact_id=None):
        tenant = _required(tenant, "tenant", 120)
        description = _required(description, "description")
        if contact_id is not None and not self._owned_contact(tenant, contact_id):
            raise ValueError("contact not found in tenant")
        with self.db:
            cur = self.db.execute(
                "INSERT INTO estimates(tenant,contact_id,description,total_cents,created_at) VALUES(?,?,?,?,?)",
                (tenant,contact_id,description,_cents(total),_now()))
        return cur.lastrowid

    def post_journal(self, tenant, reference, lines):
        """Balanced, append-only double-entry journal. Never moves real money."""
        tenant = _required(tenant, "tenant", 120)
        reference = _required(reference, "reference", 120)
        if not isinstance(lines, list) or len(lines) < 2 or len(lines) > 100:
            raise ValueError("journal needs 2-100 entries")
        normalized = []
        for line in lines:
            if not isinstance(line, dict):
                raise ValueError("invalid journal entry")
            account = _required(line.get("account"), "account", 120)
            debit, credit = _cents(line.get("debit", 0)), _cents(line.get("credit", 0))
            if (debit == 0) == (credit == 0):
                raise ValueError("exactly one of debit or credit must be positive")
            normalized.append((tenant,reference,account,debit,credit,_now()))
        if sum(x[3] for x in normalized) != sum(x[4] for x in normalized):
            raise ValueError("journal does not balance")
        with self.db:
            if self.db.execute("SELECT 1 FROM journal WHERE tenant=? AND reference=? LIMIT 1",
                               (tenant, reference)).fetchone():
                raise ValueError("duplicate reference")
            self.db.executemany(
                "INSERT INTO journal(tenant,reference,account,debit_cents,credit_cents,created_at) VALUES(?,?,?,?,?,?)",
                normalized)
        return len(normalized)

    def propose_action(self, tenant, action, payload):
        """Records request ONLY. No provider invocation, message, charge, or payment."""
        tenant = _required(tenant, "tenant", 120)
        if action not in SENSITIVE_ACTIONS:
            raise ValueError("unsupported action")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        if len(serialized) > 10000:
            raise ValueError("payload too large")
        with self.db:
            cur = self.db.execute(
                "INSERT INTO approvals(tenant,action,payload,created_at) VALUES(?,?,?,?)",
                (tenant,action,serialized,_now()))
        return cur.lastrowid

    def review_action(self, tenant, approval_id, decision):
        """Approval is audit-only; execution must still use the owner's existing /confirmar gate."""
        tenant = _required(tenant, "tenant", 120)
        if decision not in ("approved", "rejected"):
            raise ValueError("invalid decision")
        with self.db:
            cur = self.db.execute(
                "UPDATE approvals SET status=?, reviewed_at=? WHERE tenant=? AND id=? AND status='pending'",
                (decision,_now(),tenant,approval_id))
        if cur.rowcount != 1:
            raise ValueError("pending request not found")
        return decision

    def overview(self, tenant):
        tenant = _required(tenant, "tenant", 120)
        def count(table, suffix="", args=()):
            return self.db.execute(
                f"SELECT COUNT(*) FROM {table} WHERE tenant=?" + suffix, (tenant,*args)).fetchone()[0]
        rows = self.db.execute(
            "SELECT account, SUM(debit_cents-credit_cents) balance_cents "
            "FROM journal WHERE tenant=? GROUP BY account ORDER BY account", (tenant,)).fetchall()
        return {"contacts":count("contacts"),"open_tickets":count("tickets"," AND status=?",("open",)),
                "draft_estimates":count("estimates"," AND status=?",("draft",)),
                "pending_approvals":count("approvals"," AND status=?",("pending",)),
                "ledger_balances_cents":{row["account"]:row["balance_cents"] for row in rows}}

    def _owned_contact(self, tenant, contact_id):
        return self.db.execute("SELECT 1 FROM contacts WHERE id=? AND tenant=?",
                               (contact_id,tenant)).fetchone() is not None
