# Project Handoff — Glen Eachach / "The Grey Wolf" site

> Handoff written 2026-06-22 to move from a remote (web/mobile-started) Claude Code
> session to a **full local code session** on the user's Windows laptop, where the
> AWS CLI and the `ObsidianRiver` profile are available.

---

## 1. What this project is

A small **static website** built around an AI-generated portrait (the user, restyled
by his wife as a Scottish Highland chieftain). The site presents an **original-fiction
backstory** for the character and a **system-agnostic homebrew TTRPG campaign** seed.

- **Character:** Alasdair "the Grey Wolf" MacBrae (*Madadh-allaidh Glas*), 8th and last
  Laird of **Glen Eachach**.
- **Tone (decided):** historical Highlands with a touch of myth (Jacobite-era feel,
  folklore on the edges).
- **Campaign material (decided):** **system-agnostic** — no specific ruleset.
- All names/lore are **invented** (Clan MacBrae, Glen Eachach, Dùn Cailleach, the pact)
  — free to build on.

### Canon already written (keep consistent)
- **Seat:** Dùn Cailleach — half-ruined keep on a tidal islet, joined to the road by a
  single arched stone bridge; lowest vault never unsealed.
- **Loch Eachach:** black water the glen is named for; boats go missing; "the drowned
  are owed, not lost."
- **The two rents:** one to the Crown; one to **the Thing Under the Cailleach** — the
  old pact that the bridge stands and the glen prospers so long as the Laird walks the
  **13 boundary stones** sunwise each **Samhain** and speaks the names of the dead.
- **The crisis:** a **new road** (surveyors, charters) is pulling up boundary stones;
  the corrie grows hungry; last Samhain a name **answered back**.
- **The hook:** the player characters are **the strangers riding up the glen**, arriving
  the week before Samhain.
- **Grief:** a fever year killed both his sons; no blood heir.
- **Regalia:** MacBrae sett (bog-brown / pine-green / one thread dried-blood red);
  bronze brooch — a wolf curled round a standing stone.

---

## 2. Repository state

- **GitHub:** `nat-obsidianriver/claude-sandbox`
- **Working branch:** `claude/ai-image-backstory-ufydv9` (pushed to origin)
- **Static site, no build step / no dependencies.** Open `index.html` to view.

| File | Purpose |
|------|---------|
| `index.html` | Themed single-page site: hero (portrait), The Tale, The Man, The Pact, The Glen (gazetteer), The Campaign. |
| `css/styles.css` | Highland theme — bronze/peat palette, Cinzel + EB Garamond (Google Fonts), scroll-reveal, responsive, reduced-motion support. |
| `js/main.js` | IntersectionObserver scroll-reveal only. |
| `assets/alasdair-macbrae.png` | The portrait (~2.5 MB). Committed. (Excluded from Claude *context* via `.claudeignore`, but tracked in git.) |

**Commit already pushed:** `Build Glen Eachach site: backstory of Alasdair 'the Grey Wolf' MacBrae`

---

## 3. The hosting goal (not yet started)

Host the static site on the user's **AWS account** (profile `ObsidianRiver`):

**Target architecture:** S3 (private bucket) → CloudFront (Origin Access Control) →
ACM cert → Route 53 alias record.

### Gotchas to remember
- **ACM certificate MUST be in `us-east-1`** for CloudFront, regardless of bucket region.
- Use **OAC** (not legacy OAI); keep the bucket **private**, no public-website hosting.
- CloudFront needs a **default root object** (`index.html`) and ideally a 403/404 →
  `index.html` behavior if we add client routing later (not needed yet — single page).
- Domain decision still open (see §4).

### Deferred decision
How to provision: hand-run AWS CLI vs. **CloudFormation/Terraform template**. In a local
session, Claude can run the CLI directly with the `ObsidianRiver` profile, OR generate
IaC for the user to apply. Recommendation: a small **CloudFormation or Terraform** stack
for repeatability.

---

## 4. Domain selection — IN PROGRESS (this is where we stopped)

**Goal:** pick a **vacant** Route 53 domain that also **fits the theme** (short,
evocative, Highland/clan/TTRPG-flavored) for the site.

**"Vacant"** = registered (owned) AND has **no hosted zone**, or a hosted zone with only
the **2 default records** (NS + SOA) and no live `A`/alias pointing at a real site.

### Data still needed (re-run locally)
The remote sandbox had **no AWS credentials**, so we couldn't query directly. On the
laptop with the `ObsidianRiver` profile, re-run:

```bat
set AWS_PROFILE=ObsidianRiver
aws route53domains list-domains --region us-east-1 --query "Domains[].{Domain:DomainName,AutoRenew:AutoRenew,Expiry:Expiry}" --output table
aws route53 list-hosted-zones --query "HostedZones[].{Zone:Name,Records:ResourceRecordSetCount}" --output table
```

(PowerShell: `$env:AWS_PROFILE="ObsidianRiver"` then the same `aws` lines.)

### Captured so far (PARTIAL — list was truncated alphabetically at `lojunior.com`)
Owned domains seen (AutoRenew / Expiry):
advancestoragesolutions.com (T), afterburnsf.com (T), arcadiapta.com (T),
arcadiapta.org (F), beekeepingcentral.com (T), bejuulin.com (T), **bejuulin.net (F,
exp 2026-06-24)**, **bejuuling.com (F, exp 2026-06-24)**, **bejuuling.net (F, exp
2026-06-24)**, bestsodcalculator.com (T), bethelevc.org (T), brisktoken.com (T),
codeemu.com (T), coolflashcards.com (T), domainventuresinternational.com (T),
domainventuresofalabama.com (T), dynamicstudysystems.com (T), easywebsitediy.com (T),
fullaccessai.com (T), glutenfreenearmehq.com (T), housecents.com (T),
jaaacsoftwareconsulting.com (T), kanbanchallenge.com (T), kandlcollectibles.com (T),
lojunior.com (T) … **(more below `lojunior.com` not yet captured)**

- **Hosted-zones table: not yet captured.**

### Notes / warnings
- **`bejuulin.net`, `bejuuling.com`, `bejuuling.net`** are **AutoRenew=False, expiring
  2026-06-24** (~2 days after handoff) — do **not** build on a domain about to lapse
  unless the user renews. `bejuulin.com` is AutoRenew=True (safe).
- None of the captured names are obviously Highland-themed; most are project/business
  domains. May want to weigh "vacant + brandable" (e.g. `bejuulin.com`, `lojunior.com`)
  if no thematic domain exists — or register a new fitting one.

---

## 5. Next steps (suggested order)

1. **Capture full domain + hosted-zone data** (commands in §4).
2. **Cross-reference** → produce ranked shortlist of vacant domains; flag thematic fit.
3. **User picks a domain** (or decides to register a new on-theme one).
4. **Provision hosting** (S3 + CloudFront + ACM us-east-1 + Route 53) — likely via a
   CloudFormation/Terraform template applied with the `ObsidianRiver` profile.
5. **Deploy** the site (sync to S3, invalidate CloudFront).
6. (Optional, ongoing) **Deepen lore / campaign** — Laird timeline, NPCs, map, one-shot.

---

## 6. Environment note (why we moved local)
The previous session ran in an **ephemeral remote container** with general internet but
**no AWS credentials** and no access to the laptop's `~/.aws` profile. The device used to
*start* a session (the user started on mobile) does **not** determine where code runs.
Moving to a **local** session gives direct use of the laptop's AWS CLI + `ObsidianRiver`
profile.
