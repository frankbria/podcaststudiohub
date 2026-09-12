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
# these; being unreachable is why it's acceptable not to. 26 of 27 open alerts are
# unreachable (the 16 litellm ones are proxy-server issues and we never run a proxy;
# the rest are unused features). The exception is GHSA-3644-q5cj-c5c7 (langsmith),
# which IS on the generation hot path via podcastfy's hub.pull() — accepted because
# every pull is commit-pinned. Full classification and re-check triggers:
#   docs/podcastfy-advisory-reachability.md
# The import-graph claims are enforced by tests/test_dependency_reachability.py.
# Added 2026-09-12: CVE-2026-12773 (improper authentication in
# litellm/proxy/_experimental/mcp_server/auth/user_api_key_auth_mcp.py, MCP Proxy)
# and CVE-2026-12795 (missing authentication in
# litellm/proxy/management_endpoints/ui_sso.py, SSO debug flow). Same proxy-only
# class as everything below.
#
# Added 2026-09-10: CVE-2026-12771 (M2M JWT improper authorization in
# litellm/proxy/auth/user_api_key_auth.py) and CVE-2026-12772 (session expiration
# in litellm/proxy/auth/login_utils.py's authenticate_user). Both are
# litellm/proxy/* — the same proxy-only class as the 12 above, unreachable for the
# same reason: we import podcastfy's engine and never start a proxy. That claim is
# enforced rather than asserted, by
# tests/test_dependency_reachability.py::test_litellm_proxy_is_not_reachable_from_the_generation_stack
#
# Keep every --ignore-vuln on its own continued line with NO comment lines between
# them: a `#` line inside a `\`-continuation ends the command, which would
# silently drop the remaining flags rather than comment them.
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
  --ignore-vuln CVE-2026-12771 \
  --ignore-vuln CVE-2026-12772 \
  --ignore-vuln CVE-2026-12773 \
  --ignore-vuln CVE-2026-12795 \
  `# litellm 1.80.0, all five capped by openai<2 as described above:` \
  `# 3478 fixed in 1.82.0, 3477 in 1.83.7, 3476 in 1.83.10, 3479 in 1.84.0,` \
  `# CVE-2026-37004 in 1.83.7 -- SSTI in the proxy's /prompts/test endpoint,` \
  `# unreachable for the same reason as the other 11 proxy advisories (#446).` \
  --ignore-vuln PYSEC-2026-3476 \
  --ignore-vuln PYSEC-2026-3477 \
  --ignore-vuln PYSEC-2026-3478 \
  --ignore-vuln PYSEC-2026-3479 \
  --ignore-vuln CVE-2026-37004
