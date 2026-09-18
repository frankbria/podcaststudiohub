# Issue #503: the rate-limiter fail-open is now observable

*2026-09-18T04:41:05Z*

The API runs locally on :8018 with LOG_FORMAT=json and REDIS_URL pointed at a throwaway Redis container on :6390, so Redis can be taken down and brought back without touching anything else. The auth rate limiter keeps failing open by design (not in scope to change); what the issue asks for is that the disarm is an error-level, alertable signal, that it is observable somewhere other than a log line, and that the `remaining: -1` sentinel is consumed rather than dead. Each is exercised below.

**Baseline** — Redis healthy: the readiness probe now carries a `rate_limiter` block, and it starts at zero.

```bash
curl -s $API/ready | jq "{status, checks, rate_limiter}"
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

**Criterion 1 — error-level, alertable signal.** The API log now has two ERROR records for that request: the limiter's own (was WARNING before this fix) with the Redis cause, and the distinct structured `rate_limit_fail_open` event from the dependency naming the endpoint and client IP. Both are error-level, so Sentry's logging integration captures them and a log filter can alert on the event name.

```bash
grep "^{" $LOG | jq -c "select(.level==\"ERROR\") | {level, logger, event, endpoint, message}"
```

```output
{"level":"ERROR","logger":"src.services.rate_limiter","event":null,"endpoint":null,"message":"Rate limiter Redis error (failing open): Error 111 connecting to 127.0.0.1:6390. Connection refused."}
{"level":"ERROR","logger":"src.dependencies","event":"rate_limit_fail_open","endpoint":"login","message":"Rate limiting disabled (Redis unreachable): endpoint=login ip=127.0.0.1 allowed unmetered"}
```

**Criterion 3 — the sentinel is consumed.** The event above exists only because `dependencies.py` now reads the limiter's `remaining == FAIL_OPEN_REMAINING` and acts on it; before this fix that value was returned and never read.

**Criterion 2 — observable beyond a log line.** While Redis is down the probe is 503 as before (the live Redis check owns that decision), and the `rate_limiter` block now reports the fail-open count and timestamp.

```bash
curl -s -w "\nHTTP %{http_code}\n" $API/ready | { read body; read blank; read code; echo "$body" | jq "{status, checks, rate_limiter}"; echo "$code"; }
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
    "last_fail_open_at": "2026-09-18T04:41:06.130796+00:00"
  }
}

```

**Recovery** — bring Redis back. The probe returns to 200/ready, but the counter persists: a blip between two green probes leaves durable, pollable evidence that the brute-force control was off, which is what a WARNING line alone never gave anyone.

```bash
docker start psh-503-redis >/dev/null && sleep 2 && curl -s -w "\nHTTP %{http_code}\n" $API/ready | { read body; read blank; read code; echo "$body" | jq "{status, checks, rate_limiter}"; echo "$code"; }
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
    "last_fail_open_at": "2026-09-18T04:41:06.130796+00:00"
  }
}

```

And a metered login now that Redis is back: 401 again, and the counter does not move — only genuine fail-opens are counted.

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST $API/auth/login -H "Content-Type: application/json" -d "{\"email\":\"nobody-503@example.com\",\"password\":\"Wrong-Passw0rd!\"}"; curl -s $API/ready | jq -c .rate_limiter
```

```output
HTTP 401
{"fail_open_count":1,"last_fail_open_at":"2026-09-18T04:41:06.130796+00:00"}
```

## Evidence

| Criterion | Action | Outcome evidence | Status |
|---|---|---|---|
| Redis outage during login produces an error-level, alertable signal | Stop Redis, POST /auth/login | Two `level: ERROR` JSON records: limiter `Rate limiter Redis error (failing open)` and dependency event `rate_limit_fail_open` with `endpoint=login`; request still answered 401 (fail-open kept) | VERIFIED |
| Fail-open observable somewhere other than a log line | GET /ready during and after the outage | `rate_limiter.fail_open_count` went 0 → 1 with `last_fail_open_at` set, and persisted at 1 after Redis returned and the probe was back to `ready`; a metered login did not move it | VERIFIED |
| `remaining: -1` sentinel consumed, not dead | Same outage login | The `rate_limit_fail_open` event is emitted by `dependencies.py` only when `remaining == FAIL_OPEN_REMAINING`; the metered login emitted none | VERIFIED |
| Not in scope: fail-open decision unchanged | Login with Redis down | HTTP 401 (auth ran), not 429/500 | VERIFIED |
