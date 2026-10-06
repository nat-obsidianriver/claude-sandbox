import json

from dealhunter import analysis
from dealhunter.config import Config, Search
from dealhunter.marketplace import (
    extract_details,
    extract_listings,
    load_cookies,
    parse_json_blobs,
    parse_mileage,
)
from dealhunter.store import Store


def node(id, title, price, miles="98K miles", city="Austin, TX"):
    return {
        "id": id,
        "marketplace_listing_title": title,
        "listing_price": {"amount": f"{price}.00", "formatted_amount": f"${price:,}"},
        "location": {"reverse_geocode": {"city_page": {"display_name": city}}},
        "primary_listing_photo": {"image": {"uri": f"https://scontent.fbcdn.net/{id}.jpg"}},
        "custom_sub_titles_with_rendering_flags": [{"subtitle": miles}],
        "is_sold": False,
        "is_pending": False,
    }


def search_payload(*nodes):
    edges = [{"node": {"listing": n}} for n in nodes]
    return {"data": {"marketplace_search": {"feed_units": {"edges": edges}}}}


CFG = Config(
    marketplace_location="austin",
    notify_email="me@example.com",
    exclude_keywords=["salvage", "rebuilt"],
    searches=[Search(query="Tacoma TRD", make="Toyota", model="Tacoma", my_max=25000,
                     year_min=2012, max_mileage=150000)],
)


def test_payload_parsing_handles_graphql_framing():
    a = json.dumps(search_payload(node("1", "2019 Toyota Tacoma TRD Sport", 27400)))
    b = json.dumps(search_payload(node("2", "2016 Toyota Tacoma TRD Off-Road", 24900)))
    payloads = parse_json_blobs(["for (;;);" + a + "\n" + b, "<not json>"])
    listings = extract_listings(payloads)
    assert [l["id"] for l in listings] == ["1", "2"]
    assert listings[0]["year"] == 2019
    assert listings[0]["price"] == 27400
    assert listings[0]["mileage"] == 98000
    assert listings[0]["location"] == "Austin, TX"


def test_mileage_formats():
    assert parse_mileage("130K miles") == 130000
    assert parse_mileage("85,200 mi") == 85200
    assert parse_mileage("100K km") == 62137
    assert parse_mileage("Dealership") is None


def test_details_extraction():
    payload = {"x": {"redacted_description": {"text": "Clean title, new tires"},
                     "marketplace_listing_seller": {"name": "Vlad", "id": "9"},
                     "vehicle_trim_display_name": "TRD Sport",
                     "vehicle_odometer_data": {"unit": "MILES", "value": 61000}}}
    d = extract_details([payload])
    assert d == {"description": "Clean title, new tires", "seller": "Vlad", "seller_id": "9",
                 "trim": "TRD Sport", "mileage": 61000}


def test_cookie_formats():
    assert {c["name"] for c in load_cookies("c_user=1; xs=abc; datr=z")} == {"c_user", "xs", "datr"}
    js = json.dumps([{"name": "c_user", "value": "1"}, {"name": "xs", "value": "a"}])
    assert len(load_cookies(js)) == 2


def scan(store, listing):
    listing["search"] = "Tacoma TRD"
    result = store.upsert(listing)
    l = store.listings[listing["id"]]
    analysis.apply_filters(l, CFG)
    analysis.evaluate(l, CFG)
    return result, l


def test_full_flow(tmp_path):
    store = Store(tmp_path / "db.json")
    good = extract_listings([search_payload(node("1", "2019 Toyota Tacoma TRD Sport", 27400))])[0]
    salvage = extract_listings([search_payload(node("2", "2018 Toyota Tacoma TRD salvage", 9000))])[0]
    old = extract_listings([search_payload(node("3", "2008 Toyota Tacoma", 9000))])[0]
    wrong = extract_listings([search_payload(node("4", "2019 Nissan Frontier", 20000))])[0]

    assert scan(store, good)[1]["status"] == "new"
    assert scan(store, salvage)[1]["filter_reason"] == "mentions 'salvage'"
    assert scan(store, old)[1]["filter_reason"] == "2008 older than 2012"
    assert "doesn't mention" in scan(store, wrong)[1]["filter_reason"]
    assert [l["id"] for l in analysis.needs_value(store)] == ["1"]

    # 27,400 vs 31,600 is 13% under: fair, not a deal.
    analysis.set_valuation(store.get("1"), 31600, "kbb-private-party", "", CFG)
    assert store.get("1")["status"] == "fair"
    assert analysis.render_digest(store, CFG) is None

    # Seller drops to 26,000 (18% under): becomes a deal and shows in the digest.
    result, l = scan(store, good | {"price": 26000})
    assert result == "price_drop" and l["status"] == "deal"
    l["draft"] = "Hi! Is the Tacoma still available?"
    digest = analysis.render_digest(store, CFG)
    assert "2019 Toyota Tacoma TRD Sport — $26,000 (18% under)" in digest
    assert "> Hi! Is the Tacoma still available?" in digest

    assert analysis.mark_notified(store) == 1
    assert analysis.render_digest(store, CFG) is None

    # A further drop on a car we already emailed about is reported once.
    scan(store, good | {"price": 24000})
    assert "$26,000 → $24,000" in analysis.render_digest(store, CFG)
    analysis.mark_notified(store)
    assert analysis.render_digest(store, CFG) is None

    store.save()
    assert Store(tmp_path / "db.json").get("1")["valuation"]["value"] == 31600


def test_comps(tmp_path):
    store = Store(tmp_path / "db.json")
    for i, (yr, price) in enumerate([(2019, 30000), (2018, 28000), (2020, 32000), (2015, 20000)]):
        scan(store, extract_listings([search_payload(node(str(i), f"{yr} Toyota Tacoma", price))])[0])
    target = store.get("0")
    assert analysis.comps(store, target) is None  # only 2 peers within ±1 year
    scan(store, extract_listings([search_payload(node("9", "2019 Toyota Tacoma", 29000))])[0])
    assert analysis.comps(store, target) == {"median": 29000, "n": 3}
