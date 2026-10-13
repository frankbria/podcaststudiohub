# #496 — /api/monitoring reaches Next and is rate-limited at nginx

*2026-10-13T16:25:06Z by Showboat 0.6.1*
<!-- showboat-id: 0003d544-0a9e-402a-9528-a8da3cca18da -->

The shipped `deployment/nginx/podcastfy.conf` loaded into a real nginx (`nginx:stable`) by `/tmp/demo_496.sh`. nginx stands in for both upstreams: `:3010` answers `next` (the Next.js app) and `:8005` answers `fastapi`. Then one POST to see who answers `/api/monitoring`, and 25 POSTs back to back.

`main`:

```bash
cd /home/frankbria/projects/podcaststudiohub && git worktree add -q --detach /tmp/demo496-main main && timeout 120 bash /tmp/demo_496.sh /tmp/demo496-main 2>/dev/null | grep -E "answered by|^ +[0-9]+ [0-9]{3}$"; git worktree remove --force /tmp/demo496-main; git worktree prune
```

```output
POST /api/monitoring is answered by: fastapi
       25 200
```

This branch:

```bash
timeout 120 bash /tmp/demo_496.sh "$PWD" 2>/dev/null | grep -E "answered by|^ +[0-9]+ [0-9]{3}$"
```

```output
POST /api/monitoring is answered by: next
       10 200
       15 429
```

On `main`, the client-error relay falls into `location /api/`, is rewritten to `/monitoring` and lands on FastAPI, which has no such route: every report 404s, so no client error reached Sentry. Every request is also forwarded, with no limit. On this branch it reaches the Next route handler; the first request plus a burst of 10 pass, and the rest of the flood gets 429 at nginx and never reaches the app or Sentry. Applying this to the dev VPS is an operator step: its nginx is installed by hand, not deployed (see `deployment/README.md`).
