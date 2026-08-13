#!/usr/bin/env bash
# npm audit (high+) gate over the workspace lockfile, with an allowlist.
# Mirrors apps/api/scripts/security-audit.sh — see that file for the Python side.
# Run from the repo root: bash scripts/npm-security-audit.sh
set -euo pipefail

cd "$(dirname "$0")/.."

# Allowlisted advisories. npm has no native per-advisory ignore, so we filter the
# JSON ourselves rather than pulling in audit-ci/better-npm-audit for this.
#
# CURRENTLY EMPTY — every known high+ advisory is fixed in the lockfile, so this
# gate is equivalent to a plain `npm audit --audit-level=high` today. The
# mechanism is kept because unfixable advisories recur (see the 22-entry
# structural ignore list in apps/api/scripts/security-audit.sh for the Python
# side); an empty list means nothing is being hidden right now.
#
# Only add an entry when NO release fixes it. Verify that claim against the
# registry (`npm view <pkg> versions`) rather than the advisory's affected range:
# a range of `<=X` means X+1 is the fix, not that every release is affected. That
# misreading is what previously masked next-auth 4.24.15.
#
# Each entry must carry: why no bump fixes it, an issue link, and a re-check trigger.
ALLOWED_ADVISORIES=()

audit_json="$(mktemp)"
trap 'rm -f "$audit_json"' EXIT

# npm audit exits non-zero when it finds anything, so we can't treat its exit code
# as success/failure — but we must still distinguish "found nothing" from "never
# ran" (ENOLOCK, network failure, npm crash). The node step below fails closed if
# the output isn't a well-formed audit report.
npm audit --audit-level=high --json > "$audit_json" || true

ALLOWED="${ALLOWED_ADVISORIES[*]}" node -e '
const fs = require("fs");
// filter(Boolean): an empty ALLOWED yields [""] from split, which would put an
// empty string in the set and match any advisory with a blank id.
const allowed = new Set(process.env.ALLOWED.trim().split(/\s+/).filter(Boolean));

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
