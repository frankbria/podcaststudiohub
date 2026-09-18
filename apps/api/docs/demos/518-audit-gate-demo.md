# #518 — litellm advisories warn instead of blocking the audit gate

*2026-09-18T16:05:26Z*

**Criterion 1: a litellm advisory doesn't block.** This is a real run of the CI script on the current lock, which has 21 open litellm advisories. None of them is in any ignore list now.

```bash
cd apps/api && bash scripts/security-audit.sh 2>/dev/null | grep -v "^  " ; echo "exit=${PIPESTATUS[0]}"
```

```output
::warning title=litellm advisories - non-blocking::21 (#518) — listed below
pip-audit gate: 0 blocking, 21 litellm (non-blocking)
exit=0
```

**Criterion 1, a brand-new advisory.** A fresh litellm CVE the repo has never seen (CVE-2099-0001) is added to the real report. It shows up in the warning count and doesn't block.

```bash
cd apps/api && uv export --format requirements-txt --no-hashes --no-emit-project -o /tmp/r518.txt -q && (uvx pip-audit -r /tmp/r518.txt --no-deps --disable-pip --strict -f json -o /tmp/a518.json 2>/dev/null || true) && python3 -c "
import json;d=json.load(open(\"/tmp/a518.json\"))
for dep in d[\"dependencies\"]:
    if dep[\"name\"]==\"litellm\": dep[\"vulns\"].append({\"id\":\"CVE-2099-0001\",\"aliases\":[],\"fix_versions\":[],\"description\":\"new\"})
json.dump(d,open(\"/tmp/a518-new-litellm.json\",\"w\"))" && python3 scripts/pip_audit_gate.py /tmp/a518-new-litellm.json | grep -E "::warning|CVE-2099|gate:"; echo "exit=${PIPESTATUS[0]}"
```

```output
::warning title=litellm advisories - non-blocking::22 (#518) — listed below
  litellm 1.80.0: CVE-2099-0001 ()
pip-audit gate: 0 blocking, 22 litellm (non-blocking)
exit=0
```

**Criterion 2: an advisory we haven't accepted still fails loudly.** The same real report, plus one unlisted advisory against `fastapi`, a package we definitely run.

```bash
cd apps/api && python3 -c "
import json;d=json.load(open(\"/tmp/a518.json\"))
for dep in d[\"dependencies\"]:
    if dep[\"name\"]==\"fastapi\": dep[\"vulns\"].append({\"id\":\"CVE-2099-0002\",\"aliases\":[\"GHSA-demo\"],\"fix_versions\":[\"9.9\"],\"description\":\"reachable\"})
json.dump(d,open(\"/tmp/a518-fastapi.json\",\"w\"))" && python3 scripts/pip_audit_gate.py /tmp/a518-fastapi.json | grep -E "::error|gate:"; echo "exit=${PIPESTATUS[0]}"
```

```output
::error title=Unaccepted vulnerability::fastapi 0.141.1: CVE-2099-0002 (GHSA-demo)
pip-audit gate: 1 blocking, 21 litellm (non-blocking)
exit=1
```

**Criterion 2, fail closed.** If pip-audit dies before writing its report, the gate still fails. An empty report stands in for that crash.

```bash
cd apps/api && : > /tmp/a518-empty.json && python3 scripts/pip_audit_gate.py /tmp/a518-empty.json; echo "exit=$?"
```

```output
::error::pip-audit report unreadable (Expecting value: line 1 column 1 (char 0)) — failing closed
exit=1
```

**Criterion 4: the compensating control can actually fail.** On our call path (model_name=None, which falls back to the configured gemini model), no litellm module loads. The same probe with a non-gemini model loads litellm, which is what `test_litellm_is_never_imported_by_the_generation_stack` would catch.

```bash
cd apps/api && uv run --quiet python /tmp/probe518.py 2>/dev/null | tail -1; uv run --quiet python /tmp/probe518.py gpt-4o 2>/dev/null | tail -1; uv run pytest tests/test_dependency_reachability.py tests/test_pip_audit_gate.py -q -p no:cacheprovider --no-cov 2>&1 | tail -1 | sed -E "s/ in [0-9.]+s//"
```

```output
model_name=None -> litellm modules loaded: 0
model_name='gpt-4o' -> litellm modules loaded: 907
============================== 11 passed ==============================
```

**Criteria 3 and 4: documented where the old justification lived.**

```bash
sed -n 5,14p apps/api/scripts/security-audit.sh; grep -n "Gate policy\|compensating control is" apps/api/docs/podcastfy-advisory-reachability.md
```

```output
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
11:## Gate policy (#518, 2026-09-18)
30:**The compensating control is `tests/test_dependency_reachability.py`, not a list.**
```
