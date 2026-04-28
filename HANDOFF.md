# Package Tracker — Handoff

A static daily tracker for FedEx package **871172274092** (Dothan, AL → Tuscaloosa, AL, scheduled 2026-04-29). Built to be deployed to S3 + CloudFront from your laptop.

## What's in the repo

| File | Purpose |
|---|---|
| `index.html` | Tracker UI: package details, expected timeline, daily log form |
| `css/styles.css` | Dark-theme styles |
| `js/main.js` | Timeline state + daily log persisted in `localStorage` |
| `deploy.sh` | One-shot deploy to S3 + CloudFront invalidation |
| `HANDOFF.md` | This file |

Branch: `claude/package-location-tracker-Rji0m` (pushed to origin).

## Features

- **Package details** card grid pre-filled from the FedEx receipt.
- **Expected timeline** with 7 steps from pickup to delivery. Click a step to confirm it (green dot); the hero status banner updates to show the latest confirmed milestone.
- **Daily log** — date + location + optional note. Saved per-browser in `localStorage` under `tracker:871172274092:log`.
- **"Check Live Status on FedEx"** button deep-links to `fedex.com/fedextrack/?trknbr=871172274092` for the actual carrier feed.
- **Copy tracking #** button for quick paste elsewhere.

## Limitations

- **No live FedEx data.** The page is fully client-side; FedEx requires API credentials and blocks cross-origin browser calls. Live status is via the deep-link.
- **Local-only state.** The daily log lives in `localStorage` on whichever browser/device you use. Use the same device each day or re-enter from the FedEx history.

## Deploying from your laptop

Prereqs: `aws` CLI installed, your AWS profile configured (`aws configure --profile <name>`).

```bash
# pull the branch
git fetch origin claude/package-location-tracker-Rji0m
git checkout claude/package-location-tracker-Rji0m

# deploy to existing bucket + distribution
./deploy.sh \
  --profile <your-profile> \
  --bucket  <your-bucket-name> \
  --distribution <your-distribution-id>

# OR create the bucket on first run
./deploy.sh \
  --profile <your-profile> \
  --bucket  <new-bucket-name> \
  --region  us-east-1 \
  --create-bucket
```

The script:
1. Verifies credentials with `sts get-caller-identity`.
2. Optionally creates the bucket with public access blocked (CloudFront should reach it via Origin Access Control).
3. `aws s3 sync`s the site, excluding `.git`, `deploy.sh`, `HANDOFF.md`, etc.
4. Sets cache headers (60s for `index.html`, 1 day for CSS/JS).
5. Issues a `/*` CloudFront invalidation if `--distribution` is provided.

## If you need to provision CloudFront from scratch

The script doesn't create the distribution — that's a one-time setup. Recommended path:

1. Create the bucket via `--create-bucket`.
2. In the AWS console, create a CloudFront distribution:
   - Origin: the S3 bucket (use **Origin Access Control**, not public bucket)
   - Default root object: `index.html`
   - Viewer protocol policy: Redirect HTTP to HTTPS
   - Update the bucket policy with the snippet CloudFront generates for OAC
3. Grab the distribution ID and run `deploy.sh` with `--distribution`.

Happy to scaffold a Terraform module for this if you'd rather codify it.

## Updating the tracker

Edit the relevant file, commit, push, re-run `deploy.sh`. The expected timeline is in `js/main.js` under `EXPECTED_STEPS` — adjust dates/locations there if the FedEx scan history surprises you.
