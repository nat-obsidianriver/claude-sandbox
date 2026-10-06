# Deal Hunter

Built from Angus The Tech Bro's "vibe code a $20B vending machine" reel: a
do-it-yourself Carvana. Every morning an agent searches Facebook Marketplace for
the cars you want, prices each one against Kelley Blue Book, flags anything well
under value, drafts the message to the seller, and emails you.

It runs as a **Claude Code routine**, a scheduled cloud session, so your
computer can be off.

```
 every morning (Claude routine, cloud)
   │
   ├─ scan      headless Chrome + your FB cookies → Marketplace searches → data/listings.json
   ├─ value     agent looks up the KBB private-party value of each new car
   ├─ flag      ≥ 15% under value → "deal"; item page checked for salvage/red flags
   ├─ draft     agent writes the opener + negotiation plan (never above your max)
   ├─ email     digest to you via Gmail, only when there's something new
   └─ save      database committed to the claude/deal-hunter-data branch
```

**What's different from the video, on purpose:** the agent never messages sellers
itself. It drafts the message and you send it from Messenger. Automated messaging from
a personal Facebook account is the fastest way to get that account restricted, and it
puts a bot in charge of negotiating with strangers using your name.

## Setup

1. **Your cars**: edit [`config.yaml`](config.yaml): location, searches, `my_max` per car.
2. **Network access**: in the cloud environment's settings (cloud icon on the new-session
   screen → gear), Network access = Custom, with:
   ```
   facebook.com
   *.facebook.com
   *.fbcdn.net
   kbb.com
   *.kbb.com
   ```
   and "Also include default list of common package managers" checked.
3. **Facebook login**: in the same dialog, under Environment variables, add
   `FB_COOKIES=c_user=...; xs=...; datr=...; fr=...` (see below).

### Refreshing the Facebook login

Marketplace search only works logged in, so the robot borrows your browser's
session cookies. They last weeks to months; when they expire you get an email.

1. In Chrome, log in to facebook.com.
2. Press F12 → **Application** tab → **Cookies** → `https://www.facebook.com`.
3. Copy the values of `c_user`, `xs`, `datr` and `fr`.
4. Set the environment variable (one line):
   `FB_COOKIES=c_user=<value>; xs=<value>; datr=<value>; fr=<value>`

**Treat these like a password.** They give full access to your Facebook account. They
sit in your personal cloud environment's variables, visible to anyone who can use that
environment. To revoke them, use Facebook → Settings → Security and login → "Where
you're logged in" → log out of that session. A secondary Facebook account is a
reasonable choice if you'd rather not risk your main one.

## Running it by hand

```bash
cd deal-hunter
pip install -r requirements.txt
python -m dealhunter scan              # search Marketplace
python -m dealhunter todo              # what still needs a valuation
python -m dealhunter value <id> 31600 --source kbb-private-party
python -m dealhunter digest            # the email body
python -m pytest -q                    # tests
```

[`RUNBOOK.md`](RUNBOOK.md) is the procedure the scheduled agent follows. Edit it to
change how the agent judges cars or writes messages.

## Known limits

- **Facebook changes its pages often.** The scraper reads the page's underlying data
  rather than its layout, which holds up better, but expect to ask Claude to repair
  it occasionally. The run emails you when searches start coming back empty.
- **KBB has no public API.** The agent looks values up through web search and records
  the source (KBB, Edmunds or comparable listings) next to every number, so you can see
  how much to trust it.
