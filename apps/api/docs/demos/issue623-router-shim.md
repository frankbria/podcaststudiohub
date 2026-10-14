# #623 — the router's podcastfy shim is gone; generate_podcast is split

*2026-10-14T03:17:17Z by Showboat 0.6.1*
<!-- showboat-id: 0f6098ae-391d-44f8-8bcb-8cab81cd1b56 -->

Done-when 1: no podcastfy shim names left in the backend source.

```bash
grep -rn "_podcastfy\|geminimulti" src || echo "no matches"
```

```output
no matches
```

The endpoint was one function of cyclomatic complexity 56. It is now a short orchestrator over small helpers; none of the 17 changed or new functions reaches the gate's ceiling (cc-only run shown; the coverage run passes the same way).

```bash
cd ../.. && node "$(ls -d ~/.claude/plugins/cache/eigenwise-toolshed/quartermaster/*/ | sort -V | tail -1)bin/quartermaster.js" crap --cc-only 2>&1 | tail -1
```

```output
CRAP gate (cc-only, no coverage) passed: 0 of 17 changed or new functions at or above 6
```

Behaviour net: the router, distribution-wiring, regenerate, PDF pipeline, RSS and task tests against the real database.

```bash
. /home/frankbria/.claude/jobs/a14abad9/tmp/testenv.sh && $PY -m pytest tests/test_generation_router.py tests/test_distribution_wiring.py tests/test_regenerate_endpoint.py tests/test_pdf_pipeline_integration.py tests/test_rss_feed.py tests/test_sse_auth.py tests/unit/test_native_generation.py --no-cov -p no:cacheprovider -q 2>&1 | tail -1 | sed 's/ in .*//'
```

```output
============================= 102 passed
```
