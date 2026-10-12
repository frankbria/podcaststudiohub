"""Classify a pip-audit JSON report into pass / warn / fail (#518).

Usage: python scripts/pip_audit_gate.py <pip-audit-report.json>

- Advisories in packages listed in WARN_ONLY_PACKAGES warn and never block.
- Advisories in TRIAGED below are ignored, by id or alias.
- Anything else FAILS the gate, as does an unreadable report or a skipped package.

Both lists are empty since #543 removed podcastfy, whose version caps were the
only reason anything was ever let through (litellm warn-only since #518, and ten
langchain/langsmith/aiplatform/pytest IDs assessed in
docs/podcastfy-advisory-reachability.md). An entry added here again needs the
same: a reason no bump can clear it, and evidence the vulnerable code is
unreachable, enforced by a test where possible.
"""

import json
import os
import sys

WARN_ONLY_PACKAGES: set = set()

TRIAGED: set = set()


def main(path: str) -> int:
    try:
        with open(path) as f:
            dependencies = json.load(f)["dependencies"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"::error::pip-audit report unreadable ({exc}) — failing closed")
        return 1

    warned, failed = [], []
    for dep in dependencies:
        if "skip_reason" in dep:
            failed.append(f"{dep['name']}: not audited ({dep['skip_reason']})")
            continue
        for vuln in dep.get("vulns", []):
            if TRIAGED & {vuln["id"], *vuln.get("aliases", [])}:
                continue
            line = f"{dep['name']} {dep['version']}: {vuln['id']} ({', '.join(sorted(vuln.get('aliases', [])))})"
            (warned if dep["name"] in WARN_ONLY_PACKAGES else failed).append(line)

    # pip-audit repeats an advisory once per matching record; report each once.
    warned, failed = list(dict.fromkeys(warned)), list(dict.fromkeys(failed))
    if warned:
        print(
            f"::warning title=Warn-only advisories - non-blocking::{len(warned)} — listed below"
        )
        print("\n".join(f"  {line}" for line in warned))
    for line in failed:
        print(f"::error title=Unaccepted vulnerability::{line}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write("### pip-audit\n\n")
            f.writelines(f"- :x: {line}\n" for line in failed)
            f.writelines(
                f"- :warning: {line} — non-blocking (WARN_ONLY_PACKAGES)\n" for line in warned
            )
            if not failed and not warned:
                f.write("No unaccepted vulnerabilities.\n")

    print(
        f"pip-audit gate: {len(failed)} blocking, {len(warned)} warn-only (non-blocking)"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
