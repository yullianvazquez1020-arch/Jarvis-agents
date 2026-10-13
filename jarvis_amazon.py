"""Amazon SP-API, solo lectura, para la cuenta propia del dueño.

Qué hace: inventario FBA (getInventorySummaries), pedidos sin datos personales
(getOrders, sin RDT, y además se descartan campos de comprador/dirección) y
precios (getPricing / getCompetitivePricing).

Qué NO hace, a propósito:
- Nada que gaste dinero (compras de inventario, envíos FBA, anuncios, tarifas).
  Eso requiere /aprobar + /confirmar del dueño con topes de $100 por operación
  y $300 por día, y no está implementado en este módulo.
- Ningún mensaje a clientes. Eso solo sale con /enviar N.
- Ningún cambio en listados ni precios (sin PUT/PATCH/POST a SP-API).

Apagado si falta cualquier variable SPAPI_*. Los secretos nunca se registran.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

LWA_URL = "https://api.amazon.com/auth/o2/token"
ENDPOINTS = {
    "na": "https://sellingpartnerapi-na.amazon.com",
    "eu": "https://sellingpartnerapi-eu.amazon.com",
    "fe": "https://sellingpartnerapi-fe.amazon.com",
}
REQUIRED = ("SPAPI_LWA_CLIENT_ID", "SPAPI_LWA_CLIENT_SECRET", "SPAPI_REFRESH_TOKEN",
            "SPAPI_SELLER_ID", "SPAPI_MARKETPLACE_ID")
# Campos que nunca salen de este módulo aunque Amazon los mande.
PII_KEYS = {"BuyerInfo", "BuyerEmail", "BuyerName", "ShippingAddress", "DefaultShipFromLocationAddress",
            "BuyerTaxInfo", "BuyerCounty", "BuyerTaxInformation"}
GASTO_MSG = ("Esta acción gasta dinero o contacta clientes y no está implementada. "
             "Gastos: /aprobar + /confirmar (tope $100/op, $300/día). Clientes: /enviar N.")
TIMEOUT = 20.0

_token: Dict[str, Any] = {"value": None, "exp": 0.0}


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def enabled() -> bool:
    return all(_env(n) for n in REQUIRED)


def missing() -> List[str]:
    return [n for n in REQUIRED if not _env(n)]


def _base() -> str:
    region = (_env("SPAPI_REGION") or "na").lower()
    if region not in ENDPOINTS:
        raise ValueError("SPAPI_REGION debe ser na, eu o fe")
    return ENDPOINTS[region]


def _strip_pii(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_pii(v) for k, v in obj.items() if k not in PII_KEYS}
    if isinstance(obj, list):
        return [_strip_pii(v) for v in obj]
    return obj


async def access_token(client: httpx.AsyncClient) -> str:
    if _token["value"] and time.time() < _token["exp"] - 60:
        return _token["value"]
    r = await client.post(LWA_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": _env("SPAPI_REFRESH_TOKEN"),
        "client_id": _env("SPAPI_LWA_CLIENT_ID"),
        "client_secret": _env("SPAPI_LWA_CLIENT_SECRET"),
    }, timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"LWA rechazó el token (HTTP {r.status_code})")
    data = r.json()
    _token["value"] = data["access_token"]
    _token["exp"] = time.time() + float(data.get("expires_in", 3600))
    return _token["value"]


async def _get(client: httpx.AsyncClient, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    tok = await access_token(client)
    r = await client.get(_base() + path, params=params,
                         headers={"x-amz-access-token": tok, "accept": "application/json"},
                         timeout=TIMEOUT)
    if r.status_code == 429:
        raise RuntimeError("Amazon limitó la frecuencia (429); intenta en un minuto")
    if r.status_code != 200:
        raise RuntimeError(f"SP-API respondió HTTP {r.status_code} en {path}")
    return _strip_pii(r.json())


async def inventario(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    mkt = _env("SPAPI_MARKETPLACE_ID")
    data = await _get(client, "/fba/inventory/v1/summaries", {
        "granularityType": "Marketplace", "granularityId": mkt, "marketplaceIds": mkt, "details": "false"})
    out = []
    for s in (data.get("payload") or {}).get("inventorySummaries", []):
        out.append({"sku": s.get("sellerSku"), "asin": s.get("asin"),
                    "nombre": s.get("productName"), "cantidad": s.get("totalQuantity")})
    return out


async def pedidos(client: httpx.AsyncClient, dias: int = 7) -> List[Dict[str, Any]]:
    desde = (datetime.now(timezone.utc) - timedelta(days=max(1, min(dias, 30)))).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = await _get(client, "/orders/v0/orders", {
        "MarketplaceIds": _env("SPAPI_MARKETPLACE_ID"), "CreatedAfter": desde})
    out = []
    for o in (data.get("payload") or {}).get("Orders", []):
        total = o.get("OrderTotal") or {}
        out.append({"id": o.get("AmazonOrderId"), "fecha": o.get("PurchaseDate"),
                    "estado": o.get("OrderStatus"), "total": total.get("Amount"),
                    "moneda": total.get("CurrencyCode"), "unidades": o.get("NumberOfItemsShipped", 0)
                    + o.get("NumberOfItemsUnshipped", 0)})
    return out


async def precios(client: httpx.AsyncClient, skus: List[str]) -> List[Dict[str, Any]]:
    skus = [s for s in skus if s][:20]
    if not skus:
        return []
    mkt = _env("SPAPI_MARKETPLACE_ID")
    propios = await _get(client, "/products/pricing/v0/price",
                         {"MarketplaceId": mkt, "ItemType": "Sku", "Skus": ",".join(skus)})
    out = []
    for item in propios.get("payload", []):
        prod = item.get("Product") or {}
        offers = prod.get("Offers") or []
        precio = (((offers[0] if offers else {}).get("BuyingPrice") or {}).get("ListingPrice") or {}).get("Amount")
        asin = ((prod.get("Identifiers") or {}).get("MarketplaceASIN") or {}).get("ASIN")
        out.append({"sku": item.get("SellerSKU"), "asin": asin, "mi_precio": precio, "competitivo": None})
    asins = [p["asin"] for p in out if p["asin"]]
    if asins:
        comp = await _get(client, "/products/pricing/v0/competitivePrice",
                          {"MarketplaceId": mkt, "ItemType": "Asin", "Asins": ",".join(asins)})
        by_asin = {}
        for item in comp.get("payload", []):
            cps = (((item.get("Product") or {}).get("CompetitivePricing") or {}).get("CompetitivePrices") or [])
            if cps:
                by_asin[item.get("ASIN")] = ((cps[0].get("Price") or {}).get("LandedPrice") or {}).get("Amount")
        for p in out:
            p["competitivo"] = by_asin.get(p["asin"])
    return out


def _fmt(sub: str, rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return f"Amazon {sub}: sin resultados."
    lines = [f"Amazon {sub} ({len(rows)}):"]
    for r in rows[:25]:
        lines.append("• " + " · ".join(f"{k}: {v}" for k, v in r.items() if v is not None))
    return "\n".join(lines)


async def command(text: str, client: Optional[httpx.AsyncClient] = None) -> str:
    """Texto de /amazon <inventario|pedidos [días]|precios SKU1,SKU2>. Solo lectura."""
    parts = text.strip().split()
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub in ("comprar", "anunciar", "ads", "enviar", "publicar", "precio", "mensaje"):
        return GASTO_MSG
    if sub not in ("inventario", "pedidos", "precios"):
        return "Uso: /amazon inventario | /amazon pedidos [días] | /amazon precios SKU1,SKU2"
    if not enabled():
        return "Amazon está apagado. Faltan en Render: " + ", ".join(missing())
    own = client is None
    client = client or httpx.AsyncClient()
    try:
        if sub == "inventario":
            return _fmt(sub, await inventario(client))
        if sub == "pedidos":
            dias = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 7
            return _fmt(sub, await pedidos(client, dias))
        skus = ",".join(parts[2:]).split(",") if len(parts) > 2 else []
        if not skus:
            return "Indica los SKU: /amazon precios SKU1,SKU2"
        return _fmt(sub, await precios(client, skus))
    except Exception as exc:  # nunca se filtra el token
        return f"Amazon no respondió: {type(exc).__name__}: {str(exc)[:160]}"
    finally:
        if own:
            await client.aclose()
