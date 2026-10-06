"""Facebook Marketplace access: a headless Chromium logged in with your cookies.

Marketplace search is login-only, so this needs FB_COOKIES (see README). Rather
than depend on CSS class names, which Facebook rotates constantly, we collect
every JSON payload the page loads (embedded <script> data plus /api/graphql
responses while scrolling) and pull out any object shaped like a listing.
"""

import json
import os
import re
from urllib.parse import urlencode

from .config import Config, Search

BASE = "https://www.facebook.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
CHROMIUM = "/opt/pw-browsers/chromium"


class LoginRequired(RuntimeError):
    pass


# ---------------------------------------------------------------- parsing


def walk(obj):
    """Yield every dict nested anywhere inside obj."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def parse_json_blobs(texts: list[str]) -> list:
    """Parse page payloads. GraphQL responses can be several JSON docs, one per line."""
    out = []
    for text in texts:
        text = text.removeprefix("for (;;);")
        for chunk in text.splitlines() or [text]:
            chunk = chunk.strip()
            if chunk.startswith(("{", "[")):
                try:
                    out.append(json.loads(chunk))
                except json.JSONDecodeError:
                    pass
    return out


def parse_mileage(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"([\d.,]+)\s*(k)?\s*(miles|mi\b|km)", text, re.I)
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    if m.group(2):
        n *= 1000
    if m.group(3).lower() == "km":
        n *= 0.621371
    return int(n)


def parse_year(title: str) -> int | None:
    m = re.match(r"\s*((?:19|20)\d\d)\b", title)
    return int(m.group(1)) if m else None


def listing_from_node(node: dict) -> dict | None:
    title = node.get("marketplace_listing_title") or node.get("custom_title")
    listing_id = node.get("id")
    price = (node.get("listing_price") or {}).get("amount")
    if not (title and listing_id and price):
        return None

    subtitles = [
        s.get("subtitle", "")
        for s in node.get("custom_sub_titles_with_rendering_flags") or []
        if isinstance(s, dict)
    ]
    geo = ((node.get("location") or {}).get("reverse_geocode") or {})
    city = (geo.get("city_page") or {}).get("display_name") or ", ".join(
        p for p in (geo.get("city"), geo.get("state")) if p
    )
    photo = (((node.get("primary_listing_photo") or {}).get("image")) or {}).get("uri")

    return {
        "id": str(listing_id),
        "title": title.strip(),
        "year": parse_year(title),
        "price": int(float(price)),
        "mileage": next((m for m in map(parse_mileage, subtitles) if m), None),
        "location": city or None,
        "photo": photo,
        "url": f"{BASE}/marketplace/item/{listing_id}/",
        "is_sold": bool(node.get("is_sold")),
        "is_pending": bool(node.get("is_pending")),
    }


def extract_listings(payloads: list) -> list[dict]:
    seen: dict[str, dict] = {}
    for payload in payloads:
        for node in walk(payload):
            if "marketplace_listing_title" not in node:
                continue
            listing = listing_from_node(node)
            if listing and listing["id"] not in seen:
                seen[listing["id"]] = listing
    return list(seen.values())


DETAIL_KEYS = {
    "description": ("redacted_description", "text"),
    "seller": ("marketplace_listing_seller", "name"),
    "seller_id": ("marketplace_listing_seller", "id"),
    "trim": ("vehicle_trim_display_name", None),
    "make": ("vehicle_make_display_name", None),
    "model": ("vehicle_model_display_name", None),
    "transmission": ("vehicle_transmission_type", None),
    "title_status": ("vehicle_title_status", None),
    "condition": ("condition", None),
}


def extract_details(payloads: list) -> dict:
    """Pull the extra fields only an item page has (description, seller, trim...)."""
    details: dict = {}
    for payload in payloads:
        for node in walk(payload):
            for field, (key, sub) in DETAIL_KEYS.items():
                if field in details or key not in node or node[key] is None:
                    continue
                value = node[key]
                if sub:
                    value = value.get(sub) if isinstance(value, dict) else None
                if value not in (None, ""):
                    details[field] = value
            odo = node.get("vehicle_odometer_data")
            if "mileage" not in details and isinstance(odo, dict) and odo.get("value"):
                factor = 0.621371 if str(odo.get("unit", "")).upper().startswith("K") else 1
                details["mileage"] = int(float(odo["value"]) * factor)
    return details


# ---------------------------------------------------------------- browser


def load_cookies(raw: str | None = None) -> list[dict]:
    """Accept either a Cookie-Editor JSON export or a 'name=value; name2=value2' header string."""
    raw = (raw if raw is not None else os.environ.get("FB_COOKIES", "")).strip()
    if not raw:
        raise LoginRequired("FB_COOKIES is not set. See deal-hunter/README.md.")
    if raw.startswith("["):
        pairs = [(c["name"], c["value"]) for c in json.loads(raw)]
    else:
        pairs = [tuple(p.strip().split("=", 1)) for p in raw.split(";") if "=" in p]
    cookies = [
        {"name": n, "value": v, "domain": ".facebook.com", "path": "/", "secure": True}
        for n, v in pairs
    ]
    if not {"c_user", "xs"} <= {c["name"] for c in cookies}:
        raise LoginRequired("FB_COOKIES must include at least the c_user and xs cookies.")
    return cookies


class Marketplace:
    def __init__(self, cookies: list[dict] | None = None):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        launch = {}
        if os.path.exists(CHROMIUM):
            launch["executable_path"] = CHROMIUM
        if proxy := os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"):
            launch["proxy"] = {"server": proxy}
        self._browser = self._pw.chromium.launch(**launch)
        self._ctx = self._browser.new_context(
            user_agent=UA, viewport={"width": 1280, "height": 900}, locale="en-US"
        )
        self._ctx.add_cookies(cookies if cookies is not None else load_cookies())

    def close(self) -> None:
        self._browser.close()
        self._pw.stop()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _capture(self, url: str, scrolls: int = 0) -> list:
        page = self._ctx.new_page()
        texts: list[str] = []

        def on_response(resp):
            if "/api/graphql" in resp.url:
                try:
                    texts.append(resp.text())
                except Exception:
                    pass

        page.on("response", on_response)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)
            if re.search(r"/(login|checkpoint)", page.url):
                raise LoginRequired(
                    f"Facebook sent the browser to {page.url.split('?')[0]}; "
                    "the FB_COOKIES session has expired or was challenged."
                )
            for _ in range(scrolls):
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(1500)
            texts.extend(page.locator('script[type="application/json"]').all_inner_texts())
        finally:
            page.close()
        return parse_json_blobs(texts)

    def search(self, cfg: Config, s: Search, scrolls: int = 3) -> list[dict]:
        params = {
            "query": s.query,
            "maxPrice": int(s.my_max * 1.5),
            "minPrice": cfg.min_price,
            "daysSinceListed": cfg.days_since_listed,
            "sortBy": "creation_time_descend",
            "exact": "false",
        }
        url = f"{BASE}/marketplace/{cfg.marketplace_location}/search?{urlencode(params)}"
        return extract_listings(self._capture(url, scrolls=scrolls))

    def details(self, listing_id: str) -> dict:
        return extract_details(self._capture(f"{BASE}/marketplace/item/{listing_id}/"))
