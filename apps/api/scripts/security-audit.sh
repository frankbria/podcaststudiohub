#!/usr/bin/env bash
# pip-audit gate over the locked dependency closure (#306).
# Run from apps/api: bash scripts/security-audit.sh
set -euo pipefail

cd "$(dirname "$0")/.."

reqs="$(mktemp)"
trap 'rm -f "$reqs"' EXIT
uv export --format requirements-txt --no-hashes --no-emit-project -o "$reqs" -q

# Ignored IDs are all structurally capped by podcastfy==0.4.1's requirement set
# (every litellm release above 1.80.0 needs openai>=2.20 — verified 2026-08-12,
# `uv lock --upgrade-package 'litellm>=1.81.0'` is unsatisfiable against
# podcastfy's openai<2; langchain 1.x / langsmith 0.8 / aiplatform 1.133 /
# pytest 9 conflict the same way; PYSEC-2026-2562 is langchain-core, fixed only
# in 1.2.11). The fix is a podcastfy release that supports langchain 1.x —
# 0.4.2/0.4.3 do NOT (evaluated & deferred in #363, see
# docs/podcastfy-0.4.3-evaluation.md) — not an override. Re-check this list on
# every podcastfy bump.
#
# Reachability was assessed on 2026-08-13 (#446) — being capped is why we CAN'T fix
# these; being unreachable is why it's acceptable not to. 21 of 22 open alerts are
# unreachable (the 11 litellm ones are proxy-server issues and we never run a proxy;
# the rest are unused features). The exception is GHSA-3644-q5cj-c5c7 (langsmith),
# which IS on the generation hot path via podcastfy's hub.pull() — accepted because
# every pull is commit-pinned. Full classification and re-check triggers:
#   docs/podcastfy-advisory-reachability.md
# The import-graph claims are enforced by tests/test_dependency_reachability.py.
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
  --ignore-vuln PYSEC-2026-1845 \
  --ignore-vuln PYSEC-2026-2193 \
  --ignore-vuln PYSEC-2026-2562 \
  `# litellm 1.80.0, all four capped by openai<2 as described above:` \
  `# 3478 fixed in 1.82.0, 3477 in 1.83.7, 3476 in 1.83.10, 3479 in 1.84.0` \
  --ignore-vuln PYSEC-2026-3476 \
  --ignore-vuln PYSEC-2026-3477 \
  --ignore-vuln PYSEC-2026-3478 \
  --ignore-vuln PYSEC-2026-3479
