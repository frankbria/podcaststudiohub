# Issue #503: the rate-limiter fail-open is now observable

*2026-09-18T04:44:48Z*

The API runs locally on :8018 with LOG_FORMAT=json and REDIS_URL pointed at a throwaway Redis container on :6390, so Redis can be taken down and brought back without touching anything else. The auth rate limiter keeps failing open by design (not in scope to change); what the issue asks for is that the disarm is an error-level, alertable signal, that it is observable somewhere other than a log line, and that the `remaining: -1` sentinel is consumed rather than dead. Each is exercised below.

**Baseline** — Redis healthy: the readiness probe now carries a `rate_limiter` block, and it starts at zero.

```bash
curl -s -w "\nHTTP %{http_code}\n" $API/ready | { read body; read code; echo "$body" | jq "{status, checks, rate_limiter}"; echo "$code"; }
```

```output
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "redis": "ok"
  },
  "rate_limiter": {
    "fail_open_count": 0,
    "last_fail_open_at": null
  }
}
HTTP 200
```

A login attempt on the metered path (Redis up). Unknown credentials → 401, and nothing about a fail-open is logged.

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST $API/auth/login -H "Content-Type: application/json" -d "{\"email\":\"nobody-503@example.com\",\"password\":\"Wrong-Passw0rd!\"}"; echo "fail-open events in log: $(grep -c rate_limit_fail_open $LOG)"
```

```output
HTTP 401
fail-open events in log: 0
```

**Redis outage** — stop the container, then attempt a login. The request must still go through (fail-open preserved), so the answer is the same 401, not a 500 or a 429.

```bash
docker stop psh-503-redis >/dev/null && echo "redis stopped"; curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST $API/auth/login -H "Content-Type: application/json" -d "{\"email\":\"nobody-503@example.com\",\"password\":\"Wrong-Passw0rd!\"}"
```

```output
redis stopped
HTTP 401
```

**Criterion 1 — error-level, alertable signal.** The API log has exactly one ERROR record for that request (it was a WARNING before this fix, and a first cut of this fix logged two — one per layer — which would have been two Sentry issues per request). It carries the Redis cause, the limiter key (endpoint and client IP), and a structured `event` field a log filter or Sentry rule can key on; Sentry's logging integration captures error-level records.

```bash
grep "^{" $LOG | jq -c "select(.level==\"ERROR\") | {level, logger, event, key, message}"
```

```output
{"level":"ERROR","logger":"src.services.rate_limiter","event":"rate_limit_fail_open","key":"login:127.0.0.1","message":"Rate limiter Redis error (failing open, request allowed unmetered): key=login:127.0.0.1 error=Error 111 connecting to 127.0.0.1:6390. Connection refused."}
```

**Criterion 3 — the sentinel is gone.** `is_allowed` no longer returns `remaining: -1`; nothing ever read it, so the fail-open case returns an empty info dict and the signal lives in the log record and the counter instead of in dead protocol.

**Criterion 2 — observable beyond a log line.** While Redis is down the probe is 503 as before (the live Redis check owns that decision), and the `rate_limiter` block now reports the fail-open count and timestamp.

```bash
curl -s -w "\nHTTP %{http_code}\n" $API/ready | { read body; read code; echo "$body" | jq "{status, checks, rate_limiter}"; echo "$code"; }
```

```output
{
  "status": "not_ready",
  "checks": {
    "database": "ok",
    "redis": "error"
  },
  "rate_limiter": {
    "fail_open_count": 1,
    "last_fail_open_at": "2026-09-18T04:44:49.972993+00:00"
  }
}
HTTP 503
```

**Recovery** — bring Redis back. The probe returns to 200/ready, but the counter persists: a blip between two green probes leaves durable, pollable evidence that the brute-force control was off, which is what a WARNING line alone never gave anyone.

```bash
docker start psh-503-redis >/dev/null && sleep 2 && curl -s -w "\nHTTP %{http_code}\n" $API/ready | { read body; read code; echo "$body" | jq "{status, checks, rate_limiter}"; echo "$code"; }
```

```output
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "redis": "ok"
  },
  "rate_limiter": {
    "fail_open_count": 1,
    "last_fail_open_at": "2026-09-18T04:44:49.972993+00:00"
  }
}
HTTP 200
```

And a metered login now that Redis is back: 401 again, and the counter does not move — only genuine fail-opens are counted.

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST $API/auth/login -H "Content-Type: application/json" -d "{\"email\":\"nobody-503@example.com\",\"password\":\"Wrong-Passw0rd!\"}"; curl -s $API/ready | jq -c .rate_limiter
```

```output
HTTP 401
{"fail_open_count":1,"last_fail_open_at":"2026-09-18T04:44:49.972993+00:00"}
```

## Evidence

| Criterion | Action | Outcome evidence | Status |
|---|---|---|---|
| Redis outage during login produces an error-level, alertable signal | Stop Redis, POST /auth/login | Exactly one `level: ERROR` JSON record with `event: rate_limit_fail_open`, `key: login:127.0.0.1` and the Redis cause; request still answered 401 (fail-open kept) | VERIFIED |
| Fail-open observable somewhere other than a log line | GET /ready during and after the outage | `rate_limiter.fail_open_count` went 0 → 1 with `last_fail_open_at` set, and persisted at 1 after Redis returned and the probe was back to `ready` (HTTP 200); a metered login did not move it | VERIFIED |
| `remaining: -1` sentinel consumed or removed | Same outage login | Removed: the fail-open path returns an empty info dict; the metered login emitted no event and moved no counter | VERIFIED |
| Not in scope: fail-open decision unchanged | Login with Redis down | HTTP 401 (auth ran), not 429/500 | VERIFIED |
