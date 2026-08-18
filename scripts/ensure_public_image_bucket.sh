#!/usr/bin/env bash
set -euo pipefail

# CORS + public-read for catalog images on s3://renown-public
# Does not create the bucket. Only catalog/* is publicly readable.

BUCKET="${PUBLIC_IMAGE_BUCKET:-renown-public}"
REGION="${AWS_DEFAULT_REGION:-ap-south-2}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CORS_FILE="$SCRIPT_DIR/s3_public_cors.json"

if ! aws s3api head-bucket --bucket "$BUCKET" --region "$REGION" 2>/dev/null; then
  echo "Bucket s3://$BUCKET not found in $REGION."
  echo "Create it (or set PUBLIC_IMAGE_BUCKET) then re-run."
  exit 1
fi

echo "Setting CORS on s3://$BUCKET (browser PUT from admin)..."
aws s3api put-bucket-cors \
  --bucket "$BUCKET" \
  --region "$REGION" \
  --cors-configuration "file://$CORS_FILE"

echo "Allowing a public GetObject policy on catalog/* only (ACLs stay blocked)..."
aws s3api put-public-access-block \
  --bucket "$BUCKET" \
  --region "$REGION" \
  --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=false,RestrictPublicBuckets=false"

aws s3api put-bucket-policy --bucket "$BUCKET" --region "$REGION" --policy "$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadCatalogImages",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::${BUCKET}/catalog/*"
    }
  ]
}
EOF
)"

echo "Done. Objects will be at https://${BUCKET}.s3.${REGION}.amazonaws.com/catalog/products/{id}/{uuid}.ext"
