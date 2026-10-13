# #571 — the uncalled update_generation_status is gone

*2026-10-13T22:48:02Z by Showboat 0.6.1*
<!-- showboat-id: 6de31cac-61d0-4778-a81d-c840d2286962 -->

```bash
grep -rn "update_generation_status" src tests ../web/src || echo "no references in src, tests or web"
```

```output
no references in src, tests or web
```

```bash
. /tmp/claude-1002/-home-frankbria-projects-podcaststudiohub/0cff25cd-5ade-4521-b4a7-6a902107273a/scratchpad/testenv.sh && .venv/bin/python -m pytest tests/test_episodes.py -q --no-cov -p no:cacheprovider 2>&1 | tail -1
```

```output
======================== 94 passed, 1 skipped in 32.94s ========================
```
