#!/usr/bin/env python3
"""Create GitHub issues from the release-readiness audit output.

Reads the workflow JSON, maps each issue's raw labels onto the repo's existing
label taxonomy, and creates issues via `gh` (critical/high first). Writes a
title->number mapping to scripts/audit_issue_map.json for the plan doc.
"""
import json
import subprocess
import sys
import tempfile
import os

if len(sys.argv) < 2:
    print("Usage: create_audit_issues.py <audit_json_file>", file=sys.stderr)
    sys.exit(1)
AUDIT_JSON = sys.argv[1]

# Raw finding-label -> existing repo label (only labels that exist or we created).
LABEL_MAP = {
    "bug": "bug",
    "blocker": "blocker",
    "generation": "area-generation",
    "integration": "area-generation",
    "security": "area-security",
    "auth": "area-auth",
    "authz": "area-auth",
    "ssrf": "area-security",
    "secrets": "area-security",
    "deployment": "area-deployment",
    "tls": "area-deployment",
    "storage": "area-storage",
    "unfinished": "unfinished",
    "distribution": "area-distribution",
    "reliability": "area-reliability",
    "tts": "area-tts",
    "tech-debt": "tech-debt",
    "ux": "area-ux",
    "design-system": "area-ux",
    "slop": "area-quality",
    "hygiene": "area-quality",
    "ci": "area-deployment",
    "docs": "documentation",
    "billing": "area-api",
    "teams": "area-api",
    "defense-in-depth": "area-security",
}
SEV_LABELS = {
    "critical": ["priority-p0", "critical"],
    "high": ["priority-p1"],
    "medium": ["priority-p2"],
    "low": ["priority-p3"],
}
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

try:
    with open(AUDIT_JSON) as f:
        data = json.load(f)
    issues = data["result"]["report"]["issues"]
except FileNotFoundError:
    print(f"Error: audit file not found: {AUDIT_JSON}", file=sys.stderr)
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"Error: invalid JSON in {AUDIT_JSON}: {e}", file=sys.stderr)
    sys.exit(1)
except KeyError as e:
    print(f"Error: missing expected key in audit JSON: {e}", file=sys.stderr)
    sys.exit(1)
issues.sort(key=lambda i: SEV_ORDER.get(i["severity"], 9))

mapping = {}
for idx, issue in enumerate(issues, 1):
    labels = set(["release-audit"])
    labels.update(SEV_LABELS.get(issue["severity"], []))
    for raw in issue.get("labels", []):
        if raw in LABEL_MAP:
            labels.add(LABEL_MAP[raw])
    body = issue["body"] + (
        "\n\n---\n_Filed from the automated release-readiness audit (2026-06-13). "
        f"Severity: **{issue['severity']}** · Area: **{issue['area']}**._"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as tf:
        tf.write(body)
        body_file = tf.name
    try:
        cmd = ["gh", "issue", "create", "--title", issue["title"], "--body-file", body_file]
        for lab in sorted(labels):
            cmd += ["--label", lab]
        print(f"[{idx}/{len(issues)}] ({issue['severity']}) {issue['title'][:70]}...")
        res = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        os.unlink(body_file)
    if res.returncode != 0:
        print("  ERROR:", res.stderr.strip())
        mapping[issue["title"]] = {"number": None, "url": None, "error": res.stderr.strip(), "severity": issue["severity"], "area": issue["area"]}
        continue
    url = res.stdout.strip()
    num = url.rstrip("/").split("/")[-1]
    print("  ->", url)
    mapping[issue["title"]] = {"number": int(num), "url": url, "severity": issue["severity"], "area": issue["area"]}

with open("scripts/audit_issue_map.json", "w") as f:
    json.dump(mapping, f, indent=2)
print("\nDone. Map written to scripts/audit_issue_map.json")
