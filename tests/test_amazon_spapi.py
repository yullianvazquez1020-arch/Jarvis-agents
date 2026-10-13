"""Pruebas de jarvis_amazon con datos ficticios y transporte simulado (sin red)."""
import ast
import asyncio
import os
import unittest
from pathlib import Path
from unittest import mock

import httpx

import jarvis_amazon as amz

ROOT = Path(__file__).resolve().parents[1]
ENV = {"SPAPI_LWA_CLIENT_ID": "amzn1.application-oa2-client.FICTICIO", "SPAPI_LWA_CLIENT_SECRET": "secreto-ficticio",
       "SPAPI_REFRESH_TOKEN": "Atzr|ficticio", "SPAPI_SELLER_ID": "A1FICTICIO", "SPAPI_MARKETPLACE_ID": "ATVPDKIKX0DER",
       "SPAPI_REGION": "na"}


def handler(calls):
    def h(req: httpx.Request):
        calls.append(req)
        u = str(req.url)
        if u.startswith(amz.LWA_URL):
            return httpx.Response(200, json={"access_token": "Atza|ficticio", "expires_in": 3600})
        assert req.headers.get("x-amz-access-token") == "Atza|ficticio"
        if "/fba/inventory/v1/summaries" in u:
            return httpx.Response(200, json={"payload": {"inventorySummaries": [
                {"sellerSku": "ISLA-001", "asin": "B0FICTICIO", "productName": "Soporte ficticio", "totalQuantity": 12}]}})
        if "/orders/v0/orders" in u:
            return httpx.Response(200, json={"payload": {"Orders": [
                {"AmazonOrderId": "111-0000000-0000000", "PurchaseDate": "2026-10-10T12:00:00Z", "OrderStatus": "Shipped",
                 "OrderTotal": {"Amount": "19.99", "CurrencyCode": "USD"}, "NumberOfItemsShipped": 1,
                 "BuyerInfo": {"BuyerEmail": "x@ficticio.test"}, "ShippingAddress": {"City": "San Juan"}}]}})
        if "/products/pricing/v0/price" in u:
            return httpx.Response(200, json={"payload": [{"SellerSKU": "ISLA-001", "Product": {
                "Identifiers": {"MarketplaceASIN": {"ASIN": "B0FICTICIO"}},
                "Offers": [{"BuyingPrice": {"ListingPrice": {"Amount": 24.5}}}]}}]})
        if "/products/pricing/v0/competitivePrice" in u:
            return httpx.Response(200, json={"payload": [{"ASIN": "B0FICTICIO", "Product": {"CompetitivePricing": {
                "CompetitivePrices": [{"Price": {"LandedPrice": {"Amount": 22.0}}}]}}}]})
        return httpx.Response(404)
    return h


def run(text, calls=None):
    calls = [] if calls is None else calls
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler(calls))) as c:
            return await amz.command(text, c)
    return asyncio.run(go())


class AmazonTests(unittest.TestCase):
    def setUp(self):
        amz._token.update(value=None, exp=0.0)

    def test_apagado_sin_variables(self):
        with mock.patch.dict(os.environ, {k: "" for k in ENV}):
            self.assertFalse(amz.enabled())
            out = run("/amazon inventario")
            self.assertIn("apagado", out)
            self.assertIn("SPAPI_REFRESH_TOKEN", out)

    def test_inventario(self):
        with mock.patch.dict(os.environ, ENV):
            calls = []
            out = run("/amazon inventario", calls)
            self.assertIn("ISLA-001", out)
            self.assertIn("12", out)
            self.assertTrue(all(c.method in ("GET", "POST") for c in calls))
            self.assertEqual([c.method for c in calls if c.method == "POST"], ["POST"])  # solo LWA

    def test_pedidos_sin_pii(self):
        with mock.patch.dict(os.environ, ENV):
            out = run("/amazon pedidos 3")
            self.assertIn("111-0000000-0000000", out)
            self.assertNotIn("ficticio.test", out)
            self.assertNotIn("San Juan", out)

    def test_precios(self):
        with mock.patch.dict(os.environ, ENV):
            out = run("/amazon precios ISLA-001")
            self.assertIn("24.5", out)
            self.assertIn("22.0", out)

    def test_token_se_reusa(self):
        with mock.patch.dict(os.environ, ENV):
            calls = []
            run("/amazon inventario", calls)
            run("/amazon inventario", calls)
            self.assertEqual(sum(1 for c in calls if str(c.url).startswith(amz.LWA_URL)), 1)

    def test_lwa_falla_sin_filtrar_secretos(self):
        def h(req):
            return httpx.Response(400, json={"error": "invalid_grant"})
        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(h)) as c:
                return await amz.command("/amazon inventario", c)
        with mock.patch.dict(os.environ, ENV):
            out = asyncio.run(go())
        self.assertIn("HTTP 400", out)
        for v in ENV.values():
            if "ficticio" in v.lower():
                self.assertNotIn(v, out)

    def test_acciones_de_gasto_no_existen(self):
        with mock.patch.dict(os.environ, ENV):
            for sub in ("comprar", "anunciar", "enviar", "mensaje"):
                out = run(f"/amazon {sub} algo")
                self.assertIn("/confirmar", out)
                self.assertIn("/enviar", out)

    def test_strip_pii_recursivo(self):
        d = amz._strip_pii({"a": [{"BuyerInfo": 1, "ok": 2}], "ShippingAddress": 3})
        self.assertEqual(d, {"a": [{"ok": 2}]})


class AmazonEstatico(unittest.TestCase):
    """Reglas fijas verificadas en el código, sin dependencias."""
    src = (ROOT / "jarvis_amazon.py").read_text(encoding="utf-8")

    def test_solo_get_a_spapi(self):
        tree = ast.parse(self.src)
        metodos = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute) and n.func.attr in ("get", "post", "put", "patch", "delete")
                   and getattr(n.func.value, "id", "") == "client"}
        self.assertEqual(metodos, {"get", "post"})
        posts = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "post" and getattr(n.func.value, "id", "") == "client"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(getattr(posts[0].args[0], "id", ""), "LWA_URL")

    def test_no_registra_secretos(self):
        self.assertNotIn("logger", self.src)
        self.assertNotIn("print(", self.src)

    def test_main_ruta_solo_dueno(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        i = main.index('== "/amazon"')
        self.assertIn("is_owner_private(msg)", main[i:i + 300])

    def test_env_example_vacio(self):
        env = (ROOT / ".env.example").read_text(encoding="utf-8")
        for k in ("SPAPI_LWA_CLIENT_ID", "SPAPI_LWA_CLIENT_SECRET", "SPAPI_REFRESH_TOKEN", "SPAPI_SELLER_ID"):
            self.assertIn(f"\n{k}=\n", env)


if __name__ == "__main__":
    unittest.main()
