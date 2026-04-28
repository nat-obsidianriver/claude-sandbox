#!/usr/bin/env bash
# Deploy the package tracker to S3 + CloudFront.
# Run from the repo root on a machine with your AWS profile configured.

set -euo pipefail

# ---- Config (override via env or flags) -----------------------------------
PROFILE="${AWS_PROFILE:-default}"
REGION="${AWS_REGION:-us-east-1}"
BUCKET="${S3_BUCKET:-}"
DISTRIBUTION_ID="${CF_DISTRIBUTION_ID:-}"
CREATE_BUCKET="${CREATE_BUCKET:-false}"

usage() {
    cat <<EOF
Usage: $0 --bucket <name> [--distribution <id>] [--profile <name>] [--region <region>] [--create-bucket]

Required:
  --bucket          S3 bucket name to deploy to
Optional:
  --distribution    CloudFront distribution ID (skip invalidation if omitted)
  --profile         AWS profile (default: \$AWS_PROFILE or "default")
  --region          AWS region (default: us-east-1)
  --create-bucket   Create the bucket if it doesn't exist

Example:
  $0 --profile personal --bucket package-tracker.example.com --distribution E1ABCDEF23GHIJ
EOF
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bucket) BUCKET="$2"; shift 2 ;;
        --distribution) DISTRIBUTION_ID="$2"; shift 2 ;;
        --profile) PROFILE="$2"; shift 2 ;;
        --region) REGION="$2"; shift 2 ;;
        --create-bucket) CREATE_BUCKET="true"; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown arg: $1"; usage ;;
    esac
done

[[ -z "$BUCKET" ]] && { echo "Error: --bucket is required"; usage; }

export AWS_PROFILE="$PROFILE"
export AWS_REGION="$REGION"

echo "==> Profile:       $PROFILE"
echo "==> Region:        $REGION"
echo "==> Bucket:        s3://$BUCKET"
echo "==> Distribution:  ${DISTRIBUTION_ID:-<none, skipping invalidation>}"
echo

# ---- Sanity check creds ---------------------------------------------------
aws sts get-caller-identity --output table

# ---- Optional: create bucket ---------------------------------------------
if [[ "$CREATE_BUCKET" == "true" ]]; then
    if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
        echo "==> Bucket already exists, skipping create."
    else
        echo "==> Creating bucket $BUCKET in $REGION..."
        if [[ "$REGION" == "us-east-1" ]]; then
            aws s3api create-bucket --bucket "$BUCKET"
        else
            aws s3api create-bucket --bucket "$BUCKET" \
                --create-bucket-configuration LocationConstraint="$REGION"
        fi
        # Block public access — CloudFront will reach it via OAC.
        aws s3api put-public-access-block --bucket "$BUCKET" \
            --public-access-block-configuration \
            "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
    fi
fi

# ---- Sync site ------------------------------------------------------------
echo "==> Syncing site to s3://$BUCKET ..."
aws s3 sync . "s3://$BUCKET" \
    --delete \
    --exclude ".git/*" \
    --exclude ".github/*" \
    --exclude ".claude/*" \
    --exclude ".claudeignore" \
    --exclude ".gitignore" \
    --exclude "deploy.sh" \
    --exclude "HANDOFF.md" \
    --exclude "*.DS_Store"

# Cache: long for static assets, short for HTML so updates show up fast.
echo "==> Setting cache headers..."
aws s3 cp "s3://$BUCKET/index.html" "s3://$BUCKET/index.html" \
    --metadata-directive REPLACE \
    --cache-control "public, max-age=60, must-revalidate" \
    --content-type "text/html; charset=utf-8"

aws s3 cp "s3://$BUCKET/css/styles.css" "s3://$BUCKET/css/styles.css" \
    --metadata-directive REPLACE \
    --cache-control "public, max-age=86400" \
    --content-type "text/css; charset=utf-8"

aws s3 cp "s3://$BUCKET/js/main.js" "s3://$BUCKET/js/main.js" \
    --metadata-directive REPLACE \
    --cache-control "public, max-age=86400" \
    --content-type "application/javascript; charset=utf-8"

# ---- CloudFront invalidation ---------------------------------------------
if [[ -n "$DISTRIBUTION_ID" ]]; then
    echo "==> Invalidating CloudFront distribution $DISTRIBUTION_ID ..."
    aws cloudfront create-invalidation \
        --distribution-id "$DISTRIBUTION_ID" \
        --paths "/*" \
        --output table
fi

echo
echo "==> Done."
[[ -n "$DISTRIBUTION_ID" ]] && \
    echo "    Live URL: check your CloudFront distribution domain."
