#!/usr/bin/env bash
# pip-audit gate over the locked dependency closure (#306).
# Run from apps/api: bash scripts/security-audit.sh
set -euo pipefail

cd "$(dirname "$0")/.."

reqs="$(mktemp)"
trap 'rm -f "$reqs"' EXIT
uv export --format requirements-txt --no-hashes --no-emit-project -o "$reqs" -q

# Ignored IDs are all structurally capped by podcastfy==0.4.1's requirement set
# (litellm>=1.84 needs openai>=2.20 vs podcastfy's openai<2; langchain 1.x /
# langsmith 0.8 / aiplatform 1.133 / pytest 9 conflict the same way). The fix is
# the podcastfy upgrade (#204 coupling), not an override. Re-check this list on
# every podcastfy bump.
uvx pip-audit -r "$reqs" --no-deps --disable-pip --strict \
  --ignore-vuln CVE-2026-35029 \
  --ignore-vuln CVE-2026-42271 \
  --ignore-vuln CVE-2026-47101 \
  --ignore-vuln CVE-2026-47102 \
  --ignore-vuln GHSA-69x8-hrgq-fjj8 \
  --ignore-vuln PYSEC-2026-388 \
  --ignore-vuln PYSEC-2026-390 \
  --ignore-vuln CVE-2026-55443 \
  --ignore-vuln PYSEC-2026-1515 \
  --ignore-vuln PYSEC-2026-77 \
  --ignore-vuln CVE-2026-41182 \
  --ignore-vuln CVE-2026-45134 \
  --ignore-vuln GHSA-f4xh-w4cj-qxq8 \
  --ignore-vuln CVE-2026-2472 \
  --ignore-vuln CVE-2026-2473 \
  --ignore-vuln PYSEC-2026-1845
