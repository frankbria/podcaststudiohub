# #614 — the local suite's iat 401s were the WSL clock stepping back

*2026-10-13T05:59:57Z by Showboat 0.6.1*
<!-- showboat-id: 40a874f2-6f35-4144-8e96-cf6564557a61 -->

Every local full run this session lost 4–10 tests to `401 {"detail":"Invalid token: The token is not yet valid (iat)"}`, a different set each time, always green in isolation. PyJWT floors `iat` to the second and rejects `iat > now + leeway`, so a token minted and verified in one process fails only if the wall clock moves **backwards**. A 60 s sample of this machine's wall clock against the monotonic clock (`/tmp/clockwatch.py`):

```bash
python3 /tmp/clockwatch.py 60 | tail -6
```

```output
23:00:38 wall step -7.296s (wall went BACK)
23:00:51 wall step +6.796s (wall went fwd)
23:00:43 wall step -7.297s (wall went BACK)
23:00:56 wall step +6.797s (wall went fwd)
23:00:48 wall step -7.297s (wall went BACK)
done: 22 wall-clock steps in 60s
```

The wall clock steps back about 7.2 s and forward again every few seconds (240 steps in 11 minutes during a full run, whose 7 failures were all `iat`). The host is WSL2 with `systemd-timesyncd` active and a Hyper-V PTP clock (`ptp0`).

Fix: both `jwt.decode` sites take `leeway=CLOCK_SKEW_LEEWAY_SECONDS` (10 s). Two consecutive full runs after the fix (logs at the time of the PR):

```bash
for run in 1 2; do echo "run $run: iat 401s=$(grep -c "not yet valid" /tmp/claude-1002/-home-frankbria-projects-podcaststudiohub/0cff25cd-5ade-4521-b4a7-6a902107273a/scratchpad/614-run$run.log); $(grep -E "passed|failed" /tmp/claude-1002/-home-frankbria-projects-podcaststudiohub/0cff25cd-5ade-4521-b4a7-6a902107273a/scratchpad/614-run$run.log | tail -1)"; done
```

```output
run 1: iat 401s=0; ================= 2157 passed, 9 skipped in 414.08s (0:06:54) ==================
run 2: iat 401s=0; ================= 2157 passed, 9 skipped in 419.60s (0:06:59) ==================
```
