"""Pruebas de alibaba_research. Sin red: el lector se sustituye por un servidor falso en memoria.
Solo datos ficticios: nombres, URLs y HTML inventados."""
import asyncio, os, re, unittest
from unittest.mock import patch

import test_jarvis as base
import jarvis_alibaba as al

j = base.j

FAKE_HTML = """
<div>
 <a href="/company_profile/PROV-FICTICIO-1.html">Proveedor Ficticio Uno</a>
 <span>US$1.20 - $1.50</span> Min. Order: 500 pieces <span>3 yrs</span>
 <span>Verified Supplier</span> Shipping: $35
</div>
<div>
 <a href="/product-detail/ficticio-2.html">Producto Ficticio Dos</a> Min. Order: 10
</div>
<div>
 <a href="/store/ficticio-3">Tienda Ficticia Tres</a> $4.50 por unidad
</div>
<div>
 <a href="/company_profile/PROV-FICTICIO-1.html">Repetido</a> $9.99
</div>
<div>
 <a href="/company_profile/sin-datos.html">Sin datos</a> Contacto
</div>
"""

ROBOTS_OPEN = "User-agent: *\nDisallow: /admin/\n"
ROBOTS_NO_SEARCH = "User-agent: *\nDisallow: /trade/search\n"


class Fake:
    """Servidor falso: responde según la URL y registra cada petición."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def __call__(self, url):
        self.calls.append(url)
        for prefix, reply in self.routes.items():
            if url.endswith(prefix):
                return reply
        return 404, ""


class AlibabaResearch(unittest.TestCase):
    def setUp(self):
        base.Tests.setUp(self)
        self.env = patch.dict(os.environ, {"ALIBABA_RESEARCH_ENABLED": "1"})
        self.env.start(); self.addCleanup(self.env.stop)
        al._cache.clear(); al._robots.clear(); al._last_request[0] = 0.0
        self.pace = patch.object(al, "MIN_INTERVAL", 0.0); self.pace.start(); self.addCleanup(self.pace.stop)

    def use(self, routes):
        fake = Fake(routes)
        p = patch.object(al, "_fetcher", new=fake); p.start(); self.addCleanup(p.stop)
        return fake

    def run_tool(self, **kw):
        return asyncio.run(al.alibaba_research(**kw))

    # --- apagado y solo lectura ---
    def test_disabled_by_default_no_network(self):
        with patch.dict(os.environ, {"ALIBABA_RESEARCH_ENABLED": "0"}):
            fake = self.use({})
            r = self.run_tool(query="bomba de agua ficticia")
        self.assertEqual(r["status"], "desactivada"); self.assertEqual(fake.calls, [])

    def test_default_env_value_is_off(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ALIBABA_RESEARCH_ENABLED", None)
            self.assertFalse(al.enabled())

    def test_module_never_sends_post(self):
        with open(al.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIsNone(re.search(r"\.post\(|method\s*=\s*['\"]POST|\.put\(|\.delete\(", src))
        self.assertIsNone(re.search(r"follow_redirects\s*=\s*True", src))

    # --- dominios ---
    def test_only_https_alibaba_or_1688(self):
        for u in ("http://www.alibaba.com/x", "https://www.alibaba.com.evil.test/x", "https://evil.test/alibaba.com",
                  "https://user:pw@www.alibaba.com/x", "https://www.alibaba.com:8443/x", "https://127.0.0.1/x",
                  "https://alibaba.com.attacker.example/x", "ftp://1688.com/x", "https://xalibaba.com/x"):
            with self.subTest(u=u), self.assertRaises(al.ResearchError):
                al.check_url(u)

    def test_allowed_hosts_accepted(self):
        self.assertEqual(al.check_url("https://www.alibaba.com/product-detail/x.html"),
                         "https://www.alibaba.com/product-detail/x.html")
        self.assertEqual(al.check_url("https://detail.1688.com/offer/1.html"), "https://detail.1688.com/offer/1.html")

    def test_query_text_is_bounded(self):
        u = al.search_url("  taladro   ficticio  ")
        self.assertIn("SearchText=taladro+ficticio", u)
        with self.assertRaises(al.ResearchError):
            al.search_url("   ")

    # --- robots.txt: fallo cerrado ---
    def test_robots_missing_refuses_page(self):
        fake = self.use({"robots.txt": (404, ""), "/trade/search?SearchText=x": (200, FAKE_HTML)})
        r = self.run_tool(query="x")
        self.assertEqual(r["status"], "necesita_capturas")
        self.assertFalse(any("SearchText" in c for c in fake.calls))

    def test_robots_disallow_refuses_page(self):
        fake = self.use({"robots.txt": (200, ROBOTS_NO_SEARCH), "SearchText=x": (200, FAKE_HTML)})
        r = self.run_tool(query="x")
        self.assertEqual(r["status"], "necesita_capturas")
        self.assertFalse(any("SearchText" in c for c in fake.calls))

    def test_robots_allow_reads_and_caches(self):
        fake = self.use({"robots.txt": (200, ROBOTS_OPEN), "SearchText=x": (200, FAKE_HTML)})
        r1 = self.run_tool(query="x"); r2 = self.run_tool(query="x")
        self.assertEqual(r1["status"], "ok"); self.assertEqual(r2["status"], "ok")
        self.assertEqual(sum("SearchText" in c for c in fake.calls), 1)     # segunda vez desde caché
        self.assertEqual(sum("robots.txt" in c for c in fake.calls), 1)

    def test_redirect_is_not_followed(self):
        self.use({"robots.txt": (200, ROBOTS_OPEN), "SearchText=x": (302, "")})
        r = self.run_tool(query="x")
        self.assertEqual(r["status"], "necesita_capturas")
        self.assertIn("302", r["message"])

    def test_rate_limit_spaces_requests(self):
        sleeps = []

        async def fake_sleep(s):
            sleeps.append(s)
        with patch.object(al, "MIN_INTERVAL", 10.0), patch.object(al.asyncio, "sleep", new=fake_sleep):
            self.use({"robots.txt": (200, ROBOTS_OPEN), "SearchText=x": (200, FAKE_HTML)})
            al._last_request[0] = al.time.monotonic()
            self.run_tool(query="x")
        self.assertTrue(sleeps and sleeps[0] > 0)

    # --- análisis ---
    def test_parse_fields_and_limits(self):
        out = al.parse_providers(FAKE_HTML, base="https://www.alibaba.com/trade/search")
        self.assertEqual([p["url"] for p in out],
                         ["https://www.alibaba.com/company_profile/PROV-FICTICIO-1.html",
                          "https://www.alibaba.com/product-detail/ficticio-2.html",
                          "https://www.alibaba.com/store/ficticio-3"])
        first = out[0]
        self.assertEqual(first["unit_price_usd"], 1.20)
        self.assertEqual(first["moq"], 500)
        self.assertEqual(first["years"], 3)
        self.assertTrue(first["verified"])
        self.assertEqual(first["shipping_estimate_usd"], 35.0)
        self.assertIsNone(out[1]["unit_price_usd"])          # sin precio: null, no inventado
        self.assertEqual(out[1]["moq"], 10)
        self.assertIsNone(out[2]["moq"])
        self.assertEqual(out[2]["unit_price_usd"], 4.50)
        self.assertFalse(out[2]["verified"])

    def test_at_most_five_and_no_empty_cards(self):
        many = "".join(f'<a href="/company_profile/p{i}.html">P{i}</a> $1.{i} Min. Order: {i + 1} ' for i in range(9))
        self.assertEqual(len(al.parse_providers(many)), 5)
        self.assertEqual(al.parse_providers("<p>sin enlaces de proveedor, $5</p>"), [])

    def test_pasted_text_path_needs_no_network(self):
        with patch.dict(os.environ, {"ALIBABA_RESEARCH_ENABLED": "0"}):
            fake = self.use({})
            r = self.run_tool(html=FAKE_HTML)
        self.assertEqual(r["status"], "ok"); self.assertEqual(fake.calls, [])
        self.assertEqual(r["source"], "texto_pegado_por_el_dueño")
        self.assertEqual(len(r["providers"]), 3)

    def test_empty_result_asks_for_captures(self):
        self.use({"robots.txt": (200, ROBOTS_OPEN), "SearchText=x": (200, "<p>nada</p>")})
        r = self.run_tool(query="x")
        self.assertEqual(r["status"], "sin_resultados")

    # --- conexión con product_economics ---
    ECON = {"shipping_total": 100, "duties_total": 0, "other_total": 0, "sale_price": 20, "referral_percent": 15,
            "fulfillment_per_unit": 3, "ads_per_unit": 1, "returns_percent": 2, "fixed_monthly": 30,
            "expected_monthly_units": 100}

    def test_economics_only_with_all_owner_inputs(self):
        r = self.run_tool(html=FAKE_HTML, economics=dict(self.ECON))
        first = r["providers"][0]["economics"]
        self.assertIn("net_per_unit", first)
        self.assertEqual(first["inputs"]["units"], 500.0)

    def test_economics_missing_inputs_reported_not_invented(self):
        partial = {k: v for k, v in self.ECON.items() if k != "duties_total"}
        r = self.run_tool(html=FAKE_HTML, economics=partial)
        self.assertEqual(r["providers"][0]["economics"]["status"], "faltan_datos")
        self.assertIn("duties_total", r["providers"][0]["economics"]["missing"])

    def test_economics_none_when_not_asked(self):
        r = self.run_tool(html=FAKE_HTML)
        self.assertIsNone(r["providers"][0]["economics"])

    def test_read_only_note_and_no_watch_created(self):
        r = self.run_tool(html=FAKE_HTML)
        self.assertIn("No se contactó", r["note"]); self.assertIn("no se crea automáticamente", r["next"])

    # --- registro en Jarvis ---
    def test_registered_as_async_tool(self):
        self.assertIn("alibaba_research", j.ASYNC_TOOLS)
        self.assertTrue(any(t.get("name") == "alibaba_research" for t in j.TOOLS if isinstance(t, dict)) or
                        any("alibaba_research" in str(t) for t in j.TOOLS))


if __name__ == "__main__":
    unittest.main()
