#!/usr/bin/env bash
# Enable S3 bucket versioning so generated audio is protected against accidental
# overwrite/delete (issue #292). Administrative action — run from AWS CloudShell
# (admin identity); the app's least-privilege IAM user cannot toggle versioning.
#
# Usage: enable-s3-versioning.sh <bucket-name>
set -euo pipefail

BUCKET="${1:?Usage: enable-s3-versioning.sh <bucket-name>}"

aws s3api put-bucket-versioning \
  --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled

aws s3api get-bucket-versioning --bucket "$BUCKET"
echo "Versioning enabled on $BUCKET"
