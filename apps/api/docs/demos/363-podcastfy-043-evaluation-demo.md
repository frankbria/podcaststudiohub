# Demo: #363 podcastfy 0.4.1→0.4.3 evaluation (verdict: defer)

*2026-07-13T19:44:05Z*

Issue #363 asked for a deliberate evaluation of upgrading the podcastfy engine 0.4.1→0.4.3. Each checklist item below is mapped to executable evidence. Verdict: DEFER — full rationale in apps/api/docs/podcastfy-0.4.3-evaluation.md. The upstream sdists used for the diff are re-downloaded here so evidence is reproducible.

```bash
cd /tmp && rm -rf pf-demo && mkdir pf-demo && cd pf-demo && for v in 0.4.1 0.4.3; do curl -s https://pypi.org/pypi/podcastfy/$v/json | python3 -c "import json,sys; d=json.load(sys.stdin); print([u[\"url\"] for u in d[\"urls\"] if u[\"packagetype\"]==\"sdist\"][0])" | xargs curl -sL -o pf-$v.tar.gz && tar xzf pf-$v.tar.gz; done && ls -d podcastfy-*/
```

```output
podcastfy-0.4.1/
podcastfy-0.4.3/
```

**Checklist 1 — upstream diff review.** The generation entrypoint we're coupled to (#204), `client.py`, is byte-identical between 0.4.1 and 0.4.3 — no signature risk:

```bash
cmp /tmp/pf-demo/podcastfy-0.4.1/podcastfy/client.py /tmp/pf-demo/podcastfy-0.4.3/podcastfy/client.py && echo "client.py IDENTICAL 0.4.1 vs 0.4.3"
```

```output
client.py IDENTICAL 0.4.1 vs 0.4.3
```

**The blocker**: 0.4.3 imports playwright at module top of website_extractor.py — a module our app imports at startup — yet declares no playwright dependency:

```bash
grep -n "from playwright" /tmp/pf-demo/podcastfy-0.4.3/podcastfy/content_parser/website_extractor.py; echo "--- playwright in 0.4.3 declared deps?"; grep -c playwright /tmp/pf-demo/podcastfy-0.4.3/pyproject.toml || echo "NOT DECLARED (0 matches) -> ModuleNotFoundError at import; app cannot boot"
```

```output
16:from playwright.sync_api import sync_playwright
--- playwright in 0.4.3 declared deps?
0
NOT DECLARED (0 matches) -> ModuleNotFoundError at import; app cannot boot
```

**Checklist 2+3 — bump + uv sync + call-site recheck.** The spike was executed live on this branch (pin→0.4.3, `uv lock` resolved, `uv sync` installed, then the #204 signature-guard suite failed collection with `ModuleNotFoundError: No module named 'playwright'` via the exact import chain main.py guards). Spike transcript is in the evaluation doc. The spike was then reverted; proof the repo remains pinned and green on 0.4.1:

```bash
grep -n "podcastfy==" apps/api/pyproject.toml | head -1
```

```output
26:    "podcastfy==0.4.1",  # pinned: task kwargs are coupled to this signature (see #204); bumping needs a signature recheck
```

```bash
cd apps/api && uv run pytest tests/test_imports.py tests/unit/test_podcast_generation_task.py -q 2>&1 | tail -1 | sed 's/in [0-9.]*s/in <time>/'
```

```output
============================== 32 passed in <time> ==============================
```

**Checklist 4 — pip-audit ignore list.** Staying on 0.4.1 means the capped ignore list is unchanged; the script comment no longer implies a 0.4.x bump clears the langchain CVEs (0.4.3 still pins langchain <0.4):

```bash
grep -n "langchain <0.4\|langchain>=0.3.3,<0.4.0" /tmp/pf-demo/podcastfy-0.4.3/pyproject.toml; grep -n "langchain" /tmp/pf-demo/podcastfy-0.4.3/pyproject.toml | head -2; sed -n "15,18p" apps/api/scripts/security-audit.sh
```

```output
33:langchain = "^0.3.3"
34:langchain-google-vertexai = "^2.0.4"
# is langchain-core, fixed only in 1.2.11). The fix is a podcastfy release that
# supports langchain 1.x — 0.4.2/0.4.3 do NOT (evaluated & deferred in #363, see
# docs/podcastfy-0.4.3-evaluation.md) — not an override. Re-check this list on
# every podcastfy bump.
```

**Checklist 5 — full suite + e2e generation:** N/A under the defer verdict — no dependency or code changed on main; the branch diff is docs/comments only (CI runs the full suite on the PR regardless).

**Checklist 6 — CLAUDE.md pin note updated** with the verdict and a pointer to the evaluation doc:

```bash
grep -n -A3 "0.4.2/0.4.3 were evaluated" CLAUDE.md
```

```output
60:**0.4.2/0.4.3 were evaluated 2026-07-13 and deferred** (#363): 0.4.2+ imports `playwright` at module
61-top without declaring it (breaks app startup), offers no benefit to our call paths, and does not clear
62-the langchain CVEs on the pip-audit ignore list. See `apps/api/docs/podcastfy-0.4.3-evaluation.md` for
63-the full evaluation and re-evaluation triggers (chiefly: upstream langchain 1.x support).
```

**Outcome**: evaluation complete, verdict DEFER, re-evaluation triggers documented (upstream langchain 1.x support chief among them). Dependabot's podcastfy ignore stays in place.
