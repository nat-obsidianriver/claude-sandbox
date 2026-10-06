"""The "database": one JSON file, committed to the data branch after every run.

A few hundred listings a month fits comfortably, stays diffable in git, and
lets the agent read it directly when it needs context.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import DB_PATH


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.listings: dict[str, dict] = {}
        if path.exists():
            self.listings = json.loads(path.read_text()).get("listings", {})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {"updated_at": now(), "listings": self.listings}
        self.path.write_text(json.dumps(body, indent=1, sort_keys=True) + "\n")

    def get(self, listing_id: str) -> dict:
        if listing_id not in self.listings:
            raise KeyError(f"No listing with id {listing_id}")
        return self.listings[listing_id]

    def upsert(self, scraped: dict) -> str:
        """Insert or refresh a scraped listing. Returns 'new', 'price_drop', 'price_up' or 'seen'."""
        ts = now()
        existing = self.listings.get(scraped["id"])
        if existing is None:
            self.listings[scraped["id"]] = {
                **scraped,
                "first_seen": ts,
                "last_seen": ts,
                "price_history": [[ts, scraped["price"]]],
                "status": "new",
            }
            return "new"

        old_price = existing["price"]
        # Keep the agent's work (valuation, draft, status); refresh scraped fields.
        existing.update({k: v for k, v in scraped.items() if v is not None})
        existing["last_seen"] = ts
        if scraped["price"] == old_price:
            return "seen"
        existing["price_history"].append([ts, scraped["price"]])
        existing["previous_price"] = old_price
        return "price_drop" if scraped["price"] < old_price else "price_up"
