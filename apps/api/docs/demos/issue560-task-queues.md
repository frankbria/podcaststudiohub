# #560 — the worker consumes every queue tasks are routed to

*2026-10-13T22:36:01Z by Showboat 0.6.1*
<!-- showboat-id: 46adbbfa-3792-4f93-af04-64597e717bc7 -->

A real Celery worker started the way production starts it (`celery ... worker`, **no `-Q`**) against a local Redis (its own DB index), driven by `/tmp/demo_560.sh`. It asks the worker which queues it consumes, then puts a `reap_stuck_episodes` tick on `callbacks` and checks it after 6 s. On the dev box this exact gap had left 39,312 reaper and outbox-drain ticks and 11 content extractions unconsumed in Redis.

`main`:

```bash
cd /home/frankbria/projects/podcaststudiohub && git worktree add -q --detach /tmp/demo560-main main && ln -s /home/frankbria/projects/podcaststudiohub/apps/api/.venv /tmp/demo560-main/apps/api/.venv && timeout 90 bash /tmp/demo_560.sh /tmp/demo560-main/apps/api; git worktree remove --force /tmp/demo560-main; git worktree prune
```

```output
queues the worker consumes:
  'celery'
reap_stuck_episodes left waiting in 'callbacks' after 6s: 1
```

This branch:

```bash
timeout 90 bash /tmp/demo_560.sh "$PWD"
```

```output
queues the worker consumes:
  'audio_processing'
  'callbacks'
  'celery'
  'content_extraction'
  'distribution'
  'podcast_generation'
  'uploads'
reap_stuck_episodes left waiting in 'callbacks' after 6s: 0
```
