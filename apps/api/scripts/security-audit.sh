#!/usr/bin/env bash
# pip-audit gate over the locked dependency closure (#306).
# Run from apps/api: bash scripts/security-audit.sh
#
# pip-audit writes a JSON report; scripts/pip_audit_gate.py decides what blocks (#518):
#   - litellm advisories WARN and never block. litellm is capped by podcastfy==0.4.1
#     and never imported — tests/test_dependency_reachability.py fails CI the moment
#     any litellm module loads with the generation engine. That test is the
#     compensating control; the per-CVE ID list it replaces was hand-patched six
#     times and added no safety.
#   - the other capped advisories stay enumerated, one per line, in TRIAGED in the
#     gate script, each assessed in docs/podcastfy-advisory-reachability.md (#446).
#   - anything else fails, as does a missing/unparseable report or an unaudited package.
# The whole cap goes away with the engine replacement (#538 / #543).
set -euo pipefail

cd "$(dirname "$0")/.."

reqs="$(mktemp)"
report="$(mktemp)"
trap 'rm -f "$reqs" "$report"' EXIT
uv export --format requirements-txt --no-hashes --no-emit-project -o "$reqs" -q

# pip-audit exits 1 whenever it finds anything, triaged or not; the gate below reads
# the report and fails closed if pip-audit died before writing it.
uvx pip-audit -r "$reqs" --no-deps --disable-pip --strict -f json -o "$report" || true
python3 scripts/pip_audit_gate.py "$report"
