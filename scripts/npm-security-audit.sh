#!/usr/bin/env bash
# npm audit (high+) gate over the workspace lockfile, with an allowlist.
# Mirrors apps/api/scripts/security-audit.sh — see that file for the Python side.
# Run from the repo root: bash scripts/npm-security-audit.sh
set -euo pipefail

cd "$(dirname "$0")/.."

# Allowlisted advisories. npm has no native per-advisory ignore, so we filter the
# JSON ourselves rather than pulling in audit-ci/better-npm-audit for this.
#
# All four are next-auth v4 and its uuid dependency. EVERY v4 release is affected
# (`next-auth <=4.24.14`, and 4.24.14 is the last v4), so no bump clears them —
# the fix is the Auth.js v5 / BetterAuth migration tracked in #442, not an
# override. We use CredentialsProvider only, with no OAuth providers configured,
# which bounds exposure on the provider-binding advisory. Re-check this list on
# every next-auth bump, and drop it entirely once #442 lands.
ALLOWED_ADVISORIES=(
  GHSA-x445-f3h2-j279  # next-auth: OAuth state/nonce/PKCE cookies not bound to provider
  GHSA-xmf8-cvqr-rfgj  # next-auth: getToken() uncaught exception on malformed Bearer header
  GHSA-7rqj-j65f-68wh  # next-auth: email normalizer homoglyph @ bypass
  GHSA-w5hq-g745-h8pq  # uuid <11.1.1: missing buffer bounds check (transitive via next-auth)
)

audit_json="$(mktemp)"
trap 'rm -f "$audit_json"' EXIT

# npm audit exits non-zero when it finds anything, so we can't treat its exit code
# as success/failure — but we must still distinguish "found nothing" from "never
# ran" (ENOLOCK, network failure, npm crash). The node step below fails closed if
# the output isn't a well-formed audit report.
npm audit --audit-level=high --json > "$audit_json" || true

ALLOWED="${ALLOWED_ADVISORIES[*]}" node -e '
const fs = require("fs");
const allowed = new Set(process.env.ALLOWED.trim().split(/\s+/));

let report;
try {
  report = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
} catch (e) {
  console.error(`npm audit gate FAILED — could not parse audit output: ${e.message}`);
  process.exit(1);
}

// Fail closed: an error object (ENOLOCK, registry failure) or any output missing
// the report shape means the audit never ran. Without this the gate would report
// a clean pass on zero iterations and silently stop protecting anything.
if (report.error || !report.metadata || !report.metadata.vulnerabilities) {
  console.error("npm audit gate FAILED — audit did not produce a valid report.");
  if (report.error) console.error(`  npm error: ${report.error.summary || report.error.code}`);
  console.error("  The gate fails closed rather than passing on an audit that never ran.");
  process.exit(1);
}

const blocking = [];
for (const [name, vuln] of Object.entries(report.vulnerabilities || {})) {
  if (!["high", "critical"].includes(vuln.severity)) continue;
  // A package is only cleared when EVERY advisory against it is allowlisted, so
  // a new advisory on an already-allowlisted package still fails the gate.
  const ids = (vuln.via || [])
    .filter((v) => typeof v === "object" && v.url)
    .map((v) => v.url.split("/").pop());
  const unlisted = ids.filter((id) => !allowed.has(id));
  if (ids.length === 0 || unlisted.length > 0) {
    blocking.push(`${name} (${vuln.severity}): ${unlisted.join(", ") || "via vulnerable dependency"}`);
  }
}

if (blocking.length > 0) {
  console.error("npm audit gate FAILED — advisories not on the allowlist:\n");
  blocking.forEach((b) => console.error(`  - ${b}`));
  console.error("\nFix them, or add to ALLOWED_ADVISORIES in scripts/npm-security-audit.sh");
  console.error("with a justification comment and a re-check trigger.");
  process.exit(1);
}
console.log(`npm audit: no high+ advisories outside the allowlist (${allowed.size} allowlisted).`);
' "$audit_json"
