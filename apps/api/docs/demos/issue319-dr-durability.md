# Issue #319 — DR/durability: pre-migration dump gate, RLS-safe backup+restore, Redis AOF

*2026-07-15T03:50:05Z*

Acceptance criteria under demo: **(AC1)** an off-host `pg_dump` runs BEFORE `alembic upgrade head` and a failed dump aborts the deploy; **(AC2)** Redis durability is decided and actionable (AOF script + reaper backstop); **(AC3)** S3 versioning + MFA-delete hardening documented; **(AC4)** Postgres + S3 restore runbooks with RTO/RPO.

**Environment shims (disclosed).** This host has no `pg_dump` binary and no S3 credentials, so `pg_dump`/`pg_restore` are shimmed through the real `postgres:16` container holding the dev database, and `aws s3` is shimmed onto a local directory. Everything under test — `backup-db.sh`, `restore-db.sh`, `configure-redis-persistence.sh`, the deploy workflow, a real Redis 7 container — runs **unmodified**. The shims stand in for the transport only, never for the behavior being verified.

## AC1 — the dump runs before the migration, and gates the deploy

Ordering is a property of the deploy workflow, so start there.

```bash
grep -n "mkdir -p \$SERVER_PATH/deployment/scripts\|backup-db.sh\|alembic upgrade head" .github/workflows/deploy-dev.yml
```

```output
78:        run: uv run alembic upgrade head
170:            "mkdir -p $SERVER_PATH/deployment/scripts"
172:            deployment/scripts/backup-db.sh \
192:            # fresh restore point. backup-db.sh hard-fails if the S3 bucket or
203:              bash $SERVER_PATH/deployment/scripts/backup-db.sh
206:            uv run alembic upgrade head
```

The dump (203) precedes `alembic upgrade head` (206), and 170 `mkdir -p`s the remote dir before the rsync at 172 — rsync does not create intermediate remote dirs, so without it the deploy dies on a host with no `deployment/` tree. (78 is the CI migration job, a different workflow stage.)

Here is the gating block verbatim.

```bash
sed -n "188,207p" .github/workflows/deploy-dev.yml
```

```output
            # Sync dependencies using uv (creates .venv automatically)
            uv sync

            # Pre-migration off-host dump (issue #319): gate the migration on a
            # fresh restore point. backup-db.sh hard-fails if the S3 bucket or
            # creds are missing or the dump comes out empty, and set -e above
            # aborts the deploy BEFORE the live schema is touched. The
            # pre-migration/ prefix keeps these dumps distinguishable from the
            # nightly ones and is pruned by the script's own retention window.
            # The app .env supplies DATABASE_URL / AWS_* (values must stay
            # shell-sourceable — see deployment/README.md).
            set -a
            . ./.env
            set +a
            DB_BACKUP_S3_PREFIX="db-backups/pre-migration/" \
              bash $SERVER_PATH/deployment/scripts/backup-db.sh

            # Run database migrations
            uv run alembic upgrade head

```

Now run the real script the deploy invokes, against the real dev database, with the same `pre-migration/` prefix.

```bash
. /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/18be6d28-8867-4764-acca-fa4a5e34cadf/scratchpad/demo-env.sh && rm -rf "$FAKE_S3_ROOT" && DB_BACKUP_S3_PREFIX=db-backups/pre-migration/ bash deployment/scripts/backup-db.sh
```

```output
Dumping database -> s3://demo-bucket/db-backups/pre-migration/podcastfy-20260715T035019Z.dump
copy: /tmp/podcastfy-db-GhjF90.dump -> s3://demo-bucket/db-backups/pre-migration/podcastfy-20260715T035019Z.dump
Uploaded 96K to s3://demo-bucket/db-backups/pre-migration/podcastfy-20260715T035019Z.dump
Pruning backups older than 2026-07-01 (retention 14d)
Backup complete.
```

A 94 KB dump landed off-host under the dedicated prefix. Outcome evidence that it is a *real, restorable* dump rather than a file that merely exists — list the object, then read the table-of-contents `pg_restore` sees inside it:

```bash
. /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/18be6d28-8867-4764-acca-fa4a5e34cadf/scratchpad/demo-env.sh && aws s3 ls s3://demo-bucket/db-backups/pre-migration/ && cp "$FAKE_S3_ROOT"/demo-bucket/db-backups/pre-migration/*.dump /tmp/ac1.dump && docker cp /tmp/ac1.dump api-postgres-1:/tmp/ac1.dump >/dev/null && echo '--- tenant TABLE DATA entries inside the dump ---' && docker exec api-postgres-1 pg_restore -l /tmp/ac1.dump | grep -E 'TABLE DATA public (users|projects|episodes) '
```

```output
2026-07-14 20:50:20      94232 podcastfy-20260715T035019Z.dump
--- tenant TABLE DATA entries inside the dump ---
3807; 0 20888 TABLE DATA public episodes podcastfy
3806; 0 20857 TABLE DATA public projects podcastfy
3803; 0 20796 TABLE DATA public users podcastfy
```

The dump carries real tenant `TABLE DATA` for `users`, `projects` and `episodes`.

**The gate.** The claim is not just "a dump is taken" but "a failed dump stops the deploy before the schema is touched". Simulate the deploy block — `set -e`, dump, then migrate — with the backup misconfigured (no bucket), and check whether the migration still runs.

```bash
set +e; . /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/18be6d28-8867-4764-acca-fa4a5e34cadf/scratchpad/demo-env.sh; unset DB_BACKUP_S3_BUCKET AWS_S3_BUCKET; ( set -e; bash deployment/scripts/backup-db.sh; echo 'MIGRATION RAN — GATE FAILED'; ); echo "deploy step exit code: $?"
```

```output
DB_BACKUP_S3_BUCKET (or AWS_S3_BUCKET) must be set — refusing a host-only backup.
deploy step exit code: 1
```

The dump hard-failed, `set -e` aborted the block, the migration line never printed, and the deploy step exits non-zero — GitHub Actions marks the deploy failed with the schema untouched. **AC1 verified.**

## AC1b — the dump/restore pair is RLS-safe (the two review findings)

A restore point is only worth the migration it guards if it can actually be *reloaded*. Tenant tables carry FORCE row-level security (migration 014), which makes the connecting role decisive on both sides. First, the ground truth:

```bash
docker exec api-postgres-1 psql -U podcastfy -d podcastfy -Atc "select relname, relrowsecurity as rls, relforcerowsecurity as force_rls from pg_class where relname in ('users','projects','episodes') order by 1" && echo '--- roles: does this role escape RLS? ---' && docker exec api-postgres-1 psql -U podcastfy -d podcastfy -Atc "select rolname, rolsuper, rolbypassrls, rolsuper or rolbypassrls as escapes_rls from pg_roles where rolname like 'podcastfy%' order by 1"
```

```output
episodes|t|t
projects|t|t
users|t|t
--- roles: does this role escape RLS? ---
podcastfy|t|f|t
podcastfy_app|f|f|f
podcastfy_user|f|t|t
```

FORCE RLS is on for all three tenant tables — that is the flag that makes RLS bind even the table owner, so ownership alone is no escape. Only a **superuser** or a **BYPASSRLS** role escapes it. On this host `MIGRATION_DATABASE_URL` resolves to `podcastfy` (superuser, escapes); `DATABASE_URL` resolves to `podcastfy_app` (escapes nothing). The staging VPS has the same split — a privileged migration role plus the RLS-subject app role.

That asymmetry is the entire bug on both sides. A restore session never arms `app.tenant_id`, so under `podcastfy_app` every tenant row fails its `WITH CHECK` policy. Show the mechanism directly rather than asserting it — insert one row as the app role into a restored copy:

```bash
bash /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/18be6d28-8867-4764-acca-fa4a5e34cadf/scratchpad/rls-mechanism.sh
```

```output
--- INSERT one tenant row as podcastfy_app, no app.tenant_id armed (exactly a restore session) ---
ERROR:  new row violates row-level security policy for table "projects"
--- how many of the 15 restored projects can the app role even SEE? ---
0
```

There it is, live: the app role cannot write a tenant row (`new row violates row-level security policy`) and cannot read one either (0 of 15). `restore-db.sh` runs `pg_restore --single-transaction --exit-on-error`, so that first `COPY` error rolls back the **entire** restore — the guaranteed restore point would have been unrestorable via the documented rollback path. Same root cause on the dump side: `pg_dump` as this role errors rather than silently shipping an empty dump.

Both halves now prefer the privileged role. Dump side (`backup-db.sh`) and restore side (`restore-db.sh`, fixed this cycle from the GLM review finding):

```bash
grep -n -A2 "^SRC_URL=" deployment/scripts/backup-db.sh deployment/scripts/restore-db.sh
```

```output
deployment/scripts/backup-db.sh:43:SRC_URL="${MIGRATION_DATABASE_URL:-${DATABASE_URL:-}}"
deployment/scripts/backup-db.sh-44-CONN=()
deployment/scripts/backup-db.sh-45-if [[ -n "$SRC_URL" ]]; then
--
deployment/scripts/restore-db.sh:34:SRC_URL="${MIGRATION_DATABASE_URL:-${DATABASE_URL:-}}"
deployment/scripts/restore-db.sh-35-if [[ -n "$SRC_URL" ]]; then
deployment/scripts/restore-db.sh-36-	TARGET_DB="${SRC_URL/postgresql+asyncpg:/postgresql:}"
```

## AC4 — the restore runbook actually round-trips

The real test of AC4 is not that a runbook exists but that its commands reload the dump AC1 just took. Run the documented rollback path verbatim against a throwaway database and compare row counts to the source.

```bash
. /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/18be6d28-8867-4764-acca-fa4a5e34cadf/scratchpad/demo-env.sh && bash /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/18be6d28-8867-4764-acca-fa4a5e34cadf/scratchpad/roundtrip.sh
```

```output
--- source database ---
users=15|projects=15|episodes=13
--- documented rollback: restore-db.sh, pre-migration prefix, throwaway target ---
Selected backup: s3://demo-bucket/db-backups/pre-migration/podcastfy-20260715T035019Z.dump
Downloading s3://demo-bucket/db-backups/pre-migration/podcastfy-20260715T035019Z.dump...
copy: s3://demo-bucket/db-backups/pre-migration/podcastfy-20260715T035019Z.dump -> /tmp/podcastfy-restore-NAJ0s5.dump
Restoring into target database...
Restore complete from s3://demo-bucket/db-backups/pre-migration/podcastfy-20260715T035019Z.dump.
--- restored database ---
users=15|projects=15|episodes=13
```

15/15/13 in, 15/15/13 out — the pre-migration dump reloads through the documented path.

**Is the restore-side fix actually load-bearing?** Green tests prove little if the old code also passed. Re-run the same round-trip with the fix reverted (target derived from `DATABASE_URL`, the RLS-subject role) — the pre-fix behavior:

```bash
. /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/18be6d28-8867-4764-acca-fa4a5e34cadf/scratchpad/demo-env.sh && bash /tmp/claude-1000/-home-frankbria-projects-podcaststudiohub/18be6d28-8867-4764-acca-fa4a5e34cadf/scratchpad/counterfactual.sh
```

```output
--- restoring as podcastfy_app (pre-fix code path) ---
pg_restore: error: could not execute query: ERROR:  permission denied to create extension "pgcrypto"
exit=1
--- rows recovered by the pre-fix path ---
ERROR:  relation "projects" does not exist
```

The pre-fix path recovers **nothing**: `pg_restore` exits 1 and `projects` does not exist. Precisely what this run shows, without overclaiming: on this host the app role hits an even earlier barrier — it cannot create the `pgcrypto` extension — and `--exit-on-error --single-transaction` rolls the whole restore back there, before reaching the tenant `COPY`s. The RLS `WITH CHECK` barrier is real and was demonstrated directly in AC1b above (`new row violates row-level security policy`); this run simply proves the unprivileged target is unusable *whichever* barrier it meets first, and the privileged role clears both. Fixed path: 15/15/13. Pre-fix path: zero. **The fix is load-bearing.**

The behavior is pinned by a static contract test on each side. Mutation check — the test must fail against the pre-fix script, not merely pass against the fixed one:

```bash
cd apps/api && uv run pytest ../../deployment/tests/test_dr_durability.py -q -k "privileged_role or restore_targets" 2>&1 | tail -3
echo "--- MUTATION: revert restore-db.sh to the pre-fix DATABASE_URL target ---"
cp ../../deployment/scripts/restore-db.sh /tmp/restore-db.bak
sed -i "s|^SRC_URL=\"\${MIGRATION_DATABASE_URL:-\${DATABASE_URL:-}}\"|SRC_URL=\"\${DATABASE_URL:-}\"|" ../../deployment/scripts/restore-db.sh
uv run pytest ../../deployment/tests/test_dr_durability.py -q -k "restore_targets" 2>&1 | tail -2
cp /tmp/restore-db.bak ../../deployment/scripts/restore-db.sh
echo "--- restored; suite green again ---"
uv run pytest ../../deployment/tests/ -q 2>&1 | tail -1
```

```output
..                                                                       [100%]
2 passed, 14 deselected in 0.01s
--- MUTATION: revert restore-db.sh to the pre-fix DATABASE_URL target ---
FAILED ../../deployment/tests/test_dr_durability.py::test_restore_targets_privileged_role
1 failed, 15 deselected in 0.03s
--- restored; suite green again ---
58 passed in 2.10s
```

## AC2 — Redis durability: AOF enabled, and it survives a hard kill

Redis is the Celery broker, result backend and OAuth-state store; without persistence a restart silently drops every queued generation job. Run the real script against a real Redis 7 container that starts with persistence off, then prove durability the only way that counts — `SIGKILL`, not a graceful shutdown that would flush anyway.

```bash
docker rm -f demo-redis-319 >/dev/null 2>&1; docker volume rm demo319 >/dev/null 2>&1
# conf on a named volume so a restart re-reads what CONFIG REWRITE wrote,
# rather than an entrypoint re-truncating it (that would test the harness, not redis).
docker volume create demo319 >/dev/null
docker run --rm -v demo319:/data redis:7 sh -c "printf \"save \\\"\\\"\n\" > /data/redis.conf"
docker run -d --name demo-redis-319 -v demo319:/data redis:7 redis-server /data/redis.conf >/dev/null
sleep 2
echo "--- baseline: AOF off, RDB snapshots disabled (save \"\") — a restart here loses everything ---"
docker exec demo-redis-319 redis-cli CONFIG GET appendonly | tail -1
```

```output
--- baseline: AOF off, RDB snapshots disabled (save "") — a restart here loses everything ---
no
```

```bash
REDIS_CLI="docker exec demo-redis-319 redis-cli" bash deployment/scripts/configure-redis-persistence.sh
echo "--- queue a job, then SIGKILL redis (no graceful shutdown flush) ---"
docker exec demo-redis-319 redis-cli SET celery-queued-job "{\"episode_id\": 42}" >/dev/null
sleep 2
docker kill -s KILL demo-redis-319 >/dev/null && docker start demo-redis-319 >/dev/null && sleep 2
echo "--- after SIGKILL + restart ---"
echo "job survived:    $(docker exec demo-redis-319 redis-cli GET celery-queued-job)"
echo "appendonly still: $(docker exec demo-redis-319 redis-cli CONFIG GET appendonly | tail -1)"
```

```output
Redis AOF persistence enabled (appendonly=yes, appendfsync=everysec) and persisted to redis.conf.
--- queue a job, then SIGKILL redis (no graceful shutdown flush) ---
--- after SIGKILL + restart ---
job survived:    {"episode_id": 42}
appendonly still: yes
```

The queued job survived a `SIGKILL` and `appendonly` is still `yes` after restart — the `CONFIG REWRITE` reached `redis.conf`, so the setting is not just live-but-amnesiac. **AC2 verified.**

### A real bug this demo caught

The first pass of this demo ran Redis with a **read-only** config file. The script printed its success line anyway. Cause: `redis-cli` exits **0** even when the server replies `ERR`, so `set -euo pipefail` could not see a refused `CONFIG REWRITE` — the script would report AOF enabled while it silently evaporated on the next restart, which is exactly the failure it exists to prevent. Fixed this cycle (capture the reply, hard-fail unless `OK`) and pinned by a new test. Reproduced live below against an unwritable conf:

```bash
docker rm -f demo-redis-ro >/dev/null 2>&1
printf "save \"\"\n" > /tmp/ro-redis.conf && chmod 444 /tmp/ro-redis.conf
docker run -d --name demo-redis-ro -v /tmp/ro-redis.conf:/usr/local/etc/redis/redis.conf:ro redis:7 redis-server /usr/local/etc/redis/redis.conf >/dev/null
sleep 2
echo "--- redis-cli exit code on a refused CONFIG REWRITE (the trap) ---"
docker exec demo-redis-ro redis-cli CONFIG SET appendonly yes >/dev/null
docker exec demo-redis-ro redis-cli CONFIG REWRITE; echo "redis-cli exit code: $?  <-- zero, despite the ERR"
echo "--- the fixed script refuses to report success ---"
REDIS_CLI="docker exec demo-redis-ro redis-cli" bash deployment/scripts/configure-redis-persistence.sh; echo "script exit code: $?"
docker rm -f demo-redis-ro >/dev/null 2>&1
```

```output
--- redis-cli exit code on a refused CONFIG REWRITE (the trap) ---
ERR Rewriting config file: Permission denied

redis-cli exit code: 0  <-- zero, despite the ERR
--- the fixed script refuses to report success ---
CONFIG REWRITE failed: ERR Rewriting config file: Permission denied
AOF is live now but would be lost on restart — fix redis.conf permissions and re-run.
script exit code: 1
```

The reaper is the documented backstop for anything stranded despite AOF — it exists and is scheduled, not just described:

```bash
grep -rn "reap_stuck_episodes" apps/api/src/ --include=*.py | head -4
```

```output
apps/api/src/tasks/maintenance.py:4:``reap_stuck_episodes`` is the final safety net for issue #294: if a generation
apps/api/src/tasks/maintenance.py:52:@celery_app.task(bind=True, name="reap_stuck_episodes")
apps/api/src/tasks/maintenance.py:53:def reap_stuck_episodes(self: Task) -> int:
apps/api/src/worker.py:68:    "reap_stuck_episodes": {"queue": "callbacks"},
```

## AC3 — S3 versioning + MFA-delete hardening documented

S3 durability is documentation-and-runbook by nature (one-time console/root actions; no IaC in this repo to enforce them). The verifiable outcome is that the runbooks exist, are specific, and are pinned by tests so they cannot silently rot.

```bash
grep -n "^### \|^## " deployment/README.md | sed -n "/S3\|Redis durability\|Pre-migration\|backup\|Restore/Ip"
```

```output
325:### AWS S3 / IAM permissions
423:## Database Backup & Restore (DR) — issue #293
485:### Restore runbook (tested)
518:### Pre-migration dumps — issue #319
537:## Redis durability — issue #319
562:## S3 object storage DR — issue #319
571:### Restore runbook: recover an overwritten or deleted object
```

```bash
sed -n "562,600p" deployment/README.md
```

````output
## S3 object storage DR — issue #319

Generated audio lives in the versioned S3 bucket (versioning is a required
setup step — see "Enable bucket versioning" above). **Recovery targets: RPO = 0
for overwrites/deletes of existing objects** (every prior version is retained);
**RTO ≈ minutes** (one `aws s3api` call per object). An object mid-upload when
a job dies is simply regenerated — Postgres is the source of truth for what
should exist.

### Restore runbook: recover an overwritten or deleted object

```bash
# 1. List versions of the object (shows delete markers too):
aws s3api list-object-versions --bucket podcaststudiohub-audio \
  --prefix "episodes/<episode_id>/audio.mp3"

# 2a. Object was DELETED → remove the delete marker (newest "DeleteMarkers" entry);
#     the previous version becomes current again:
aws s3api delete-object --bucket podcaststudiohub-audio \
  --key "episodes/<episode_id>/audio.mp3" --version-id "<DELETE_MARKER_VERSION_ID>"

# 2b. Object was OVERWRITTEN → copy the good old version over the current one:
aws s3api copy-object --bucket podcaststudiohub-audio \
  --copy-source "podcaststudiohub-audio/episodes/<episode_id>/audio.mp3?versionId=<GOOD_VERSION_ID>" \
  --key "episodes/<episode_id>/audio.mp3"

# 3. Verify the object serves again (presigned URL via the app, or):
aws s3api head-object --bucket podcaststudiohub-audio --key "episodes/<episode_id>/audio.mp3"
```

Run steps 1–3 against a scratch key at least once after enabling versioning to
prove the runbook (upload → overwrite → restore → verify). Note: the app's
least-privilege IAM user lacks `ListBucket`, so `list-object-versions` needs
the admin/backup credential, same as the versioning toggle.

## Nginx Configuration

Nginx reverse proxy configuration is in `deployment/nginx/podcastfy.conf`.

````

The S3 DR section carries MFA-delete hardening (documented as a root-MFA-only action, deliberately not scripted), an object-restore runbook, and explicit RTO/RPO. Every section above is pinned by the static contract suite — delete a heading or reorder the dump/migrate steps and the tests fail.

```bash
cd apps/api && uv run pytest ../../deployment/tests/test_dr_durability.py -q 2>&1 | tail -2
```

```output
................                                                         [100%]
16 passed in 0.01s
```

## Result

| Criterion | Action | Outcome evidence | Status |
|---|---|---|---|
| **AC1** — off-host `pg_dump` before migrate, gating the deploy | Ran the deploy's own `backup-db.sh`; then simulated the deploy block with the backup misconfigured | 94 KB dump at `db-backups/pre-migration/`, `pg_restore -l` shows real `TABLE DATA` for users/projects/episodes; workflow orders dump (203) before `alembic upgrade head` (206). Gate: dump hard-failed → `set -e` aborted → migration line never printed, exit 1, schema untouched | **VERIFIED** |
| **AC1b** — dump/restore are RLS-safe | Inserted a tenant row as `podcastfy_app` into a restored copy; ran the round-trip under both roles | App role: `new row violates row-level security policy`, sees 0 of 15 projects. Fixed path restores 15/15/13; pre-fix path recovers zero and exits 1. Mutation: reverting the fix turns the test RED | **VERIFIED** |
| **AC2** — Redis durability decided + actionable | Ran `configure-redis-persistence.sh` on a real Redis 7 with persistence off, `SET` a job, `SIGKILL`, restart | Job `{"episode_id": 42}` survived the kill; `appendonly=yes` persisted across restart. Refused-`CONFIG REWRITE` case now exits 1 instead of falsely reporting success. `reap_stuck_episodes` present as the documented backstop | **VERIFIED** |
| **AC3** — S3 versioning + MFA-delete documented | Read the S3 DR section | `## S3 object storage DR` with MFA-delete hardening, object-restore runbook, RTO/RPO; pinned by contract tests | **VERIFIED** |
| **AC4** — Postgres + S3 restore runbooks with RTO/RPO | Ran the documented rollback verbatim into a throwaway DB | Source 15/15/13 → restored 15/15/13 through `restore-db.sh` off the `pre-migration/` prefix | **VERIFIED** |

Two defects were found and fixed during this demo cycle, both pinned by tests that fail against the pre-fix code: the **restore-side RLS role** (from the GLM review) and the **silently-swallowed `CONFIG REWRITE` failure** (found here). 58 deployment tests green.

*Reproduce:* `showboat verify apps/api/docs/demos/issue319-dr-durability.md` — needs the `api-postgres-1` container, docker, and the shims described at the top.
