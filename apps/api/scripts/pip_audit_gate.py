"""Classify a pip-audit JSON report into pass / warn / fail (#518).

Usage: python scripts/pip_audit_gate.py <pip-audit-report.json>

- litellm advisories WARN (one annotation; listed in the log and step summary) and
  never block. litellm is capped by podcastfy==0.4.1 (every release above 1.80.0
  needs openai>=2.20 against podcastfy's openai<2) and is never imported: tests/test_dependency_reachability.py
  fails CI the moment any `litellm` module loads with the generation engine. That
  test is the control that makes these safe — not an enumerated ID list, which only
  had to be hand-patched every time litellm published a batch (#440, #487, #500,
  #517, #523, #557).
- Advisories in TRIAGED below are ignored, by id or alias.
- Anything else FAILS the gate, as does an unreadable report or a skipped package.
"""

import json
import os
import sys

WARN_ONLY_PACKAGES = {"litellm"}

# Every entry is capped by podcastfy==0.4.1's requirement set and assessed unreachable
# (or accepted) in docs/podcastfy-advisory-reachability.md (#446). Re-check on every
# podcastfy bump.
TRIAGED = {
    "CVE-2026-55443",  # langchain: file-search middleware, not used
    "PYSEC-2026-1515",  # langchain-community: XXE in EverNoteLoader, never called
    "PYSEC-2026-77",  # langchain-text-splitters: split_text_from_url, never called
    "PYSEC-2026-2193",  # langchain-core: legacy load_prompt, never called
    "PYSEC-2026-2562",  # langchain-core GHSA-2g6r: image_url SSRF, no image sources
    "CVE-2026-41182",  # langsmith: streaming redaction, tracing never configured
    "CVE-2026-45134",  # langsmith GHSA-3644: hub.pull() IS reachable — accepted, commit-pinned
    "GHSA-f4xh-w4cj-qxq8",  # langsmith: TracingMiddleware, tracing never configured
    "CVE-2026-2472",  # google-cloud-aiplatform: no Vertex usage
    "CVE-2026-2473",  # google-cloud-aiplatform: no Vertex usage
    "PYSEC-2026-1845",  # pytest: tmpdir handling; runtime dep only by podcastfy packaging defect
}


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
            f"::warning title=litellm advisories - non-blocking::{len(warned)} (#518) — listed below"
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
                f"- :warning: {line} — non-blocking, see #518\n" for line in warned
            )
            if not failed and not warned:
                f.write("No unaccepted vulnerabilities.\n")

    print(
        f"pip-audit gate: {len(failed)} blocking, {len(warned)} litellm (non-blocking)"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
