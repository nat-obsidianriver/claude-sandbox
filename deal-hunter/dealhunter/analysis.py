"""Deterministic judgment: which search a listing belongs to, whether it passes
the hard filters, what comparable listings say, and whether it's a deal."""

import re
from statistics import median

from .config import Config, Search
from .store import Store, now

MODEL_ALIASES = {"miata": ["miata", "mx5"], "4runner": ["4runner", "4 runner"]}


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower())


def matches_model(listing: dict, s: Search) -> bool:
    title = norm(listing["title"]).replace(" ", "")
    names = MODEL_ALIASES.get(norm(s.model).replace(" ", ""), [s.model])
    return any(norm(n).replace(" ", "") in title for n in names)


def filter_reason(listing: dict, s: Search, cfg: Config) -> str | None:
    """Why this listing should be ignored, or None if it passes."""
    if listing.get("is_sold") or listing.get("is_pending"):
        return "sold or pending"
    if not matches_model(listing, s):
        return f"title doesn't mention {s.model}"
    if listing["price"] < cfg.min_price:
        return f"placeholder price ${listing['price']}"
    year = listing.get("year")
    if year and s.year_min and year < s.year_min:
        return f"{year} older than {s.year_min}"
    if year and s.year_max and year > s.year_max:
        return f"{year} newer than {s.year_max}"
    miles = listing.get("mileage")
    if miles and s.max_mileage and miles > s.max_mileage:
        return f"{miles:,} miles over {s.max_mileage:,}"
    text = norm(f"{listing['title']} {listing.get('description', '')}")
    for word in cfg.exclude_keywords:
        if norm(word) in text:
            return f"mentions '{word}'"
    return None


def comps(store: Store, listing: dict) -> dict | None:
    """Median asking price of similar listings we've seen (same search, ±1 year, ±30k miles)."""
    peers = []
    for other in store.listings.values():
        if other["id"] == listing["id"] or other.get("search") != listing.get("search"):
            continue
        if other.get("status") == "filtered" or not (other.get("year") and listing.get("year")):
            continue
        if abs(other["year"] - listing["year"]) > 1:
            continue
        if listing.get("mileage") and other.get("mileage"):
            if abs(other["mileage"] - listing["mileage"]) > 30000:
                continue
        peers.append(other["price"])
    if len(peers) < 3:
        return None
    return {"median": int(median(peers)), "n": len(peers)}


def evaluate(listing: dict, cfg: Config) -> None:
    """Set status to deal/fair from the reference valuation."""
    val = listing.get("valuation")
    if listing.get("status") == "filtered" or not val:
        return
    discount = 1 - listing["price"] / val["value"]
    listing["discount"] = round(discount, 3)
    listing["status"] = "deal" if discount >= cfg.undervalued_threshold else "fair"


def apply_filters(listing: dict, cfg: Config) -> None:
    s = cfg.search(listing["search"])
    reason = filter_reason(listing, s, cfg) if s else "search removed from config"
    if reason:
        listing["status"], listing["filter_reason"] = "filtered", reason
    elif listing.get("status") == "filtered":
        listing["status"] = "new"
        listing.pop("filter_reason", None)


def set_valuation(listing: dict, value: int, source: str, note: str, cfg: Config) -> None:
    listing["valuation"] = {"value": int(value), "source": source, "note": note, "at": now()}
    evaluate(listing, cfg)


def needs_value(store: Store) -> list[dict]:
    return [l for l in store.listings.values() if l["status"] == "new"]


# ---------------------------------------------------------------- digest


def _money(n) -> str:
    return f"${n:,.0f}"


def digest_items(store: Store) -> tuple[list[dict], list[dict]]:
    """(new deals not yet emailed, price drops on tracked cars since they were last emailed)."""
    deals, drops = [], []
    for l in store.listings.values():
        if l["status"] == "deal" and not l.get("notified_at"):
            deals.append(l)
        elif (
            l["status"] in ("deal", "fair")
            and l.get("previous_price")
            and l["price"] <= l["previous_price"] * 0.97
            and l.get("notified_price") != l["price"]
        ):
            drops.append(l)
    deals.sort(key=lambda l: -l.get("discount", 0))
    return deals, drops


def render_digest(store: Store, cfg: Config) -> str | None:
    deals, drops = digest_items(store)
    if not deals and not drops:
        return None
    lines = [f"# Deal Hunter — {len(deals)} new deal(s), {len(drops)} price drop(s)", ""]
    for l in deals:
        s = cfg.search(l["search"])
        v = l["valuation"]
        lines += [
            f"## {l['title']} — {_money(l['price'])} ({l['discount']:.0%} under)",
            f"- Reference value: {_money(v['value'])} ({v['source']}{'; ' + v['note'] if v.get('note') else ''})",
            f"- Mileage: {l['mileage']:,}" if l.get("mileage") else "- Mileage: not listed",
            f"- Location: {l.get('location') or 'unknown'} · Seller: {l.get('seller') or 'unknown'}",
            f"- Your max: {_money(s.my_max)}" if s else "",
            f"- Listing: {l['url']}",
        ]
        if c := comps(store, l):
            lines.append(f"- Similar listings we've seen: median {_money(c['median'])} (n={c['n']})")
        if l.get("draft"):
            lines += ["", "**Message to send (copy into Messenger):**", "", "> " + l["draft"].replace("\n", "\n> ")]
        if l.get("plan"):
            lines += ["", f"**Negotiation plan:** {l['plan']}"]
        lines.append("")
    if drops:
        lines += ["## Price drops on cars we're tracking", ""]
        for l in drops:
            lines.append(
                f"- {l['title']}: {_money(l['previous_price'])} → {_money(l['price'])}"
                f" (value {_money(l['valuation']['value'])}) — {l['url']}"
            )
    return "\n".join(lines).strip() + "\n"


def mark_notified(store: Store) -> int:
    deals, drops = digest_items(store)
    ts = now()
    for l in deals + drops:
        l["notified_at"] = ts
        l["notified_price"] = l["price"]
    return len(deals) + len(drops)
