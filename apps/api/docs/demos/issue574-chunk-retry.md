# #574 — a transient provider failure no longer discards paid long-form chunks

*2026-10-12T05:42:50Z by Showboat 0.6.1*
<!-- showboat-id: 48210d46-a03a-43ce-b2c9-fa6aebe5308f -->

Every run below is a **real** long-form generation against Gemini (`gemini-3.5-flash`, `ENGINE_MAX_CHUNKS=3`). Exactly one call is faked: the second (the middle chunk) raises a real `google.genai.errors.ServerError(503)` built from a real HTTP response, the way an overloaded Gemini replies. Every other call goes to Google. `time.sleep` is wrapped to record, not skip, so the backoff is real. The driver, `/tmp/demo_574.py`, runs unchanged from `main`'s `apps/api` and from this branch's; keys load from the root `.env` via `/tmp/demo574env.sh` and are never printed.

```bash
sed -n '/^class CountingClient/,/^        return response/p' /tmp/demo_574.py
```

```output
class CountingClient:
    """Wraps a real genai.Client; numbers each generate_content call."""

    def __init__(self, **kwargs):
        self._real = real_genai.Client(**kwargs)
        self.models = self

    def generate_content(self, **kwargs):
        n = len(calls) + 1
        if mode == "transient" and n == FAIL_ON_CALL:
            calls.append("503 (injected)")
            print(f"  call {n}: -> injected 503 UNAVAILABLE", flush=True)
            raise _503()
        start = time.monotonic()
        try:
            response = self._real.models.generate_content(**kwargs)
        except genai_errors.APIError as exc:
            calls.append(f"real {exc.code}")
            print(f"  call {n}: -> real Gemini {exc.code} {exc.status}", flush=True)
            raise
        calls.append("ok")
        print(f"  call {n}: -> real Gemini 200 ({time.monotonic() - start:.0f}s)", flush=True)
        return response
```

```bash
sed -n '/^_RealClient/p;/^class CountingClient/,/^        return response/p' /tmp/demo_574.py
```

```output
_RealClient = real_genai.Client  # captured before the patch below replaces it
class CountingClient:
    """Wraps a real genai.Client; numbers each generate_content call."""

    def __init__(self, **kwargs):
        self._real = _RealClient(**kwargs)
        self.models = self

    def generate_content(self, **kwargs):
        n = len(calls) + 1
        if mode == "transient" and n == FAIL_ON_CALL:
            calls.append("503 (injected)")
            print(f"  call {n}: -> injected 503 UNAVAILABLE", flush=True)
            raise _503()
        start = time.monotonic()
        try:
            response = self._real.models.generate_content(**kwargs)
        except genai_errors.APIError as exc:
            calls.append(f"real {exc.code}")
            print(f"  call {n}: -> real Gemini {exc.code} {exc.status}", flush=True)
            raise
        calls.append("ok")
        print(f"  call {n}: -> real Gemini 200 ({time.monotonic() - start:.0f}s)", flush=True)
        return response
```

**Before (main):** the 503 on chunk 2 escapes `generate_script`. Chunk 1 was generated and paid for, and is thrown away; the Celery retry would regenerate it from scratch.

```bash
cd /home/frankbria/projects/podcaststudiohub/apps/api && git log --oneline -1 && . /tmp/demo574env.sh && PYTHONPATH=. .venv/bin/python /tmp/demo_574.py transient 2>&1 | grep -v '^{'
```

```output
c99a1f7 docs: record #578 lessons (bot predictions, Sentry locals, showboat signature)
  call 1: -> real Gemini 200 (24s)
  call 2: -> injected 503 UNAVAILABLE
RESULT: ProviderError escaped: Gemini call failed: 503 UNAVAILABLE. {'error': {'message': 'The model is overloaded.', 'st
        retryable=<attribute absent on this code>
provider calls: 2 -> ['ok', '503 (injected)']
backoff sleeps: []
```

**After (this branch):** the 503 is retryable. The engine waits 2s (real sleep), re-sends chunk 2's identical request, and carries on. Chunk 1 is never requested again: 3 chunks cost 4 calls, one of them the failed one, which generated nothing.

```bash
cd /home/frankbria/projects/worktrees/issue-574-long-form-chunk-retry/apps/api && git log --oneline -1 && . /tmp/demo574env.sh && PYTHONPATH=. .venv/bin/python /tmp/demo_574.py transient 2>&1 | grep -v '^{' | grep -v '^WARNING' ; . /tmp/demo574env.sh; true
```

```output
85ed16e fix(engine): retry only fast provider failures; wrap every requests error (#574 review)
  call 1: -> real Gemini 200 (24s)
  call 2: -> injected 503 UNAVAILABLE
  call 3: -> real Gemini 200 (23s)
  call 4: -> real Gemini 200 (13s)
RESULT: script with 39 turns stitched from all chunks
provider calls: 4 -> ['ok', '503 (injected)', 'ok', 'ok']
backoff sleeps: [2]
```

**A permanent failure is not retried.** Same driver, no injection, but an invalid API key: Google's real rejection comes back as a non-retryable `ProviderError` after exactly one call and no sleep, so a revoked key or wrong model id fails as fast as it did before.

```bash
cd /home/frankbria/projects/worktrees/issue-574-long-form-chunk-retry/apps/api && . /tmp/demo574env.sh && PYTHONPATH=. .venv/bin/python /tmp/demo_574.py badkey 2>&1 | grep -v '^{' | grep -v '^WARNING'
```

```output
  call 1: -> real Gemini 400 INVALID_ARGUMENT
RESULT: ProviderError escaped: Gemini call failed: 400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key not 
        retryable=False
provider calls: 1 -> ['real 400']
backoff sleeps: []
```

**The regression test** fails the middle chunk and asserts chunk 1 is not regenerated, and that the retry re-sent chunk 2's request byte-for-byte, with chunk 1's rolling summary still in it.

```bash
cd /home/frankbria/projects/worktrees/issue-574-long-form-chunk-retry/apps/api && . /tmp/demo574env.sh && .venv/bin/python -m pytest tests/unit/test_engine_script.py -q --no-cov -p no:cacheprovider -k 'mid_episode or retryable or permanent or transport or openai_failures' 2>&1 | grep -E 'passed|failed'
```

```output
====================== 18 passed, 48 deselected in 1.87s =======================
```

**The policy in script.py** (it previously said, via `ProviderError`, that provider failures belong to the Celery task alone):

```bash
cd /home/frankbria/projects/worktrees/issue-574-long-form-chunk-retry/apps/api && sed -n '/^# Waits before each retry/,/^_BACKOFF_SECONDS/p' src/engine/script.py
```

```output
# Waits before each retry of a retryable provider failure (#574): what keeps a
# 503 on chunk 7 from discarding chunks 1-6, which were paid for. Only failures
# that return fast and generated nothing are retryable (see ProviderError), so
# this adds at most ~10s of sleep plus a few quick round trips per chunk; a
# timeout is never retried here, because each one already spent the full
# provider timeout of the Celery soft time limit. An outage that outlasts this
# belongs to the task's own backoff. In-process only, so a worker restart still
# starts the episode over.
_BACKOFF_SECONDS = (2, 8)
```

| Criterion | Evidence | Status |
|---|---|---|
| A transient failure mid-episode does not throw away generated chunks | Live run: main loses chunk 1 on a 503 at chunk 2; the branch retries once after 2s and finishes 3 chunks in 4 calls, chunk 1 never re-requested | VERIFIED |
| A test fails a middle chunk and asserts earlier ones are not regenerated | `test_a_retryable_failure_mid_episode_does_not_regenerate_earlier_chunks` passes, and fails under mutation of the retry | VERIFIED |
| The choice is reflected in `script.py`'s docstring | `_BACKOFF_SECONDS` comment and `_attempt` docstring above; `ProviderError` docstring rewritten | VERIFIED |
| (guard) permanent failures still fail fast | Live run with an invalid key: real 400, `retryable=False`, one call, no sleep | VERIFIED |
