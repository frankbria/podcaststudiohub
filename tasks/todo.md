# Issue #320 — [P5.4] Observability gaps (self-authored plan)

Plan source: self-authored (no plan comment on the issue).
Verified against `main` @ `c0218b0`, 2026-07-14.

## Verified current state (every claim in the issue re-checked against live code)

| Issue claim | Verdict | Evidence |
|---|---|---|
| No Sentry in API or worker | TRUE | no `sentry` in `apps/api/pyproject.toml:10-33`; absent from `main.py`/`worker.py` |
| `/health` unconditional, no `/ready` | TRUE | `main.py:70-73` returns a static dict; no `/ready` route exists |
| Deploy gate relies on `/health` | TRUE | `deploy-dev.yml:378` `wait_for "API" "$API_URL/health" "200"`; nginx pass-through at `podcastfy.conf:178-181` |
| No correlation ID; tenant_id not on logs | TRUE | zero `ContextVar` in `src/`; `tenant_id` lives only on `request.state` (`tenant.py:53-54`) |
| No log rotation | TRUE | zero `logrotate` hits repo-wide; `harden-host.sh:58` installs `pm2 startup` but never `pm2-logrotate` |
| Logs freeform, not JSON | TRUE | `main.py:15-19` `basicConfig(format="%(asctime)s - %(name)s - ...")` |

Three findings that **sharpen** the issue:
- **nginx logs are worse than stated.** They go to a *custom* path `/opt/podcaststudiohub/logs/frontend-{access,error}.log`
  (`podcastfy.conf:74-75`), which the distro's stock `/etc/logrotate.d/nginx` (globbing `/var/log/nginx/*.log`) does
  **not** match. Nothing rotates them today.
- **Redis PING needs no new dependency.** `redis>=5.0.0` (`pyproject.toml:23`) already ships `redis.asyncio`.
  `sentry-sdk` is the only genuinely new dep.
- **Celery has no signal hooks or Task base class** (confirmed: zero `celery.signals` usage), and the generation chain
  uses **immutable `.si()` signatures** (`podcast_generation.py:930-935`, issue #211) — so propagation must go through
  message **headers**, not kwargs.

## Steps (TDD: step 1 first, RED)

1. **Tests (RED)** — extend `apps/api/tests/test_health.py`; new `apps/api/tests/test_observability.py`;
   new `deployment/tests/test_log_rotation.py` (static-read pattern per `test_dr_durability.py`):
   - `/ready` → 200 + per-check body when DB+Redis are up
   - `/ready` → **503** when DB raises, and (independently) when Redis PING raises
   - `/health` stays 200 + static even when DB/Redis are down — the two probes must not collapse into one
   - `/ready` is in `TenantContextMiddleware.PUBLIC_PATHS` (else it gets metered + tenant-resolved)
   - `X-Request-ID` echoed on responses; minted when absent; **reused** when the client supplies one
   - JSON formatter emits parseable JSON carrying `request_id` + `tenant_id`; `exc_info` → `exception` field
   - Celery `before_task_publish` puts both ids on headers; `task_prerun` binds them into worker contextvars
   - deploy workflow gates on `/ready`; installs pm2-logrotate; installs the nginx logrotate drop-in

2. **JSON logging** — new `apps/api/src/logging_config.py`:
   - `CORRELATION_ID` / `TENANT_ID` `ContextVar`s (single home; imported by middleware + Celery signals)
   - `JsonFormatter(logging.Formatter)` — stdlib `json`, ~25 lines: ts/level/logger/msg/request_id/tenant_id/exception
   - `setup_logging()` — configures the root handler **and** replaces the formatter on `uvicorn.access`/`uvicorn.error`
     handlers, since uvicorn installs its own log config that root config alone won't reach
   - `LOG_FORMAT: str = "json"` in `config.py` (`"text"` escape hatch for local dev)
   - Called from `main.py` (replacing `basicConfig`) **and** from Celery's `setup_logging` signal (which suppresses
     Celery's own config) → one formatter, both processes = AC5

3. **Correlation ID + tenant binding** — new `apps/api/src/middleware/correlation.py`:
   - `CorrelationIdMiddleware`: read `X-Request-ID` or mint `uuid4`; set contextvar; echo header on the response
   - Registered **last** in `main.py` so it is outermost (Starlette `add_middleware` is LIFO) → wraps CORS + tenant
   - `TenantContextMiddleware` additionally sets the `TENANT_ID` contextvar beside its existing `request.state` write
     (purely additive; `request.state` stays the RLS source of truth)
   - `worker.py`: `before_task_publish` → inject both ids into headers; `task_prerun` → bind into worker contextvars;
     `task_postrun` → reset. Ids flow API → chain with **no task signature changes** (keeps the `.si()` invariant, #211)

4. **Sentry** — `uv add sentry-sdk`; `init_sentry()` in `logging_config.py`, called from `main.py` + `worker.py`:
   - gated on `SENTRY_DSN: Optional[str] = None` → **None is a no-op**, so dev/CI/tests stay offline
     (matches the repo's `Optional[str] = None` convention, e.g. `config.py:79-80`)
   - `environment=settings.ENVIRONMENT`, `traces_sample_rate=0.0` (errors only, no APM bill)
   - **ponytail:** rely on sentry-sdk's auto-enabling FastAPI/Celery/logging integrations; no manual wiring
   - `send_default_pii=False` + a `before_send` scrub — multi-tenant app; don't ship user data to a third party
   - add `SENTRY_DSN` to `.env.example`

5. **`/ready` probe** — `main.py`: `SELECT 1` via `from src.database import engine` (`engine.connect()`,
   `pool_pre_ping=True`); Redis via `redis.asyncio.from_url(settings.REDIS_URL).ping()`. Both under an
   `asyncio.wait_for` (~2s) so a hung dependency can't hang the probe. 503 + per-check detail on failure.
   Add `/ready` to `PUBLIC_PATHS`.

6. **Point the gates at `/ready`** — `deploy-dev.yml:378` → `$API_URL/ready`; nginx `location /ready` mirroring
   `/health` (`podcastfy.conf:178-181`, `access_log off`). `/health` stays the liveness probe.

7. **Log rotation** — workflow: `pm2 install pm2-logrotate` + `pm2 set` (10M, retain 7, compress, daily) — idempotent,
   per the CI/CD-idempotent-only rule. New `deployment/logrotate/podcaststudiohub-nginx` for
   `/opt/podcaststudiohub/logs/*.log` (daily, rotate 14, compress, delaycompress, notifempty, missingok,
   `postrotate` nginx reopen) + rsync/install step.

8. **Gates** — `uv run pytest tests/` (from `apps/api`), `python -m pytest deployment/tests/`, ruff, coverage ≥85,
   deslop, opencode/GLM review pre-PR, demo per AC, PR, post-PR review, CI, docs sync, merge.

## Acceptance criteria checklist
- [ ] AC1 Sentry in API + worker (step 4)
- [ ] AC2 `/ready` doing SELECT 1 + Redis PING, deploy/uptime gate pointed at it (steps 5, 6)
- [ ] AC3 Correlation ID propagated into Celery, bound to logs with tenant_id (steps 2, 3)
- [ ] AC4 pm2-logrotate + logrotate for nginx (step 7)
- [ ] AC5 JSON formatter shared by uvicorn and Celery (step 2)

## Autonomous decisions (no architectural fork)
- **`/health` stays static (liveness); `/ready` does the checks (readiness).** The standard split. Collapsing them would
  make a brownout restart-loop the API instead of merely draining it from the gate. The issue asks for `/ready` and is
  silent on changing `/health`, so `/health` keeps its contract and its existing tests (and its 8 other callers:
  playwright, rm-review, e2e global-setup, webServer readiness).
- **Hand-rolled JSON formatter + correlation middleware** over `python-json-logger` / `asgi-correlation-id`: ~25 and
  ~40 lines of stdlib versus two new supply-chain deps in a repo with live CVE gates (#306). `sentry-sdk` is the only
  new dep, and it has no stdlib substitute.
- **Celery headers over task kwargs** for propagation: kwargs would touch every `.si()`/`.s()` call site and break the
  immutable-signature invariant (#211).
- **Sentry defaults to off** (`SENTRY_DSN=None`) — tests/CI/local stay offline with no opt-out ceremony.
- **`traces_sample_rate=0.0`** — the issue asks for error tracking, not APM. YAGNI.

## Risks / notes
- `filterwarnings = error` is live (#348) — the sentry-sdk import must not emit warnings under pytest.
- `meter_api_call` opens a DB session even on public paths (`dependencies.py:38-40`), so `/ready` touches the DB via the
  app-level dependency regardless; the explicit `SELECT 1` is still what makes the check meaningful and 503-able.
- Coverage gates are real (85% backend, #345) — new modules need real tests, not smoke.
- Tasks are tested by direct `.run()` with a faked request (`test_celery_workflow.py:38-46`), not eager mode — signal
  tests must drive the signals directly rather than relying on `task_always_eager`.
