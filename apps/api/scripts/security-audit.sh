#!/usr/bin/env bash
# pip-audit gate over the locked dependency closure (#306).
# Run from apps/api: bash scripts/security-audit.sh
#
# pip-audit writes a JSON report; scripts/pip_audit_gate.py decides what blocks:
# any advisory fails, as does a missing/unparseable report or an unaudited package.
# Its allowlists are empty since #543 removed podcastfy, whose version caps were
# the only reason advisories were ever let through (#306, #446, #518).
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
