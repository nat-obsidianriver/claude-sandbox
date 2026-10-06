from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
DB_PATH = ROOT / "data" / "listings.json"


@dataclass
class Search:
    query: str
    make: str
    model: str
    my_max: int
    year_min: int | None = None
    year_max: int | None = None
    max_mileage: int | None = None


@dataclass
class Config:
    marketplace_location: str
    searches: list[Search]
    notify_email: str
    days_since_listed: int = 1
    undervalued_threshold: float = 0.15
    min_price: int = 1500
    exclude_keywords: list[str] = field(default_factory=list)

    def search(self, query: str) -> Search | None:
        return next((s for s in self.searches if s.query == query), None)


def load(path: Path = CONFIG_PATH) -> Config:
    raw = yaml.safe_load(path.read_text())
    raw["searches"] = [Search(**s) for s in raw["searches"]]
    return Config(**raw)
