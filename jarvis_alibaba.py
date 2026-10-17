"""Jarvis · alibaba_research: lee proveedores públicos de Alibaba/1688. SOLO LECTURA.

Reglas de diseño
- Apagado por defecto: ALIBABA_RESEARCH_ENABLED=0. Mientras esté apagado no hace ninguna petición de red.
- Solo https a alibaba.com o 1688.com. Sin login, sin cookies, sin formularios, sin POST.
- robots.txt se consulta en tiempo de ejecución para cada host. Si no se puede leer (no es 200) o no permite
  la página, NO se lee: fallo cerrado.
- Redirecciones no se siguen (una redirección podría salir del dominio permitido).
- Pausa mínima entre peticiones y caché de 24 h. Respuestas máximas de 1.5 MB.
- Respaldo: el dueño pega el texto o el HTML de la página y se analiza localmente, sin red.
- No contacta proveedores, no crea cuentas, no compra. No crea watches ni publica nada: solo devuelve datos
  y sugerencias que el dueño decide usar.
- Los campos que no aparecen en la página quedan en null. Nunca se inventan.
"""
import asyncio, os, re, time
from html.parser import HTMLParser
from urllib import robotparser
from urllib.parse import urljoin, urlsplit, quote_plus

UA = "JarvisResearch/1.0 (solo lectura; ISLAFIX PRO LLC)"
UA_TOKEN = "JarvisResearch"          # token que se compara contra robots.txt
ALLOWED_HOSTS = ("alibaba.com", "1688.com")
MAX_PROVIDERS = 5
MIN_INTERVAL = 10.0                  # segundos entre peticiones de red
CACHE_TTL = 24 * 3600
MAX_BYTES = 1_500_000
MAX_WINDOW = 800                     # caracteres de texto que se asocian a cada enlace de proveedor
ECON_KEYS = ("shipping_total", "duties_total", "other_total", "sale_price", "referral_percent",
             "fulfillment_per_unit", "ads_per_unit", "returns_percent", "fixed_monthly", "expected_monthly_units")

core = None
_cache = {}          # url -> (timestamp, text)
_robots = {}         # host -> (timestamp, RobotFileParser | None)
_last_request = [0.0]
_fetcher = None      # pruebas: async def fetch(url) -> (status, text). Nunca se usa en producción.


class ResearchError(ValueError):
    pass


def enabled():
    return os.environ.get("ALIBABA_RESEARCH_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


def check_url(url):
    """Devuelve la URL normalizada o lanza ResearchError. Sin query en logs ni en errores."""
    parts = urlsplit((url or "").strip())
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host:
        raise ResearchError("Solo URLs https de Alibaba o 1688")
    if parts.username or parts.password or parts.port not in (None, 443):
        raise ResearchError("URL no permitida")
    if not any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
        raise ResearchError("Solo Alibaba o 1688")
    query = f"?{parts.query}" if parts.query else ""
    return f"https://{host}{parts.path or '/'}{query}"


def search_url(query):
    text = re.sub(r"\s+", " ", (query or "")).strip()[:200]
    if not text:
        raise ResearchError("Falta el producto a buscar")
    return f"https://www.alibaba.com/trade/search?SearchText={quote_plus(text)}"


async def _get(url):
    if _fetcher is not None:
        return await _fetcher(url)
    import httpx
    async with httpx.AsyncClient(timeout=20, follow_redirects=False,
                                 headers={"User-Agent": UA, "Accept": "text/html,text/plain"}) as client:
        r = await client.get(url)
    return r.status_code, r.text[:MAX_BYTES]


async def _pace():
    wait = MIN_INTERVAL - (time.monotonic() - _last_request[0])
    if wait > 0:
        await asyncio.sleep(wait)
    _last_request[0] = time.monotonic()


async def allowed(url):
    """True solo si robots.txt del host es legible (200) y permite la URL para JarvisResearch."""
    host = urlsplit(url).hostname
    now = time.time()
    hit = _robots.get(host)
    if hit is None or now - hit[0] > CACHE_TTL:
        await _pace()
        status, text = await _get(f"https://{host}/robots.txt")
        rp = None
        if status == 200:
            rp = robotparser.RobotFileParser()
            rp.parse(text.splitlines())
        _robots[host] = (now, rp)
        hit = _robots[host]
    rp = hit[1]
    return bool(rp) and rp.can_fetch(UA_TOKEN, url)


async def read_page(url):
    """Texto de una página pública permitida por robots.txt. Lanza ResearchError si no se puede leer."""
    url = check_url(url)
    if not enabled():
        raise ResearchError("alibaba_research está apagada (ALIBABA_RESEARCH_ENABLED=0)")
    cached = _cache.get(url)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]
    if not await allowed(url):
        raise ResearchError("robots.txt no permite leer esta página o no pudo verificarse")
    await _pace()
    status, text = await _get(url)
    if status != 200:
        raise ResearchError(f"Lectura rechazada (HTTP {status})")
    _cache[url] = (time.time(), text)
    return text


class _Providers(HTMLParser):
    """Agrupa el texto que sigue a cada enlace de proveedor o producto en una 'tarjeta'."""

    LINK = re.compile(r"(company_profile|product-detail|/supplier|/store/)", re.I)

    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.cards = []          # [href, [texts]]
        self._in_link = False

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        if self.LINK.search(href):
            self.cards.append([urljoin(self.base, href), []])
            self._in_link = True

    def handle_endtag(self, tag):
        if tag == "a":
            self._in_link = False

    def handle_data(self, data):
        if self.cards and data.strip():
            texts = self.cards[-1][1]
            if sum(len(t) for t in texts) < MAX_WINDOW:
                texts.append(data.strip())


PRICE = re.compile(r"(?:US\s?)?\$\s?(\d[\d,]*(?:\.\d+)?)", re.I)
MOQ = re.compile(r"(?:min\.?\s*order|moq|pedido m[ií]nimo)\D{0,25}(\d[\d,]*)", re.I)
YEARS = re.compile(r"(\d{1,2})\s*(?:yrs?|years?|a[ñn]os)\b", re.I)
SHIP = re.compile(r"(?:shipping|env[ií]o|freight|flete)\D{0,30}\$\s?(\d[\d,]*(?:\.\d+)?)", re.I)
VERIFIED = re.compile(r"verified|verificado|gold supplier|trade assurance", re.I)


def _num(s):
    return float(s.replace(",", "")) if s else None


def parse_providers(html, base="https://www.alibaba.com/"):
    """Hasta 5 proveedores de un HTML. Solo campos presentes en el texto; el resto queda en None."""
    p = _Providers(base)
    p.feed(html or "")
    out, seen = [], set()
    for href, texts in p.cards:
        if href in seen:
            continue
        window = " ".join(texts)[:MAX_WINDOW]
        price = PRICE.search(window)
        moq = MOQ.search(window)
        if not price and not moq:
            continue            # sin precio ni MOQ no es un resultado útil
        seen.add(href)
        years = YEARS.search(window)
        ship = SHIP.search(window)
        out.append({
            "name": (texts[0] if texts else "")[:120] or None,
            "url": href,
            "unit_price_usd": _num(price.group(1)) if price else None,
            "moq": int(_num(moq.group(1))) if moq else None,
            "shipping_estimate_usd": _num(ship.group(1)) if ship else None,
            "years": int(years.group(1)) if years else None,
            "verified": bool(VERIFIED.search(window)),
        })
        if len(out) == MAX_PROVIDERS:
            break
    return out


def _economics(provider, econ):
    """Pasa precio y MOQ del proveedor a product_economics. Solo si el dueño dio TODOS los demás datos."""
    if not econ:
        return None
    missing = [k for k in ECON_KEYS if econ.get(k) is None]
    if missing or provider.get("unit_price_usd") is None or provider.get("moq") is None:
        return {"status": "faltan_datos", "missing": missing or ["precio o MOQ del proveedor"]}
    from jarvis_growth import product_economics     # import local: solo lectura, sin efectos
    try:
        return product_economics(provider["unit_price_usd"], provider["moq"],
                                 **{k: econ[k] for k in ECON_KEYS})
    except ValueError as e:
        return {"status": "error", "message": str(e)}


async def alibaba_research(query=None, url=None, html=None, economics=None):
    """Herramienta de solo lectura. Ruta: texto pegado > URL pública permitida > búsqueda pública."""
    if economics is not None and not isinstance(economics, dict):
        raise ValueError("economics debe ser un objeto con los datos del dueño")
    source = None
    try:
        if html:
            if len(html) > MAX_BYTES:
                raise ResearchError("Texto demasiado grande")
            page, source = html, "texto_pegado_por_el_dueño"
        else:
            if not enabled():
                return {"status": "desactivada", "providers": [],
                        "message": "Lectura de Alibaba apagada. Pega el texto o el HTML de la página, o pide que se active."}
            target = check_url(url) if url else search_url(query)
            page, source = await read_page(target), target
    except ResearchError as e:
        return {"status": "necesita_capturas", "providers": [], "message": str(e),
                "fallback": "Pega el texto de la página o mándame capturas; lo analizo sin conectarme."}
    providers = parse_providers(page, base=source if source.startswith("https://") else "https://www.alibaba.com/")
    if not providers:
        return {"status": "sin_resultados", "source": source, "providers": [],
                "message": "No encontré proveedores con precio o MOQ en esa página. Pega el texto o mándame capturas."}
    for p in providers:
        p["economics"] = _economics(p, economics)
    return {"status": "ok", "source": source, "providers": providers,
            "note": "Solo lectura. No se contactó a ningún proveedor ni se compró nada. "
                    "Las órdenes requieren tu aprobación y respetan los topes de $100 por operación y $300 por día.",
            "next": "Para vigilar el producto usa add_supplier_watch con el tema; no se crea automáticamente."}


DESCRIPTION = ("Lee hasta 5 proveedores públicos de Alibaba o 1688: nombre, URL, precio por unidad, MOQ, envío, años y "
               "verificación. Solo lectura: no contacta proveedores ni compra. Si no se puede leer, pide que el dueño pegue "
               "el texto o capturas. Los campos que no aparecen quedan null.")
PROPS = {"query": {"type": "string"}, "url": {"type": "string"}, "html": {"type": "string"},
         "economics": {"type": "object"}}


def install(j):
    global core
    core = j
    j.ASYNC_TOOLS["alibaba_research"] = alibaba_research
    j.TOOLS.append(j._t("alibaba_research", DESCRIPTION, PROPS, []))
