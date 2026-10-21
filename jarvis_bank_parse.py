"""Parsers de extractos bancarios (OFX/QFX y CSV) y sus helpers de normalización.

Extraído de main.py (extracción 2 ampliada) sin cambio de lógica: main.py
re-exporta todos estos nombres, así que sus llamadores no cambian.
Este módulo NO importa main (sin ciclos): solo biblioteca estándar.
"""
import datetime, math, re


def _norm_desc(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    # long numbers (account/card/reference) are masked to their last 4 digits
    s = re.sub(r"(?<!\d)\d{8,}(?!\d)", lambda m: "••" + m.group()[-4:], s)
    return s[:90]

def _bank_amount(v):
    """'$1,234.56' '(12.00)' '-12' '12.00-' 'CR 5' -> float. Blank -> None."""
    s = str("" if v is None else v).strip()
    if not s:
        return None
    neg = (s.startswith(("-", "(", "$-", "$(", "-$")) or s.endswith("-")
           or bool(re.search(r"\bDR\b", s, re.I)))
    s2 = re.sub(r"[^\d.,]", "", s)
    if not s2 or not re.search(r"\d", s2):
        return None
    if "," in s2 and "." in s2 and s2.rfind(",") > s2.rfind("."):
        s2 = s2.replace(".", "").replace(",", ".")   # 1.234,56 -> 1234.56
    elif "," in s2 and "." not in s2 and re.search(r",\d{2}$", s2):
        s2 = s2.replace(",", ".")                    # 12,50 -> 12.50
    else:
        s2 = s2.replace(",", "")                     # 1,234.56 -> 1234.56
    try:
        val = float(s2)
    except ValueError:
        return None
    if not math.isfinite(val): return None
    return -val if neg else val

def _bank_date(v):
    """US banks write month/day. Returns 'YYYY-MM-DD' or None."""
    s = str("" if v is None else v).strip()[:19]
    if not s:
        return None
    m = re.match(r"^(\d{4})(\d{2})(\d{2})", s)            # OFX 20261005120000[-4:AST]
    if m:
        try:
            return datetime.date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        except ValueError:
            return None
    for fmt in ("%b %d, %Y", "%B %d, %Y"):                 # "Oct 5, 2026" has spaces
        try: return datetime.datetime.strptime(s, fmt).date().isoformat()
        except ValueError: pass
    s = s.split(" ")[0].split("T")[0]
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y", "%d-%b-%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


# --- OFX / QFX ---------------------------------------------------------------
def _ofx_tag(block, tag):
    m = re.search(r"<" + tag + r">\s*([^<\r\n]*)", block, re.I)
    return m.group(1).strip() if m else ""

def parse_ofx(text):
    """-> list of statements: {last4, acct_type, balance, available, balance_date, tx:[...]}"""
    out = []
    parts = re.split(r"<(?:STMTRS|CCSTMTRS)>", text, flags=re.I)[1:]
    for p in parts:
        acct = _ofx_tag(p, "ACCTID"); atype = _ofx_tag(p, "ACCTTYPE") or ("CREDITCARD" if "CCACCTFROM" in p.upper() else "")
        txs = []
        for t in re.findall(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))", p, re.I | re.S):
            amt = _bank_amount(_ofx_tag(t, "TRNAMT")); dt = _bank_date(_ofx_tag(t, "DTPOSTED"))
            if amt is None or not dt:
                continue
            desc = " ".join(x for x in (_ofx_tag(t, "NAME"), _ofx_tag(t, "MEMO")) if x)
            txs.append({"date": dt, "amount": amt, "desc": _norm_desc(desc or _ofx_tag(t, "TRNTYPE")),
                        "fitid": _ofx_tag(t, "FITID")})
        led = re.search(r"<LEDGERBAL>(.*?)(?:</LEDGERBAL>|<AVAILBAL>|$)", p, re.I | re.S)
        av = re.search(r"<AVAILBAL>(.*?)(?:</AVAILBAL>|$)", p, re.I | re.S)
        out.append({"last4": re.sub(r"\D", "", acct)[-4:] or acct[-4:], "acct_type": atype.lower(),
                    "balance": _bank_amount(_ofx_tag(led.group(1), "BALAMT")) if led else None,
                    "available": _bank_amount(_ofx_tag(av.group(1), "BALAMT")) if av else None,
                    "balance_date": _bank_date(_ofx_tag(led.group(1), "DTASOF")) if led else None,
                    "tx": txs})
    return out

# --- CSV -----------------------------------------------------------------------
_COLS = {
    "date": ["posting date", "post date", "transaction date", "fecha de transacción", "fecha de transaccion",
             "fecha", "date", "posted"],
    "type": ["debit/credit", "credit/debit", "dr/cr", "cr/dr", "crédito/débito", "débito/crédito",
             "transaction type", "type", "tipo"],
    "debit": ["debit amount", "debit", "débito", "debito", "withdrawal", "withdrawals", "retiro", "retiros", "cargo", "cargos"],
    "credit": ["credit amount", "credit", "crédito", "credito", "deposit", "deposits", "depósito", "deposito", "depósitos", "abono"],
    "desc": ["description", "descripción", "descripcion", "payee", "detalle", "concepto", "memo", "transaction",
             "name", "nombre", "referencia"],
    "amount": ["amount", "monto", "cantidad", "importe", "valor"],
    "balance": ["running balance", "balance", "saldo"],
}

def _match_cols(header):
    """Exact header names win over 'contains' matches for every column."""
    h = [str(x or "").strip().lower() for x in header]
    found = {}
    for exact in (True, False):
        for key, names in _COLS.items():
            if key in found: continue
            for name in names:
                idx = next((i for i, c in enumerate(h) if i not in found.values()
                            and (c == name if exact else name in c)), None)
                if idx is not None: found[key] = idx; break
    # a "balance" header must not be mistaken for an amount
    if "amount" in found and "balance" in h[found["amount"]]: found.pop("amount")
    return found

def parse_csv(text):
    """-> one statement {tx, balance, balance_date} or raises ValueError with a clear reason."""
    import csv, io
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("el archivo está vacío")
    try:
        first = csv.Sniffer().sniff("\n".join(lines[:20]), delimiters=",;\t|").delimiter
    except csv.Error:
        first = ","
    rows, hdr_i, cols = [], None, {}
    for delim in [first] + [x for x in ",;\t|" if x != first]:   # sniffing can guess wrong
        rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delim))
        for i, r in enumerate(rows[:15]):      # some banks put a few info lines before the header
            c = _match_cols(r)
            if "date" in c and ("amount" in c or "debit" in c or "credit" in c):
                hdr_i, cols = i, c; break
        if hdr_i is not None:
            break
    if hdr_i is None:
        raise ValueError("no encontré columnas de fecha y monto (encabezados: " + ", ".join(rows[0][:8])[:120] + ")")
    pre = " ".join(" ".join(r) for r in rows[:hdr_i])
    m4 = re.search(r"(?:[*xX#•]{2,}|ending in|termina en)\s*(\d{4})\b", pre, re.I)
    txs = []
    for r in rows[hdr_i + 1:]:
        get = lambda k: r[cols[k]] if k in cols and cols[k] < len(r) else ""
        dt = _bank_date(get("date"))
        if not dt:
            continue
        if "amount" in cols:
            amt = _bank_amount(get("amount"))
            typ = get("type").strip().lower()
            if amt is not None and amt > 0 and typ and (typ in ("dr", "d", "-") or any(
                    w in typ for w in ("debit", "débito", "debito", "withdraw", "retiro", "cargo"))):
                amt = -amt
        else:
            dr = _bank_amount(get("debit")); cr = _bank_amount(get("credit"))
            amt = (abs(cr) if cr else 0.0) - (abs(dr) if dr else 0.0)
            if not dr and not cr:
                amt = None
        if amt is None or amt == 0:
            continue
        txs.append({"date": dt, "amount": round(amt, 2), "desc": _norm_desc(get("desc")),
                    "row_balance": _bank_amount(get("balance"))})
    if not txs:
        raise ValueError("encontré el encabezado pero ninguna fila con fecha y monto")
    # balance = balance column of the newest row (files can be newest-first or oldest-first)
    bal = None; bdate = None
    with_bal = [t for t in txs if t.get("row_balance") is not None]
    if with_bal:
        newest = max(t["date"] for t in with_bal)
        same = [t for t in with_bal if t["date"] == newest]
        if len(same) == 1:
            bal, bdate = same[0]["row_balance"], newest
        elif txs[0]["date"] != txs[-1]["date"]:
            asc = txs[0]["date"] < txs[-1]["date"]
            pick = same[-1] if asc else same[0]
            bal, bdate = pick["row_balance"], newest
    for t in txs:   # v4.0.1: keep the running balance as identity evidence (two equal coffees differ here)
        rb = t.pop("row_balance", None)
        if rb is not None: t["bal"] = round(rb, 2)
    warn = ("No pude saber el balance final: varias filas del mismo día sin orden claro."
            if with_bal and bal is None else "")
    if len(txs) >= 3 and all(t["amount"] > 0 for t in txs):
        warn = ("Todos los montos vinieron positivos (el archivo no marca qué es retiro). Revisa con /movimientos; "
                "si salió mal, bórralo y baja el archivo en formato QFX/OFX.")
    return {"last4": m4.group(1) if m4 else "", "acct_type": "", "balance": bal, "available": None,
            "balance_date": bdate, "tx": txs, "warning": warn}
