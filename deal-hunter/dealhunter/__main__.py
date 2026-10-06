"""Deal Hunter CLI. Run from the deal-hunter/ directory: python -m dealhunter <command>.

Each command is one step of the daily run in RUNBOOK.md. Commands print JSON
(or the digest's Markdown) so the agent driving the run can read the results.
"""

import argparse
import json
import sys

from . import analysis, config
from .marketplace import LoginRequired, Marketplace
from .store import Store


def out(obj) -> None:
    print(json.dumps(obj, indent=1))


def cmd_scan(args, cfg, store):
    summary = {"new": [], "price_drop": [], "price_up": [], "seen": 0, "filtered": 0, "errors": []}
    searches = [s for s in cfg.searches if not args.search or s.query == args.search]
    with Marketplace() as mp:
        for s in searches:
            try:
                found = mp.search(cfg, s)
            except LoginRequired:
                raise
            except Exception as e:  # one broken search shouldn't sink the run
                summary["errors"].append(f"{s.query}: {e.__class__.__name__}: {e}")
                continue
            for listing in found:
                listing["search"] = s.query
                result = store.upsert(listing)
                l = store.listings[listing["id"]]
                analysis.apply_filters(l, cfg)
                analysis.evaluate(l, cfg)  # a price change can turn a fair car into a deal
                if l["status"] == "filtered":
                    summary["filtered"] += 1 if result == "new" else 0
                elif result == "seen":
                    summary["seen"] += 1
                else:
                    summary[result].append(l["id"])
    store.save()
    out(summary)


def cmd_todo(args, cfg, store):
    """Listings waiting for a reference value, with what the agent needs to look one up."""
    items = []
    for l in analysis.needs_value(store):
        keys = ("id", "title", "year", "price", "mileage", "location", "search", "url", "trim")
        items.append({k: l.get(k) for k in keys} | {"comps": analysis.comps(store, l)})
    out(items)


def cmd_value(args, cfg, store):
    l = store.get(args.id)
    analysis.set_valuation(l, args.amount, args.source, args.note or "", cfg)
    store.save()
    out({k: l.get(k) for k in ("id", "title", "price", "valuation", "discount", "status")})


def cmd_details(args, cfg, store):
    l = store.get(args.id)
    with Marketplace() as mp:
        l.update(mp.details(args.id))
    analysis.apply_filters(l, cfg)  # the description may reveal 'salvage', etc.
    analysis.evaluate(l, cfg)
    store.save()
    out(l)


def cmd_draft(args, cfg, store):
    l = store.get(args.id)
    l["draft"] = args.message
    if args.plan:
        l["plan"] = args.plan
    store.save()
    out({"id": l["id"], "draft": l["draft"], "plan": l.get("plan")})


def cmd_deals(args, cfg, store):
    deals, _ = analysis.digest_items(store)
    out([l | {"my_max": cfg.search(l["search"]).my_max} for l in deals])


def cmd_digest(args, cfg, store):
    print(analysis.render_digest(store, cfg) or "NOTHING NEW")


def cmd_mark_notified(args, cfg, store):
    out({"marked": analysis.mark_notified(store)})
    store.save()


def cmd_show(args, cfg, store):
    out(store.get(args.id))


def main(argv=None):
    p = argparse.ArgumentParser(prog="dealhunter")
    sub = p.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="search Marketplace and save new/changed listings")
    sc.add_argument("--search", help="only run the search with this exact query")
    sub.add_parser("todo", help="listings that still need a reference value")
    v = sub.add_parser("value", help="record a reference value and re-check the deal")
    v.add_argument("id")
    v.add_argument("amount", type=int)
    v.add_argument("--source", required=True, help="e.g. kbb-private-party, edmunds, comps")
    v.add_argument("--note")
    d = sub.add_parser("details", help="fetch an item page (seller, description, trim)")
    d.add_argument("id")
    dr = sub.add_parser("draft", help="store the opener message (and plan) for a deal")
    dr.add_argument("id")
    dr.add_argument("message")
    dr.add_argument("--plan")
    sub.add_parser("deals", help="deals not yet emailed, as JSON")
    sub.add_parser("digest", help="print the email digest as Markdown")
    sub.add_parser("mark-notified", help="record that the current digest was sent")
    sh = sub.add_parser("show")
    sh.add_argument("id")
    args = p.parse_args(argv)

    cfg, store = config.load(), Store()
    try:
        globals()["cmd_" + args.cmd.replace("-", "_")](args, cfg, store)
    except LoginRequired as e:
        out({"error": "login_required", "detail": str(e)})
        sys.exit(2)


if __name__ == "__main__":
    main()
