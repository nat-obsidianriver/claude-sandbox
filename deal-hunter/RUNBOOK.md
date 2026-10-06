# Deal Hunter — daily run

You are the deal-hunting agent. Each morning a scheduled Claude Code session
follows this file top to bottom. The Python CLI does the mechanical work
(browsing, storing, math); you do the judgment (valuations, messages, the email).

**Hard rules**
- Never message a seller, comment, or click anything on Facebook. Read only.
  You *draft* messages; the owner sends them.
- Never draft an offer above the search's `my_max`.
- Don't invent a valuation. If you can't find a credible number, say so in the note
  and use the most conservative figure you have.
- Finish every run by committing the database (step 7), even if a step failed.

All commands run from `deal-hunter/`.

## 1. Sync

```bash
cd "$(git rev-parse --show-toplevel)"
git fetch origin
git checkout -B claude/deal-hunter-data origin/claude/deal-hunter-data
git merge --no-edit origin/main || git merge --abort   # pick up config/code merged to main
cd deal-hunter
python -m pip install -q -r requirements.txt
```

## 2. Scan Marketplace

```bash
python -m dealhunter scan
```

Prints `new`, `price_drop`, `price_up`, `seen`, `filtered` and `errors`.

- **Exit code 2 / `login_required`**: the Facebook cookies expired. Skip to step 6 and
  email the owner (subject `Deal Hunter: Facebook login needed`) with the instructions
  under "Refreshing the Facebook login" in README.md. Then step 7.
- **All searches errored, or 0 listings across every search for 3+ days running**
  (check `last_seen` dates in `data/listings.json`): Facebook probably changed its
  page format. Email the owner the error text so they can ask Claude to fix the scraper.

## 3. Value new listings — `price-vs-kbb`

```bash
python -m dealhunter todo
```

For each listing (most promising first: lowest price relative to `comps.median`, then
newest; cap at 20 per run, leftovers wait for tomorrow), find its **Kelley Blue Book
private-party value** for that year/model/trim/mileage, in good condition, in the owner's
area:

1. Search the web (e.g. `2019 Toyota Tacoma TRD Sport 60000 miles KBB private party value`).
   Prefer KBB's own figure; Edmunds private-party or a J.D. Power value is an acceptable
   substitute — record which.
2. If the title doesn't give the trim, assume the most common trim for that query
   (e.g. "Tacoma TRD" → TRD Sport) and say so in the note.
3. Sanity-check against `comps` when present. If your number and the comps median disagree
   by more than 25%, trust neither blindly: say so in the note, use the lower.
4. If nothing credible turns up but `comps` exists (n ≥ 3), use the comps median with
   source `comps`.

Record it:

```bash
python -m dealhunter value <id> <amount> --source kbb-private-party --note "TRD Sport, 60k mi, good condition"
```

The command reports `status`: `deal` (≥ threshold under value) or `fair`.

## 4. Check each deal up close — `flag-undervalued`

```bash
python -m dealhunter deals
```

For every deal, fetch the item page:

```bash
python -m dealhunter details <id>
```

This adds seller, description, trim and title status, and re-runs the filters: if the
description reveals salvage/rebuilt etc., the listing drops out automatically. Also
read the description yourself for red flags the keyword filter can't catch (flood,
"needs transmission", "mechanic special", out-of-state title, price clearly a typo).
**Too good to be true:** a car priced 40%+ under value is usually a scam (deposit
fraud, "I'm deployed, shipping only", wants payment off-platform) or a typo. Don't drop
it silently: keep it, but begin its draft with `⚠️ LIKELY SCAM:` and the reason, and
write the message as a verification question (ask to see it in person, ask for the VIN),
never an offer.
If the trim from the page changes the value, re-run step 3's `value` command. If a
listing is obviously not a real deal, record a corrected value with a note explaining why.

## 5. Draft the outreach — `message-seller` + `negotiate`

For each remaining deal, write the first Messenger message the owner will send, and a
short negotiation plan:

```bash
python -m dealhunter draft <id> "<message>" --plan "<plan>"
```

**Message**: 2–4 friendly sentences, plain language, sounds like a person. Ask whether
it's still available and why they're selling; ask one useful question the listing didn't
answer (title in hand? maintenance records? accidents?). No offer in the first message.

**Plan** (one or two sentences): opening offer, walk-away price, and the lever to use.
Open around 8–12% below asking, justified by something real (mileage, needed tires,
comps). Walk-away = the lower of `my_max` and the reference value. Never exceed `my_max`.

## 6. Email the digest — `text-me`

```bash
python -m dealhunter digest
```

If it prints `NOTHING NEW` and nothing went wrong, send no email. Otherwise, use the
Gmail connector to send the digest to the `notify_email` in `config.yaml`:

- Subject: `Deal Hunter: <n> deal(s) — <best car> $<x> under` (or the error subject above)
- Body: the digest Markdown as-is. Put any run problems (errors, skipped valuations)
  in a short "Run notes" section at the end.

Once it's sent:

```bash
python -m dealhunter mark-notified
```

## 7. Save the database

```bash
git add data/listings.json
git commit -m "Deal Hunter run $(date -u +%F)" || true
git push origin claude/deal-hunter-data
```

If the push is rejected, `git pull --rebase origin claude/deal-hunter-data` and push again.
