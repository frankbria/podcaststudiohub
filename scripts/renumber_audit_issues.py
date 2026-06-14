#!/usr/bin/env python3
"""Prepend [PX.Y] phase tags to the release-readiness audit issue titles."""
import subprocess
import json

PHASE = {
    # Phase 1 - stop the bleeding (urgent security)
    207: "P1.1", 205: "P1.2", 206: "P1.3", 212: "P1.4",
    # Phase 2 - restore the core product (generation)
    204: "P2.1", 213: "P2.2", 217: "P2.3", 214: "P2.4", 210: "P2.5", 211: "P2.6",
    # Phase 3 - deploy hardening
    208: "P3.1", 209: "P3.2", 224: "P3.3",
    # Phase 4 - correctness & authz mediums
    215: "P4.1", 220: "P4.2", 216: "P4.3", 218: "P4.4", 219: "P4.5", 222: "P4.6",
    # Phase 5 - UX, tech-debt, docs
    221: "P5.1", 223: "P5.2", 226: "P5.3", 225: "P5.4",
}

for num, tag in sorted(PHASE.items(), key=lambda kv: kv[1]):
    cur = subprocess.run(
        ["gh", "issue", "view", str(num), "--json", "title", "-q", ".title"],
        capture_output=True, text=True,
    ).stdout.strip()
    if cur.startswith(f"[{tag}]"):
        print(f"#{num} already tagged {tag}")
        continue
    # strip any pre-existing [PX.Y] tag, then prepend the correct one
    base = cur
    if base.startswith("[P") and "]" in base:
        base = base.split("]", 1)[1].lstrip()
    new = f"[{tag}] {base}"
    r = subprocess.run(["gh", "issue", "edit", str(num), "--title", new], capture_output=True, text=True)
    status = "ok" if r.returncode == 0 else f"ERR {r.stderr.strip()}"
    print(f"#{num} -> {new[:80]}  [{status}]")
